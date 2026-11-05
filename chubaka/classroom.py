import math
import random

import numpy as np

from chubaka import asset
from chubaka.geometry import Batch, jitter
from chubaka.layout import *
from lysyk.engine.mesh import Mesh, MeshBuilder
from lysyk.engine.model import load_textured

LEVELS = (1.6, 1.0, 0.75)
STEPS = {
    "Walls": 0.3, "Wainscot": 0.6, "Floor": 0.35, "Ceiling": 0.45, "Windows": 0.5, "Blackboard": 0.4, "Hangings": 0.07,
    "DoorFrame": 0.4, "DoorLeaf": 0.4, "Cabinet": 0.3, "CoatRack": 0.4, "Corridor": 0.6, "Yard": 4.0,
    "Chair": 0.3, "TeacherDesk": 0.4, "OfficeChair": 0.4, "Pigeonholes": 0.4, "Lamp": 0.4, "Torch": 0.4,
    "Paper": 1.0, "Brick": 1.0, "Rubble": 1.0, "Plank": 1.0, "Book": 1.0, "Bag": 1.0, "Carton": 1.0, "Desk": 0.3,
}
SHELL_PARTS = {"Walls": None, "Ceiling": None, "Windows": None}
TUBE_SIZE = (0.055, 0.025, 1.2)
LAMPS = ((-2.6, -2.0, False), (-2.6, 0.4, True), (2.2, -2.0, False), (2.2, 1.8, True), (-2.6, 2.0, None))
tx_book = (-4.4, 2.8)
DESK_PICKS = {(1, 1), (2, 3), (0, 2)}
WALL_COLOR = (92, 138, 130)


class Classroom:
    def __init__(self):
        self.floor = None
        self.shell = None
        self.trim = None
        self.furniture = None
        self.decor = None
        self.corridor = None
        self.outside = None
        self.sky = None
        self.tubes = []
        self.tube_mesh = None
        self.door_leaf = None
        self.door_hinge = (0.0, 0.0, 0.0)
        self.torch = None
        self.triangles = 0


def model_path(name):
    return asset("game", "models", name + ".obj")


class Models:
    def __init__(self, detail):
        self.k = LEVELS[max(0, min(2, detail))]
        self.cache = {}

    def parts(self, name, only=None, step=None):
        key = (name, None if only is None else tuple(only), step)
        if key not in self.cache:
            kw = {}
            self.cache[key] = load_textured(model_path(name), step=(step or STEPS[name]) * self.k, only=only, **kw)
        return self.cache[key]

    def mesh(self, name, only=None, tone=1.0, step=None):
        return merge([p.mesh for p in self.parts(name, only, step)], tone)

    def arrays(self, name, only=None):
        return [(np.asarray(p.mesh.vertices), np.asarray(p.mesh.colors), np.asarray(p.mesh.faces)) for p in self.parts(name, only)]


def merge(meshes, tone=1.0):
    vs, cs, fs = [], [], []
    base = 0
    for m in meshes:
        v = np.asarray(m.vertices)
        c = np.asarray(m.colors).copy()
        if tone != 1.0:
            c[:, :3] = np.clip(c[:, :3].astype(np.float32) * tone, 0, 255).astype(np.uint8)
        vs.append(v)
        cs.append(c)
        fs.append(np.asarray(m.faces, dtype=np.uint32) + base)
        base += len(v)
    return Mesh(np.concatenate(vs), np.concatenate(cs), np.concatenate(fs))


def grime(mesh, floor_dirt=0.55, height=0.9):
    v = np.asarray(mesh.vertices)
    c = np.asarray(mesh.colors).copy()
    k = floor_dirt + (1.0 - floor_dirt) * np.clip(v[:, 1] / height, 0.0, 1.0)
    top = np.clip((v[:, 1] - (WALL_TOP - 0.35)) / 0.35, 0.0, 1.0) * 0.18
    k = k - top
    c[:, :3] = np.clip(c[:, :3].astype(np.float32) * k[:, None], 0, 255).astype(np.uint8)
    return Mesh(v, c, np.asarray(mesh.faces))


def place(batch, arrays, pos, rot=None, scale=1.0, tint=None):
    for v, c, f in arrays:
        batch.mesh_arrays(v, c, f, pos, rot, scale, tint)


def lamp_pos(x, z):
    return (x, ceiling_y(x) - 0.3, z)


def build_steps(detail=1, seed=17):
    rng = random.Random(seed)
    models = Models(detail)
    out = Classroom()

    def shell():
        parts = [models.mesh("Walls", tone=1.12), models.mesh("Ceiling"), models.mesh("Windows")]
        parts[0] = grime(parts[0])
        batch = Batch()
        for i, (x, z, live) in enumerate(LAMPS):
            for v, c, f in models.arrays("Lamp"):
                if live is None:
                    batch.mesh_arrays(v, c, f, (x - 0.2, ceiling_y(x) - 0.55, z), (0.0, 0.0, -0.55))
                else:
                    batch.mesh_arrays(v, c, f, lamp_pos(x, z))
        out.shell = merge(parts + [batch.build()])

    def trim():
        out.trim = merge([models.mesh("Wainscot"), models.mesh("Blackboard"), models.mesh("Hangings"), models.mesh("DoorFrame"), models.mesh("Cabinet"), models.mesh("CoatRack")])

    def floor():
        planks = models.mesh("Floor", only=("planks", "threshold"), tone=0.95)
        base = models.mesh("Floor", only=("base",), step=8.0)
        out.floor = grime(merge([planks, base]), 0.7, 0.4)

    solids = [
        (TEACHER_DESK[0] - 0.4, TEACHER_DESK[0] + 0.4, TEACHER_DESK[1] - 0.78, TEACHER_DESK[1] + 0.78),
        (TEACHER_CHAIR[0] - 0.4, TEACHER_CHAIR[0] + 0.4, TEACHER_CHAIR[1] - 0.4, TEACHER_CHAIR[1] + 0.4),
        (CABINET_X[0], CABINET_X[1], -HZ, -HZ + 0.6),
    ]

    def free(x, z, m):
        return not any(x0 - m < x < x1 + m and z0 - m < z < z1 + m for x0, x1, z0, z1 in solids)

    def furniture():
        f = Batch()
        desks = models.arrays("Desk")
        chair = models.arrays("Chair")
        for r, x in enumerate(ROWS_X):
            for c, z in enumerate(DESKS_Z):
                if r == 0 and c == len(DESKS_Z) - 1:
                    continue
                px = x + rng.uniform(-0.04, 0.04)
                pz = z + rng.uniform(-0.03, 0.03)
                place(f, desks, (px, 0.0, pz), (0.0, -math.pi / 2 + rng.uniform(-0.03, 0.03), 0.0))
                solids.append((px - 0.4, px + 0.4, pz - 0.62, pz + 0.62))
                if (r, c) in DESK_PICKS:
                    for dz in (-0.28, 0.28):
                        place(f, chair, (px - 0.17 + rng.uniform(-0.02, 0.02), 1.2025, pz + dz + rng.uniform(-0.02, 0.02)), (math.pi, -math.pi / 2 + rng.uniform(-0.08, 0.08), 0.0))
                    continue
                for dz in (-0.3, 0.3):
                    if (r + c) % 4 == 1 and dz < 0:
                        continue
                    cx = px - 0.68 + rng.uniform(-0.12, 0.02)
                    cz = pz + dz + rng.uniform(-0.04, 0.04)
                    place(f, chair, (cx, 0.0, cz), (0.0, math.pi / 2 + rng.uniform(-0.2, 0.2), 0.0))
                    solids.append((cx - 0.3, cx + 0.3, cz - 0.3, cz + 0.3))
        tx, tz = TEACHER_DESK
        place(f, models.arrays("TeacherDesk"), (tx, 0.0, tz), (0.0, math.pi / 2, 0.0))
        place(f, models.arrays("OfficeChair"), (TEACHER_CHAIR[0], 0.0, TEACHER_CHAIR[1]), (0.0, -math.pi / 2, 0.0))
        place(f, models.arrays("Pigeonholes"), (tx - 0.2, 0.765, tz - 0.35), (0.0, math.pi / 2, 0.0), 0.9)
        out.furniture = f.build()

    def wall_zones(wall):
        if wall == "L":
            zones = [(z - WINDOW_W / 2 - 0.15, z + WINDOW_W / 2 + 0.15, WINDOW_Y0 - 0.2, 3.2) for z in WINDOW_Z]
            zones.append((MAP_Z[0] - 0.1, MAP_Z[1] + 0.1, MAP_Y[0] - 0.1, MAP_Y[1] + 0.1))
            return zones
        if wall == "R":
            return [(BOARD_Z[0] - 0.15, BOARD_Z[1] + 0.15, BOARD_Y[0] - 0.2, BOARD_Y[1] + 0.25)]
        if wall == "B":
            return [
                (DOOR_X0 - 0.4, DOOR_X1 + 0.4, 0.0, WALL_TOP),
                (CABINET_X[0], CABINET_X[1] + 0.2, 0.0, 2.5),
                (RACK_X[0], RACK_X[1], 1.4, 2.4),
                ((DOOR_X0 + DOOR_X1) / 2 - 0.5, (DOOR_X0 + DOOR_X1) / 2 + 0.1, 2.5, 3.1),
            ]
        return []

    def wall_free(wall, u, v, w, h):
        return not any(u - w / 2 < u1 and u + w / 2 > u0 and v - h / 2 < v1 and v + h / 2 > v0 for u0, u1, v0, v1 in wall_zones(wall))

    def decor():
        d = Batch()
        k = LEVELS[max(0, min(2, detail))]
        papers = models.arrays("Paper")
        bricks = models.arrays("Brick")
        rubble = models.arrays("Rubble")
        planks = models.arrays("Plank")
        books = models.arrays("Book")
        bags = models.arrays("Bag")
        hx0, hx1, hz0, hz1 = HOLE
        cx, cz = (hx0 + hx1) / 2, (hz0 + hz1) / 2
        d.box((cx, 0.004, cz), (hx1 - hx0 + 0.1, 0.008, hz1 - hz0 + 0.3), (40, 32, 26))
        for i in range(int(46 * 0.6 + 14 / k)):
            a = rng.uniform(0, 6.28)
            r = rng.uniform(0.05, 0.8)
            x, z = cx + math.cos(a) * r * 0.55, cz + math.sin(a) * r * 1.1
            if free(x, z, 0.12):
                place(d, rubble, (x, 0.012, z), (rng.uniform(-0.3, 0.3), rng.uniform(0, 3), rng.uniform(-0.3, 0.3)), rng.uniform(0.6, 1.6))
        for i in range(5):
            a = rng.uniform(0, 6.28)
            r = rng.uniform(0.1, 0.5)
            x, z = cx + math.cos(a) * r * 0.45, cz + math.sin(a) * r
            if free(x, z, 0.1):
                place(d, planks, (x, 0.012, z), (rng.uniform(-0.1, 0.1), rng.uniform(0, 3), rng.uniform(-0.1, 0.1)), rng.uniform(0.4, 0.8))

        def scatter(arrs, n, y, margin, scale=(1.0, 1.0), tint=None):
            placed = 0
            tries = 0
            while placed < n and tries < n * 12:
                tries += 1
                x = rng.uniform(-HX + 0.4, HX - 0.4)
                z = rng.uniform(-HZ + 0.4, HZ - 0.4)
                if not free(x, z, margin) or (hx0 - 0.3 < x < hx1 + 0.3 and hz0 - 0.3 < z < hz1 + 0.3):
                    continue
                place(d, arrs, (x, y + rng.random() * 0.004, z), (0.0, rng.uniform(0, 3.14), 0.0), rng.uniform(*scale), tint() if tint else None)
                placed += 1

        scatter(papers, int(30 / (k ** 0.5)), 0.014, 0.05)
        scatter(bricks, 8, 0.0, 0.25, (0.5, 1.3))
        palette = ((1.0, 1.0, 1.0), (2.2, 0.9, 0.8), (2.6, 2.2, 0.9), (0.9, 1.7, 1.0))
        scatter(books, 6, 0.014, 0.1, (1.0, 1.0), lambda: rng.choice(palette))
        spots = ((-4.2, -2.2), (-4.2, 0.5), (4.2, 2.0), (-0.9, 3.0), (1.0, 3.0))
        n = 0
        for (x, z), yaw in zip(spots, (0.6, 2.2, 4.0, 1.1, 3.3)):
            if n < 3 and free(x, z, 0.3):
                place(d, bags, (x, 0.0, z), (0.0, yaw, 0.0))
                n += 1
        place(d, books, (tx_book[0], 0.765, tx_book[1]), (0.0, 0.4, 0.0))
        place(d, books, (tx_book[0], 0.789, tx_book[1] + 0.02), (0.0, 0.9, 0.0), 0.9, (1.8, 1.0, 0.9))
        for i in range(14):
            wall = rng.choice(("L", "R", "B", "F"))
            w, h = rng.uniform(0.3, 0.9), rng.uniform(0.2, 0.6)
            col = rng.choice(((132, 128, 112), (58, 72, 58), (104, 70, 58), (86, 108, 98)))
            v = rng.uniform(PANEL + 0.2, WALL_TOP - 0.3)
            e = 0.012 + rng.random() * 0.006
            if wall in ("L", "R"):
                u = rng.uniform(-HZ + 0.5, HZ - 0.5)
            else:
                u = rng.uniform(-HX + 0.5, HX - 0.5)
            if not wall_free(wall, u, v, w, h):
                continue
            if wall == "L":
                d.box((-HX + e, v, u), (0.012, h, w), jitter(rng, col, 0.1))
            elif wall == "R":
                d.box((HX - e, v, u), (0.012, h, w), jitter(rng, col, 0.1))
            elif wall == "B":
                d.box((u, v, -HZ + e), (w, h, 0.012), jitter(rng, col, 0.1))
            else:
                d.box((u, v, HZ - e), (w, h, 0.012), jitter(rng, col, 0.1))
        for i in range(8):
            wall = rng.choice(("L", "R"))
            z = rng.uniform(-HZ + 0.4, HZ - 0.4)
            length = rng.uniform(0.4, 1.0)
            y = rng.uniform(2.3, WALL_TOP - 0.1)
            if wall_free(wall, z, y - length / 2, 0.3, length):
                x = -HX + 0.04 if wall == "L" else HX - 0.04
                d.box((x, y - length / 2, z), (0.014, length, rng.uniform(0.1, 0.25)), jitter(rng, WALL_COLOR, 0.12), rot=(rng.uniform(-0.1, 0.1), 0, rng.uniform(-0.06, 0.06)))
        out.decor = d.build()

    def corridor():
        out.corridor = models.mesh("Corridor", tone=1.25)

    def outside():
        out.outside = models.mesh("Yard", tone=1.5)
        sky = MeshBuilder()
        sky.ellipsoid((0, 0, 0), (300, 300, 300), (255, 255, 255), rings=8, segments=16, inside=True)
        out.sky = sky.build()

    def dynamic():
        leaf_parts = models.parts("DoorLeaf")
        out.door_leaf = merge([p.mesh for p in leaf_parts])
        out.door_hinge = (DOOR_X0 + 0.01, 0.02, DOOR_Z)
        out.torch = models.mesh("Torch")
        tubes = []
        for x, z, live in LAMPS:
            if live:
                tubes.append((x, ceiling_y(x) - 0.34, z))
        out.tubes = tubes
        t = MeshBuilder()
        t.box((0, 0, 0), TUBE_SIZE, (255, 244, 214))
        out.tube_mesh = t.build()
        out.triangles = sum(len(np.asarray(m.faces)) for m in (out.floor, out.shell, out.trim, out.furniture, out.decor, out.corridor, out.outside))

    return out, [shell, trim, floor, furniture, decor, corridor, outside, dynamic]


def build(detail=1, seed=17):
    out, steps = build_steps(detail, seed)
    for s in steps:
        s()
    return out
