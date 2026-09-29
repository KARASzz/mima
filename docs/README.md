# Crypto Canvas

> 可视化文件加密 — "画图即加密"

一个 Python 演示工具，将文件（≤10 MB）加密为单个自包含的 PNG 图像。
加密密钥由用户在复平面上绘制的轨迹派生而来，加密过程会主动拉满
CPU（multiprocessing + Argon2id）和 GPU（OpenGL fragment shader），
同时屏幕上有一个 16×16 的像素人物在跑动。

PNG 自带了解密所需的一切：密文编码为彩色像素，外加轨迹、盐和元数据
（保存在 PNG `tEXt` chunks 中）。分享图像就是分享加密后的文件。

## 特性

- **单 PNG 输出** — 密文、密钥材料和可视化都在同一个文件中
- **基于轨迹的视觉密码** — 在复平面上画图 → 256 字节置换表
- **AES-256-GCM + Argon2id** — 工业级加密算法，主动制造 CPU 压力
- **OpenGL fragment shader 窗口** — 加密期间 GPU 持续 ~60 FPS
- **像素人物动画** — 16×16 角色加密时**向左**跑、解密时**向右**跑
- **无损 HSV 编码** — 每个字节映射到唯一的 RGB 像素
- **轨迹完整性校验** — 轨迹的 SHA-256 写入 PNG 元数据，篡改会在解密时被发现

---

## ⚠️ macOS 平台限制

> **如果你在 macOS 上运行，请先阅读这一节。**

GPU 压力窗口（OpenGL fragment shader）在 macOS 上**静默跳过**。
像素人物动画窗口（tkinter）在 macOS 上**正常运行** —— 加密管线
本身在所有平台都能运行。

### 原因

- macOS AppKit（Cocoa）要求每个 `NSWindow` 必须在**主线程**实例化。
- 在 macOS 上，从工作线程调用 AppKit 会触发
  `NSInternalInconsistencyException` — 这是一个**无法拦截的 C++ 异常**，
  会导致整个进程崩溃。

### 当前实现

**像素人物窗口（tkinter）** — `RunnerWindow.run_blocking()` 由主线程调用，
加密 / 解密逻辑放到 worker 线程。这是 macOS 上**必需**的模式（AppKit 限制），
也是其他平台的正确模式（事件循环驱动）。`start()` 仍向后兼容旧的
worker-thread 模式，但在 macOS 上会打印 warning 后直接返回，
提示调用方改用 `run_blocking()`。

**GPU 压力窗口（OpenGL fragment shader）** — 仍在 `sys.platform == "darwin"`
守卫下静默跳过（`crypto/gpu_window.py`）。要在 macOS 上运行需将其
也移到主线程，超出本演示范围。

### 影响

| 组件                          | Linux / Windows | macOS                       |
|-------------------------------|-----------------|-----------------------------|
| 加密 / 解密管线               | ✅ 运行          | ✅ 运行                      |
| Argon2id CPU 压力             | ✅ 运行          | ✅ 运行                      |
| 多进程并行 AES                | ✅ 运行          | ✅ 运行                      |
| OpenGL GPU 压力窗口           | ✅ 运行          | ⚠️ **静默跳过**              |
| 像素人物动画                  | ✅ 运行          | runs (main-thread Tk)       |
| 轨迹绘制 GUI                  | ✅ 运行          | ✅ 运行（matplotlib 后端）   |

在 macOS 上，加密/解密能成功完成并产出相同的 PNG 文件，且能**看到**
像素人物窗口。OpenGL GPU 压力窗口仍看不到。

---

## 安装

```bash
pip install -r requirements.txt
```

依赖 Python 3.10+、NumPy、Pillow、PyOpenGL、glfw、matplotlib、cryptography、
argon2-cffi，以及 pytest（用于 `selftest`）。

---

## 使用方法

```bash
# 加密文件（交互式轨迹绘制）
python crypto_canvas.py encrypt myfile.txt

# 解密 PNG 还原原始文件
python crypto_canvas.py decrypt myfile.txt.png

# 显示 PNG 元数据（算法、轨迹、盐等）
python crypto_canvas.py info myfile.txt.png

# 运行所有测试
python crypto_canvas.py selftest
```

### CLI 标志

| 标志                          | 适用范围       | 描述                                                                |
|-------------------------------|----------------|----------------------------------------------------------------------------|
| `-o, --output <path>`         | encrypt/decrypt | 自定义输出路径（默认：encrypt 输出 `<file>.png`，decrypt 输出 `<file>_decrypted`） |
| `--no-gpu`                    | encrypt/decrypt | 跳过 OpenGL fragment-shader GPU 压力窗口                          |
| `--no-runner`                 | encrypt/decrypt | 跳过 tkinter 像素人物动画窗口                          |
| `--trajectory <file.json>`    | encrypt     | 使用预存轨迹（如 `examples/circle.traj`）并跳过 GUI       |
| `--help`                      | all         | 显示子命令帮助                                                       |

> 注意：`--no-gpu` 和 `--no-runner` 是仅有的退出选项。在 macOS 上，
> 这两个窗口本来就会自动跳过（见 **macOS 平台限制**）。

---

## 示例输出

```bash
$ python crypto_canvas.py encrypt examples/sample.txt \
    --trajectory examples/circle.traj --no-runner --no-gpu
✓ Encrypted: examples/sample.txt -> /tmp/encrypted.png
  Size: 361 -> 4817 bytes
  Time: 0.4s

$ python crypto_canvas.py decrypt /tmp/encrypted.png --no-runner --no-gpu
✓ Decrypted: /tmp/encrypted.png -> /tmp/encrypted_decrypted
  Size: 4817 -> 361 bytes

$ python crypto_canvas.py info /tmp/encrypted.png
Algorithm: AES-256-GCM-v1
Image size: 64x64
Trajectory points: 40
Trajectory hash: a3f1d2b9c4e5f678...
Salt: 7e2c1d4b9a8f6053...
Ciphertext length: 4809 bytes
Nonce: ...
Tag: ...
```

解密后的文件与原始文件**字节完全一致**（由 `tests/test_e2e.py`
中的 SHA-256 校验验证）。

---

## 工作原理

1. **轨迹绘制** — 用户在 matplotlib 画布（复平面）上点击。
   也可以用 `--trajectory <file.json>` 跳过 GUI，使用预存的 `(x, y)` 点列表。
2. **视觉密码** — 轨迹几何经过 SHA-256 哈希后，通过 `crypto/trajectory.py`
   映射到 256 字节置换表。
3. **字节置换** — 明文字节按置换表重新排列。置换本身不具有密码学强度，
   它的作用是让密文"看上去像彩虹噪点"。
4. **密钥派生** — `Argon2id(轨迹 SHA-256 指纹, salt)` → 32 字节 AES-256 密钥
   （`crypto/kdf.py`）。演示参数故意激进（见下方安全说明）。
5. **加密** — AES-256-GCM 通过 `multiprocessing` 并行分块加密
   （`crypto/cipher.py`）。输出格式：
   `[8 字节明文长度大端] + (nonce + ct + tag) × chunks`。
6. **HSV 渲染** — `crypto/visualizer.py` 将每个密文字节映射到唯一的
   RGB 像素（无损，覆盖全色域）。
7. **PNG 输出** — `crypto/container.py` 写入像素网格及 `tEXt` chunks
   （`algo`、`trajectory`、`trajectory_hash`、`salt`、`ciphertext_len`）。
   PNG 完全自包含。
8. **视觉反馈**（非 macOS）— OpenGL fragment shader 渲染全屏 GPU 负载，
   像素人物在屏幕上跑动。加密完成后两个窗口立即关闭。

解密路径是加密的逆过程，但多一步：从 PNG 元数据中读取轨迹哈希，
与新计算的 SHA-256 比对。若不匹配则抛出 `ValueError("轨迹已被篡改")` 并中止。

---

## 安全说明

这是**演示工具**，不是生产级加密方案。

- Argon2id 参数（`t=5`、`m=64 MiB`、`p=8`）故意激进，让 CPU 压力肉眼可见。
  生产环境请改回 `t=1`、`p=4`（spec §7.3, §17.6）。
- 字节置换**只是视觉上的** — 它不增加密码学强度。真正保护数据的是 AES-256-GCM。
- PNG 中保存的轨迹是解密必需的。任何能读 PNG 的人都能读出轨迹；
  Argon2id KDF 提供一点点暴力破解阻力，但**不能**替代真正的密码。
- 分块长度由密文开头的 8 字节明文长度头推断（没有逐块长度元数据）。
  spec §2 注明了这一简化。

---

## 项目结构

```
crypto/
  cipher.py           AES-256-GCM + multiprocessing 并行分块
  kdf.py              Argon2id 密钥派生（演示参数）
  trajectory.py       SHA-256 指纹 → 256 字节置换表
  container.py        PNG tEXt chunk 读写
  visualizer.py       无损字节 ↔ 像素 HSV 编码
  gpu_window.py       OpenGL fragment-shader 压力窗口（macOS 跳过）
  runner.py           Tkinter 像素人物动画（macOS 主线程模式）
  trajectory_gui.py   Matplotlib 交互式轨迹绘制
  encrypt.py          加密编排（调用所有层）
  decrypt.py          解密编排（加密的逆过程）
crypto_canvas.py      CLI 入口（encrypt / decrypt / info / selftest）
tests/                Pytest 测试套件（57 个测试，全部通过）
examples/
  circle.traj         预存轨迹（单位圆，40 个点）
  sample.txt          小型演示明文
docs/                 本 README + spec + plan
```

---

## 规格说明

完整设计文档位于
[`docs/superpowers/specs/2026-09-29-crypto-canvas-design.md`](../superpowers/specs/2026-09-29-crypto-canvas-design.md)。
实现计划位于
[`docs/superpowers/plans/2026-09-29-crypto-canvas.md`](../superpowers/plans/2026-09-29-crypto-canvas.md)。

---

## 许可

演示 / 教育用途。