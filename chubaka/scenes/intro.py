from chubaka import asset
from lysyk.engine import keys as K
from lysyk.engine.media.video import VideoPlayer
from lysyk.engine.scenes import Scene
from lysyk.engine.texture import FIT_CONTAIN


class IntroScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.video = VideoPlayer(game.canvas, asset("video", "HX_Foundation_intro.lyv"), game.audio, False, 1.0, "sfx")
        self.leaving = False

    def enter(self, **kwargs):
        self.leaving = False
        self.video.prepare()
        self.video.play()

    def exit(self):
        self.video.stop()

    def skip(self):
        if not self.leaving:
            self.leaving = True
            self.game.scenes.goto("title", fade=0.4)

    def key_press(self, key, mods):
        if key == K.ESCAPE:
            self.skip()

    def mouse_press(self, x, y, button):
        self.skip()

    def touch(self, touch_id, phase, x, y):
        if phase == "down":
            self.skip()

    def update(self, dt):
        self.video.update(dt)
        if self.video.finished:
            self.skip()

    def draw(self, sc):
        st = sc.stage
        self.video.draw(sc, 0, 0, st.width, st.height, FIT_CONTAIN)
