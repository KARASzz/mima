#!/usr/bin/env python3
"""Crypto Canvas CLI 入口。

命令：
  encrypt <file>        加密文件（弹出画布画轨迹）
  decrypt <file.png>    解密 PNG 还原文件
  info <file.png>       显示 PNG 元数据
  selftest              运行自检
"""
import argparse
import sys
from pathlib import Path


def encrypt_cmd(args):
    """加密命令。"""
    from crypto.trajectory_gui import collect_trajectory
    from crypto.encrypt import encrypt_file

    trajectory = collect_trajectory()
    output_path = args.output or (args.file + ".png")
    stats = encrypt_file(
        args.file,
        output_path,
        trajectory,
        use_gpu=not args.no_gpu,
        use_runner=not args.no_runner,
    )
    print(f"✓ Encrypted: {args.file} -> {output_path}")
    print(f"  Size: {stats['input_size']} -> {stats['output_size']} bytes")
    print(f"  Time: {stats['elapsed_seconds']:.1f}s")


def decrypt_cmd(args):
    """解密命令。"""
    from crypto.decrypt import decrypt_file

    output_path = args.output or _default_decrypted_name(args.file)
    stats = decrypt_file(
        args.file,
        output_path,
        use_gpu=not args.no_gpu,
        use_runner=not args.no_runner,
    )
    print(f"✓ Decrypted: {args.file} -> {output_path}")
    print(f"  Size: {stats['input_size']} -> {stats['output_size']} bytes")


def info_cmd(args):
    """显示 PNG 元数据。"""
    from crypto.container import read_encrypted_png
    pixels, container = read_encrypted_png(args.file)
    print(f"Algorithm: {container.algo}")
    print(f"Image size: {pixels.shape[1]}x{pixels.shape[0]}")
    print(f"Trajectory points: {len(container.trajectory)}")
    print(f"Trajectory hash: {container.trajectory_hash[:16]}...")
    print(f"Salt: {container.salt.hex()[:16]}...")
    print(f"Nonce: {container.nonce.hex()[:16]}...")
    print(f"Tag: {container.tag.hex()[:16]}...")


def selftest_cmd(args):
    """自检：测试所有模块。"""
    import subprocess
    result = subprocess.run(
        ["pytest", "tests/", "-v", "--tb=short"],
        cwd=Path(__file__).parent,
    )
    sys.exit(result.returncode)


def _default_decrypted_name(png_path: str) -> str:
    """从 .png 路径推导解密文件名。"""
    p = Path(png_path)
    name = p.stem
    if name.endswith(".enc"):
        name = name[:-4]
    return str(p.parent / f"{name}_decrypted")


def main():
    parser = argparse.ArgumentParser(
        prog="crypto_canvas",
        description="Visualizable file encryption (trajectory -> AES-256-GCM -> PNG)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # encrypt
    p_enc = subparsers.add_parser("encrypt", help="Encrypt a file to PNG")
    p_enc.add_argument("file", help="Input file (<=10MB)")
    p_enc.add_argument("-o", "--output", help="Output PNG path")
    p_enc.add_argument("--no-gpu", action="store_true", help="Skip GPU stress window")
    p_enc.add_argument("--no-runner", action="store_true", help="Skip pixel character window")
    p_enc.add_argument("--trajectory", help="Pre-saved trajectory JSON (skip GUI)")
    p_enc.set_defaults(func=encrypt_cmd)

    # decrypt
    p_dec = subparsers.add_parser("decrypt", help="Decrypt a PNG back to file")
    p_dec.add_argument("file", help="Input PNG file")
    p_dec.add_argument("-o", "--output", help="Output file path")
    p_dec.add_argument("--no-gpu", action="store_true", help="Skip GPU stress window")
    p_dec.add_argument("--no-runner", action="store_true", help="Skip pixel character window")
    p_dec.set_defaults(func=decrypt_cmd)

    # info
    p_info = subparsers.add_parser("info", help="Show PNG metadata")
    p_info.add_argument("file", help="Input PNG file")
    p_info.set_defaults(func=info_cmd)

    # selftest
    p_test = subparsers.add_parser("selftest", help="Run all tests")
    p_test.set_defaults(func=selftest_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()