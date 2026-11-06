from chubaka import asset
from chubaka.settings_ui import translate
from chubaka.widgets import Button
from lysyk.engine.scenes import Scene
from lysyk.engine.texture import FIT_STRETCH
from lysyk.engine.media.video import VideoPlayer


class CutsceneScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.video = VideoPlayer(game.canvas, asset("video", "night1_cutscene.lyv"), game.audio, False, 1.0, "sfx")
        self.skip_button = Button("", 1058, 23, 192, 57, self.skip, 35)
        self.skip_button.arrow = False
        self.leaving = False

    def enter(self, **kwargs):
        self.skip_button.label = translate(self.game.settings.language, "skip")
        self.leaving = False
        self.skip_button.hover = False
        self.skip_button.down = False
        self.video.play()

    def exit(self):
        self.video.stop()

    def skip(self):
        if self.leaving:
            return
        self.leaving = True
        self.game.scenes.goto("night", fade=0.4, night=1)

    def update(self, dt):
        self.video.update(dt)
        self.skip_button.update(dt)
        if self.video.finished and not self.leaving:
            self.skip()

    def mouse_motion(self, x, y):
        self.skip_button.motion(x, y)

    def mouse_press(self, x, y, button):
        if button == 0:
            self.skip_button.press(x, y)

    def mouse_release(self, x, y, button):
        if button == 0:
            self.skip_button.release(x, y)

    def touch(self, touch_id, phase, x, y):
        if phase == "down":
            self.skip_button.motion(x, y)
            self.skip_button.press(x, y)
        elif phase == "up":
            self.skip_button.release(x, y)
            self.skip_button.hover = False

    def draw(self, sc):
        st = sc.stage
        sc.raw.rect(0, 0, st.win_w, st.win_h, (0, 0, 0, 255))
        self.video.draw(sc, 0, 0, st.width, st.height, FIT_STRETCH)
        self.skip_button.draw(sc)
