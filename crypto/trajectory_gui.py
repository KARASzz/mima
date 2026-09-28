"""matplotlib 复平面轨迹采集 GUI。

弹出窗口，用户用鼠标画轨迹，按 Enter 完成采集。
叠加 16×16 hex 网格作为辅助参考（spec §5.3）。
"""
import matplotlib

# Linux/Windows 默认 TkAgg；macOS 优先尝试更原生的 MacOSX；
# 都失败则退回到环境默认后端（无显示环境也能 import）。
try:
    matplotlib.use("TkAgg")
except Exception:
    try:
        matplotlib.use("MacOSX")
    except Exception:
        pass  # 使用默认后端

import matplotlib.pyplot as plt


def collect_trajectory() -> "list[tuple[float, float]]":
    """弹出交互窗口采集用户轨迹。

    流程：
    1. 创建 1.2×1.2 的复平面窗口，叠加 16×16 hex 网格作为视觉参考
    2. 调用 plt.ginput(n=-1, timeout=0) 阻塞采集用户点击
       - 按 Enter 完成采集
       - 关闭窗口等同于取消

    Returns:
        复平面上的点序列（list of (x, y) tuple），至少 10 个点

    Raises:
        RuntimeError: 轨迹点过少（< 10）——密码学强度不足
    """
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-1.2, 1.2)
    ax.set_aspect("equal")
    ax.set_title("Draw your trajectory, then press Enter", fontsize=14)
    ax.set_xlabel("Re")
    ax.set_ylabel("Im")
    ax.grid(True, alpha=0.3)

    # 叠加 16×16 hex 网格（半透明视觉参考）
    for i in range(-8, 9):
        ax.axvline(x=i / 8, color="gray", alpha=0.15, linewidth=0.5)
        ax.axhline(y=i / 8, color="gray", alpha=0.15, linewidth=0.5)

    plt.show()  # 显示窗口（测试时可被 mock 为 no-op）
    # ginput 阻塞采集：n=-1 表示无限点，timeout=0 表示无超时
    # 用户按 Enter 结束，或关闭窗口取消
    points = plt.ginput(n=-1, timeout=0)

    try:
        plt.close(fig)
    except Exception:
        pass  # 后端不支持时静默忽略

    if len(points) < 10:
        raise RuntimeError(
            f"轨迹点过少（{len(points)} < 10）。请至少画 10 个点。"
        )

    # 确保返回标准 float tuple
    return [(float(p[0]), float(p[1])) for p in points]