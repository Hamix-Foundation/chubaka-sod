import math

import numpy as np

from lysyk.engine.mesh import Mesh
from lysyk.engine.objects import MODE_GLOW, MODE_LIT, GameObject


def load_rgba(path):
    from lysyk.engine._native import read_png

    return np.ascontiguousarray(read_png(path), dtype=np.uint8)


def downsample(rgba, columns, rows):
    src = np.asarray(rgba, dtype=np.float64)
    h, w = src.shape[:2]
    columns = max(1, min(int(columns), w))
    rows = max(1, min(int(rows), h))
    alpha = src[..., 3:4] / 255.0
    pre = np.concatenate([src[..., :3] * alpha, alpha], axis=2)
    integral = np.zeros((h + 1, w + 1, 4), dtype=np.float64)
    integral[1:, 1:] = pre.cumsum(axis=0).cumsum(axis=1)
    ys = np.linspace(0, h, rows + 1).round().astype(np.int64)
    xs = np.linspace(0, w, columns + 1).round().astype(np.int64)
    y0, y1, x0, x1 = ys[:-1], ys[1:], xs[:-1], xs[1:]
    total = (
        integral[np.ix_(y1, x1)] - integral[np.ix_(y0, x1)] - integral[np.ix_(y1, x0)] + integral[np.ix_(y0, x0)]
    )
    area = ((y1 - y0)[:, None] * (x1 - x0)[None, :]).astype(np.float64)
    mean = total / area[..., None]
    cover = mean[..., 3]
    rgb = mean[..., :3] / np.maximum(cover, 1e-6)[..., None]
    return np.clip(rgb, 0, 255).astype(np.uint8), cover


def sprite_arrays(rgba, height=1.8, columns=48, threshold=0.5, pivot=(0.5, 0.0), quantize=12, double_sided=True):
    rgba = np.asarray(rgba)
    h, w = rgba.shape[:2]
    aspect = w / float(h)
    width = height * aspect
    columns = max(1, min(int(columns), w))
    rows = max(1, min(int(round(columns / aspect)), h))
    rgb, cover = downsample(rgba, columns, rows)
    mask = cover >= threshold
    q = max(1, int(quantize))
    keys = (rgb[..., 0] // q).astype(np.int64) * 65536 + (rgb[..., 1] // q).astype(np.int64) * 256 + (rgb[..., 2] // q).astype(np.int64)
    rects = []
    open_runs = {}
    for r in range(rows + 1):
        runs = {}
        if r < rows:
            c = 0
            while c < columns:
                if not mask[r, c]:
                    c += 1
                    continue
                c1 = c
                while c1 + 1 < columns and mask[r, c1 + 1] and keys[r, c1 + 1] == keys[r, c]:
                    c1 += 1
                runs[(c, c1, int(keys[r, c]))] = rgb[r, c:c1 + 1].astype(np.float64).mean(axis=0)
                c = c1 + 1
        for key in list(open_runs):
            if key not in runs:
                rects.append(open_runs.pop(key))
        for key, color in runs.items():
            if key in open_runs:
                entry = open_runs[key]
                entry[1] = r + 1
                entry[2] += color
                entry[3] += 1
            else:
                open_runs[key] = [r, r + 1, color.copy(), 1, key[0], key[1]]
    if not rects:
        rects.append([0, 1, np.zeros(3), 1, 0, 0])
    verts = np.empty((len(rects) * 4, 3), dtype=np.float32)
    colors = np.empty((len(rects) * 4, 4), dtype=np.uint8)
    for i, (ra, rb, acc, n, ca, cb) in enumerate(rects):
        x0 = (ca / columns - pivot[0]) * width
        x1 = ((cb + 1) / columns - pivot[0]) * width
        y1 = (1.0 - ra / rows - pivot[1]) * height
        y0 = (1.0 - rb / rows - pivot[1]) * height
        verts[i * 4:i * 4 + 4] = ((x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0))
        col = np.clip(acc / n, 0, 255).astype(np.uint8)
        colors[i * 4:i * 4 + 4, :3] = col
        colors[i * 4:i * 4 + 4, 3] = 0
    base = (np.arange(len(rects), dtype=np.uint32) * 4)[:, None]
    front = np.concatenate([base + (0, 1, 2), base + (0, 2, 3)], axis=1).reshape(-1, 3)
    faces = front
    if double_sided:
        faces = np.concatenate([front, front[:, ::-1]], axis=0)
    return verts, colors, faces.astype(np.uint32), width


def sprite_mesh(rgba, height=1.8, columns=48, **kwargs):
    v, c, f, width = sprite_arrays(rgba, height, columns, **kwargs)
    return Mesh(v, c, f), width


class Sprite:
    def __init__(self, frames, height=1.8, columns=48, **kwargs):
        if isinstance(frames, np.ndarray) and frames.ndim == 3:
            frames = [frames]
        self.height = height
        self.meshes = []
        self.width = height
        for image in frames:
            mesh, self.width = sprite_mesh(image, height, columns, **kwargs)
            self.meshes.append(mesh)

    @classmethod
    def from_png(cls, path, height=1.8, columns=48, **kwargs):
        return cls(load_rgba(path), height, columns, **kwargs)

    @property
    def triangle_count(self):
        return sum(m.triangle_count for m in self.meshes)


def facing_yaw(source, target):
    return math.atan2(target[0] - source[0], target[2] - source[2])


class Billboard:
    def __init__(self, sprite, position=(0.0, 0.0, 0.0), scale=1.0, mode=MODE_LIT, tint=(255, 255, 255), gloss=0.0, cast=False):
        self.sprite = sprite
        self.frame = 0
        self.object = GameObject(sprite.meshes[0], tint, position=position, scale=(scale, scale, scale), mode=mode, cast=cast, gloss=gloss)

    @property
    def position(self):
        return tuple(float(v) for v in self.object.position)

    @position.setter
    def position(self, value):
        self.object.position = (float(value[0]), float(value[1]), float(value[2]))

    @property
    def visible(self):
        return self.object.visible

    @visible.setter
    def visible(self, value):
        self.object.visible = bool(value)

    @property
    def mode(self):
        return self.object.mode

    @mode.setter
    def mode(self, value):
        self.object.mode = value

    @property
    def tint(self):
        return self.object.color

    @tint.setter
    def tint(self, value):
        self.object.color = (value[0], value[1], value[2])

    def set_frame(self, index):
        index %= len(self.sprite.meshes)
        if index != self.frame:
            self.frame = index
            self.object.mesh = self.sprite.meshes[index]

    def face(self, target):
        self.object.rotation = (0.0, facing_yaw(self.position, target), 0.0)


class BillboardLayer:
    def __init__(self, world=None):
        self.world = world
        self.items = []

    def add(self, billboard):
        self.items.append(billboard)
        if self.world is not None:
            self.world.add(billboard.object)
        return billboard

    def remove(self, billboard):
        if billboard in self.items:
            self.items.remove(billboard)
            if self.world is not None:
                self.world.remove(billboard.object)

    def face_all(self, target):
        for item in self.items:
            if item.visible:
                item.face(target)


__all__ = [
    "MODE_GLOW", "MODE_LIT", "Billboard", "BillboardLayer", "Sprite", "downsample", "facing_yaw",
    "load_rgba", "sprite_arrays", "sprite_mesh",
]
