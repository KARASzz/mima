import math
import pytest
from crypto.trajectory import (
    trajectory_to_permutation,
    invert_permutation,
    trajectory_fingerprint,
    apply_permutation,
    apply_inverse_permutation,
)


def test_permutation_is_full_range():
    """置换表必须是 0-255 的完整排列。"""
    trajectory = [(0.0, 0.0), (1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0)] * 2
    perm = trajectory_to_permutation(trajectory)
    assert sorted(perm) == list(range(256))


def test_permutation_is_deterministic():
    """同轨迹两次计算必须得到完全相同的置换表。"""
    trajectory = [(i * 0.1, i * 0.2) for i in range(50)]
    p1 = trajectory_to_permutation(trajectory)
    p2 = trajectory_to_permutation(trajectory)
    assert p1 == p2


def test_permutation_differs_for_different_trajectories():
    """不同轨迹应产生不同的置换表（大多数情况）。"""
    circle = [(math.cos(i * 0.1), math.sin(i * 0.1)) for i in range(60)]
    line = [(i * 0.05, 0.0) for i in range(60)]
    p_circle = trajectory_to_permutation(circle)
    p_line = trajectory_to_permutation(line)
    assert p_circle != p_line


def test_too_few_points_raises():
    """轨迹 < 10 点必须抛 ValueError。"""
    with pytest.raises(ValueError, match="轨迹点过少"):
        trajectory_to_permutation([(0.0, 0.0)] * 9)


def test_invert_permutation_round_trip():
    """P^-1(P(b)) == b 对所有 b 成立。"""
    perm = trajectory_to_permutation([(i * 0.1, i * 0.05) for i in range(30)])
    inv = invert_permutation(perm)
    for b in range(256):
        assert perm[inv[b]] == b
        assert inv[perm[b]] == b


def test_apply_permutation_round_trip():
    """置换 + 反置换应还原原始字节。"""
    perm = trajectory_to_permutation([(i * 0.07, i * 0.13) for i in range(40)])
    inv = invert_permutation(perm)
    original = bytes(range(256))
    permuted = apply_permutation(original, perm)
    assert permuted != original  # 确实被置换
    assert apply_inverse_permutation(permuted, inv) == original


def test_fingerprint_is_32_bytes():
    """轨迹指纹必须是 32 字节（SHA-256）。"""
    trajectory = [(i * 0.1, i * 0.2) for i in range(20)]
    fp = trajectory_fingerprint(trajectory)
    assert len(fp) == 32


def test_fingerprint_is_deterministic():
    """同轨迹 → 同指纹。"""
    trajectory = [(i * 0.1, i * 0.2) for i in range(20)]
    assert trajectory_fingerprint(trajectory) == trajectory_fingerprint(trajectory)


def test_fingerprint_differs_for_different_trajectories():
    """不同轨迹 → 不同指纹。"""
    t1 = [(0.1 * i, 0.2 * i) for i in range(20)]
    t2 = [(0.1 * i, 0.3 * i) for i in range(20)]
    assert trajectory_fingerprint(t1) != trajectory_fingerprint(t2)