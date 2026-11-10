from lysyk.engine import _native
from lysyk.paths import FONTS


class _Target:
    def _setup(self, core):
        self._core = core
        self._gpu = core.gpu
        self.canvas = core.canvas

    @property
    def width(self):
        return self._core.width

    @property
    def height(self):
        return self._core.height

    def clear(self, color=(0, 0, 0)):
        self._core.clear(color)

    def set_msaa(self, enabled):
        self._core.set_msaa(enabled)

    @property
    def api(self):
        return self._gpu.api

    def gpu_info(self):
        return self._gpu.info()

    def profile(self):
        return self._gpu.profile()


class Window(_Target):
    def __init__(self, width=1280, height=720, title="Window", resizable=True, vsync=True, msaa=True, backend="auto"):
        self._setup(_native.WindowCore(int(width), int(height), title, bool(resizable), bool(vsync), bool(msaa), backend, FONTS))

    @property
    def pixel_ratio(self):
        return self._core.pixel_ratio

    @property
    def mouse_x(self):
        return self._core.mouse_x

    @property
    def mouse_y(self):
        return self._core.mouse_y

    @property
    def fps(self):
        return self._core.fps

    @property
    def frame_time_ms(self):
        return self._core.frame_time_ms

    @property
    def fullscreen(self):
        return self._core.fullscreen

    @property
    def title(self):
        return self._core.title

    @property
    def overlay(self):
        return self._core.overlay

    @overlay.setter
    def overlay(self, value):
        self._core.overlay = bool(value)

    def set_title(self, title):
        self._core.set_title(title)

    def set_vsync(self, enabled):
        self._core.set_vsync(bool(enabled))

    def set_fps_limit(self, fps):
        self._core.set_fps_limit(float(fps or 0))

    def set_fullscreen(self, enabled):
        self._core.set_fullscreen(bool(enabled))

    def set_cursor_visible(self, visible):
        self._core.set_cursor_visible(bool(visible))

    def set_cursor_grab(self, mode="none"):
        return self._core.set_cursor_grab(mode)

    @property
    def is_mobile(self):
        return self._core.is_mobile

    @property
    def touch_emulates_mouse(self):
        return self._core.touch_emulates_mouse

    @touch_emulates_mouse.setter
    def touch_emulates_mouse(self, value):
        self._core.touch_emulates_mouse = bool(value)

    def set_clipboard(self, text):
        self._core.set_clipboard(text)

    def monitor_info(self):
        return self._core.monitor_info()

    def center_window(self):
        self._core.center_window()

    def screenshot(self, path):
        self._core.screenshot(path)

    def close(self):
        self._core.close()

    def run(self):
        self._core.run(self)

    def on_update(self, dt):
        pass

    def on_draw(self):
        pass

    def on_resize(self, width, height):
        pass

    def on_key_press(self, key, mods):
        pass

    def on_key_release(self, key, mods):
        pass

    def on_mouse_motion(self, x, y):
        pass

    def on_mouse_press(self, x, y, button):
        pass

    def on_mouse_release(self, x, y, button):
        pass

    def on_touch(self, touch_id, phase, x, y):
        pass

    def on_scroll(self, dx, dy):
        pass

    def on_suspend(self):
        pass

    def on_resume(self):
        pass

    def on_close(self):
        pass


class OffscreenWindow(_Target):
    def __init__(self, width=1280, height=720, msaa=True, backend="auto"):
        self._setup(_native.OffscreenCore(int(width), int(height), bool(msaa), backend, FONTS))

    pixel_ratio = 1.0

    def frame(self, draw):
        self._core.frame(draw)

    def read_pixels(self):
        return self._core.read_pixels()

    def save_png(self, path):
        self._core.save_png(path)
