from lysyk.audio import Audio
from lysyk.engine import keys as K
from lysyk.engine.scenes import SceneManager
from lysyk.engine.stage import Stage, StageCanvas
from lysyk.engine.window import Window


class Game(Window):
    def __init__(self, title="Lysyk Engine", width=1280, height=720, stage_size=(1280, 720), audio=True, audio_buffer_ms=50, **window_args):
        super().__init__(width, height, title, **window_args)
        self.stage = Stage(*stage_size)
        self.stage.fit(self.width, self.height)
        self.sc = StageCanvas(self.canvas, self.stage)
        self.audio = Audio(audio, audio_buffer_ms)
        self.scenes = SceneManager(self)
        self.time = 0.0
        self.clear_color = (0, 0, 0)
        self.hotkeys = {}

    def on_resize(self, width, height):
        self.stage.fit(width, height)

    def on_update(self, dt):
        dt = min(dt, 0.1)
        self.time += dt
        self.audio.update(dt)
        self.scenes.update(dt)

    def on_draw(self):
        self.clear(self.clear_color)
        self.stage.fit(self.width, self.height)
        self.scenes.draw(self.sc)
        self.sc.letterbox()

    def on_key_press(self, key, mods):
        if key == K.F11:
            self.set_fullscreen(not self.fullscreen)
            return
        fn = self.hotkeys.get(key)
        if fn is not None:
            fn()
            return
        self.scenes.route("key_press", key, mods)

    def on_key_release(self, key, mods):
        self.scenes.route("key_release", key, mods)

    def on_mouse_motion(self, x, y):
        sx, sy = self.stage.to_stage(x, y)
        self.scenes.route("mouse_motion", sx, sy)

    def on_mouse_press(self, x, y, button):
        sx, sy = self.stage.to_stage(x, y)
        self.scenes.route("mouse_press", sx, sy, button)

    def on_mouse_release(self, x, y, button):
        sx, sy = self.stage.to_stage(x, y)
        self.scenes.route("mouse_release", sx, sy, button)

    def on_touch(self, touch_id, phase, x, y):
        sx, sy = self.stage.to_stage(x, y)
        self.scenes.route("touch", touch_id, phase, sx, sy)

    def on_suspend(self):
        self.audio.pause()
        self.scenes.route("suspend")

    def on_resume(self):
        self.audio.resume()
        self.scenes.route("resume")

    def on_close(self):
        self.audio.close()
