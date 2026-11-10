import argparse
import os
import sys

from chubaka import asset
from chubaka.scenes.classroom import ClassroomScene
from chubaka.scenes.cutscene import CutsceneScene
from chubaka.scenes.jumpscare import JumpscareScene
from chubaka.scenes.intro import IntroScene
from chubaka.scenes.night import NightScene
from chubaka.scenes.title import TitleScene
from chubaka.pause_menu import PauseMenu
from chubaka.state import Progress
from lysyk.config import Settings
from lysyk.engine import keys as K
from lysyk.engine.fx import FilmFx
from lysyk.engine.game import Game
from lysyk.profile import PROFILES, frame_limit, resolve


def android_device():
    return "LYSYK_ROOT" in os.environ or ("ANDROID_ROOT" in os.environ and "ANDROID_DATA" in os.environ)


APP_NAME = "ChubakaSOD"
TITLE = "Chubaka: The Smell Of Death"


class ChubakaGame(Game):
    def __init__(self, settings=None, audio=True):
        self.settings = settings or Settings.load(APP_NAME)
        if self.settings.language not in ("uk", "en"):
            self.settings.language = "uk"
        quality = resolve(self.settings.quality, android_device())
        self.profile = dict(PROFILES[quality])
        super().__init__(
            TITLE, 1280, 720, (1280, 720), audio, 120 if android_device() else 50,
            vsync=self.settings.vsync and not (android_device() and self.profile["fps"] == 30), msaa=self.settings.msaa and self.profile["msaa"], backend=self.settings.graphics_api,
        )
        self.quality = quality
        try:
            self.ray_tracing_enabled = bool(self.settings.ray_tracing and self.gpu_info().get("ray_tracing_supported", False))
        except Exception:
            self.ray_tracing_enabled = False
        self.canvas.load_font("zombie", asset("fonts", "BloodVictimZombie.ttf"))
        self.audio.master = self.settings.master
        self.audio.buses["music"] = self.settings.music
        self.audio.buses["sfx"] = self.settings.sfx
        self.set_fps_limit(frame_limit(self.settings.quality, self.is_mobile, self.settings.fps_limit))
        if self.settings.fullscreen:
            self.set_fullscreen(True)
        self.progress = Progress()
        self.fx = FilmFx(self.canvas, grain=self.profile["grain"] > 0.0, scanlines=self.profile["scanlines"] > 0.0)
        self.paused = False
        self.pause_menu = PauseMenu(self)
        self.scenes.register("title", TitleScene(self))
        self.scenes.register("intro", IntroScene(self))
        self.scenes.register("cutscene", CutsceneScene(self))
        self.scenes.register("night", NightScene(self))
        self.scenes.register("classroom", ClassroomScene(self))
        self.scenes.register("jumpscare", JumpscareScene(self))
        self.scenes.switch("intro")

    def on_update(self, dt):
        if self.paused:
            self.pause_menu.update(min(dt, 0.1))
            return
        super().on_update(dt)

    def on_draw(self):
        super().on_draw()
        if self.paused:
            self.pause_menu.draw(self.sc)
        elif self.pause_hud_visible():
            self.pause_menu.draw_hud(self.sc)

    def pause_hud_visible(self):
        return self.scenes.current_name == "classroom" and getattr(self.scenes.current, "state", None) != "laptop"

    def pause_game(self):
        if self.scenes.current_name not in ("classroom", "cutscene", "night", "jumpscare") or self.paused:
            return
        self.paused = True
        self.pause_menu.anim = 0.0
        self.pause_menu.resume_button.down = False
        self.pause_menu.menu_button.down = False
        self.audio.pause()

    def resume_game(self):
        if not self.paused:
            return
        self.paused = False
        self.audio.resume()

    def return_to_title(self):
        if not self.paused:
            return
        self.paused = False
        self.audio.resume()
        self.scenes.goto("title", fade=0.5)

    def on_key_press(self, key, mods):
        if self.paused:
            if key == K.ESCAPE:
                self.resume_game()
            return
        if key == K.ESCAPE and self.scenes.current_name in ("classroom", "cutscene", "night", "jumpscare"):
            self.pause_game()
            return
        super().on_key_press(key, mods)

    def on_mouse_motion(self, x, y):
        sx, sy = self.stage.to_stage(x, y)
        if self.paused:
            self.pause_menu.motion(sx, sy)
            return
        super().on_mouse_motion(x, y)

    def on_mouse_press(self, x, y, button):
        sx, sy = self.stage.to_stage(x, y)
        if self.paused:
            if button == 0:
                self.pause_menu.press(sx, sy)
            return
        px, py, pw, ph = self.pause_menu.HUD_X, self.pause_menu.HUD_Y, self.pause_menu.HUD_W, self.pause_menu.HUD_H
        if button == 0 and self.pause_hud_visible() and px <= sx <= px + pw and py <= sy <= py + ph:
            self.pause_game()
            return
        super().on_mouse_press(x, y, button)

    def on_mouse_release(self, x, y, button):
        sx, sy = self.stage.to_stage(x, y)
        if self.paused:
            if button == 0:
                self.pause_menu.release(sx, sy)
            return
        super().on_mouse_release(x, y, button)

    def on_touch(self, touch_id, phase, x, y):
        sx, sy = self.stage.to_stage(x, y)
        if self.paused:
            if phase == "down":
                self.pause_menu.press(sx, sy)
            elif phase == "up":
                self.pause_menu.release(sx, sy)
            return
        px, py, pw, ph = self.pause_menu.HUD_X, self.pause_menu.HUD_Y, self.pause_menu.HUD_W, self.pause_menu.HUD_H
        if phase == "down" and self.pause_hud_visible() and px <= sx <= px + pw and py <= sy <= py + ph:
            self.pause_game()
            return
        super().on_touch(touch_id, phase, x, y)

    def on_scroll(self, dx, dy):
        if self.paused:
            return
        current = self.scenes.current
        if self.scenes.current_name == "title" and current is not None and current.license_open:
            current.license_panel.scroll_wheel(dy)

    def on_resume(self):
        if self.paused:
            self.scenes.route("resume")
            return
        super().on_resume()

    def on_close(self):
        self.settings.fullscreen = self.fullscreen
        self.settings.save(APP_NAME)
        super().on_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Chubaka: The Smell Of Death on Lysyk Engine")
    ap.add_argument("--api", default=None, choices=["auto", "vulkan", "gl", "dx12"] if sys.platform == "win32" else ["auto", "vulkan", "gl"])
    ap.add_argument("--quality", default=None, choices=sorted(PROFILES))
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--overlay", action="store_true")
    a = ap.parse_args(argv)
    settings = Settings.load(APP_NAME)
    if a.api:
        settings.graphics_api = a.api
    if a.quality:
        settings.quality = a.quality
    if a.fullscreen:
        settings.fullscreen = True
    game = ChubakaGame(settings, not a.no_audio)
    if a.overlay:
        game.overlay = True
    game.run()
