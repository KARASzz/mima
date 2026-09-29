"""解密流程编排。

从 PNG 还原原始文件：
PNG → 像素 → ciphertext_with_header（含 8B 长度头）→ parallel_decrypt
       → 视觉反向置换 → 原始明文

按 critical ruling，**绝不**在 decrypt 内部手动切块——直接调用
parallel_decrypt(key, ciphertext)，它会读取 8B 长度头并自行还原切块边界。

线程模型（spec §17）：
- macOS 上 RunnerWindow 必须在主线程运行（AppKit 限制）。因此解密逻辑放到
  worker 线程，主线程调用 RunnerWindow.run_blocking()。
- 其他平台：GPU/runner 窗口在 worker 线程运行，解密在主线程（向后兼容）。
"""
import hashlib
import logging
import os
import sys
import threading
import time

from .cipher import parallel_decrypt
from .container import read_encrypted_png
from .kdf import derive_key
from .trajectory import (
    apply_inverse_permutation,
    invert_permutation,
    trajectory_fingerprint,
    trajectory_to_permutation,
)
from .visualizer import pixels_to_bytes

log = logging.getLogger(__name__)


def decrypt_file(
    input_png: str,
    output_path: str,
    use_gpu: bool = True,
    use_runner: bool = True,
) -> dict:
    """从 PNG 解密到文件。

    Args:
        input_png: 加密 PNG 路径
        output_path: 输出文件路径
        use_gpu: 是否启动 GPU 拉满窗口
        use_runner: 是否启动像素人物窗口

    Returns:
        统计信息字典

    Raises:
        ValueError: 轨迹被篡改、密钥错误、数据损坏
    """
    start_time = time.time()

    # 实例化窗口对象（不启动）
    gpu_win = None
    runner_win = None
    if use_runner:
        from .runner import RunnerWindow
        runner_win = RunnerWindow(direction="right")
    if use_gpu:
        from .gpu_window import GPUStressWindow
        gpu_win = GPUStressWindow()
        gpu_win.start()  # GPU 窗口：worker 线程；macOS 上内部静默跳过

    # macOS: RunnerWindow 必须在主线程运行；解密逻辑放到 worker 线程
    if sys.platform == "darwin" and runner_win is not None:
        result_holder: dict = {}

        def crypto_worker():
            try:
                result_holder["stats"] = _do_decrypt(
                    input_png, output_path, start_time
                )
            except Exception as e:  # noqa: BLE001
                result_holder["error"] = e
            finally:
                if runner_win is not None:
                    runner_win.stop()  # 触发 mainloop 退出，释放主线程

        worker = threading.Thread(target=crypto_worker, daemon=True)
        worker.start()
        runner_win.run_blocking()  # 主线程阻塞；worker.crypto_worker 调用 stop() 解除
        worker.join(timeout=10)

        if gpu_win is not None:
            gpu_win.stop()

        if "error" in result_holder:
            raise result_holder["error"]
        return result_holder["stats"]

    # 其他平台：原有模式（GUI 在 worker 线程，解密在主线程）
    try:
        if runner_win is not None:
            runner_win.start()
        stats_dict = _do_decrypt(input_png, output_path, start_time)
        return stats_dict
    finally:
        if gpu_win is not None:
            gpu_win.stop()
        if runner_win is not None:
            runner_win.stop()


def _do_decrypt(
    input_png: str,
    output_path: str,
    start_time: float,
) -> dict:
    """实际解密逻辑（不含窗口管理）。可被主线程或 worker 线程调用。"""
    # 1. 读取 PNG + 元数据
    pixels, container = read_encrypted_png(input_png)

    # 2. 验证轨迹哈希（防篡改）
    expected_hash = hashlib.sha256(
        trajectory_fingerprint(container.trajectory)
    ).hexdigest()
    if expected_hash != container.trajectory_hash:
        raise ValueError("轨迹已被篡改（hash 不匹配）")

    # 3. 派生密钥
    key = derive_key(
        trajectory_fingerprint(container.trajectory), container.salt
    )

    # 4. 从像素还原 ciphertext_with_header（含 8B 长度头）
    #    container.ciphertext_len = 仅 chunks 部分长度
    #    因此带头的总长 = ciphertext_len + 8
    total_len = container.ciphertext_len + 8
    ciphertext_with_header = pixels_to_bytes(pixels, original_len=total_len)

    # 5. AES-GCM 并行解密（内部读取 8B 头并按计划切块）
    permuted = parallel_decrypt(key, ciphertext_with_header)

    # 6. 视觉密码层反向置换
    perm = trajectory_to_permutation(container.trajectory)
    inv_perm = invert_permutation(perm)
    plaintext = apply_inverse_permutation(permuted, inv_perm)

    # 7. 写入
    with open(output_path, "wb") as f:
        f.write(plaintext)

    elapsed = time.time() - start_time
    return {
        "input_path": input_png,
        "output_path": output_path,
        "input_size": os.path.getsize(input_png),
        "output_size": len(plaintext),
        "elapsed_seconds": elapsed,
    }
