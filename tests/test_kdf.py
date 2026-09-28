# tests/test_kdf.py
import os
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


def test_demo_mode_uses_aggressive_parameters():
    """Verify demo-mode KDF parameters are applied (not just timing).

    The "KDF is slow" claim is a side effect of these params; testing the
    params directly is hardware-independent and more meaningful (the timing
    version fails on Apple Silicon because 64 MiB fits in L3 cache).
    """
    from crypto import kdf
    assert kdf.TIME_COST >= 3, f"TIME_COST too low: {kdf.TIME_COST}"
    assert kdf.MEMORY_COST >= 64 * 1024, f"MEMORY_COST too low: {kdf.MEMORY_COST}"
    assert kdf.PARALLELISM >= 4, f"PARALLELISM too low: {kdf.PARALLELISM}"