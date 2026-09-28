"""HSV 像素图可视化（无损编码）。

字节 b → HSV(H=b/256, S=1, V=1) → RGB 三元组存储到 PNG。
通过预计算查找表保证 256 个 byte 值的精确往返（spec §6）。

可视化双视角：
1. 像素图视角：直接观察 HSV 颜色分布
2. 16×16 hex 散点视角：对像素按 (high_nibble, low_nibble) 分箱

设计注记：
- hue 用 ``b/256`` 而非 brief 中的 ``b/255``：因为 ``hsv_to_rgb`` 在
  h=1.0 处会回绕到 h=0，使 byte 0 和 byte 255 撞色（都映射到纯红），
  破坏无损性。改用 ``b/256`` 后 hue ∈ [0, 255/256) ⊂ [0, 1)，
  所有 256 个 byte 都有唯一 RGB，roundtrip 严格成立。
- hex_scatter_view 用查找表（而非 RGB→HSV 逆推）恢复每个像素的
  原始字节值。原因是整数 RGB 经 HSV 逆推会有系统性偏差（已验证），
  无法在均匀数据上得到均匀的 hex 散点图。查找表方式仍保持全向量化。
"""
import colorsys
import math
from typing import Tuple

import numpy as np


# 预计算查找表：byte → RGB
BYTE_TO_RGB: list[Tuple[int, int, int]] = [
    tuple(round(c * 255) for c in colorsys.hsv_to_rgb(b / 256.0, 1.0, 1.0))
    for b in range(256)
]
RGB_TO_BYTE: dict[Tuple[int, int, int], int] = {
    rgb: b for b, rgb in enumerate(BYTE_TO_RGB)
}

# 向量化查找表：把 (R, G, B) ∈ [0, 255]³ 映射到 byte ∈ [0, 255]。
# 索引 = R*65536 + G*256 + B；未被 encode_byte_to_rgb 产生过的
# RGB 组合返回 -1。预计算一次，hex_scatter_view / pixels_to_bytes
# 均可 O(1) 索引。
_RGB_INDEX: np.ndarray = np.full(256 ** 3, -1, dtype=np.int32)
for _byte_val, _rgb in enumerate(BYTE_TO_RGB):
    _RGB_INDEX[_rgb[0] * 65536 + _rgb[1] * 256 + _rgb[2]] = _byte_val


def encode_byte_to_rgb(b: int) -> Tuple[int, int, int]:
    """字节 → RGB 三元组（HSV 全饱和映射）。

    Args:
        b: 0-255 字节值

    Returns:
        (R, G, B) 整数三元组，0-255
    """
    if not 0 <= b <= 255:
        raise ValueError(f"byte must be in 0-255, got {b}")
    return BYTE_TO_RGB[b]


def decode_rgb_to_byte(rgb: Tuple[int, int, int]) -> int:
    """RGB 三元组 → 字节（必须由 encode_byte_to_rgb 产生）。

    Raises:
        KeyError: RGB 不在查找表中（理论上不应发生）
    """
    return RGB_TO_BYTE[rgb]


def bytes_to_pixels(data: bytes) -> Tuple[np.ndarray, int, int]:
    """字节流 → (RGB 像素数组, 宽, 高)。

    像素数 ≥ 字节数，多余像素填 0（H=0 = 红色）。
    尺寸取 ceil(sqrt(N)) × ceil(N/W)，尽量接近正方形。

    向量化：通过将 BYTE_TO_RGB 转为 numpy LUT 一次性查表，避免 Python 循环。
    尾部 padding 像素用 byte 0 的 RGB（红色）填充。
    """
    n = len(data)
    if n == 0:
        return np.zeros((1, 1, 3), dtype=np.uint8), 1, 1

    w = max(1, math.ceil(math.sqrt(n)))
    h = math.ceil(n / w)
    total = h * w

    # Vectorized lookup: convert BYTE_TO_RGB table to numpy array
    lut = np.array(BYTE_TO_RGB, dtype=np.uint8)  # shape (256, 3)
    byte_arr = np.frombuffer(data, dtype=np.uint8)
    if len(byte_arr) < total:
        # Pad with byte 0 so reshape(h, w, 3) always has exactly total*3 values
        padded = np.zeros(total, dtype=np.uint8)
        padded[:len(byte_arr)] = byte_arr
        byte_arr = padded
    elif len(byte_arr) > total:
        byte_arr = byte_arr[:total]

    flat_pixels = lut[byte_arr]  # shape (total, 3)
    pixels = flat_pixels.reshape(h, w, 3)
    return pixels, w, h


def pixels_to_bytes(pixels: np.ndarray, original_len: int) -> bytes:
    """像素数组 → 字节流（截断填充像素）。

    Args:
        pixels: RGB 数组，shape (H, W, 3) uint8
        original_len: 原始字节数（用于截断填充像素）

    Returns:
        字节流，长度等于 original_len
    """
    flat = pixels.reshape(-1, 3).astype(np.uint8)
    n = min(original_len, len(flat))
    if n == 0:
        return b""
    idx = (
        flat[:n, 0].astype(np.int32) * 65536
        + flat[:n, 1].astype(np.int32) * 256
        + flat[:n, 2].astype(np.int32)
    )
    byte_arr = _RGB_INDEX[idx]
    # 无效 RGB（理论不应出现）兜底为 0
    byte_arr = np.where(byte_arr < 0, 0, byte_arr).astype(np.uint8)
    return bytes(byte_arr.tobytes())


def hex_scatter_view(pixels: np.ndarray) -> np.ndarray:
    """像素数组 → 16×16 hex 散点视图。

    用 RGB 查找表无损恢复每个像素的原始字节值，再按
    (high_nibble, low_nibble) 分箱到 16×16 网格。
    所有像素都会被分箱。

    Returns:
        shape (16, 16) int32 直方图
    """
    flat = pixels.reshape(-1, 3).astype(np.int32)
    idx = flat[:, 0] * 65536 + flat[:, 1] * 256 + flat[:, 2]
    byte_vals = _RGB_INDEX[idx]
    # 填充像素（(0,0,0) 等不在表中的 RGB）兜底为 0（红色 = byte 0）
    byte_vals = np.where(byte_vals < 0, 0, byte_vals)
    high = (byte_vals >> 4) & 0xF
    low = byte_vals & 0xF

    grid = np.zeros((16, 16), dtype=np.int32)
    np.add.at(grid, (high, low), 1)
    return grid