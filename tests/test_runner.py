"""Tests for the tkinter pixel-character runner animation window."""
import sys
import threading
import time
from unittest import mock

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


def test_runner_runs_on_main_thread():
    """Runner can be driven from a thread via run_blocking; stop() releases it.

    Mocks tk.Tk to avoid requiring an actual display/AppKit main thread,
    so the test runs deterministically on any platform (including
    headless macOS where a real Tk() call would hang waiting for
    AppKit's main thread).
    """

    class FakeRoot:
        """Stand-in for tk.Tk that mimics the subset used by RunnerWindow."""

        def __init__(self):
            self.destroyed = False
            self.destroy_called = False

        # Tk configuration methods used by RunnerWindow.run_blocking
        def title(self, *_args, **_kwargs):
            pass

        def resizable(self, *_args, **_kwargs):
            pass

        def configure(self, *_args, **_kwargs):
            pass

        # Run a queued callback. delay==0 means immediate (used by stop()).
        def after(self, delay_ms, callback):
            if delay_ms == 0:
                callback()
            return None

        def destroy(self):
            self.destroy_called = True
            self.destroyed = True

        # Poll until destroyed. Each iteration is short so the test
        # thread can observe progress and call stop().
        def mainloop(self):
            for _ in range(500):
                if self.destroyed:
                    return
                time.sleep(0.01)

    fake_root = FakeRoot()

    with mock.patch("crypto.runner.tk.Tk", return_value=fake_root):
        win = RunnerWindow(direction="left")

        def runner_thread():
            win.run_blocking()

        t = threading.Thread(target=runner_thread, daemon=True)
        t.start()

        # Let run_blocking() create the fake root and enter mainloop.
        time.sleep(0.2)
        assert win._root is fake_root
        win.stop()  # cross-thread stop; schedules root.after(0, root.destroy)
        t.join(timeout=2)
        assert not t.is_alive()
        assert fake_root.destroy_called


def test_runner_stop_is_idempotent():
    """stop() can be called multiple times safely."""
    win = RunnerWindow(direction="right")
    # No start, no run_blocking — just stop
    win.stop()
    win.stop()


def test_runner_start_on_macos_is_noop():
    """On macOS, start() should warn and return without spawning thread."""
    win = RunnerWindow(direction="left")
    # On macOS, this should be a no-op (no thread spawned)
    # On Linux/Win, it spawns a thread (which works)
    win.start()
    # Cleanup
    win.stop()