import math

import numpy as np

from lysyk.engine import store

MODE_LIT = 0
MODE_GLOW = 1
MODE_SKY = 2
MODE_CLOUD = 3
MODE_WATER = 4


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def euler_from_matrix(m):
    sy = max(-1.0, min(1.0, -float(m[2, 0])))
    y = math.asin(sy)
    if abs(sy) > 0.99999:
        return 0.0, y, math.atan2(-float(m[0, 1]), float(m[1, 1]))
    return math.atan2(float(m[2, 1]), float(m[2, 2])), y, math.atan2(float(m[1, 0]), float(m[0, 0]))


class GameObject:
    __slots__ = ("slot", "_mesh", "cast", "__weakref__")

    def __init__(self, mesh, color=(255, 255, 255), position=None, rotation=None, scale=None,
                 mode=MODE_LIT, cast=False, gloss=0.0):
        self.slot = store.alloc()
        self._mesh = None
        self.mesh = mesh
        self.cast = cast
        self.color = color
        if gloss:
            self.gloss = gloss
        if position is not None:
            self.position = position
        if rotation is not None:
            self.rotation = rotation
        if scale is not None:
            self.scale = scale
        store.data[self.slot, 7] = float(mode)

    def __del__(self):
        try:
            store.release(self.slot)
        except Exception:
            pass

    @property
    def mesh(self):
        return self._mesh

    @mesh.setter
    def mesh(self, m):
        self._mesh = m
        store.mesh_ids[self.slot] = m.gid if m is not None else -1

    @property
    def position(self):
        return store.data[self.slot, 0:3]

    @position.setter
    def position(self, v):
        store.data[self.slot, 0:3] = v

    @property
    def rotation(self):
        return store.data[self.slot, 4:7]

    @rotation.setter
    def rotation(self, v):
        store.data[self.slot, 4:7] = v

    @property
    def scale(self):
        return store.data[self.slot, 8:11]

    @scale.setter
    def scale(self, v):
        store.data[self.slot, 8:11] = v

    @property
    def visible(self):
        return store.data[self.slot, 11] > 0.5

    @visible.setter
    def visible(self, v):
        store.data[self.slot, 11] = 1.0 if v else 0.0

    @property
    def mode(self):
        return int(store.data[self.slot, 7])

    @mode.setter
    def mode(self, v):
        store.data[self.slot, 7] = float(v)

    @property
    def gloss(self):
        return ((int(store.color_bits[self.slot, 3]) >> 24) & 255) / 255.0

    @gloss.setter
    def gloss(self, g):
        bits = int(store.color_bits[self.slot, 3]) & 0x00FFFFFF
        store.color_bits[self.slot, 3] = bits | (int(round(min(1.0, max(0.0, g)) * 255.0)) << 24)

    @property
    def color(self):
        c = int(store.color_bits[self.slot, 3])
        return (c & 255, (c >> 8) & 255, (c >> 16) & 255)

    @color.setter
    def color(self, v):
        bits = int(store.color_bits[self.slot, 3]) & 0xFF000000
        store.color_bits[self.slot, 3] = bits | (int(v[0]) & 255) | ((int(v[1]) & 255) << 8) | ((int(v[2]) & 255) << 16)

    def place(self, x, y, z, rx=0.0, ry=0.0):
        d = store.data[self.slot]
        d[0] = x
        d[1] = y
        d[2] = z
        d[4] = rx
        d[5] = ry

    def set_matrix(self, m, t):
        d = store.data[self.slot]
        d[0:3] = t
        d[4:7] = euler_from_matrix(m)


def camera_matrix(rotation):
    pitch, yaw, roll = float(rotation[0]), float(rotation[1]), float(rotation[2])
    cx, sx = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cz, sz = math.cos(roll), math.sin(roll)
    ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]])
    rz = np.array([[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]])
    return ry @ rx @ rz


class Camera:
    __slots__ = ("position", "rotation", "fov", "z_near")

    def __init__(self, fov=70.0, z_near=0.1):
        self.position = np.array([0.0, 2.0, -10.0], dtype=np.float64)
        self.rotation = np.zeros(3, dtype=np.float64)
        self.fov = fov
        self.z_near = z_near

    def look_at(self, tx, ty, tz):
        dx = tx - self.position[0]
        dy = ty - self.position[1]
        dz = tz - self.position[2]
        self.rotation[1] = math.atan2(dx, dz)
        self.rotation[0] = -math.atan2(dy, math.hypot(dx, dz))
        self.rotation[2] = 0.0
