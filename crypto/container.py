"""PNG 自包含容器。

使用 PNG tEXt chunks 存储加密元数据：
- algo: 算法标识
- trajectory: 轨迹 JSON（base64 编码）
- thash: 轨迹 SHA-256 哈希
- salt: Argon2id 盐
- nonce: AES-GCM nonce
- tag: AES-GCM 认证标签
- clen: 原始密文字节长度（供 Task 10 decrypt 剥离 padding 像素）

像素数据本身存储密文的 HSV 编码（spec §6）。
"""
import base64
import json
from dataclasses import dataclass
from typing import Tuple

import numpy as np
from PIL import Image, PngImagePlugin


CHUNK_ALGO = "algo"
CHUNK_TRAJ = "trajectory"
CHUNK_THASH = "thash"
CHUNK_SALT = "salt"
CHUNK_NONCE = "nonce"
CHUNK_TAG = "tag"
CHUNK_CLEN = "clen"

EXPECTED_ALGO = "AES-256-GCM-v1"


class InvalidContainer(Exception):
    """PNG 不是有效的加密容器。"""
    pass


@dataclass
class PngContainer:
    """PNG 中嵌入的加密元数据。"""
    algo: str
    trajectory: list
    trajectory_hash: str
    salt: bytes
    nonce: bytes
    tag: bytes
    ciphertext_len: int


def _encode_bytes(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _decode_str(s: str) -> bytes:
    return base64.b64decode(s)


def write_encrypted_png(
    path: str,
    pixels: np.ndarray,
    width: int,
    height: int,
    container: PngContainer,
) -> None:
    """写入带元数据的 PNG 文件。

    Args:
        path: 输出路径
        pixels: shape (H, W, 3) uint8 像素数组
        width: 图像宽度
        height: 图像高度
        container: 加密元数据
    """
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text(CHUNK_ALGO, container.algo)
    pnginfo.add_text(CHUNK_TRAJ, _encode_bytes(json.dumps(container.trajectory).encode("utf-8")))
    pnginfo.add_text(CHUNK_THASH, container.trajectory_hash)
    pnginfo.add_text(CHUNK_SALT, _encode_bytes(container.salt))
    pnginfo.add_text(CHUNK_NONCE, _encode_bytes(container.nonce))
    pnginfo.add_text(CHUNK_TAG, _encode_bytes(container.tag))
    pnginfo.add_text(CHUNK_CLEN, str(container.ciphertext_len))

    img = Image.fromarray(pixels, mode="RGB")
    img.save(path, pnginfo=pnginfo, compress_level=6)


def read_encrypted_png(path: str) -> Tuple[np.ndarray, PngContainer]:
    """读取加密 PNG，返回像素数组和元数据。

    Raises:
        InvalidContainer: 缺少必要元数据
    """
    img = Image.open(path)
    info = img.info

    required = [
        CHUNK_ALGO, CHUNK_TRAJ, CHUNK_THASH,
        CHUNK_SALT, CHUNK_NONCE, CHUNK_TAG, CHUNK_CLEN,
    ]
    for key in required:
        if key not in info:
            raise InvalidContainer(f"missing required metadata chunk: {key}")

    algo = info[CHUNK_ALGO]
    if algo != EXPECTED_ALGO:
        raise InvalidContainer(f"unsupported algorithm: {algo}")

    trajectory = json.loads(_decode_str(info[CHUNK_TRAJ]).decode("utf-8"))
    # trajectory 应转为 list[tuple[float, float]]
    trajectory = [(float(p[0]), float(p[1])) for p in trajectory]

    container = PngContainer(
        algo=algo,
        trajectory=trajectory,
        trajectory_hash=info[CHUNK_THASH],
        salt=_decode_str(info[CHUNK_SALT]),
        nonce=_decode_str(info[CHUNK_NONCE]),
        tag=_decode_str(info[CHUNK_TAG]),
        ciphertext_len=int(info[CHUNK_CLEN]),
    )

    pixels = np.array(img.convert("RGB"))
    img.close()

    return pixels, container