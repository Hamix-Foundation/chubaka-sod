import os

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.environ.get("CHUBAKA_ASSETS_ROOT", os.path.join(ROOT, "assets"))


def asset(*parts):
    return os.path.join(ASSETS, *parts)
