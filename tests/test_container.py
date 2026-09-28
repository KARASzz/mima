"""crypto.container 测试：PNG tEXt 元数据自包含容器。

按 preflight 裁决新增 `ciphertext_len` 字段往返测试：
Task 10 解密需要原始 ciphertext 字节长度以正确剥离 padding 像素。
"""
import os
import tempfile

import numpy as np

from crypto.container import (
    PngContainer,
    write_encrypted_png,
    read_encrypted_png,
)


def _make_container():
    return PngContainer(
        algo="AES-256-GCM-v1",
        trajectory=[(0.0, 0.0), (1.0, 1.0), (-1.0, 1.0)],
        trajectory_hash="a" * 64,
        salt=b"\x01" * 16,
        nonce=b"\x02" * 12,
        tag=b"\x03" * 16,
        ciphertext_len=0,
    )


def test_write_read_round_trip():
    """完整字段往返：像素 + 元数据必须完全一致。"""
    container = _make_container()
    container.ciphertext_len = 12345
    pixels = np.random.randint(0, 256, (32, 32, 3), dtype=np.uint8)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name

    try:
        write_encrypted_png(path, pixels, 32, 32, container)
        read_pixels, read_container = read_encrypted_png(path)

        assert np.array_equal(read_pixels, pixels)
        assert read_container.algo == container.algo
        assert read_container.trajectory == container.trajectory
        assert read_container.trajectory_hash == container.trajectory_hash
        assert read_container.salt == container.salt
        assert read_container.nonce == container.nonce
        assert read_container.tag == container.tag
        assert read_container.ciphertext_len == container.ciphertext_len
    finally:
        os.unlink(path)


def test_missing_algo_chunk_raises():
    """缺少 algo 元数据 → 报错。"""
    # 直接读取普通 PNG 应失败
    pixels = np.zeros((8, 8, 3), dtype=np.uint8)
    from PIL import Image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
        Image.fromarray(pixels).save(path)

    try:
        from crypto.container import InvalidContainer
        import pytest
        with pytest.raises(InvalidContainer):
            read_encrypted_png(path)
    finally:
        os.unlink(path)


def test_trajectory_list_serialization():
    """轨迹列表应能正确序列化到 base64 JSON。"""
    traj = [(0.1, 0.2), (0.3, 0.4), (-0.5, 0.6)]
    container = _make_container()
    container.trajectory = traj

    pixels = np.zeros((8, 8, 3), dtype=np.uint8)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name

    try:
        write_encrypted_png(path, pixels, 8, 8, container)
        _, read_container = read_encrypted_png(path)
        assert read_container.trajectory == traj
    finally:
        os.unlink(path)


def test_ciphertext_len_round_trip():
    """ciphertext_len 字段必须正确序列化往返。"""
    container = _make_container()
    container.ciphertext_len = 12345
    pixels = np.zeros((16, 16, 3), dtype=np.uint8)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        write_encrypted_png(path, pixels, 16, 16, container)
        _, read_container = read_encrypted_png(path)
        assert read_container.ciphertext_len == 12345
    finally:
        os.unlink(path)