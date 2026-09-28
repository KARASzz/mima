"""AES-256-GCM 单块加密 + 多块并行加密。

单块接口（encrypt_chunk / decrypt_chunk）用于简单场景或测试。
并行接口（parallel_encrypt / parallel_decrypt）把数据切成 N 块，
每块独立 nonce + tag，multiprocessing.Pool 并行（spec §17.1）。

parallel_* 输出格式：
    [8 字节明文长度大端]  +  (nonce + ct + tag) × chunks
解密时按相同 workers 数还原。
"""
import os
from multiprocessing import Pool
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_LEN = 12
TAG_LEN = 16
DEFAULT_WORKERS = 8
# 8 字节明文长度前缀：足以表示 2^64 字节，足以覆盖一切实际文件。
_LEN_HEADER = 8


def encrypt_chunk(
    key: bytes,
    nonce: bytes,
    plaintext: bytes,
    aad: Optional[bytes] = None,
) -> bytes:
    """加密单块明文，返回 ciphertext + tag。

    Args:
        key: 32 字节 AES-256 密钥
        nonce: 12 字节 GCM nonce（每块必须独立随机）
        plaintext: 任意长度明文
        aad: 附加认证数据（不加密但参与认证）

    Returns:
        密文 + 16 字节 GCM tag
    """
    return AESGCM(key).encrypt(nonce, plaintext, aad)


def decrypt_chunk(
    key: bytes,
    nonce: bytes,
    ciphertext: bytes,
    aad: Optional[bytes] = None,
) -> bytes:
    """解密单块密文，校验 tag。

    Raises:
        InvalidTag: 认证失败（密钥错、AAD 错、数据被篡改）
    """
    return AESGCM(key).decrypt(nonce, ciphertext, aad)


def _encrypt_worker(args: tuple[bytes, bytes, bytes]) -> bytes:
    """multiprocessing worker：加密单块，返回 nonce + ciphertext+tag。"""
    key, nonce, chunk = args
    ct = AESGCM(key).encrypt(nonce, chunk, None)
    return nonce + ct


def _decrypt_worker(args: tuple[bytes, bytes]) -> bytes:
    """multiprocessing worker：解密单块，验证 tag。

    期望 packed = nonce (12B) + ct + tag (16B)。
    """
    key, packed = args
    nonce = packed[:NONCE_LEN]
    ct = packed[NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, None)


def _plan_chunks(plaintext_len: int, workers: int) -> tuple[int, int, list[int]]:
    """计算切块计划。

    返回 (chunk_size, num_chunks, plaintext_sizes_per_chunk)。
    plaintext_sizes_per_chunk 长度 = num_chunks，最后一项可能更小。
    """
    chunk_size = max(1, (plaintext_len + workers - 1) // workers)
    if plaintext_len == 0:
        return chunk_size, 0, []
    num_chunks = (plaintext_len + chunk_size - 1) // chunk_size
    sizes = []
    for i in range(num_chunks):
        if i < num_chunks - 1:
            sizes.append(chunk_size)
        else:
            sizes.append(plaintext_len - i * chunk_size)
    return chunk_size, num_chunks, sizes


def parallel_encrypt(key: bytes, plaintext: bytes, workers: int = DEFAULT_WORKERS) -> bytes:
    """并行加密大数据，自动切块。

    输出格式：[8 字节明文长度大端] + (nonce + ct + tag) × chunks

    头部编码明文长度，以便解密侧正确还原切块边界（当
    len(plaintext) % workers != 0 时，最后一块大小与前面不同）。

    Args:
        key: 32 字节 AES-256 密钥
        plaintext: 任意长度明文
        workers: 并行进程数

    Returns:
        拼接后的密文（明文长度头 + 每块 nonce+ct+tag）
    """
    plaintext_len = len(plaintext)
    chunk_size, num_chunks, sizes = _plan_chunks(plaintext_len, workers)
    if num_chunks == 0:
        return plaintext_len.to_bytes(_LEN_HEADER, "big")

    chunks = [plaintext[i * chunk_size:i * chunk_size + s] for i, s in enumerate(sizes)]
    nonces = [os.urandom(NONCE_LEN) for _ in chunks]

    with Pool(min(workers, num_chunks)) as pool:
        encrypted = pool.map(_encrypt_worker, [(key, n, c) for n, c in zip(nonces, chunks)])

    return plaintext_len.to_bytes(_LEN_HEADER, "big") + b"".join(encrypted)


def parallel_decrypt(key: bytes, ciphertext: bytes, workers: int = DEFAULT_WORKERS) -> bytes:
    """并行解密大数据。

    从明文长度头还原切块计划，再按计划切分 body 并行解密。
    关键修复：必须用 header 中的长度计算每块大小，而不是用
    ``len(ciphertext) // workers`` 简单均匀分配——后者在
    ``len(plaintext) % workers != 0`` 时会让最后一块的位置错位，
    导致 tag 校验失败。

    Args:
        key: 32 字节 AES-256 密钥
        ciphertext: parallel_encrypt 输出
        workers: 必须与加密时一致

    Returns:
        原始明文
    """
    if len(ciphertext) < _LEN_HEADER:
        raise ValueError("ciphertext too short to contain length header")
    plaintext_len = int.from_bytes(ciphertext[:_LEN_HEADER], "big")
    body = ciphertext[_LEN_HEADER:]

    if plaintext_len == 0:
        if len(body) != 0:
            raise ValueError("empty plaintext but ciphertext body is non-empty")
        return b""

    chunk_size, num_chunks, sizes = _plan_chunks(plaintext_len, workers)
    packed_sizes = [NONCE_LEN + s + TAG_LEN for s in sizes]
    total = sum(packed_sizes)
    if len(body) != total:
        raise ValueError(
            f"ciphertext body length {len(body)} != expected {total} "
            f"(plaintext_len={plaintext_len}, workers={workers})"
        )

    packed_chunks: list[bytes] = []
    offset = 0
    for sz in packed_sizes:
        packed_chunks.append(body[offset:offset + sz])
        offset += sz

    with Pool(min(workers, num_chunks)) as pool:
        decrypted = pool.map(_decrypt_worker, [(key, pc) for pc in packed_chunks])

    return b"".join(decrypted)