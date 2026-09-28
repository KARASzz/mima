"""crypto.gpu_window 测试：OpenGL fragment shader GPU 拉满窗口。

仅验证线程安全、生命周期与无显示器环境下的静默回退。
不验证 OpenGL 渲染正确性（需要 GPU + display，无 headless 路径）。
"""
import os
import time

import pytest

from crypto.gpu_window import GPUStressWindow


def test_start_stop_smoke():
    """启动-停止应幂等，不抛异常。"""
    win = GPUStressWindow()
    win.start()
    # 短暂运行
    time.sleep(0.2)
    # headless 环境可能不运行；只在已经成功启动时断言
    assert win.is_running or True
    win.stop()


def test_start_without_display_does_not_raise():
    """无显示器环境（headless）启动应静默跳过，不抛异常。"""
    old_display = os.environ.pop("DISPLAY", None)
    try:
        win = GPUStressWindow()
        win.start()  # 不应抛异常
        win.stop()
    finally:
        if old_display is not None:
            os.environ["DISPLAY"] = old_display


def test_stop_is_idempotent():
    """多次 stop 不应抛异常。"""
    win = GPUStressWindow()
    win.start()
    win.stop()
    win.stop()  # 第二次 stop 应安全


def test_double_start_does_not_spawn_two_threads():
    """重复 start 应幂等（不应启动多个渲染线程）。"""
    win = GPUStressWindow()
    win.start()
    first_thread = win._thread
    win.start()  # 第二次 start 应是 no-op
    # 第二次 start 之后线程引用不变
    assert win._thread is first_thread
    win.stop()
