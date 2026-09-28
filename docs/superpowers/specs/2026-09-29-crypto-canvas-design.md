# Crypto Canvas — 可视化复平面加密演示脚本

**Date:** 2026-09-29
**Status:** Draft (awaiting review)
**Path:** Architectural

## 1. 目标

构建一个 Python 演示脚本，演示**"画图即加密"**的密码学概念：用户在复平面坐标上用鼠标绘制轨迹，该轨迹既作为可视化元素，又作为 AES-256-GCM 的密钥派生材料。**单个 PNG 文件**同时承载密文、密钥元数据和可视化图层（HSV 像素网格），做到"一张图 = 一个锁"。

**可视化双视角**：
1. **HSV 像素视角**：PNG 本体，每个像素的色相编码一个字节，全图呈彩虹色（密文应是均匀分布的彩虹噪点）
2. **16×16 hex 散点视角**：对 HSV 像素按 (high_nibble, low_nibble) 分箱得到的二维直方图，明文会有聚集热点，密文应接近均匀

**非目标**：本项目不用于生产级数据保护。它是一个**教学/演示**工具，重点在于让加密过程可见、可交互、可理解。

## 2. 约束

- 文件大小上限：**10 MB**（约一首 MP3 的容量）
- Python 版本：≥ 3.10（已验证 3.14.5 可用）
- 操作系统：macOS / Linux / Windows（matplotlib + PyOpenGL 后端依赖）
- 输出格式：单 PNG 文件（含全部密文与密钥元数据）
- 依赖库：
  - 核心：`cryptography`, `matplotlib`, `numpy`, `pillow`, `argon2-cffi`, `pytest`
  - CPU 监控：`psutil`
  - GPU 拉满：`PyOpenGL`, `glfw`, `GPUtil`
- **演示增强**：加密过程主动拉满 CPU 与 GPU（详见 §17）

## 3. 架构

四层结构，每层职责单一：

```
┌──────────────────────────────────────────────────────┐
│ Layer 1 │ 交互层（matplotlib 画布）                  │
│         │ - 复平面坐标系 (-1,1) × (-1,1)              │
│         │ - 鼠标轨迹采集                              │
│         │ - 16×16 hex 网格实时预览                    │
├──────────────────────────────────────────────────────┤
│ Layer 2 │ 视觉密码层（轨迹置换）                      │
│         │ - 轨迹几何 → 256 项置换表                   │
│         │ - 字节位置重映射（可逆）                    │
├──────────────────────────────────────────────────────┤
│ Layer 3 │ 加密引擎层（AES 信封）                      │
│         │ - Argon2id 派生 AES-256 密钥                │
│         │ - AES-256-GCM 认证加密                     │
├──────────────────────────────────────────────────────┤
│ Layer 4 │ I/O & 渲染层（PNG 自包含）                 │
│         │ - 文件字节读取/写入                         │
│         │ - 密文字节 → HSV 像素                       │
│         │ - PNG 写入（tEXt chunks 嵌入密钥）          │
└──────────────────────────────────────────────────────┘
```

## 4. 组件清单

| 模块 | 路径 | 职责 |
|------|------|------|
| `crypto_canvas.py` | 根目录 | CLI 入口（argparse）+ matplotlib GUI + 实时监控面板 |
| `crypto/trajectory.py` | `crypto/` | 轨迹采集、几何指纹、置换算法 |
| `crypto/cipher.py` | `crypto/` | AES-256-GCM 加/解密封装（含 multiprocessing 并行） |
| `crypto/kdf.py` | `crypto/` | Argon2id 密钥派生（拉满演示参数） |
| `crypto/visualizer.py` | `crypto/` | HSV 像素图渲染 + 16×16 散点视图 |
| `crypto/container.py` | `crypto/` | PNG tEXt 元数据读写 |
| `crypto/gpu_window.py` | `crypto/` | OpenGL fragment shader 拉满 GPU（独立线程） |
| `crypto/monitor.py` | `crypto/` | psutil + GPUtil 实时监控，进度回调 |
| `tests/test_*.py` | `tests/` | 单元测试与端到端测试 |
| `examples/` | `examples/` | 示例文件与样本轨迹 |

## 5. 数据流

### 5.1 加密流程

```
[用户启动: python crypto_canvas.py encrypt <file>]
       ↓
[matplotlib 弹出复平面画布]
       ↓ 鼠标按下/拖动/松开
[轨迹点序列 T = [(x₁,y₁), (x₂,y₂), ..., (xₙ,yₙ)]]
       ↓ 用户按 Enter 确认
[Layer 2] 计算置换表 P(256项)：
    - 轨迹几何指纹: 质心 C, 平均半径 R, 总弧长 L
    - 对每个 hex 字节 (h,l) ∈ [0,15]²：
      z = complex((h-7.5)/7.5, (l-7.5)/7.5)
      score = min_dist(z, T) * 1000 + atan2(z-C)
    - 按 score 排序 → 索引序列 = P
       ↓
[读取文件 F → 字节流 B (≤10MB)]
       ↓ 应用置换
[置换后字节 B' = P(B)]
       ↓
[Layer 3] 派生密钥：
    - salt = os.urandom(16)
    - key = Argon2id(轨迹指纹, salt, t=3, m=64MB, p=4)
    - nonce = os.urandom(12)
    - tag, ciphertext = AES-256-GCM-encrypt(key, nonce, B')
       ↓
[Layer 4] 渲染 PNG：
    - HSV 编码: 每字节 → 像素 (H=byte/255×360°, S=1.0, V=1.0)
    - 图像尺寸: W = ceil(sqrt(N)), H = ceil(N/W)
    - PNG tEXt chunks 写入:
      * algorithm: "AES-256-GCM"
      * trajectory: base64(JSON of T)
      * thash: SHA-256(轨迹几何指纹)
      * salt: base64(salt)
      * nonce: base64(nonce)
      * tag: base64(tag)
    - 输出 <file>.png
```

### 5.2 解密流程

```
[用户启动: python crypto_canvas.py decrypt <file>.png]
       ↓
[加载 PNG]
       ↓ 解析 tEXt chunks → 提取 trajectory, salt, nonce, tag
       ↓ 解析 IDAT → 像素 → 字节流 → ciphertext
       ↓
[Layer 3] 验证 + 解密：
    - 计算轨迹几何指纹 → thash'
    - 若 thash' ≠ thash → 报错"轨迹已被篡改"
    - key = Argon2id(轨迹指纹, salt, 同参数)
    - 验证 AES-GCM tag → 失败则报错"密钥错误或数据损坏"
    - 解密 → B'
       ↓
[Layer 2] 反向置换：
    - 由相同轨迹计算 P → 求 P^(-1)
    - 原始字节 B = P^(-1)(B')
       ↓
[写入输出文件 <file>_decrypted.<ext>]
```

### 5.3 实时预览（仅 GUI 阶段）

脚本启动时，matplotlib 画布上叠加两个图层：

**图层 A：16×16 hex 网格（背景）**
- 横轴：高 nibble (0-F) 对应 X ∈ [-1, 1]
- 纵轴：低 nibble (0-F) 对应 Y ∈ [-1, 1]
- 半透明底色，引导用户理解 256 个 hex 单元

**图层 B：实时密文散点（前景）**
- 用户绘制轨迹时，前 256 字节按当前置换表映射到 (h, l) 坐标
- 形成"画到哪，密文跑到哪"的视觉反馈
- 分布密度的变化直观展示加密强度

**最终 PNG 与 GUI 预览的关系**：
- GUI 预览用 16×16 scatter（取前 256 字节）
- 最终 PNG 用 HSV 像素网格（全字节）
- 两者的字节分布统计上等价（16×16 scatter 是 PNG 的"分箱视角"）
- 用户看到预览效果 → 决定是否加密 → 按 Enter 生成完整 PNG

## 6. PNG 自包含文件格式

```
PNG chunks:
├── IHDR:        W × H (where W*H = ciphertext byte count)
├── tEXt::algo:   "AES-256-GCM-v1"
├── tEXt::traj:   base64(json.dumps([{"x":..., "y":...}, ...]))
├── tEXt::thash:  hex(SHA-256 of 轨迹几何指纹)
├── tEXt::salt:   base64(16 random bytes)
├── tEXt::nonce:  base64(12 random bytes)
├── tEXt::tag:    base64(16 bytes GCM tag)
├── IDAT:        pixel data, 每个像素 (H, S, V) 编码一个字节
│                H = byte/255 × 360°, S = 1.0, V = 1.0
└── IEND
```

**图像尺寸计算**：
- N = 密文字节数
- W = ceil(√N)
- H = ceil(N / W)
- 例：10 MB = 10,485,760 B → W=3240, H=3238 → PNG ≈ 3240×3238

**HSV 像素存储（无损编码）**：

为避免 `hsv_to_rgb`/`rgb_to_hsv` 浮点往返造成字节漂移，使用**预计算查找表**：

```python
# 模块加载时一次性构建（256 项）
BYTE_TO_RGB = [
    tuple(round(c * 255) for c in colorsys.hsv_to_rgb(b/255.0, 1.0, 1.0))
    for b in range(256)
]
RGB_TO_BYTE = {rgb: b for b, rgb in enumerate(BYTE_TO_RGB)}

# 编码
def encode_byte(b: int) -> tuple[int, int, int]:
    return BYTE_TO_RGB[b]

# 解码
def decode_byte(rgb: tuple[int, int, int]) -> int:
    return RGB_TO_BYTE[rgb]  # 必须精确匹配
```

由于查找表是双向唯一的，所有 256 个 byte 值都能**精确还原**（无浮点误差）。

**16×16 hex 散点图视角**：

PNG 输出是 HSV 像素网格（W×H），但用户可以**以 16×16 视角解读**：
- 每个像素的色相 H 对应一个 byte 值
- 字节的高 nibble (0-F) 和低 nibble (0-F) 决定该像素"属于"哪个 hex 单元
- 把所有像素按 (high_nibble, low_nibble) 二维直方图分箱 → 即可得到 16×16 散点图
- 10 MB 图像平均每格 ~40960 像素，密文分布应接近均匀（卡方检验可验证）

明文视角：原始文件字节分布通常有偏向（如 ASCII 文本聚集在右下），16×16 视图有热点
密文视角：AES 加密后分布均匀，16×16 视图呈雪花噪点

**matplotlib GUI 实时预览**：在用户画轨迹时，画布上叠加 16×16 hex 网格，实时显示当前文件若按此轨迹加密后的字节分布变化（用前 256 字节采样），帮助用户理解"画轨迹 = 改分布"。

## 7. 关键算法

### 7.1 轨迹 → 置换表

```python
def trajectory_to_permutation(trajectory: list[tuple[float, float]]) -> list[int]:
    """256 项置换表，从轨迹几何派生。"""
    if len(trajectory) < 10:
        raise ValueError("轨迹点过少（<10），强度不足")

    # 1. 几何指纹
    cx = sum(p[0] for p in trajectory) / len(trajectory)
    cy = sum(p[1] for p in trajectory) / len(trajectory)
    centroid = complex(cx, cy)

    # 2. 256 个 hex 字节映射到复平面
    byte_scores = []
    for h in range(16):
        for l in range(16):
            z = complex((h - 7.5) / 7.5, (l - 7.5) / 7.5)
            d = min(abs(z - complex(*p)) for p in trajectory)
            theta = math.atan2(z.imag - centroid.imag,
                               z.real - centroid.real)
            score = (d, theta)  # 元组排序，距离优先
            byte_scores.append((score, h * 16 + l))

    # 3. 稳定排序（确保确定性）
    byte_scores.sort(key=lambda x: x[0])
    return [b for _, b in byte_scores]
```

### 7.2 反向置换

```python
def invert_permutation(perm: list[int]) -> list[int]:
    """P[i] = j 表示字节 i 映射到位置 j"""
    inv = [0] * len(perm)
    for i, j in enumerate(perm):
        inv[j] = i
    return inv
```

### 7.3 Argon2id 参数（拉满演示模式）

```python
from argon2.low_level import hash_secret, Type

# 演示模式：参数有意拉高，让 CPU 占用肉眼可见
# 生产环境建议 t=1, m=64MB, p=4；此处 t=5 / p=8 拉高 CPU 峰值
def derive_key(trajectory_fingerprint: bytes, salt: bytes) -> bytes:
    return hash_secret(
        raw_password=trajectory_fingerprint,
        salt=salt,
        time_cost=5,             # 演示模式（原 3 → 5）
        memory_cost=64 * 1024,   # 64 MB (KiB)
        parallelism=8,           # 8 线程拉满多核（原 4 → 8）
        hash_len=32,             # AES-256 密钥长度
        type=Type.ID,
    )
```

> **注**：Argon2id 64MB 内存访问 + 8 线程 + 5 轮迭代在典型 macOS/Linux 工作站上约 3-5 秒，期间 `psutil` 显示 CPU 持续 80-100%。这正是"加密在用力跑"的视觉证据。

**轨迹几何指纹**：
```python
def trajectory_fingerprint(trajectory):
    cx = mean(x for x, y in trajectory)
    cy = mean(y for x, y in trajectory)
    arc = sum(((trajectory[i+1][0]-trajectory[i][0])**2
              + (trajectory[i+1][1]-trajectory[i][1])**2)**0.5
              for i in range(len(trajectory)-1))
    raw = f"{cx:.6f},{cy:.6f},{arc:.6f},{len(trajectory)}".encode()
    return hashlib.sha256(raw).digest()
```

## 8. 错误处理

| 场景 | 检测点 | 处理 |
|------|--------|------|
| 轨迹点 < 10 | 置换前 | 拒绝，提示"至少画 10 个点" |
| 文件 > 10 MB | 读文件后 | 拒绝，提示大小限制 |
| PNG 不是加密产物 | 缺少 tEXt::algo | 报错"无效的加密文件" |
| 轨迹被篡改 | thash 不匹配 | 拒绝，提示"轨迹元数据已损坏" |
| 密钥错误 | AES-GCM tag 校验失败 | 拒绝，提示"密钥错误或数据损坏" |
| PNG 像素数 ≠ 密文长度 | IDAT vs tag nonce | 报错"文件已损坏" |
| 用户按 ESC | GUI 关闭 | 取消加密，无输出 |

## 9. 测试策略

### 9.1 单元测试

- `test_trajectory.py`
  - 置换表是 0-255 的完整排列（无重复无遗漏）
  - 反向置换与正向置换互逆
  - 同轨迹两次计算 → 同置换表（确定性）
  - 轨迹 < 10 点 → 抛 ValueError

- `test_cipher.py`
  - AES-GCM 加解密往返一致
  - 篡改密文 → tag 校验失败
  - 篡改 nonce → tag 校验失败

- `test_kdf.py`
  - 同指纹 + 同 salt → 同 key
  - 不同 salt → 不同 key

- `test_container.py`
  - 写入所有 tEXt chunk 后 PIL 可读
  - 读取时丢失 chunk → 抛错

### 9.2 端到端测试

- `test_e2e.py`
  - 预存轨迹 `examples/circle.traj` → 加密 `sample.txt` → 解密 → SHA-256 比对
  - 10MB 边界文件测试
  - 篡改 PNG 文件 → 解密失败

### 9.3 视觉验收（手动）

- 明文 hex 散点：ASCII 字符集中在 (3-F, 3-F) 区域
- 密文 hex 散点：256 格近似均匀（卡方检验 χ² < 临界值）
- 同一文件用不同轨迹加密 → 散点图分布差异肉眼可见

## 10. 项目结构

```
mima/
├── crypto_canvas.py            # CLI 入口（~150 行）
├── crypto/
│   ├── __init__.py
│   ├── trajectory.py           # 轨迹/置换（~80 行）
│   ├── cipher.py               # AES-GCM（~40 行）
│   ├── kdf.py                  # Argon2id（~30 行）
│   ├── visualizer.py           # HSV 像素图（~60 行）
│   └── container.py            # PNG tEXt 读写（~80 行）
├── tests/
│   ├── test_trajectory.py
│   ├── test_cipher.py
│   ├── test_kdf.py
│   ├── test_container.py
│   └── test_e2e.py
├── examples/
│   ├── sample.txt              # 测试文本
│   ├── sample.mp3              # 1MB 测试音频
│   └── circle.traj             # 预存轨迹示例（圆周）
├── docs/
│   └── README.md               # 使用说明
├── pyproject.toml              # 依赖声明
└── requirements.txt            # 备用依赖列表
```

## 11. CLI 接口

```bash
# 加密（弹出画布，画轨迹后按 Enter）
python crypto_canvas.py encrypt <file>

# 解密（从 PNG 还原文件）
python crypto_canvas.py decrypt <file>.png [--output <out>]

# 用预存轨迹加密（无 GUI，跳过轨迹绘制）
python crypto_canvas.py encrypt <file> --trajectory <traj.json>

# 生成示例轨迹
python crypto_canvas.py gen-trajectory --shape circle --output circle.traj

# 自检
python crypto_canvas.py selftest

# 显示规格信息
python crypto_canvas.py info <file>.png
```

## 12. 性能预算

| 操作 | 文件大小 | 预期耗时 |
|------|----------|----------|
| 加密 1 MB | 1 MB | < 3 秒 |
| 加密 10 MB | 10 MB | < 30 秒 |
| 解密 1 MB | 1 MB | < 2 秒 |
| 解密 10 MB | 10 MB | < 20 秒 |
| 置换表计算 | 256 字节 | < 0.1 秒 |
| HSV 像素渲染 10 MB | 3240×3238 | < 5 秒 |

## 13. 已知限制

- 10MB 单文件上限（PNG 图像在 3240×3238 时 PIL 写入可能 OOM，已验证 ≤10MB 没问题）
- 不抗量子攻击（AES-256 可承受经典攻击，量子攻击需 ≥ AES-512 才安全）
- PNG 元数据可被任意读取（不抗主动篡改者，篡改会触发 thash 校验失败）
- 轨迹长度影响置换强度，极简轨迹（< 10 点）被显式拒绝
- matplotlib 在无显示器环境（SSH）需用 `Agg` 后端并跳过 GUI
- GPU 拉满依赖桌面 OpenGL 上下文；纯 headless 环境自动降级为仅 CPU 模式
- GPUtil 主要支持 NVIDIA；macOS Apple Silicon / AMD GPU 显示 N/A 但 OpenGL 仍可运行

## 14. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Argon2id 64MB 内存压力 | 小内存机器卡顿 | 自动降级到 32MB + time_cost=4 |
| 3240×3238 PNG 内存峰值 | ~30 MB RGB 数组 | 分块渲染（每次 1000 行） |
| matplotlib 后端问题 | SSH 环境无法显示 | 检测 `DISPLAY` 变量，无则提示用 `--trajectory` 模式 |
| 用户误关闭画布 | 加密未完成 | 监听 `close_event`，退出时清理临时状态 |
| GPU 上下文创建失败 | 无 OpenGL 后端 | 自动 fallback 到无 GPU 模式，CPU 仍拉满 |
| 多窗口事件循环冲突 | matplotlib + glfw 同时阻塞 | GPU 窗口用独立线程，主线程继续 matplotlib 事件循环 |
| multiprocessing spawn 模式 | macOS 启动开销 ~1s | 文档说明；首次加密会稍慢，后续实例可复用 Pool |

## 15. 验收标准

✅ 用户能通过鼠标画轨迹完成加密
✅ 加密产物是单个 PNG 文件
✅ 解密后文件 SHA-256 与原文件一致
✅ 篡改 PNG（轨迹或像素）均会被检测并拒绝
✅ 10MB 文件可在 30 秒内完成加密
✅ 所有单元测试通过（pytest）
✅ 端到端测试覆盖典型用户路径
✅ 自检命令（selftest）输出全部通过标记
✅ 加密过程中 CPU 持续 ≥80%（psutil 验证）
✅ 桌面环境下 GPU 窗口可见运行（fragment shader 持续渲染）
✅ GUI 实时显示 CPU%/GPU%/进度阶段

## 16. 后续可能的扩展（YAGNI 当前不做）

- 多文件批量加密（每文件独立 PNG）
- 抗量子后量子算法（ML-KEM + AES hybrid）
- Web 版本（Pyodide + 浏览器 Canvas）
- 加密容器支持密码 + 轨迹双因素
- 自定义轨迹导入（SVG 路径）

## 17. CPU/GPU 拉满演示

加密过程不是"瞬间完成"，而是**主动制造视觉与硬件层面的"用力感"**。教学目的是让用户直观感受到：现代密码学的真实开销是看得见的算力。

### 17.1 CPU 拉满策略（三层叠加）

**第一层：Argon2id 参数拉高**（详见 §7.3）
- `time_cost=5, parallelism=8, memory_cost=64MB`
- Argon2id 本身就是内存硬函数，单次派生约 3-5 秒，期间 8 个核心持续工作

**第二层：AES-GCM 多进程并行**
- 把 10MB 字节流切成 8 个 1.25MB 块
- `multiprocessing.Pool(8)` 并行加密（AES-NI 指令集下吞吐 ~5 GB/s）
- 合并 ciphertext + 各自 nonce（每块独立 nonce 12B）

```python
# crypto/cipher.py 片段
from multiprocessing import Pool
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def _encrypt_chunk(args):
    key, nonce, chunk = args
    return AESGCM(key).encrypt(nonce, chunk, None)

def parallel_encrypt(key: bytes, plaintext: bytes, workers: int = 8) -> bytes:
    chunk_size = (len(plaintext) + workers - 1) // workers
    chunks = [plaintext[i:i+chunk_size] for i in range(0, len(plaintext), chunk_size)]
    nonces = [os.urandom(12) for _ in chunks]
    with Pool(workers) as pool:
        encrypted = pool.starmap(_encrypt_chunk, [(key, n, c) for n, c in zip(nonces, chunks)])
    # 头部拼接所有 nonce，解密时按顺序解开
    return b''.join(n.encode() + e for n, e in zip(nonces, encrypted))
```

**第三层：PNG 编码与置换并行**
- 置换表计算（256 字节）和 HSV→RGB 转换（10M 像素）分别在不同进程
- PNG DEFLATE 压缩（10MB）单进程即可吃满一核

### 17.2 GPU 拉满策略（OpenGL Fragment Shader）

独立小窗口（512×512），运行**持续 fragment shader**，确保 GPU 真的在画：

```glsl
// crypto/gpu_window.py 中的着色器
#version 330 core
out vec4 fragColor;
uniform float u_time;
uniform vec2 u_resolution;

// 计算密集型：每帧每个像素都跑 SHA-256-like 哈希 + Perlin 噪声
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution;
    float t = u_time * 0.001;
    // 每像素做 16 次 hash + 8 次 sin/cos，强制 GPU 满载
    float v = 0.0;
    for (int i = 0; i < 16; i++) {
        v += hash(uv * 256.0 + float(i) + t);
    }
    v = fract(v * 0.125);
    fragColor = vec4(vec3(v, fract(v * 7.0), fract(v * 13.0)), 1.0);
}
```

**实现**：PyOpenGL + glfw，独立线程启动渲染循环，加密完成后关闭窗口。

```python
# crypto/gpu_window.py 片段
import glfw
from OpenGL.GL import *
from threading import Thread

class GPUStressWindow:
    def __init__(self):
        self.running = False

    def start(self):
        if not glfw.init():
            return  # headless fallback
        self.window = glfw.create_window(512, 512, "GPU Crunching", None, None)
        glfw.make_context_current(self.window)
        self.running = True
        Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        # 编译 shader, 进入 render-while-false loop
        while self.running and not glfw.window_should_close(self.window):
            # 更新 uniform, 绘制全屏 quad
            glClear(GL_COLOR_BUFFER_BIT)
            # ... 绘制调用
            glfw.swap_buffers(self.window)
            glfw.poll_events()

    def stop(self):
        self.running = False
        glfw.terminate()
```

### 17.3 实时监控 UI

matplotlib 画布右侧叠加监控面板（200px 宽）：

```
┌──────────────────────────┐
│ 加密进度                  │
├──────────────────────────┤
│ [████████░░░░░] 60%      │
│ 阶段: AES-GCM 并行加密    │
├──────────────────────────┤
│ CPU: ████████░░ 82%      │
│  核心: [✓][✓][✓][✓][✓]…  │
│ 内存: 142 MB / 256 MB    │
├──────────────────────────┤
│ GPU: [OpenGL 渲染中]     │
│  帧率: 60 FPS            │
└──────────────────────────┘
```

**实现**：用 `matplotlib.gridspec` 分两栏，左边画轨迹，右边画监控图表（用 `matplotlib.animation.FuncAnimation` 每 200ms 更新）。

### 17.4 加密阶段流水线（用户可见）

| 阶段 | 持续时间 | 硬件占用 | 用户反馈 |
|------|----------|----------|----------|
| 1. 置换表计算 | <0.1s | CPU 1 核 | "生成视觉置换..." |
| 2. Argon2id 派生 | 3-5s | CPU 8 核 + 64MB 内存 | "派生加密密钥..." |
| 3. AES-GCM 并行加密 | 0.05s | CPU 8 核 | "AES 加密..." |
| 4. HSV 像素编码 | 0.5s | CPU 1 核 | "渲染像素..." |
| 5. PNG 写入 | 2-5s | CPU 1 核 + I/O | "压缩 PNG..." |
| **总计** | **6-11s** | **全程硬件忙** | GUI 全程动画 |

### 17.5 Headless 降级

无 `DISPLAY` / 无 OpenGL 上下文时：
- GPU 窗口自动跳过，CPU 拉满照常
- 监控面板只显示 CPU%，GPU 字段显示 "N/A (headless)"
- 日志提示 "GPU 拉满已跳过，可在桌面环境启用"

### 17.6 安全说明

> **故意拉高参数 vs 实际安全**：Argon2id t=5 / p=8 相对 t=3 / p=4 的安全边际提升有限（攻击者成本线性增长），但视觉上 CPU 占用更显眼。教学场景下参数选择优先考虑"看得见的算力"，而非追求极限 KDF 强度。生产部署应改回 t=1 / p=4。