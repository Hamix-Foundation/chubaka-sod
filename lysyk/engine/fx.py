import math
import random

import numpy as np

from lysyk.engine.tween import clamp01


class FilmFx:
    def __init__(self, canvas, grain_size=128, seed=7, grain=True, scanlines=True):
        self.grain_enabled = grain
        self.scan_enabled = scanlines
        rng = np.random.default_rng(seed)
        g = rng.integers(0, 256, size=(grain_size, grain_size), dtype=np.uint8)
        rgba = np.empty((grain_size, grain_size, 4), dtype=np.uint8)
        rgba[..., 0] = g
        rgba[..., 1] = g
        rgba[..., 2] = g
        rgba[..., 3] = 255
        self.grain = canvas.texture(grain_size, grain_size, rgba, "nearest", True)
        lines = np.zeros((4, 1, 4), dtype=np.uint8)
        lines[0] = (0, 0, 0, 0)
        lines[1] = (0, 0, 0, 0)
        lines[2] = (0, 0, 0, 255)
        lines[3] = (0, 0, 0, 255)
        self.scan = canvas.texture(1, 4, lines, "nearest", True)
        ys, xs = np.mgrid[0:36, 0:64].astype(np.float32)
        dx = (xs + 0.5) / 64.0 * 2.0 - 1.0
        dy = (ys + 0.5) / 36.0 * 2.0 - 1.0
        r = np.sqrt((dx * dx + dy * dy) * 0.5)
        edge = np.clip((r - 0.35) / 0.65, 0.0, 1.0) ** 2
        vig = np.zeros((36, 64, 4), dtype=np.uint8)
        vig[..., 3] = np.clip(edge * 255.0 * 0.85, 0, 255).astype(np.uint8)
        self.vignette = canvas.texture(64, 36, vig, "linear", False)
        self.grain_size = grain_size
        self.rand = random.Random(seed)
        self.time = 0.0
        self.flicker = 1.0
        self.glitch = 0.0

    def update(self, dt):
        self.time += dt
        base = 1.0 - 0.04 * (0.5 + 0.5 * math.sin(self.time * 47.0))
        if self.rand.random() < 0.03:
            base *= 0.8
        self.flicker = base
        self.glitch = max(0.0, self.glitch - dt * 3.0)

    def trigger_glitch(self, amount=1.0):
        self.glitch = clamp01(max(self.glitch, amount))

    def draw(self, sc, grain=0.07, scanlines=0.10, vignette=0.55, glitch_bars=True):
        st = sc.stage
        raw = sc.raw
        w, h = st.win_w, st.win_h
        if grain > 0.0 and self.grain_enabled:
            tile = self.grain_size * max(1.0, st.scale * 1.6)
            ou, ov = self.rand.random(), self.rand.random()
            reps_u, reps_v = w / tile, h / tile
            a = int(255 * grain)
            raw.image(self.grain, 0, 0, w, h, (255, 255, 255, a), (ou, ov, ou + reps_u, ov + reps_v))
        if scanlines > 0.0 and self.scan_enabled:
            reps = h / 4.0
            raw.image(self.scan, 0, 0, w, h, (255, 255, 255, int(255 * scanlines)), (0.0, 0.0, 1.0, reps))
        if vignette > 0.0:
            raw.image(self.vignette, 0, 0, w, h, (255, 255, 255, int(255 * min(1.0, vignette / 0.7))), (0.0, 0.0, 1.0, 1.0))
        if glitch_bars and self.glitch > 0.01:
            n = 1 + int(self.glitch * 5)
            for _ in range(n):
                y = self.rand.random() * h
                bh = 2 + self.rand.random() * 18 * self.glitch
                x = self.rand.random() * w * 0.3
                a = int(90 * self.glitch)
                raw.rect(x, y, w - x * 2, bh, (200, 40, 40, a))
                raw.rect(x + 6, y + 1, w - x * 2, bh * 0.4, (40, 200, 200, a // 2))
