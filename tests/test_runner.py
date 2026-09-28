"""Tests for the tkinter pixel-character runner animation window."""
import time

import numpy as np

from crypto.runner import (
    RUN_FRAMES_LEFT,
    RUN_FRAMES_RIGHT,
    RunnerWindow,
)


def test_left_frames_shape():
    """LEFT 帧形状应为 (4, 16, 16, 3) uint8。"""
    assert len(RUN_FRAMES_LEFT) == 4
    for frame in RUN_FRAMES_LEFT:
        assert frame.shape == (16, 16, 3)
        assert frame.dtype == np.uint8


def test_right_frames_are_left_mirrored():
    """RIGHT 帧应为 LEFT 帧的水平镜像。"""
    assert len(RUN_FRAMES_RIGHT) == len(RUN_FRAMES_LEFT)
    for fl, fr in zip(RUN_FRAMES_LEFT, RUN_FRAMES_RIGHT):
        assert np.array_equal(fr, np.fliplr(fl))


def test_frames_have_visible_character():
    """帧中应包含非背景色像素（即有人物）。"""
    # 至少 5% 像素不是背景色
    for frame in RUN_FRAMES_LEFT:
        non_bg = np.any(frame != 0, axis=2)
        assert non_bg.sum() > 16 * 16 * 0.05


def test_runner_start_stop_no_crash():
    """启动-停止应幂等（headless 环境可能跳过窗口，但不应崩）。"""
    win = RunnerWindow(direction="left")
    win.start()
    time.sleep(0.1)
    win.stop()


def test_runner_stop_idempotent():
    """多次 stop 应安全。"""
    win = RunnerWindow(direction="right")
    win.start()
    win.stop()
    win.stop()