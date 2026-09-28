"""轨迹采集与视觉置换算法。

复平面上鼠标轨迹 → 256 项置换表（基于距离+角度的几何指纹）。
用于加密前的视觉密码层（spec §7.1）。
"""
import hashlib
import math
from typing import Sequence


def trajectory_to_permutation(trajectory: Sequence[tuple[float, float]]) -> list[int]:
    """从轨迹几何派生 256 项置换表。

    算法：
    1. 计算轨迹质心
    2. 对每个 hex 字节 (h, l) ∈ [0,15]² 映射到复平面 z
    3. 计算 z 到轨迹的最近点距离 d 和相对质心的极角 θ
    4. 按 (d, θ) 稳定排序 → 索引序列即置换表

    Args:
        trajectory: 复平面上的点序列，至少 10 个点

    Returns:
        长度为 256 的置换表，元素为 0-255 的不重复整数
    """
    if len(trajectory) < 10:
        raise ValueError(f"轨迹点过少（{len(trajectory)} < 10），强度不足")

    # 1. 质心
    cx = sum(p[0] for p in trajectory) / len(trajectory)
    cy = sum(p[1] for p in trajectory) / len(trajectory)
    centroid = complex(cx, cy)
    traj_complex = [complex(p[0], p[1]) for p in trajectory]

    # 2. 256 个 hex 字节映射到复平面，按 (距离, 角度) 评分
    byte_scores: list[tuple[tuple[float, float], int]] = []
    for h in range(16):
        for l in range(16):
            z = complex((h - 7.5) / 7.5, (l - 7.5) / 7.5)
            d = min(abs(z - t) for t in traj_complex)
            theta = math.atan2(z.imag - centroid.imag, z.real - centroid.real)
            byte_scores.append(((d, theta), h * 16 + l))

    # 3. 稳定排序
    byte_scores.sort(key=lambda x: x[0])
    return [b for _, b in byte_scores]


def invert_permutation(perm: list[int]) -> list[int]:
    """计算置换表的逆映射。

    Args:
        perm: 正向置换表，perm[i] = j 表示字节 i 映射到 j

    Returns:
        逆置换表，inv[j] = i
    """
    inv = [0] * len(perm)
    for i, j in enumerate(perm):
        inv[j] = i
    return inv


def trajectory_fingerprint(trajectory: Sequence[tuple[float, float]]) -> bytes:
    """轨迹几何指纹 → 32 字节 SHA-256。

    包含：质心 (cx, cy)、总弧长、点数。足够区分几何不同的轨迹。
    """
    cx = sum(p[0] for p in trajectory) / len(trajectory)
    cy = sum(p[1] for p in trajectory) / len(trajectory)
    arc = sum(
        math.hypot(trajectory[i + 1][0] - trajectory[i][0],
                   trajectory[i + 1][1] - trajectory[i][1])
        for i in range(len(trajectory) - 1)
    )
    raw = f"{cx:.6f},{cy:.6f},{arc:.6f},{len(trajectory)}".encode("utf-8")
    return hashlib.sha256(raw).digest()


def apply_permutation(data: bytes, perm: list[int]) -> bytes:
    """对字节流应用正向置换。"""
    return bytes(perm[b] for b in data)


def apply_inverse_permutation(data: bytes, inv_perm: list[int]) -> bytes:
    """对字节流应用反向置换。"""
    return bytes(inv_perm[b] for b in data)