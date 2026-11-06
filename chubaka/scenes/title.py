import math
import random

from chubaka import asset
from chubaka.state import load_game_config, load_version
from chubaka.settings_ui import SettingsPanel
from chubaka.links import open_url
from chubaka.widgets import Button, SocialButton
from lysyk.engine import keys as K
from lysyk.engine.scenes import Scene
from lysyk.engine.texture import FIT_CONTAIN
from lysyk.engine.tween import smoothstep

BACKGROUND = (0, 9, 0, 255)
TITLE_TEXT = "Chubaka: \nThe Smell Of Death"


class TitleScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.chubaka = game.canvas.load_texture(asset("chubaka.png"))
        self.game_config = load_game_config()
        self.version = load_version()
        self.buttons = [Button("", 24, 419, 406, 58, self.new_game), Button("", 24, 481, 406, 58, self.continue_game)]
        self.settings_button = Button("⚙", 1168, 22, 82, 66, self.open_settings, 40, True)
        self.settings_button.arrow = False
        github_icon = game.canvas.load_texture(asset("ui", "github.png"))
        discord_icon = game.canvas.load_texture(asset("ui", "discord.png"))
        self.social_buttons = [
            SocialButton("GitHub", "github", 1166, 576, 48, 48, lambda: open_url(self.game_config.get("links", {}).get("github", "")), github_icon),
            SocialButton("Discord", "discord", 1222, 576, 48, 48, lambda: open_url(self.game_config.get("links", {}).get("discord", "")), discord_icon),
        ]
        self.settings_panel = SettingsPanel(game, self.close_settings)
        self.settings_open = False
        self.refresh_labels()
        self.music = None
        game.audio.preload([asset("audio", "title_music.mp3")])
        self.time = 0.0
        self.rand = random.Random(11)
        self.next_glitch = 2.0
        self.title_shift = 0.0

    def enter(self, **kwargs):
        self.time = 0.0
        self.next_glitch = 2.0
        for b in self.buttons:
            b.hover = False
            b.down = False
        self.settings_button.hover = False
        self.settings_button.down = False
        for button in self.social_buttons:
            button.hover = False
            button.down = False
        if self.music is None or self.music.finished:
            self.music = self.game.audio.play(asset("audio", "title_music.mp3"), 0.42, True, "music", fade_in=1.5)
        self.game.audio.preload([asset("audio", "night_start.mp3")])

    def refresh_labels(self):
        uk = self.game.settings.language == "uk"
        self.buttons[0].label = "Нова гра" if uk else "New Game"
        self.buttons[1].label = "Продовжити" if uk else "Continue"
        self.title_text = TITLE_TEXT

    def close_settings(self):
        self.settings_panel.dismiss()
        self.game.settings.save("ChubakaSOD")

    def open_settings(self):
        self.settings_open = True
        self.settings_panel.show()

    def exit(self):
        if self.music is not None:
            self.music.stop(0.6)
            self.music = None

    def new_game(self):
        self.game.progress.new_game()
        self.game.scenes.goto("cutscene", fade=0.6)

    def continue_game(self):
        data = self.game.progress.load()
        if data is None:
            self.game.progress.new_game()
            self.game.scenes.goto("cutscene", fade=0.6)
        elif data["current_night"] == 1:
            self.game.scenes.goto("cutscene", fade=0.6)
        else:
            self.game.scenes.goto("night", fade=0.6, night=data["current_night"])

    def update(self, dt):
        if self.settings_open:
            self.settings_panel.update(dt)
            if self.settings_panel.closed:
                self.settings_open = False
            return
        self.time += dt
        for b in self.buttons:
            b.update(dt)
        self.settings_button.update(dt)
        for button in self.social_buttons:
            button.update(dt)
        self.game.fx.update(dt)
        self.next_glitch -= dt
        if self.next_glitch <= 0.0:
            self.game.fx.trigger_glitch(0.6 + self.rand.random() * 0.4)
            self.title_shift = (self.rand.random() - 0.5) * 14.0
            self.next_glitch = 2.5 + self.rand.random() * 5.0
        self.title_shift *= max(0.0, 1.0 - dt * 9.0)

    def mouse_motion(self, x, y):
        if self.settings_open:
            self.settings_panel.move(x, y)
            return
        for b in self.buttons:
            b.motion(x, y)
        self.settings_button.motion(x, y)
        for button in self.social_buttons:
            button.motion(x, y)

    def mouse_press(self, x, y, button):
        if button == 0:
            if self.settings_open:
                self.settings_panel.press(x, y)
                return
            self.settings_button.press(x, y)
            for button in self.social_buttons:
                button.press(x, y)
            for b in self.buttons:
                b.press(x, y)

    def mouse_release(self, x, y, button):
        if button == 0:
            if self.settings_open:
                self.settings_panel.release(x, y)
                return
            if self.settings_button.release(x, y):
                return
            for button in self.social_buttons:
                if button.release(x, y):
                    return
            for b in self.buttons:
                if b.release(x, y):
                    break

    def touch(self, touch_id, phase, x, y):
        if self.settings_open:
            if phase == "down":
                self.settings_panel.press(x, y)
            elif phase == "up":
                self.settings_panel.release(x, y)
            return
        if phase == "down":
            self.mouse_motion(x, y)
            self.mouse_press(x, y, 0)
        elif phase == "up":
            self.mouse_release(x, y, 0)
            for b in self.buttons:
                b.hover = False
            for button in self.social_buttons:
                button.hover = False

    def draw(self, sc):
        st = sc.stage
        sc.raw.rect(0, 0, st.win_w, st.win_h, BACKGROUND)
        fade_in = smoothstep(self.time / 1.2)
        sway = math.sin(self.time * 0.7) * 6.0
        breathe = 1.0 + 0.012 * math.sin(self.time * 1.3)
        w = 500 * breathe
        h = 500 * breathe
        sc.image(self.chubaka, 785 - (w - 500) / 2 + sway, 219 - (h - 500), w, h, (255, 255, 255, int(255 * fade_in)))
        flick = 1.0 if self.rand.random() > 0.02 else 0.55
        a = int(255 * fade_in * flick)
        shift = self.title_shift
        lines = self.title_text.split("\n")
        for i, line in enumerate(lines):
            y = 67 + 72 * i
            if abs(shift) > 0.5:
                sc.text(line, 28 - shift * 1.4, y, (200, 0, 0, a // 2), 65, "left", "center", False, False, "zombie")
                sc.text(line, 28 + shift, y, (0, 180, 200, a // 3), 65, "left", "center", False, False, "zombie")
            sc.text(line, 28, y, (255, 255, 255, a), 65, "left", "center", False, False, "zombie")
        for b in self.buttons:
            b.draw(sc)
        self.settings_button.draw(sc)
        for button in self.social_buttons:
            button.draw(sc)
        sc.text(self.version, 1274, 640, (255, 255, 255, 255), 24, "right", "top", False, False, "zombie")
        publisher = self.game_config.get("publisher", "Hamix Foundation")
        year = self.game_config.get("copyright_year", 2026)
        license_name = self.game_config.get("license", "GNU GPL v3.0")
        sc.text(f"© {year} {publisher} · {license_name}", 1274, 673, (220, 220, 220, 255), 18, "right", "top")
        self.game.fx.draw(sc, grain=0.06, scanlines=0.07, vignette=0.0 if self.game.quality == "low" else 0.6)
        if self.settings_open:
            self.settings_panel.draw(sc)

    def key_press(self, key, mods):
        if key == K.ESCAPE and self.settings_open:
            if self.settings_panel.about:
                self.settings_panel.about = False
            else:
                self.close_settings()
