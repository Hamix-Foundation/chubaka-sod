import json
import os
from dataclasses import asdict, dataclass, fields

from lysyk.paths import user_dir


@dataclass
class Settings:
    master: float = 0.8
    music: float = 0.6
    sfx: float = 0.9
    fullscreen: bool = False
    vsync: bool = True
    fps_limit: int = 0
    msaa: bool = True
    graphics_api: str = "auto"
    show_fps: bool = False
    quality: str = "auto"
    ray_tracing: bool = False
    language: str = "uk"

    @staticmethod
    def path_for(app):
        return os.path.join(user_dir(app), "settings.json")

    def save(self, app):
        try:
            with open(self.path_for(app), "w", encoding="utf-8") as fh:
                json.dump(asdict(self), fh, indent=2)
        except OSError:
            pass

    @classmethod
    def load(cls, app):
        s = cls()
        try:
            with open(cls.path_for(app), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return s
        for f in fields(cls):
            if f.name in data and isinstance(data[f.name], type(getattr(s, f.name))):
                setattr(s, f.name, data[f.name])
        return s
