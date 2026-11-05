import argparse
import os

from chubaka import asset
from chubaka.scenes.classroom import ClassroomScene
from chubaka.scenes.cutscene import CutsceneScene
from chubaka.scenes.night import NightScene
from chubaka.scenes.title import TitleScene
from chubaka.state import Progress
from lysyk.config import Settings
from lysyk.engine import keys as K
from lysyk.engine.fx import FilmFx
from lysyk.engine.game import Game
from lysyk.profile import PROFILES, resolve


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
        self.canvas.load_font("zombie", asset("fonts", "BloodVictimZombie.ttf"))
        self.audio.master = self.settings.master
        self.audio.buses["music"] = self.settings.music
        self.audio.buses["sfx"] = self.settings.sfx
        self.set_fps_limit(self.settings.fps_limit or (self.profile["fps"] if self.is_mobile else 0))
        if self.settings.fullscreen:
            self.set_fullscreen(True)
        self.progress = Progress()
        self.fx = FilmFx(self.canvas, grain=self.profile["grain"] > 0.0, scanlines=self.profile["scanlines"] > 0.0)
        self.scenes.register("title", TitleScene(self))
        self.scenes.register("cutscene", CutsceneScene(self))
        self.scenes.register("night", NightScene(self))
        self.scenes.register("classroom", ClassroomScene(self))
        self.scenes.switch("title")

    def on_key_press(self, key, mods):
        if key == K.ESCAPE and self.scenes.current_name in ("classroom", "cutscene", "night"):
            self.scenes.goto("title", fade=0.5)
            return
        super().on_key_press(key, mods)

    def on_close(self):
        self.settings.fullscreen = self.fullscreen
        self.settings.save(APP_NAME)
        super().on_close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Chubaka: The Smell Of Death on Lysyk Engine")
    ap.add_argument("--api", default=None, choices=["auto", "vulkan", "gl"])
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
