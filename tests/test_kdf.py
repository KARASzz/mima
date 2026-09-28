# tests/test_kdf.py
import os
import time
from crypto.kdf import derive_key


def test_derive_key_returns_32_bytes():
    fp = b"x" * 32
    salt = os.urandom(16)
    key = derive_key(fp, salt)
    assert len(key) == 32


def test_same_inputs_produce_same_key():
    fp = b"deterministic fingerprint" * 2  # 32 bytes
    salt = b"\x00" * 16
    k1 = derive_key(fp, salt)
    k2 = derive_key(fp, salt)
    assert k1 == k2


def test_different_salts_produce_different_keys():
    fp = b"fingerprint" * 3 + b"!"  # 32 bytes
    salt1 = b"\x00" * 16
    salt2 = b"\x01" + b"\x00" * 15
    k1 = derive_key(fp, salt1)
    k2 = derive_key(fp, salt2)
    assert k1 != k2


def test_different_fingerprints_produce_different_keys():
    salt = b"\x00" * 16
    k1 = derive_key(b"a" * 32, salt)
    k2 = derive_key(b"b" * 32, salt)
    assert k1 != k2


def test_demo_mode_is_intentionally_slow():
    """演示模式 t=5 应至少消耗 1 秒（验证拉满参数生效）。"""
    fp = b"benchmark fingerprint" + b"\x00" * 13
    salt = os.urandom(16)
    start = time.time()
    derive_key(fp, salt)
    elapsed = time.time() - start
    assert elapsed >= 1.0, f"KDF too fast ({elapsed:.2f}s), demo params not active"