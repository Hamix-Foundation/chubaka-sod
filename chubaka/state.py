import json
import os

from chubaka import ROOT
from lysyk.engine.save import SaveFile
from lysyk.paths import user_dir

SAVE_NAME = "chubaka_SOD_save.dat"
SECRET_KEY = "chubaka_valeria"
DATA_TEMPLATE = {"current_night": 1, "unlocked_custom_night": False}


def load_game_config():
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def load_version():
    return load_game_config().get("version", "")


class Progress:
    def __init__(self):
        self.file = SaveFile(os.path.join(user_dir("ChubakaSOD"), SAVE_NAME), SECRET_KEY)

    def save(self, data):
        self.file.write(data)

    def load(self):
        data = self.file.read()
        if isinstance(data, dict) and "current_night" in data:
            return data
        return None

    def new_game(self):
        data = dict(DATA_TEMPLATE)
        self.save(data)
        return data

    def flag(self, name):
        data = self.load()
        return bool(data and data.get(name))

    def set_flag(self, name):
        data = self.load() or dict(DATA_TEMPLATE)
        data[name] = True
        self.save(data)
