import math

import numpy as np

from lysyk.engine.mesh import Mesh, MeshBuilder


def clamp_color(c):
    return tuple(max(0, min(255, int(v))) for v in c)


def shade(c, k):
    return clamp_color((c[0] * k, c[1] * k, c[2] * k))


def mix(a, b, t):
    return clamp_color((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t))


def jitter(rng, c, amount):
    return shade(c, 1.0 + (rng.random() - 0.5) * 2.0 * amount)


def rotation(rx=0.0, ry=0.0, rz=0.0):
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float32)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float32)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float32)
    return my @ mx @ mz


class Template:
    def __init__(self, mesh):
        self.v = np.asarray(mesh.vertices, dtype=np.float32).copy()
        self.f = np.asarray(mesh.faces, dtype=np.uint32).copy()
        self.c = np.asarray(mesh.colors, dtype=np.uint8).copy()


def _unit_box():
    b = MeshBuilder()
    b.box((0, 0, 0), (1, 1, 1), (255, 255, 255))
    return Template(b.build())


def _unit_cylinder(segments):
    b = MeshBuilder()
    b.cylinder((0, 0, 0), 1.0, 1.0, "y", (255, 255, 255), segments=segments)
    return Template(b.build())


def _unit_sphere(rings, segments):
    b = MeshBuilder()
    b.ellipsoid((0, 0, 0), (1, 1, 1), (255, 255, 255), rings=rings, segments=segments)
    return Template(b.build())


class Templates:
    def __init__(self):
        self.box = _unit_box()
        self.cyl = {}
        self.sphere = {}

    def cylinder(self, segments):
        if segments not in self.cyl:
            self.cyl[segments] = _unit_cylinder(segments)
        return self.cyl[segments]

    def ellipsoid(self, rings, segments):
        key = (rings, segments)
        if key not in self.sphere:
            self.sphere[key] = _unit_sphere(rings, segments)
        return self.sphere[key]


_TEMPLATES = None


def templates():
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = Templates()
    return _TEMPLATES


class Batch:
    def __init__(self):
        self.verts = []
        self.colors = []
        self.faces = []
        self.count = 0
        self.group = None
        self.stack = []

    def push(self, pos=(0.0, 0.0, 0.0), rot=(0.0, 0.0, 0.0)):
        if self.group is not None:
            self.stack.append(self.group)
        self.group = (rotation(*rot), np.array(pos, dtype=np.float32))
        return self

    def pop(self):
        self.group = self.stack.pop() if self.stack else None

    def _emit(self, v, f, color, alpha=0):
        if self.group is not None:
            v = v @ self.group[0].T + self.group[1]
        col = np.empty((len(v), 4), dtype=np.uint8)
        col[:, 0] = color[0]
        col[:, 1] = color[1]
        col[:, 2] = color[2]
        col[:, 3] = alpha
        self.verts.append(v.astype(np.float32))
        self.colors.append(col)
        self.faces.append(f.astype(np.uint32) + self.count)
        self.count += len(v)

    def _place(self, tpl, pos, size, rot, color, alpha=0):
        v = tpl.v * np.array(size, dtype=np.float32)
        if rot is not None and (rot[0] or rot[1] or rot[2]):
            v = v @ rotation(*rot).T
        v = v + np.array(pos, dtype=np.float32)
        self._emit(v, tpl.f, color, alpha)

    def box(self, pos, size, color, rot=None):
        self._place(templates().box, pos, size, rot, color)

    def cylinder(self, pos, radius, length, color, axis="y", segments=8, rot=None):
        v = templates().cylinder(segments).v * np.array((radius, length, radius), dtype=np.float32)
        if axis == "x":
            v = v @ rotation(0.0, 0.0, math.pi / 2).T
        elif axis == "z":
            v = v @ rotation(math.pi / 2, 0.0, 0.0).T
        if rot is not None and (rot[0] or rot[1] or rot[2]):
            v = v @ rotation(*rot).T
        self._emit(v + np.array(pos, dtype=np.float32), templates().cylinder(segments).f, color)

    def ellipsoid(self, pos, radii, color, rings=4, segments=8, rot=None):
        self._place(templates().ellipsoid(rings, segments), pos, radii, rot, color)

    def mesh_arrays(self, v, c, f, pos=(0.0, 0.0, 0.0), rot=None, scale=1.0, tint=None):
        v = np.asarray(v, dtype=np.float32) * scale
        if rot is not None and (rot[0] or rot[1] or rot[2]):
            v = v @ rotation(*rot).T
        v = v + np.array(pos, dtype=np.float32)
        c = np.asarray(c, dtype=np.uint8).copy()
        if tint is not None:
            c[:, :3] = np.clip(c[:, :3].astype(np.float32) * np.array(tint, dtype=np.float32), 0, 255).astype(np.uint8)
        if self.group is not None:
            v = v @ self.group[0].T + self.group[1]
        self.verts.append(v.astype(np.float32))
        self.colors.append(c)
        self.faces.append(np.asarray(f, dtype=np.uint32) + self.count)
        self.count += len(v)

    def double_quad(self, a, b, c, d, color):
        v = np.array([a, b, c, d], dtype=np.float32)
        f = np.array([[0, 1, 2], [0, 2, 3], [0, 2, 1], [0, 3, 2]], dtype=np.uint32)
        self._emit(v, f, color)

    def double_tri(self, a, b, c, color):
        v = np.array([a, b, c], dtype=np.float32)
        f = np.array([[0, 1, 2], [0, 2, 1]], dtype=np.uint32)
        self._emit(v, f, color)

    @property
    def empty(self):
        return self.count == 0

    def build(self):
        v = np.concatenate(self.verts, axis=0)
        c = np.concatenate(self.colors, axis=0)
        f = np.concatenate(self.faces, axis=0)
        return Mesh(v, c, f)
