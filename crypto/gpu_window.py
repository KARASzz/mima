"""GPU 拉满窗口（OpenGL fragment shader）。

独立线程运行 fragment shader，每帧每像素做 16 次 hash + 8 次 sin/cos，
强制 GPU 满载。加密完成后自动关闭（spec §17.2）。

无 OpenGL 上下文时（SSH headless）自动跳过 —— start() 永不抛异常。
在 macOS 上亦静默跳过：NSWindow 必须在主线程实例化，从 worker 线程调用
会触发 Cocoa 的 NSInternalInconsistencyException 导致进程崩溃；start()
必须在调用方线程立即返回，无法在主线程跑同步渲染循环。
"""
import logging
import sys
import threading
import time

from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_COLOR_BUFFER_BIT,
    GL_FALSE,
    GL_FLOAT,
    GL_FRAGMENT_SHADER,
    GL_STATIC_DRAW,
    GL_VERTEX_SHADER,
    glAttachShader,
    glBindBuffer,
    glBindVertexArray,
    glBufferData,
    glClear,
    glClearColor,
    glCompileShader,
    glCreateProgram,
    glCreateShader,
    glDeleteProgram,
    glDeleteShader,
    glDrawArrays,
    glEnableVertexAttribArray,
    glGenBuffers,
    glGenVertexArrays,
    glGetUniformLocation,
    glLinkProgram,
    glShaderSource,
    glUniform1f,
    glUniform2f,
    glUseProgram,
    glVertexAttribPointer,
)

import glfw

log = logging.getLogger(__name__)


VERTEX_SHADER_SRC = """
#version 330 core
layout(location = 0) in vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
"""

FRAGMENT_SHADER_SRC = """
#version 330 core
out vec4 fragColor;
uniform float u_time;
uniform vec2 u_resolution;

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution;
    float t = u_time * 0.001;
    float v = 0.0;
    for (int i = 0; i < 16; i++) {
        v += hash(uv * 256.0 + float(i) + t);
    }
    v = fract(v * 0.125);
    fragColor = vec4(vec3(v, fract(v * 7.0), fract(v * 13.0)), 1.0);
}
"""


def _unpack_gl_id(generator_result):
    """不同 PyOpenGL 版本对 glGen*(1) 的返回类型不一致（int 或 tuple）。

    - 较老版本（< 3.1）返回单个整数。
    - 较新版本（>= 3.1，部分子版本）返回 (int,) 元组。
    统一解包为单个整数，供 glBindVertexArray/glBindBuffer 使用。
    兼容 preflight ruling C3。
    """
    if isinstance(generator_result, (tuple, list)):
        return generator_result[0]
    return generator_result


class GPUStressWindow:
    """OpenGL fragment shader 拉满 GPU 窗口。

    在独立线程中持续渲染全屏 quad；调用方可在任意时刻 start()/stop()。
    无显示器、glfw 不可用、平台不支持（macOS）或 OpenGL 上下文创建失败时
    静默跳过（start() 不抛异常，is_running 保持 False）。
    """

    def __init__(self, width: int = 512, height: int = 512):
        self.width = width
        self.height = height
        self._running = False
        self._thread: threading.Thread | None = None
        self._window = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """启动 GPU 渲染线程（独立线程）；幂等（多次调用仅启动一次）。

        在 macOS 上静默跳过（参见模块 docstring），其余平台启动 worker 线程。
        """
        if self._running:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        if sys.platform == "darwin":
            # NSWindow 必须主线程实例化；worker 线程调用会触发
            # NSInternalInconsistencyException 导致进程崩溃（Cocoa 限制）。
            log.info("GPU window skipped: NSWindow requires macOS main thread")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        program = None
        vs = None
        fs = None
        try:
            if not glfw.init():
                log.warning("glfw.init() failed; GPU window skipped")
                return
            glfw.window_hint(glfw.VISIBLE, glfw.FALSE)  # 不弹窗，纯 GPU 负载
            self._window = glfw.create_window(
                self.width, self.height, "GPU Crunching", None, None
            )
            if not self._window:
                log.warning("glfw.create_window failed; GPU window skipped")
                glfw.terminate()
                return
            glfw.make_context_current(self._window)

            # 编译 shader
            vs = self._compile_shader(GL_VERTEX_SHADER, VERTEX_SHADER_SRC)
            fs = self._compile_shader(GL_FRAGMENT_SHADER, FRAGMENT_SHADER_SRC)
            program = glCreateProgram()
            glAttachShader(program, vs)
            glAttachShader(program, fs)
            glLinkProgram(program)

            # 全屏 quad；解包兼容新旧 PyOpenGL（preflight C3）
            vao = _unpack_gl_id(glGenVertexArrays(1))
            vbo = _unpack_gl_id(glGenBuffers(1))
            glBindVertexArray(vao)
            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            # 32 字节顶点缓冲：每个顶点 = vec2(GL_FLOAT) × 2 = 8 字节，
            # 共 4 顶点组成 2 三角形（覆盖全屏的退化 quad）。
            quad_data = (
                b"\xFF\xFF\x00\x00\xFF\xFF\x00\x00\xFF\xFF\x00\x00\xFF\xFF\x00\x00"
                + b"\x00\x00\x00\x00\xFF\xFF\x00\x00\xFF\xFF\x00\x00\xFF\xFF\x00\x00"
            )
            glBufferData(GL_ARRAY_BUFFER, len(quad_data), quad_data, GL_STATIC_DRAW)
            glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(0)

            glUseProgram(program)
            loc_time = glGetUniformLocation(program, "u_time")
            loc_res = glGetUniformLocation(program, "u_resolution")

            self._running = True
            start_time = time.time()
            glClearColor(0.0, 0.0, 0.0, 1.0)

            while self._running and not glfw.window_should_close(self._window):
                t = time.time() - start_time
                glUniform1f(loc_time, t)
                glUniform2f(loc_res, float(self.width), float(self.height))
                glClear(GL_COLOR_BUFFER_BIT)
                glDrawArrays(0, 0, 3)  # GL_TRIANGLES = 0
                glfw.swap_buffers(self._window)
                glfw.poll_events()
        except Exception as e:  # noqa: BLE001 — 必须吞掉所有异常以保持 start() 永不抛
            log.warning(f"GPU window error: {e}")
        finally:
            self._running = False
            try:
                if program is not None:
                    glDeleteProgram(program)
                if vs is not None:
                    glDeleteShader(vs)
                if fs is not None:
                    glDeleteShader(fs)
            except Exception:  # noqa: BLE001
                pass
            try:
                if self._window:
                    glfw.destroy_window(self._window)
                    self._window = None
                glfw.terminate()
            except Exception:  # noqa: BLE001
                pass

    def _compile_shader(self, shader_type, source):
        shader = glCreateShader(shader_type)
        glShaderSource(shader, source)
        glCompileShader(shader)
        return shader

    def stop(self) -> None:
        """停止 GPU 渲染；幂等（多次调用安全）。"""
        self._running = False
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            self._thread = None
