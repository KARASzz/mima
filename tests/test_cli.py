"""CLI 入口测试。"""
import subprocess
import sys


def test_cli_help_shows_subcommands():
    """--help 应列出所有子命令。"""
    result = subprocess.run(
        [sys.executable, "crypto_canvas.py", "--help"],
        capture_output=True, text=True, timeout=10,
        cwd="/Volumes/Sea of Symbols/+Python mac/mima",
    )
    assert result.returncode == 0
    assert "encrypt" in result.stdout
    assert "decrypt" in result.stdout
    assert "info" in result.stdout