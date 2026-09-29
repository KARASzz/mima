"""像素人物跑步动画窗口（tkinter）。

16×16 像素人物，4 帧原地跑步循环：
- 加密时面向左
- 解密时面向右（左侧帧的水平镜像）

10 FPS 切换。加密/解密完成后窗口自动关闭（spec §17.3）。

无 tkinter 显示环境自动跳过。

macOS 线程兼容性说明：
macOS 上 Tk 在初始化时会创建 NSWindow，而 AppKit 要求 NSWindow 必须在主线程
实例化 —— 在 worker 线程调用 tk.Tk() 会触发 NSInternalInconsistencyException
导致进程崩溃。

解决方案：GUI 必须在主线程运行，加密逻辑放到工作线程（spec §17）。
- 跨平台推荐做法：调用方在主线程调用 ``run_blocking()``，加密逻辑放到 worker 线程。
  这是 macOS 上的**必需**模式，也是其他平台的正确模式（事件循环驱动）。
- ``start()`` 仍按 worker 线程模式运行（向后兼容 Linux/Windows），但在 macOS
  上打印 warning 后直接返回（不抛异常），调用方需改用 ``run_blocking()``。
"""
import logging
import sys
import threading
import tkinter as tk

import numpy as np
from PIL import Image, ImageTk

log = logging.getLogger(__name__)


# 配色
BG_COLOR = (26, 26, 26)        # 背景深灰
SKIN_COLOR = (240, 192, 144)   # 头部肤色
BODY_COLOR = (48, 96, 224)     # 身体蓝色
EYE_COLOR = (0, 0, 0)          # 眼睛黑色
SHOE_COLOR = (32, 32, 32)      # 鞋子深灰


def _make_pixel_art(left_leg_forward: bool, right_leg_forward: bool) -> np.ndarray:
    """生成一帧 16×16 像素人物。

    Args:
        left_leg_forward: 左脚在前
        right_leg_forward: 右脚在前（只能有一个为 True）

    Returns:
        shape (16, 16, 3) uint8 RGB 数组
    """
    frame = np.zeros((16, 16, 3), dtype=np.uint8) + np.array(BG_COLOR, dtype=np.uint8)

    # 头部 (rows 1-4, cols 5-10)
    frame[1:5, 5:11] = SKIN_COLOR
    # 眼睛 (rows 2-3)
    frame[2:4, 6:8] = EYE_COLOR  # 左眼
    frame[2:4, 9:11] = EYE_COLOR  # 右眼

    # 身体 (rows 5-9, cols 5-10)
    frame[5:10, 5:11] = BODY_COLOR

    # 手臂 (rows 5-6)
    frame[5:7, 4:6] = BODY_COLOR   # 左臂
    frame[5:7, 10:12] = BODY_COLOR  # 右臂

    # 腿 (rows 10-15)
    if left_leg_forward and not right_leg_forward:
        # 左腿在前
        frame[10:13, 4:7] = BODY_COLOR
        frame[13:15, 3:6] = SHOE_COLOR
        # 右腿在后
        frame[10:13, 9:12] = BODY_COLOR
        frame[13:15, 10:13] = SHOE_COLOR
    elif right_leg_forward and not left_leg_forward:
        # 右腿在前
        frame[10:13, 9:12] = BODY_COLOR
        frame[13:15, 10:13] = SHOE_COLOR
        # 左腿在后
        frame[10:13, 4:7] = BODY_COLOR
        frame[13:15, 3:6] = SHOE_COLOR
    else:
        # 中间帧：双脚并拢
        frame[10:15, 5:11] = BODY_COLOR
        frame[14:16, 5:7] = SHOE_COLOR
        frame[14:16, 9:11] = SHOE_COLOR

    return frame


# 4 帧跑步循环：脚前、脚后、脚前（中）、脚后（中）
RUN_FRAMES_LEFT = [
    _make_pixel_art(left_leg_forward=True, right_leg_forward=False),
    _make_pixel_art(left_leg_forward=False, right_leg_forward=True),
    _make_pixel_art(left_leg_forward=True, right_leg_forward=False),
    _make_pixel_art(left_leg_forward=False, right_leg_forward=True),
]

# RIGHT = LEFT 的水平镜像
RUN_FRAMES_RIGHT = [np.fliplr(frame) for frame in RUN_FRAMES_LEFT]


class RunnerWindow:
    """像素人物跑步动画窗口。"""

    def __init__(self, direction: str = "left", scale: int = 16):
        """
        Args:
            direction: "left" 或 "right"
            scale: 像素放大倍数（16×16 → 256×256 默认）
        """
        if direction not in ("left", "right"):
            raise ValueError(f"direction must be 'left' or 'right', got {direction}")
        self.direction = direction
        self.scale = scale
        self._root: tk.Tk | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._frame_idx = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """启动窗口（独立线程，不阻塞主流程）。

        macOS 上打印 warning 后直接返回（NSWindow 必须在主线程实例化，
        调用方需改用 :meth:`run_blocking` 在主线程运行 GUI）。
        其他平台：启动 worker 线程调用 :meth:`run_blocking`（向后兼容）。
        """
        if self._running:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        if sys.platform == "darwin":
            # Tk 在初始化时创建 NSWindow，AppKit 要求主线程；
            # 在 worker 线程调用会触发 NSInternalInconsistencyException。
            # 调用方需改用 run_blocking() 从主线程运行 GUI。
            log.warning(
                "Runner window start() skipped on macOS: NSWindow requires main thread. "
                "Call run_blocking() from the main thread instead."
            )
            return
        self._thread = threading.Thread(target=self.run_blocking, daemon=True)
        self._thread.start()

    def run_blocking(self) -> None:
        """在调用线程上创建 Tk 窗口并运行 mainloop。

        阻塞直到 :meth:`stop` 被调用、窗口被销毁。

        macOS 上**必须**从主线程调用（AppKit 限制，违反会触发
        ``NSInternalInconsistencyException`` 导致进程崩溃）。
        其他平台无线程限制，但仍是事件循环驱动的正确模式。
        """
        try:
            self._root = tk.Tk()
            title = "🔒 加密中" if self.direction == "left" else "🔓 解密中"
            self._root.title(title)
            self._root.resizable(False, False)

            bg_hex = f"#{BG_COLOR[0]:02x}{BG_COLOR[1]:02x}{BG_COLOR[2]:02x}"
            self._root.configure(bg=bg_hex)

            self._label = tk.Label(self._root, bg=bg_hex, bd=0)
            self._label.pack(padx=20, pady=20)

            self._frames = RUN_FRAMES_LEFT if self.direction == "left" else RUN_FRAMES_RIGHT
            self._running = True
            self._animate()
            self._root.mainloop()  # blocks until stop() schedules destroy
        except Exception as e:
            log.warning(f"Runner window error: {e}")
        finally:
            self._running = False

    def _animate(self) -> None:
        if not self._running or self._root is None:
            return
        try:
            frame = self._frames[self._frame_idx]
            target_size = 16 * self.scale
            img = Image.fromarray(frame).resize((target_size, target_size), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            self._label.configure(image=photo)
            self._label.image = photo  # 防止 GC
            self._frame_idx = (self._frame_idx + 1) % len(self._frames)
            self._root.after(100, self._animate)  # 10 FPS
        except Exception:
            pass

    def stop(self) -> None:
        """关闭窗口。"""
        self._running = False
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)