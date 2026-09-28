"""AES-256-GCM 单块 + 并行接口测试。"""
import os

import pytest
from cryptography.exceptions import InvalidTag

from crypto.cipher import (
    DEFAULT_WORKERS,
    NONCE_LEN,
    TAG_LEN,
    decrypt_chunk,
    encrypt_chunk,
    parallel_decrypt,
    parallel_encrypt,
)


def test_constants():
    """Spec §7.2: nonce 12 字节，tag 16 字节，workers 8。"""
    assert NONCE_LEN == 12
    assert TAG_LEN == 16
    assert DEFAULT_WORKERS == 8


def test_encrypt_decrypt_round_trip():
    key = os.urandom(32)
    nonce = os.urandom(12)
    plaintext = b"hello world" * 100
    ct = encrypt_chunk(key, nonce, plaintext)
    pt = decrypt_chunk(key, nonce, ct)
    assert pt == plaintext


def test_encrypt_output_includes_tag():
    """密文末尾应包含 16 字节 GCM tag。"""
    key = os.urandom(32)
    nonce = os.urandom(12)
    plaintext = b"x" * 100
    ct = encrypt_chunk(key, nonce, plaintext)
    assert len(ct) == len(plaintext) + TAG_LEN


def test_tampered_ciphertext_raises():
    key = os.urandom(32)
    nonce = os.urandom(12)
    plaintext = b"secret message"
    ct = bytearray(encrypt_chunk(key, nonce, plaintext))
    ct[5] ^= 0xFF  # 翻转一个比特
    with pytest.raises(InvalidTag):
        decrypt_chunk(key, nonce, bytes(ct))


def test_tampered_tag_raises():
    key = os.urandom(32)
    nonce = os.urandom(12)
    plaintext = b"secret message"
    ct = bytearray(encrypt_chunk(key, nonce, plaintext))
    ct[-1] ^= 0xFF  # 翻转 tag 最后一字节
    with pytest.raises(InvalidTag):
        decrypt_chunk(key, nonce, bytes(ct))


def test_wrong_key_raises():
    key1 = os.urandom(32)
    key2 = os.urandom(32)
    nonce = os.urandom(12)
    ct = encrypt_chunk(key1, nonce, b"hello")
    with pytest.raises(InvalidTag):
        decrypt_chunk(key2, nonce, ct)


def test_wrong_nonce_raises():
    key = os.urandom(32)
    n1 = os.urandom(12)
    n2 = os.urandom(12)
    ct = encrypt_chunk(key, n1, b"hello")
    with pytest.raises(InvalidTag):
        decrypt_chunk(key, n2, ct)


def test_empty_plaintext():
    key = os.urandom(32)
    nonce = os.urandom(12)
    ct = encrypt_chunk(key, nonce, b"")
    assert decrypt_chunk(key, nonce, ct) == b""


def test_aad_is_authenticated():
    """AAD 不加密但参与认证，篡改应被检测。"""
    key = os.urandom(32)
    nonce = os.urandom(12)
    ct = encrypt_chunk(key, nonce, b"payload", aad=b"metadata-v1")
    # 正确 AAD 解密成功
    assert decrypt_chunk(key, nonce, ct, aad=b"metadata-v1") == b"payload"
    # 错误 AAD 失败
    with pytest.raises(InvalidTag):
        decrypt_chunk(key, nonce, ct, aad=b"metadata-v2")


# ---------------- parallel 接口测试 ----------------


def test_parallel_encrypt_decrypt_with_uneven_chunks():
    """parallel_encrypt/decrypt must handle plaintext length not divisible by workers."""
    key = os.urandom(32)
    # 150 bytes / 8 workers => chunk_size=19, last chunk=17 (not divisible)
    original = bytes(range(100)) + b"x" * 50  # 150 bytes
    ct = parallel_encrypt(key, original, workers=8)
    pt = parallel_decrypt(key, ct, workers=8)
    assert pt == original, f"round-trip failed: {len(pt)} vs {len(original)}"


def test_parallel_full_round_trip():
    """Large plaintext round-trip via parallel interface."""
    key = os.urandom(32)
    original = os.urandom(100_000)  # 100 KB
    ct = parallel_encrypt(key, original, workers=8)
    pt = parallel_decrypt(key, ct, workers=8)
    assert pt == original


def test_parallel_empty_plaintext():
    """空明文应该正常 round-trip。"""
    key = os.urandom(32)
    ct = parallel_encrypt(key, b"", workers=8)
    pt = parallel_decrypt(key, ct, workers=8)
    assert pt == b""


def test_parallel_alignment_various_sizes():
    """对多种长度（小于/等于/大于 workers，以及非整除）做 round-trip。"""
    key = os.urandom(32)
    for size in [1, 7, 8, 9, 17, 100, 1_000, 65_537]:
        original = os.urandom(size)
        ct = parallel_encrypt(key, original, workers=8)
        pt = parallel_decrypt(key, ct, workers=8)
        assert pt == original, f"size={size} round-trip failed"