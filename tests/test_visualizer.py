"""crypto.visualizer 测试：HSV 像素图 + 16x16 hex 散点视图。"""
import numpy as np

from crypto.visualizer import (
    bytes_to_pixels,
    decode_rgb_to_byte,
    encode_byte_to_rgb,
    hex_scatter_view,
    pixels_to_bytes,
)


def test_encode_decode_round_trip_all_bytes():
    """所有 256 个 byte 值必须能精确往返。"""
    for b in range(256):
        rgb = encode_byte_to_rgb(b)
        assert decode_rgb_to_byte(rgb) == b


def test_encode_uses_full_color_range():
    """HSV 编码应产生 S=V=1 的鲜艳颜色。"""
    rgb = encode_byte_to_rgb(0)
    assert rgb == (255, 0, 0)  # 红色（H=0）
    rgb = encode_byte_to_rgb(128)
    # H=128/255*360 ≈ 180.7° → 青色调
    assert rgb[0] < 50 and rgb[2] > 200  # R 很低，B 很高


def test_bytes_to_pixels_dimensions():
    """N 字节应生成 ceil(sqrt(N)) × ceil(N/W) 像素。"""
    data = bytes(range(100))
    pixels, w, h = bytes_to_pixels(data)
    assert pixels.shape == (h, w, 3)
    assert w * h >= len(data)
    assert pixels.dtype == np.uint8


def test_bytes_to_pixels_to_bytes_round_trip():
    """bytes ↔ pixels ↔ bytes 必须完全一致。"""
    original = bytes(range(256)) * 100  # 25600 bytes
    pixels, w, h = bytes_to_pixels(original)
    recovered = pixels_to_bytes(pixels, original_len=len(original))
    assert recovered == original


def test_hex_scatter_view_shape():
    """16×16 hex 散点图形状为 (16, 16)。"""
    data = bytes(range(256))
    pixels, w, h = bytes_to_pixels(data)
    view = hex_scatter_view(pixels)
    assert view.shape == (16, 16)
    assert view.sum() == len(data)  # 全部像素都被分箱


def test_hex_scatter_view_uniform_distribution():
    """均匀字节流 → 16×16 视图应近似均匀。"""
    # 构造循环 0-255 的字节流，每格平均 100 次
    data = bytes([i % 256 for i in range(256 * 100)])
    pixels, w, h = bytes_to_pixels(data)
    view = hex_scatter_view(pixels)
    # 每格应有 ~100 个像素（允许 ±10% 浮动）
    for i in range(16):
        for j in range(16):
            cell = view[i, j]
            assert 90 <= cell <= 110, f"cell ({i},{j}) has {cell}, expected ~100"