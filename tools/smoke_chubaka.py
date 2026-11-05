import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chubaka.app import ChubakaGame
from lysyk.config import Settings


class Smoke(ChubakaGame):
    def __init__(self, shots, out, api):
        s = Settings()
        s.graphics_api = api
        super().__init__(s, audio=False)
        self.shots = sorted(shots)
        self.out = out
        self.index = 0
        self.clock = 0.0
        os.makedirs(out, exist_ok=True)

    def on_update(self, dt):
        super().on_update(1.0 / 30.0)
        self.clock += 1.0 / 30.0

    def on_draw(self):
        super().on_draw()
        if self.index < len(self.shots):
            t, scene, mouse = self.shots[self.index]
            if scene and self.scenes.current_name != scene and not self.scenes.busy:
                self.scenes.switch(scene, night=1)
            if self.clock >= t:
                self.screenshot(os.path.join(self.out, f"{self.index:02d}_{self.scenes.current_name}.png"))
                self.index += 1
        else:
            self.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="shots")
    ap.add_argument("--api", default="gl")
    a = ap.parse_args()
    shots = [(1.0, "title", None), (3.0, "cutscene", None), (8.0, "cutscene", None), (14.0, "cutscene", None), (16.0, "night", None), (18.0, "classroom", None)]
    Smoke(shots, a.out, a.api).run()


if __name__ == "__main__":
    main()
