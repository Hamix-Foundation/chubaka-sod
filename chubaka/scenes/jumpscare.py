import os
import random

from chubaka import asset
from chubaka.echoes import by_id
from chubaka.echoes.art import placeholder_rgba, sprite_path
from chubaka.settings_ui import translate
from chubaka.widgets import Button
from lysyk.engine.media.video import VideoPlayer
from lysyk.engine.scenes import Scene
from lysyk.engine.sprite import load_rgba
from lysyk.engine.texture import FIT_STRETCH
from lysyk.engine.tween import smoothstep

WHITE = (255, 255, 255, 255)
RED = (190, 24, 24, 255)


class JumpscareScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.players = {}
        self.textures = {}
        self.spec = None
        self.echo_spec = None
        self.video = None
        self.texture = None
        self.night = 1
        self.time = 0.0
        self.duration = 1.5
        self.phase = "scare"
        self.rand = random.Random(9)
        self.retry_button = Button("", 440, 470, 400, 72, self.retry, 32)
        self.menu_button = Button("", 440, 560, 400, 72, self.menu, 32)
        self.retry_button.arrow = False
        self.menu_button.arrow = False
        self.leaving = False

    def video_for(self, spec):
        path = asset(spec.video) if spec.video else ""
        if not path or not os.path.isfile(path):
            return None
        player = self.players.get(path)
        if player is None:
            try:
                player = VideoPlayer(self.game.canvas, path, self.game.audio, False, 1.0, "sfx")
            except Exception:
                return None
            self.players[path] = player
        return player

    def texture_for(self, echo_spec):
        tex = self.textures.get(echo_spec.id)
        if tex is None:
            found = sprite_path(echo_spec.id)
            image = load_rgba(found) if found else placeholder_rgba(echo_spec.shape, echo_spec.color, echo_spec.eyes, 192, 384, sum(map(ord, echo_spec.id)))
            tex = self.game.canvas.texture(image.shape[1], image.shape[0], image, "linear", False)
            self.textures[echo_spec.id] = tex
        return tex

    def enter(self, echo_id=None, night=1, **kwargs):
        self.echo_spec = by_id(echo_id)
        self.night = night
        self.time = 0.0
        self.phase = "scare"
        self.leaving = False
        self.video = None
        self.texture = None
        language = self.game.settings.language
        self.retry_button.label = translate(language, "retry")
        self.menu_button.label = translate(language, "menu")
        for b in (self.retry_button, self.menu_button):
            b.hover = False
            b.down = False
        self.game.set_cursor_grab("none")
        if self.echo_spec is None:
            self.phase = "over"
            return
        self.spec = self.echo_spec.jumpscare
        self.video = self.video_for(self.spec)
        if self.video is not None:
            self.video.play()
        else:
            self.texture = self.texture_for(self.echo_spec)
            sound = asset(self.spec.sound) if self.spec.sound else ""
            if sound and os.path.isfile(sound):
                self.game.audio.play(sound, 1.0, False, "sfx")
        self.duration = self.spec.duration
        self.game.fx.trigger_glitch(1.0)

    def exit(self):
        if self.video is not None:
            self.video.stop()

    def retry(self):
        if not self.leaving:
            self.leaving = True
            self.game.scenes.goto("night", fade=0.4, night=self.night)

    def menu(self):
        if not self.leaving:
            self.leaving = True
            self.game.scenes.goto("title", fade=0.5)

    def update(self, dt):
        self.time += dt
        self.game.fx.update(dt)
        if self.video is not None:
            self.video.update(dt)
        if self.phase == "scare":
            done = self.video.finished if self.video is not None else self.time >= self.duration
            if done:
                self.phase = "over"
                self.time = 0.0
        else:
            self.retry_button.update(dt)
            self.menu_button.update(dt)

    def mouse_motion(self, x, y):
        if self.phase == "over":
            self.retry_button.motion(x, y)
            self.menu_button.motion(x, y)

    def mouse_press(self, x, y, button):
        if button == 0 and self.phase == "over":
            self.retry_button.press(x, y)
            self.menu_button.press(x, y)

    def mouse_release(self, x, y, button):
        if button == 0 and self.phase == "over":
            self.retry_button.release(x, y)
            self.menu_button.release(x, y)

    def touch(self, touch_id, phase, x, y):
        if self.phase != "over":
            return
        if phase == "down":
            self.retry_button.motion(x, y)
            self.menu_button.motion(x, y)
            self.retry_button.press(x, y)
            self.menu_button.press(x, y)
        elif phase == "up":
            self.retry_button.release(x, y)
            self.menu_button.release(x, y)

    def draw_fallback(self, sc, st):
        t = self.time / max(self.duration, 0.01)
        grow = 0.55 + 0.9 * smoothstep(min(1.0, t * 4.0))
        shake = self.spec.shake * 22.0 * max(0.0, 1.0 - t * 0.6)
        ox = self.rand.uniform(-shake, shake)
        oy = self.rand.uniform(-shake, shake)
        h = st.height * grow * 1.35
        w = h * self.texture.width / float(self.texture.height)
        sc.image(self.texture, st.width / 2 - w / 2 + ox, st.height - h * 0.92 + oy, w, h)
        flash = max(0.0, 1.0 - t * 6.0)
        if flash > 0.0:
            c = self.spec.flash
            sc.rect(0, 0, st.width, st.height, (c[0], c[1], c[2], int(255 * flash)))
        if int(self.time * 24) % 3 == 0:
            sc.rect(0, 0, st.width, st.height, (160, 0, 0, 60))

    def draw(self, sc):
        st = sc.stage
        sc.raw.rect(0, 0, st.win_w, st.win_h, (0, 0, 0, 255))
        if self.phase == "scare":
            if self.video is not None:
                self.video.draw(sc, 0, 0, st.width, st.height, FIT_STRETCH)
            elif self.texture is not None:
                self.draw_fallback(sc, st)
            if self.game.quality != "potato":
                self.game.fx.draw(sc, grain=0.12, scanlines=0.08, vignette=0.6)
            return
        language = self.game.settings.language
        a = int(255 * smoothstep(self.time / 0.6))
        sc.text(translate(language, "game_over"), st.width / 2, 250, (RED[0], RED[1], RED[2], a), 84, "center", "center", True, True, "zombie")
        if self.echo_spec is not None:
            sc.text(f"{translate(language, 'caught_by')}: {translate(language, 'echo_' + self.echo_spec.id)}", st.width / 2, 340, (255, 255, 255, a), 30, "center", "center")
        self.retry_button.draw(sc)
        self.menu_button.draw(sc)
        if self.game.quality != "potato":
            self.game.fx.draw(sc, grain=0.07, scanlines=0.06, vignette=0.6, glitch_bars=False)
