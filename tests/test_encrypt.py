"""crypto.encrypt / crypto.decrypt orchestration tests.

End-to-end round-trip: encrypt a file to PNG, decrypt the PNG back,
and verify the recovered bytes match the original (SHA-256 compare).
"""
import hashlib
import os
import tempfile

import pytest

from crypto.encrypt import FileTooLarge, encrypt_file
from crypto.decrypt import decrypt_file


def test_encrypt_decrypt_round_trip():
    """加密 → 解密 → SHA-256 比对。"""
    original_data = b"hello crypto canvas! " * 100

    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        input_path = f.name
        f.write(original_data)

    output_png = input_path + ".png"
    output_dec = input_path + ".dec"

    trajectory = [(i * 0.1, i * 0.05) for i in range(30)]

    try:
        encrypt_file(input_path, output_png, trajectory, use_gpu=False, use_runner=False)
        assert os.path.exists(output_png)
        assert os.path.getsize(output_png) > 0

        decrypt_file(output_png, output_dec, use_gpu=False, use_runner=False)

        with open(output_dec, "rb") as f:
            decrypted = f.read()

        assert hashlib.sha256(decrypted).hexdigest() == hashlib.sha256(original_data).hexdigest()
    finally:
        for p in [input_path, output_png, output_dec]:
            if os.path.exists(p):
                os.unlink(p)


def test_encrypt_file_too_large_raises():
    """超过 10 MB 的文件应拒绝。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        input_path = f.name
        f.write(b"x" * (11 * 1024 * 1024))

    try:
        trajectory = [(i * 0.1, i * 0.05) for i in range(30)]
        with pytest.raises(FileTooLarge):
            encrypt_file(input_path, "/tmp/should_not_exist.png", trajectory,
                         use_gpu=False, use_runner=False)
    finally:
        if os.path.exists(input_path):
            os.unlink(input_path)


def test_encrypt_decrypt_various_sizes():
    """不同大小的文件都能正确往返。"""
    for size in [1, 100, 1024, 1024 * 100]:  # 1B, 100B, 1KB, 100KB
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            input_path = f.name
            f.write(os.urandom(size))
        png_path = input_path + ".png"
        dec_path = input_path + ".dec"
        try:
            trajectory = [(i * 0.07, i * 0.13) for i in range(40)]
            encrypt_file(input_path, png_path, trajectory, use_gpu=False, use_runner=False)
            decrypt_file(png_path, dec_path, use_gpu=False, use_runner=False)
            with open(input_path, "rb") as f1, open(dec_path, "rb") as f2:
                assert f1.read() == f2.read(), f"size {size} roundtrip failed"
        finally:
            for p in [input_path, png_path, dec_path]:
                if os.path.exists(p):
                    os.unlink(p)
