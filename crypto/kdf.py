"""Argon2id 密钥派生。

演示模式参数：t=5, m=64MB, p=8（拉满 CPU/内存，制造视觉算力感）。
生产环境建议改为 t=1, p=4（spec §7.3, §17.6）。
"""
from argon2.low_level import hash_secret_raw, Type


# 演示模式参数（拉满 CPU + 内存）
TIME_COST = 5
MEMORY_COST = 64 * 1024  # 64 MiB (KiB 单位)
PARALLELISM = 8
HASH_LEN = 32  # AES-256 密钥长度


def derive_key(trajectory_fingerprint: bytes, salt: bytes) -> bytes:
    """从轨迹指纹派生 AES-256 密钥。

    Args:
        trajectory_fingerprint: 32 字节轨迹 SHA-256 指纹
        salt: 16 字节随机盐

    Returns:
        32 字节 AES-256 密钥
    """
    return hash_secret_raw(
        secret=trajectory_fingerprint,
        salt=salt,
        time_cost=TIME_COST,
        memory_cost=MEMORY_COST,
        parallelism=PARALLELISM,
        hash_len=HASH_LEN,
        type=Type.ID,
    )