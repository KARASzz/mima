"""加密流程编排。

按层调用：视觉置换 → Argon2id KDF → AES-GCM 并行加密 → HSV 渲染 → PNG 写入。
过程中启动 GPU 窗口和像素人物窗口（可选）。

parallel_encrypt 输出格式（来自 cipher.py）：
    [8 字节明文长度大端] + (nonce + ct + tag) × chunks

本模块对调用方屏蔽此细节：
- bytes_to_pixels 编码完整的 ciphertext_with_header（含 8B 头）
- container.ciphertext_len 记录 chunks 部分的字节数（不含 8B 头）
  即 ciphertext_len = len(parallel_encrypt_output) - 8
- 解密时用 ciphertext_len + 8 还原总长度，再交由 parallel_decrypt 自行解析。
"""
import hashlib
import logging
import os
import time

from .cipher import parallel_encrypt
from .container import PngContainer, write_encrypted_png
from .kdf import derive_key
from .trajectory import (
    apply_permutation,
    trajectory_fingerprint,
    trajectory_to_permutation,
)
from .visualizer import bytes_to_pixels

log = logging.getLogger(__name__)


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class FileTooLarge(Exception):
    """输入文件超过 MAX_FILE_SIZE 时抛出。"""
    pass


def encrypt_file(
    input_path: str,
    output_path: str,
    trajectory: list,
    use_gpu: bool = True,
    use_runner: bool = True,
) -> dict:
    """加密文件到 PNG。

    Args:
        input_path: 输入文件路径
        output_path: 输出 PNG 路径
        trajectory: 用户绘制的轨迹点序列
        use_gpu: 是否启动 GPU 拉满窗口
        use_runner: 是否启动像素人物窗口

    Returns:
        统计信息字典：耗时、文件大小等

    Raises:
        FileTooLarge: 文件 > 10 MB
    """
    start_time = time.time()

    # 启动可视化窗口（macOS 上由各 start() 内部静默跳过）
    gpu_win = None
    runner_win = None
    if use_runner:
        from .runner import RunnerWindow
        runner_win = RunnerWindow(direction="left")
        runner_win.start()
    if use_gpu:
        from .gpu_window import GPUStressWindow
        gpu_win = GPUStressWindow()
        gpu_win.start()

    try:
        # 1. 读取文件
        file_size = os.path.getsize(input_path)
        if file_size > MAX_FILE_SIZE:
            raise FileTooLarge(f"文件过大（{file_size} > {MAX_FILE_SIZE} bytes）")

        with open(input_path, "rb") as f:
            plaintext = f.read()

        # 2. 视觉密码层：置换
        perm = trajectory_to_permutation(trajectory)
        permuted = apply_permutation(plaintext, perm)

        # 3. 加密层：派生密钥 + AES-GCM 并行
        salt = os.urandom(16)
        key = derive_key(trajectory_fingerprint(trajectory), salt)
        ciphertext_with_header = parallel_encrypt(key, permuted)
        # ciphertext_with_header = [8B plaintext_len] + chunks

        # 4. 渲染层：HSV 像素（编码完整 ciphertext，含 8B 头）
        pixels, w, h = bytes_to_pixels(ciphertext_with_header)

        # 5. 写入 PNG
        container = PngContainer(
            algo="AES-256-GCM-v1",
            trajectory=trajectory,
            trajectory_hash=hashlib.sha256(trajectory_fingerprint(trajectory)).hexdigest(),
            salt=salt,
            nonce=b"",  # 实际 nonce 嵌入在 ciphertext_with_header 中
            tag=b"",    # 同上
            ciphertext_len=len(ciphertext_with_header) - 8,  # 仅 chunks 部分
        )
        write_encrypted_png(output_path, pixels, w, h, container)

        elapsed = time.time() - start_time
        return {
            "input_path": input_path,
            "output_path": output_path,
            "input_size": file_size,
            "output_size": os.path.getsize(output_path),
            "elapsed_seconds": elapsed,
            "trajectory_points": len(trajectory),
        }
    finally:
        if gpu_win is not None:
            gpu_win.stop()
        if runner_win is not None:
            runner_win.stop()
