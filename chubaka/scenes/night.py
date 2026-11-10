from chubaka import asset
from chubaka.settings_ui import translate
from lysyk.engine.scenes import Scene
from lysyk.engine.tween import Timeline, smoothstep

NIGHT_DURATION = 6.0


class NightScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.night = 1
        self.time = 0.0
        self.timeline = Timeline()
        self.done = False

    def enter(self, night=1, **kwargs):
        self.night = night
        self.time = 0.0
        self.done = False
        self.game.audio.play(asset("audio", "night_start.mp3"), 1.0, False, "sfx")
        self.timeline = Timeline()
        self.timeline.at(0.02, lambda: self.game.fx.trigger_glitch(1.0))
        self.timeline.at(NIGHT_DURATION, self.finish)

    def finish(self):
        if not self.done:
            self.done = True
            self.classroom.build()
            self.game.scenes.goto("classroom", fade=0.5, night=self.night)

    def update(self, dt):
        self.time += dt
        self.timeline.update(dt)
        self.game.fx.update(dt)
        self.classroom.prepare(0.006)

    @property
    def classroom(self):
        return self.game.scenes.scenes["classroom"]

    def draw(self, sc):
        if self.classroom.built and not self.classroom.warmed:
            self.classroom.warm()
        st = sc.stage
        sc.raw.rect(0, 0, st.win_w, st.win_h, (0, 0, 0, 255))
        a = int(255 * smoothstep(self.time / 0.8))
        shake = max(0.0, 1.0 - self.time * 1.5) * 8.0
        sc.text(f"{translate(self.game.settings.language, 'night')} {self.night}", 639 + shake * (1 if int(self.time * 40) % 2 else -1), 357, (255, 255, 255, a), 60, "center", "center")
        self.game.fx.draw(sc, grain=0.05, scanlines=0.05, vignette=0.0 if self.game.quality == "low" else 0.5)
