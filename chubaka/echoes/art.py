import os

import numpy as np

from chubaka import asset

SHAPES = {
    "wraith": (0.16, 0.085, 0.2, 0.42),
    "child": (0.3, 0.17, 0.2, 0.34),
    "tall": (0.1, 0.06, 0.12, 0.26),
    "hunched": (0.24, 0.14, 0.16, 0.5),
    "wide": (0.17, 0.1, 0.24, 0.5),
}


def sprite_path(echo_id, name="sprite.png"):
    path = asset("echoes", echo_id, name)
    return path if os.path.isfile(path) else ""


def placeholder_rgba(shape="wraith", color=(70, 76, 92), eyes=(255, 60, 60), width=96, height=192, seed=0):
    top, head_r, neck, base = SHAPES.get(shape, SHAPES["wraith"])
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    u = (xs + 0.5) / width * 2.0 - 1.0
    v = (ys + 0.5) / height
    aspect = width / float(height)
    cx = 0.0
    head_cy = top + head_r * 1.2
    head = ((u - cx) * aspect) ** 2 + (v - head_cy) ** 2 < head_r ** 2
    start = head_cy + head_r * 0.6
    t = np.clip((v - start) / max(1e-6, 1.0 - start), 0.0, 1.0)
    half = (neck * 0.5 + (base - neck * 0.5) * t ** 0.8) * (1.0 + 0.06 * np.sin(v * 38.0 + seed))
    body = (v > start) & (np.abs(u) < half * 1.7) & (v < 0.985)
    mask = head | body
    shade = 0.55 + 0.6 * (1.0 - np.abs(u) * 0.6) * (1.0 - v * 0.5)
    noise = rng.normal(0.0, 0.05, size=(height, width))
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    for i in range(3):
        rgba[..., i] = np.clip(color[i] * (shade + noise), 0, 255)
    ex = head_r * 0.42 / aspect
    ey = head_cy - head_r * 0.1
    for sx in (-1, 1):
        eye = (((u - sx * ex) * aspect) / (head_r * 0.28)) ** 2 + ((v - ey) / (head_r * 0.2)) ** 2 < 1.0
        for i in range(3):
            rgba[..., i] = np.where(eye & mask, eyes[i], rgba[..., i])
    mouth = (np.abs(u) < ex * 1.2) & (np.abs(v - (head_cy + head_r * 0.5)) < head_r * 0.06) & head
    for i in range(3):
        rgba[..., i] = np.where(mouth, 8, rgba[..., i])
    rgba[..., 3] = np.where(mask, 255, 0)
    return rgba
