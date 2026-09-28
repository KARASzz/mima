"""End-to-end integration tests.

使用预存轨迹 + --no-runner + --no-gpu 完成完整的
encrypt -> decrypt -> info CLI 流程。
"""
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
SAMPLE = REPO_ROOT / "examples" / "sample.txt"
CIRCLE = REPO_ROOT / "examples" / "circle.traj"


def test_cli_encrypt_with_preloaded_trajectory():
    """使用预存轨迹 + --no-runner + --no-gpu 完成端到端流程。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_png = os.path.join(tmpdir, "encrypted.png")
        decrypted = os.path.join(tmpdir, "decrypted.txt")

        # 加密
        result = subprocess.run(
            [sys.executable, "crypto_canvas.py", "encrypt",
             str(SAMPLE), "-o", output_png,
             "--trajectory", str(CIRCLE),
             "--no-runner", "--no-gpu"],
            capture_output=True, text=True, timeout=60,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"encrypt failed: {result.stderr}"
        assert os.path.exists(output_png)
        assert os.path.getsize(output_png) > 0

        # 解密
        result = subprocess.run(
            [sys.executable, "crypto_canvas.py", "decrypt",
             output_png, "-o", decrypted,
             "--no-runner", "--no-gpu"],
            capture_output=True, text=True, timeout=60,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, f"decrypt failed: {result.stderr}"
        assert os.path.exists(decrypted)

        # SHA-256 比对
        original_hash = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
        decrypted_hash = hashlib.sha256(Path(decrypted).read_bytes()).hexdigest()
        assert original_hash == decrypted_hash


def test_cli_info_shows_metadata():
    """info 命令应显示 PNG 元数据。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_png = os.path.join(tmpdir, "info_test.png")

        subprocess.run(
            [sys.executable, "crypto_canvas.py", "encrypt",
             str(SAMPLE), "-o", output_png,
             "--trajectory", str(CIRCLE),
             "--no-runner", "--no-gpu"],
            capture_output=True, text=True, timeout=60,
            cwd=str(REPO_ROOT),
            check=True,
        )

        result = subprocess.run(
            [sys.executable, "crypto_canvas.py", "info", output_png],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "AES-256-GCM-v1" in result.stdout
        assert "Trajectory points" in result.stdout


def test_cli_encrypt_rejects_oversized_file():
    """超过 10 MB 的文件应被拒绝。"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(b"x" * (11 * 1024 * 1024))
        oversized = f.name

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_png = os.path.join(tmpdir, "should_not_exist.png")
            result = subprocess.run(
                [sys.executable, "crypto_canvas.py", "encrypt",
                 oversized, "-o", output_png,
                 "--trajectory", str(CIRCLE),
                 "--no-runner", "--no-gpu"],
                capture_output=True, text=True, timeout=10,
                cwd=str(REPO_ROOT),
            )
            assert result.returncode != 0  # 应该失败
            assert not os.path.exists(output_png)
    finally:
        os.unlink(oversized)