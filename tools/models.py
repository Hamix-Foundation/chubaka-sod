import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from chubaka.layout import *
from objgen import Obj, material

OUT = os.path.join(ROOT, "chubaka", "assets", "game", "models")

PLASTER = material("plaster", (1, 1, 1), "plaster")
PLASTER_D = material("plaster_dark", (1, 1, 1), "plaster_dark")
WOOD = material("wood_panel", (1, 1, 1), "wood_panel")
WOOD_D = material("wood_dark", (1, 1, 1), "wood_dark")
OLD = material("wood_old", (1, 1, 1), "wood_old")
PLY = material("plywood", (1, 1, 1), "plywood")
PARQ = material("parquet", (1, 1, 1), "parquet")
BASE = material("floor_base", (0.08, 0.06, 0.05), None)
DOOR = material("door_paint", (1, 1, 1), "door_paint")
BOARD = material("chalkboard", (1, 1, 1), "chalkboard")
DESK = material("desk_top", (1, 1, 1), "desk_top")
METAL = material("metal_black", (1, 1, 1), "metal_black")
CAB_R = material("cabinet_red", (1, 1, 1), "cabinet_red")
CAB_Y = material("cabinet_yellow", (1, 1, 1), "cabinet_yellow")
CEIL = material("ceiling", (1, 1, 1), "ceiling")
TERR = material("terrazzo", (1, 1, 1), "terrazzo")
C_GREEN = material("corridor_green", (1, 1, 1), "corridor_green")
C_CREAM = material("corridor_cream", (1, 1, 1), "corridor_cream")
C_WOOD = material("corridor_wood", (1, 1, 1), "corridor_wood")
SHADE = material("lamp_shade", (1, 1, 1), "lamp_shade")
LACE = material("lace", (1, 1, 1), "lace")
GREY = material("curtain_grey", (1, 1, 1), "curtain_grey")
WHITE = material("plastic_white", (1, 1, 1), "plastic_white")
RAD = material("radiator", (1, 1, 1), "radiator")
PAPER = material("paper", (1, 1, 1), "paper")
BRICK = material("brick", (1, 1, 1), "brick")
RUBBLE = material("rubble", (1, 1, 1), "rubble")
CLOTH = material("cloth_dark", (1, 1, 1), "cloth_dark")
BOOK = material("book_blue", (1, 1, 1), "book_blue")
LEATHER = material("leather", (1, 1, 1), "leather")
PUMPKIN = material("pumpkin", (1, 1, 1), "pumpkin")
LEAF = material("leaf_brown", (1, 1, 1), "leaf_brown")
CARD = material("cardboard", (1, 1, 1), "cardboard")
GRASS = material("grass", (1, 1, 1), "grass")
BUSH = material("bush", (1, 1, 1), "bush")
YARD_WALL = material("yard_wall", (1, 1, 1), "yard_wall")
ROOF = material("roof", (1, 1, 1), "roof")
CONCRETE = material("concrete", (1, 1, 1), "concrete")
BARK = material("bark", (1, 1, 1), "bark")
GRAVEL = material("gravel", (1, 1, 1), "gravel")
DARK = material("dark", (0.04, 0.04, 0.05), None)
GLASS = material("glass", (1, 1, 1), "glass")
STEEL = material("steel", (0.55, 0.56, 0.58), None)
BRASS = material("brass", (0.62, 0.5, 0.25), None)
RED = material("red_plastic", (0.6, 0.12, 0.14), None)
WICKER = material("wicker", (0.72, 0.68, 0.58), None)
WINDOW_GLOW = material("window_dark", (0.12, 0.13, 0.16), None)
BLACK = material("black", (0.05, 0.05, 0.06), None)
MAP = material("worldmap", (1, 1, 1), "worldmap")
PORTRAIT = material("portrait", (1, 1, 1), "portrait")
SOIL = material("soil", (1, 1, 1), "soil")
WING = material("wing_wall", (1, 1, 1), "wing_wall")
STUCCO = material("stucco_peel", (1, 1, 1), "stucco_peel")
GRAFFITI = material("graffiti", (1, 1, 1), "graffiti")
PANELW = material("panel_wall", (1, 1, 1), "panel_wall")
BLUE_DOOR = material("blue_door", (0.16, 0.34, 0.62), None)
GREEN_SIGN = material("green_sign", (0.1, 0.55, 0.22), None)
EXT_RED = material("extinguisher", (0.62, 0.1, 0.08), None)
GLASS_VASE = material("vase_glass", (0.62, 0.7, 0.72), None)
BOARDS = material("boards", (0.5, 0.4, 0.28), None)
DESK_TOP = material("desk_top", (0.84, 0.74, 0.55), None)
DESK_FRAME = material("desk_frame", (0.07, 0.07, 0.08), None)
DESK_SHELF = material("desk_shelf", (0.55, 0.42, 0.28), None)


def x_edges(extra=()):
    n = 18
    e = sorted(set([round(-HX + 2 * HX * i / n, 4) for i in range(n + 1)] + [round(v, 4) for v in extra]))
    return e


def walls():
    o = Obj("Walls")
    t = 1.6
    P = "plaster"
    cut = [(zc - WINDOW_W / 2, zc + WINDOW_W / 2) for zc in WINDOW_Z]
    o.rect(P, PLASTER, "x", -HX, 0, WINDOW_Y0, -HZ, HZ, 1, t)
    o.rect(P, PLASTER, "x", -HX, WINDOW_Y1, WALL_TOP, -HZ, HZ, 1, t)
    zs = [-HZ] + [v for c in cut for v in c] + [HZ]
    for i in range(0, len(zs), 2):
        if zs[i + 1] - zs[i] > 1e-6:
            o.rect(P, PLASTER, "x", -HX, WINDOW_Y0, WINDOW_Y1, zs[i], zs[i + 1], 1, t)
    for a, b in cut:
        o.rect("reveal", PLASTER, "y", WINDOW_Y0, -HX - WALL, -HX, a, b, 1, t)
        o.rect("reveal", PLASTER, "y", WINDOW_Y1, -HX - WALL, -HX, a, b, -1, t)
        o.rect("reveal", PLASTER, "z", a, -HX - WALL, -HX, WINDOW_Y0, WINDOW_Y1, 1, t)
        o.rect("reveal", PLASTER, "z", b, -HX - WALL, -HX, WINDOW_Y0, WINDOW_Y1, -1, t)
    o.rect(P, PLASTER, "x", HX, 0, WALL_TOP, -HZ, HZ, -1, t)
    o.rect(P, PLASTER, "z", HZ, -HX, HX, 0, WALL_TOP, -1, t)
    ox0, ox1, oy = DOOR_X0 - 0.15, DOOR_X1 + 0.15, DOOR_H + 0.15
    o.rect(P, PLASTER, "z", -HZ, -HX, ox0, 0, WALL_TOP, 1, t)
    o.rect(P, PLASTER, "z", -HZ, ox1, HX, 0, WALL_TOP, 1, t)
    o.rect(P, PLASTER, "z", -HZ, ox0, ox1, oy, WALL_TOP, 1, t)
    z0, z1 = -HZ - WALL, -HZ
    o.rect("reveal", PLASTER, "x", ox0, 0, oy, z0, z1, 1, t)
    o.rect("reveal", PLASTER, "x", ox1, 0, oy, z0, z1, -1, t)
    o.rect("reveal", PLASTER, "y", oy, ox0, ox1, z0, z1, -1, t)
    edges = x_edges()
    for zc, face in ((-HZ, 1), (HZ, -1)):
        for a, b in zip(edges, edges[1:]):
            ya, yb = ceiling_y(a), ceiling_y(b)
            o.quad(P, PLASTER, [(a, WALL_TOP, zc), (b, WALL_TOP, zc), (b, yb, zc), (a, ya, zc)], [(a / t, WALL_TOP / t), (b / t, WALL_TOP / t), (b / t, yb / t), (a / t, ya / t)], (0, 0, face))
    return o


def wainscot(seed=3):
    rng = random.Random(seed)
    o = Obj("Wainscot")
    w = 0.13
    h = PANEL

    def board(face, pos, u, hh, lift):
        mat = WOOD if rng.random() > 0.2 else WOOD_D
        uvo = (rng.random(), rng.random())
        if face == "L":
            o.box("boards", mat, (-HX + 0.012 + lift, hh / 2, u), (0.024, hh, w - 0.008), 0.6, uvo=uvo, skip=("nx",))
        elif face == "R":
            o.box("boards", mat, (HX - 0.012 - lift, hh / 2, u), (0.024, hh, w - 0.008), 0.6, uvo=uvo, skip=("px",))
        elif face == "B":
            o.box("boards", mat, (u, hh / 2, -HZ + 0.012 + lift), (w - 0.008, hh, 0.024), 0.6, uvo=uvo, skip=("nz",))
        else:
            o.box("boards", mat, (u, hh / 2, HZ - 0.012 - lift), (w - 0.008, hh, 0.024), 0.6, uvo=uvo, skip=("pz",))

    win = [(zc - WINDOW_W / 2 - 0.05, zc + WINDOW_W / 2 + 0.05) for zc in WINDOW_Z]
    for wall in ("L", "R", "B", "F"):
        span = 2 * HZ if wall in "LR" else 2 * HX
        n = int(span / w)
        for i in range(n):
            u = -span / 2 + (i + 0.5) * w
            hh = h
            if wall == "R" and BOARD_Z[0] - 0.05 < u < BOARD_Z[1] + 0.05:
                hh = BOARD_Y[0] - 0.05
            if wall == "B" and DOOR_X0 - 0.3 < u < DOOR_X1 + 0.3:
                continue
            if wall == "L" and any(a < u < b for a, b in win):
                hh = WINDOW_Y0 - 0.04
            r = rng.random()
            if r < 0.05:
                continue
            if r > 0.9:
                hh *= rng.uniform(0.35, 0.85)
            lift = rng.uniform(0.0, 0.02) if r > 0.95 else 0.0
            board(wall, None, u, hh, lift)
    o.box("rail", WOOD_D, (-HX + 0.03, h + 0.0185, 0), (0.07, 0.03, 2 * HZ), 0.4, skip=("nx",))
    o.box("rail", WOOD_D, (0, h + 0.0185, HZ - 0.03), (2 * HX, 0.03, 0.07), 0.4, skip=("pz",))
    for a, b in ((-HX, DOOR_X0 - 0.3), (DOOR_X1 + 0.3, HX)):
        o.box("rail", WOOD_D, ((a + b) / 2, h + 0.0185, -HZ + 0.03), (b - a, 0.03, 0.07), 0.4, skip=("nz",))
    return o


def floor(seed=5):
    rng = random.Random(seed)
    o = Obj("Floor")
    o.rect("base", BASE, "y", -0.03, -HX - WALL, HX + WALL, -HZ - WALL, HZ + WALL, 1, 4.0)
    width = 0.155
    n = int(2 * HX / width)
    for i in range(n):
        x0 = -HX + i * width + 0.003
        x1 = x0 + width - 0.006
        z = -HZ
        while z < HZ - 0.01:
            length = rng.uniform(1.0, 2.2)
            end = min(HZ, z + length)
            r = rng.random()
            if r > 0.03:
                k = rng.randrange(8)
                v0 = k / 8.0 + 0.02
                v1 = (k + 1) / 8.0 - 0.04
                u0 = rng.random()
                u1 = u0 + (end - z) / 2.0
                lift = 0.012 if r > 0.975 else 0.0
                o.quad("planks", PARQ, [(x0, lift, z + 0.003), (x1, lift, z + 0.003), (x1, lift, end - 0.003), (x0, lift, end - 0.003)], [(u0, v0), (u0, v1), (u1, v1), (u1, v0)], (0, 1, 0))
                if lift:
                    o.rect("planks", PARQ, "z", z + 0.003, x0, x1, 0.0, lift, -1, 1.0)
            z = end
    ox0, ox1 = DOOR_X0 - 0.15, DOOR_X1 + 0.15
    o.rect("threshold", WOOD_D, "y", 0.0, ox0, ox1, -HZ - WALL, -HZ, 1, 0.5)
    return o


def ceiling(seed=7):
    rng = random.Random(seed)
    o = Obj("Ceiling")
    hx0, hx1, hz0, hz1 = HOLE
    edges = x_edges((hx0, hx1))
    t = 1.8
    for a, b in zip(edges, edges[1:]):
        ya, yb = ceiling_y(a), ceiling_y(b)
        inside = a >= hx0 - 1e-6 and b <= hx1 + 1e-6
        spans = [(-HZ, hz0), (hz1, HZ)] if inside else [(-HZ, HZ)]
        for z0, z1 in spans:
            o.quad("vault", CEIL, [(a, ya, z0), (b, yb, z0), (b, yb, z1), (a, ya, z1)], [(a / t, z0 / t), (b / t, z0 / t), (b / t, z1 / t), (a / t, z1 / t)], (0, -1, 0))
    top = ceiling_y((hx0 + hx1) / 2) + 1.5
    cx, cz = (hx0 + hx1) / 2, (hz0 + hz1) / 2
    for dx, dz, w, d, face in ((hx0, cz, 0.1, hz1 - hz0, 1), (hx1, cz, 0.1, hz1 - hz0, -1)):
        o.rect("attic", OLD, "x", dx, ceiling_y(dx), top, hz0, hz1, face, 0.8)
    for zz, face in ((hz0, 1), (hz1, -1)):
        o.rect("attic", OLD, "z", zz, hx0, hx1, ceiling_y(hx0), top, face, 0.8)
    o.rect("attic", DARK, "y", top, hx0 - 1.0, hx1 + 1.0, hz0 - 1.0, hz1 + 1.0, -1, 1.0)
    for i in range(5):
        x = hx0 - 0.4 + i * (hx1 - hx0 + 0.8) / 4
        o.box("rafters", WOOD_D, (x, top - 0.9, cz), (0.09, 0.14, hz1 - hz0 + 1.6), 0.4, rot=(0, 0, rng.uniform(-0.04, 0.04)))
    for i in range(3):
        z = hz0 + 0.15 + i * (hz1 - hz0 - 0.3) / 2
        o.box("rafters", WOOD_D, (cx, top - 0.7, z), (hx1 - hx0 + 1.4, 0.1, 0.12), 0.4)
    for i in range(14):
        x = rng.uniform(hx0 - 0.1, hx1 + 0.1)
        z = rng.choice((hz0, hz1)) + rng.uniform(-0.08, 0.08)
        length = rng.uniform(0.4, 1.1)
        o.box("hanging", WOOD, (x, ceiling_y(x) - length / 2 * 0.9, z), (0.045, length, 0.02), 0.3, rot=(rng.uniform(-0.5, 0.5), 0, rng.uniform(-0.3, 0.3)))
    for i in range(8):
        x = rng.uniform(hx0, hx1)
        z = rng.uniform(hz0, hz1)
        o.box("hanging", CEIL, (x, ceiling_y(x) - 0.02, z), (rng.uniform(0.15, 0.4), 0.02, rng.uniform(0.1, 0.3)), 0.5, rot=(0, rng.uniform(0, 3), 0))
    return o


def windows(seed=11):
    rng = random.Random(seed)
    o = Obj("Windows")
    xf = -HX - 0.3
    h = WINDOW_Y1 - WINDOW_Y0 - 0.02
    yc = (WINDOW_Y0 + WINDOW_Y1) / 2
    w = WINDOW_W - 0.02
    for k, zc in enumerate(WINDOW_Z):
        for dz in (-w / 2 + 0.04, w / 2 - 0.04):
            o.box("frame", WHITE, (xf, yc, zc + dz), (0.1, h, 0.08), 0.5)
        o.box("frame", WHITE, (xf, yc, zc), (0.1, h, 0.07), 0.5)
        o.box("frame", WHITE, (xf, WINDOW_Y0 + 0.05, zc), (0.1, 0.08, w - 0.16), 0.5)
        o.box("frame", WHITE, (xf, WINDOW_Y1 - 0.05, zc), (0.1, 0.08, w - 0.16), 0.5)
        o.box("handle", WHITE, (xf + 0.07, yc - 0.1, zc + 0.06), (0.03, 0.12, 0.025), 0.2)
        o.box("sill", WHITE, (-HX - 0.05, WINDOW_Y0 - 0.025, zc), (0.8, 0.05, WINDOW_W + 0.16), 0.6)
        o.box("sill", WHITE, (-HX + 0.34, WINDOW_Y0 - 0.04, zc), (0.06, 0.07, WINDOW_W + 0.16), 0.6)
        o.box("radiator", RAD, (-HX + 0.07, 0.5, zc), (0.1, 0.62, 1.1), 0.6, skip=("nx",))
        for j in range(12):
            o.box("radiator", RAD, (-HX + 0.07, 0.5, zc - 0.5 + j * 0.091), (0.12, 0.66, 0.02), 0.4, skip=("nx",))
        o.cylinder("radiator", METAL, (-HX + 0.07, 0.86, zc), 0.015, 1.14, "z", 6)
        o.cylinder("radiator", METAL, (-HX + 0.07, 0.18, zc), 0.015, 1.14, "z", 6)
        o.box("rod", METAL, (-HX + 0.08, 3.08, zc), (0.03, 0.03, WINDOW_W + 0.5), 0.3)
        o.box("curtain", LACE, (-HX + 0.1, 2.62, zc), (0.012, 0.58, WINDOW_W + 0.1), 0.5, uvo=(rng.random(), 0))
        for side in (-1, 1):
            length = rng.uniform(1.3, 2.0)
            o.box("curtain", LACE, (-HX + 0.13 + rng.uniform(0, 0.02), 2.9 - length / 2, zc + side * 0.7), (0.012, length, rng.uniform(0.35, 0.5)), 0.5, rot=(rng.uniform(-0.04, 0.04), 0, rng.uniform(-0.04, 0.04)), uvo=(rng.random(), rng.random()))
        side = 1 if k == 1 else -1
        length = rng.uniform(1.8, 2.5)
        o.box("curtain", GREY, (-HX + 0.2, 3.0 - length / 2, zc + side * 0.95), (0.03, length * 0.8, 0.26), 0.5, rot=(0, 0, rng.uniform(-0.03, 0.03)))
    zv = WINDOW_Z[1] - 0.45
    o.cylinder("props", GLASS_VASE, (-HX + 0.2, WINDOW_Y0 + 0.1, zv), 0.05, 0.2, "y", 8, 0.3, r_top=0.035)
    for i in range(9):
        a = rng.uniform(0, 6.28)
        o.box("props", LEAF, (-HX + 0.2 + math.cos(a) * 0.07, WINDOW_Y0 + 0.3 + rng.uniform(0, 0.14), zv + math.sin(a) * 0.07), (0.12, 0.012, 0.1), 0.2, rot=(rng.uniform(-0.6, 0.6), a, rng.uniform(-0.6, 0.6)))
    for i in range(5):
        o.box("props", BOOK, (-HX + 0.22, WINDOW_Y0 + 0.016 + i * 0.03, WINDOW_Z[0] + 0.35), (0.22, 0.028, 0.3), 0.3, rot=(0, rng.uniform(-0.2, 0.2), 0))
    return o


def blackboard():
    o = Obj("Blackboard")
    x = HX - 0.03
    z0, z1 = BOARD_Z
    y0, y1 = BOARD_Y
    yc = (y0 + y1) / 2
    zc = (z0 + z1) / 2
    o.box("frame", WOOD_D, (x, yc, zc), (0.05, y1 - y0 + 0.12, z1 - z0 + 0.12), 0.5, skip=("px",))
    cuts = (z0, z0 + 1.1, z1 - 1.1, z1)
    for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
        off = -0.025 if i != 1 else 0.0
        o.box("panel", BOARD, (x - 0.035 + off, yc, (a + b) / 2), (0.03, y1 - y0, b - a - 0.02), 1.2, uvo=(i * 0.3, 0.0), skip=("px",))
    for zz in cuts[1:3]:
        o.box("strip", WHITE, (x - 0.055, yc, zz), (0.012, y1 - y0, 0.025), 0.5)
    o.box("tray", WOOD_D, (x - 0.07, y0 - 0.04, zc), (0.12, 0.04, z1 - z0 + 0.1), 0.5)
    o.box("tray", WOOD_D, (x - 0.125, y0 - 0.015, zc), (0.012, 0.03, z1 - z0 + 0.1), 0.5)
    for k in range(4):
        o.box("chalk", WHITE, (x - 0.08, y0 - 0.005, zc - 0.5 + k * 0.4), (0.012, 0.012, 0.07), 0.2, rot=(0, k * 0.5, 0))
    o.box("frame", WOOD_D, (x - 0.02, y1 + 0.1, zc), (0.05, 0.05, z1 - z0 + 0.1), 0.5)
    return o


def door_frame():
    o = Obj("DoorFrame")
    zp = DOOR_Z
    fx0, fx1 = DOOR_X0 - 0.12, DOOR_X1 + 0.12
    top = DOOR_H + 0.08
    o.box("frame", DOOR, ((fx0 + DOOR_X0) / 2 - 0.0, top / 2, zp), (0.14, top, 0.12), 0.6)
    o.box("frame", DOOR, ((fx1 + DOOR_X1) / 2 + 0.0, top / 2, zp), (0.14, top, 0.12), 0.6)
    o.box("frame", DOOR, ((fx0 + fx1) / 2, DOOR_H + 0.04, zp), (fx1 - fx0 + 0.02, 0.1, 0.12), 0.6)
    leaf_w = LEAF_W - 0.015
    xc = DOOR_X1 - leaf_w / 2 - 0.02
    o.box("leaf", DOOR, (xc, DOOR_H / 2, zp), (leaf_w, DOOR_H - 0.04, 0.045), 1.0)
    for y0, y1 in ((0.15, 0.95), (1.1, DOOR_H - 0.25)):
        o.box("leaf", DOOR, (xc, (y0 + y1) / 2, zp + 0.027), (leaf_w - 0.2, y1 - y0, 0.012), 1.0, uvo=(0.3, 0.3), skip=("nz",))
        o.box("leaf", DOOR, (xc, (y0 + y1) / 2, zp - 0.027), (leaf_w - 0.2, y1 - y0, 0.012), 1.0, uvo=(0.3, 0.3), skip=("pz",))
    o.box("bolt", STEEL, (xc - 0.18, 1.05, zp + 0.04), (0.1, 0.035, 0.02), 0.2)
    o.box("bolt", STEEL, (xc - 0.2, 1.05, zp + 0.055), (0.04, 0.02, 0.012), 0.2)
    o.box("bolt", STEEL, (xc - 0.18, 1.05, zp - 0.04), (0.1, 0.035, 0.02), 0.2)
    sx = (DOOR_X0 + DOOR_X1) / 2 - 0.2
    o.box("clock", WHITE, (sx, 2.8, -HZ + 0.02), (0.34, 0.34, 0.03), 0.4)
    o.cylinder("clock", WHITE, (sx, 2.8, -HZ + 0.04), 0.17, 0.04, "z", 14, 0.3)
    o.cylinder("clock", RED, (sx, 2.8, -HZ + 0.038), 0.18, 0.02, "z", 14, 0.3)
    o.box("clock", BLACK, (sx, 2.84, -HZ + 0.065), (0.012, 0.11, 0.006), 0.1)
    o.box("clock", BLACK, (sx + 0.04, 2.78, -HZ + 0.065), (0.09, 0.012, 0.006), 0.1, rot=(0, 0, 0.6))
    for dx in (0.0, 0.1):
        o.box("socket", WHITE, (DOOR_X1 + 0.5 + dx, 1.4, -HZ + 0.02), (0.07, 0.07, 0.025), 0.2)
    o.box("calendar", PAPER, (CABINET_X[1] - 1.2, 2.1, -HZ + 0.015), (0.14, 0.22, 0.02), 0.3)
    return o


def door_leaf():
    o = Obj("DoorLeaf")
    w = LEAF_W - 0.02
    h = DOOR_H - 0.04
    o.box("leaf", DOOR, (w / 2, h / 2, 0), (w, h, 0.045), 1.0)
    for y0, y1 in ((0.15, 0.95), (1.1, h - 0.2)):
        o.box("panel", DOOR, (w / 2, (y0 + y1) / 2, 0.027), (w - 0.2, y1 - y0, 0.012), 1.0, uvo=(0.1, 0.1), skip=("nz",))
        o.box("panel", DOOR, (w / 2, (y0 + y1) / 2, -0.027), (w - 0.2, y1 - y0, 0.012), 1.0, uvo=(0.1, 0.1), skip=("pz",))
    for s in (1, -1):
        o.box("handle", STEEL, (w - 0.07, 1.05, s * 0.045), (0.03, 0.12, 0.012), 0.2)
        o.box("handle", STEEL, (w - 0.1, 1.05, s * 0.06), (0.1, 0.02, 0.02), 0.2)
    for y in (0.25, 1.1, 2.0):
        o.box("hinge", STEEL, (0.01, y, 0.0), (0.02, 0.1, 0.055), 0.2)
    return o


def cabinet():
    o = Obj("Cabinet")
    x0, x1 = CABINET_X
    z0, z1 = -HZ, -HZ + 0.5
    h = 1.1
    o.box("body", CAB_R, ((x0 + x1) / 2, h / 2, (z0 + z1) / 2), (x1 - x0, h, z1 - z0), 0.5, skip=("nz",))
    o.box("top", CAB_Y, ((x0 + x1) / 2, h + 0.02, (z0 + z1) / 2), (x1 - x0 + 0.04, 0.04, z1 - z0 + 0.03), 0.5)
    split = x0 + 0.9
    zf = z1 + 0.005
    layout = (
        (x0 + 0.02, split - 0.01, 0.02, 0.37, CAB_R), (x0 + 0.02, split - 0.01, 0.39, 0.74, CAB_Y), (x0 + 0.02, split - 0.01, 0.76, 1.08, CAB_Y),
        (split + 0.01, x1 - 0.02, 0.02, 0.5, CAB_Y), (split + 0.01, x1 - 0.02, 0.52, 1.08, CAB_R),
    )
    for a, b, ya, yb, mat in layout:
        o.box("doors", mat, ((a + b) / 2, (ya + yb) / 2, zf), (b - a, yb - ya, 0.02), 0.5, skip=("nz",))
        o.box("handles", STEEL, (b - 0.06 if a < split else a + 0.06, yb - 0.08, zf + 0.02), (0.012, 0.09, 0.02), 0.2)
    o.cylinder("basket", WICKER, (x1 - 0.35, h + 0.14, (z0 + z1) / 2 + 0.02), 0.11, 0.2, "y", 10, 0.3)
    o.box("books", BOOK, (x1 - 0.8, h + 0.07, (z0 + z1) / 2), (0.26, 0.1, 0.19), 0.3, rot=(0, 0.1, 0))
    o.box("books", PAPER, (x1 - 0.8, h + 0.14, (z0 + z1) / 2), (0.24, 0.04, 0.17), 0.3, rot=(0, -0.2, 0))
    o.box("heater", RED, (x0 + 0.55, h + 0.1, (z0 + z1) / 2), (0.2, 0.06, 0.16), 0.3)
    o.cylinder("heater", BLACK, (x0 + 0.55, h + 0.26, (z0 + z1) / 2 + 0.01), 0.11, 0.07, "z", 12, 0.3)
    return o


def coat_rack(seed=9):
    rng = random.Random(seed)
    o = Obj("CoatRack")
    zc = -HZ + 0.06
    x0, x1 = RACK_X
    o.box("board", WOOD_D, ((x0 + x1) / 2, 1.78, zc), (x1 - x0, 0.14, 0.04), 0.5)
    o.box("board", WOOD, ((x0 + x1) / 2, 1.6, zc), (x1 - x0, 0.2, 0.025), 0.5)
    o.box("shelf", WOOD_D, ((x0 + x1) / 2, 2.1, zc + 0.12), (x1 - x0, 0.03, 0.25), 0.5)
    for i in range(10):
        x = x0 + 0.1 + i * (x1 - x0 - 0.2) / 9
        o.box("hooks", METAL, (x, 1.76, zc + 0.04), (0.02, 0.02, 0.08), 0.2)
        if i in (2, 6):
            continue
        h = rng.uniform(0.75, 1.05)
        w = rng.uniform(0.2, 0.3)
        o.box("coats", CLOTH, (x, 1.7 - h / 2, zc + 0.1), (w, h, 0.1), 0.5, rot=(rng.uniform(-0.05, 0.05), 0, rng.uniform(-0.03, 0.03)), uvo=(rng.random(), rng.random()))
        o.sphere("coats", CLOTH, (x, 1.7 - h * 0.12, zc + 0.1), (w * 0.62, h * 0.16, 0.07), 3, 6, 0.5)
    return o


def chair():
    o = Obj("Chair")
    o.box("seat", PLY, (0, 0.44, 0), (0.4, 0.035, 0.4), 0.5)
    o.box("back", PLY, (0, 0.72, -0.19), (0.4, 0.26, 0.025), 0.5)
    for sx in (-0.17, 0.17):
        for sz in (-0.17, 0.17):
            o.cylinder("legs", METAL, (sx, 0.21, sz), 0.013, 0.42, "y", 6, 0.2)
    o.cylinder("legs", METAL, (0, 0.3, 0.17), 0.01, 0.34, "x", 5, 0.2)
    o.cylinder("legs", METAL, (0, 0.3, -0.17), 0.01, 0.34, "x", 5, 0.2)
    for sx in (-0.17, 0.17):
        o.cylinder("legs", METAL, (sx, 0.58, -0.19), 0.013, 0.3, "y", 6, 0.2)
    return o


def teacher_desk():
    o = Obj("TeacherDesk")
    o.box("top", DESK, (0, 0.74, 0), (1.5, 0.05, 0.75), 0.8)
    for x in (-0.68, 0.68):
        o.box("sides", OLD, (x, 0.37, 0), (0.05, 0.72, 0.7), 0.8)
    o.box("back", OLD, (0, 0.5, -0.33), (1.3, 0.5, 0.03), 0.8)
    o.box("drawers", PLY, (0.45, 0.55, 0.0), (0.5, 0.3, 0.6), 0.6)
    for k in range(2):
        o.box("drawers", WOOD_D, (0.45, 0.62 - k * 0.17, 0.31), (0.44, 0.13, 0.015), 0.4)
        o.box("drawers", STEEL, (0.45, 0.62 - k * 0.17, 0.325), (0.1, 0.012, 0.012), 0.2)
    o.cylinder("lamp", METAL, (-0.5, 0.78, 0.18), 0.06, 0.03, "y", 10, 0.2)
    o.cylinder("lamp", METAL, (-0.5, 0.88, 0.18), 0.01, 0.2, "y", 6, 0.2)
    o.sphere("lamp", LEATHER, (-0.5, 1.0, 0.18), (0.11, 0.07, 0.11), 4, 10, 0.3)
    return o


def office_chair():
    o = Obj("OfficeChair")
    o.cylinder("post", METAL, (0, 0.3, 0), 0.028, 0.34, "y", 8, 0.2)
    for i in range(5):
        a = i * 2 * math.pi / 5
        o.box("base", METAL, (math.cos(a) * 0.18, 0.1, math.sin(a) * 0.18), (0.36, 0.03, 0.045), 0.2, rot=(0, -a, 0))
        o.sphere("base", BLACK, (math.cos(a) * 0.33, 0.04, math.sin(a) * 0.33), (0.035, 0.035, 0.035), 3, 6, 0.2)
    o.box("seat", LEATHER, (0, 0.5, 0), (0.5, 0.08, 0.5), 0.5)
    o.box("back", LEATHER, (0, 0.86, -0.24), (0.46, 0.55, 0.07), 0.5, rot=(-0.08, 0, 0))
    for s in (-1, 1):
        o.box("arms", METAL, (s * 0.27, 0.68, 0.0), (0.04, 0.03, 0.4), 0.2)
        o.box("arms", METAL, (s * 0.27, 0.6, -0.1), (0.03, 0.18, 0.03), 0.2)
    return o


def pigeonholes():
    o = Obj("Pigeonholes")
    w, h, d = 0.8, 0.55, 0.3
    o.box("shell", PLY, (0, h / 2, 0), (w, h, d), 0.5, skip=("pz",))
    for i in range(1, 8):
        o.box("cells", WOOD_D, (-w / 2 + i * w / 8, h / 2, 0.01), (0.012, h, d), 0.3)
    for j in range(1, 3):
        o.box("cells", WOOD_D, (0, j * h / 3, 0.01), (w, 0.012, d), 0.3)
    o.box("papers", PAPER, (0.12, 0.17, 0.08), (0.14, 0.2, 0.01), 0.2)
    return o


def lamp_fixture():
    o = Obj("Lamp")
    o.box("housing", PLASTER_D, (0, 0, 0), (0.2, 0.05, 1.3), 0.5)
    for s in (-1, 1):
        o.box("housing", WHITE, (s * 0.085, -0.03, 0), (0.025, 0.07, 1.3), 0.5, rot=(0, 0, s * 0.5))
    for s in (-1, 1):
        o.cylinder("chain", METAL, (0, 0.14, s * 0.5), 0.006, 0.3, "y", 4, 0.2)
    o.box("end", WHITE, (0, -0.005, 0.66), (0.21, 0.07, 0.02), 0.3)
    o.box("end", WHITE, (0, -0.005, -0.66), (0.21, 0.07, 0.02), 0.3)
    return o


def torch():
    o = Obj("Torch")
    o.cylinder("body", BLACK, (0, 0, 0), 0.022, 0.2, "z", 8, 0.2)
    o.cylinder("head", BRASS, (0, 0, 0.1), 0.03, 0.04, "z", 8, 0.2)
    o.cylinder("cap", STEEL, (0, 0, -0.06), 0.024, 0.04, "z", 8, 0.2)
    return o


def props():
    paper = Obj("Paper")
    paper.box("sheet", PAPER, (0, 0.0015, 0), (0.21, 0.003, 0.297), 0.3)
    brick = Obj("Brick")
    brick.box("brick", BRICK, (0, 0.03, 0), (0.12, 0.06, 0.06), 0.2)
    rubble = Obj("Rubble")
    rubble.box("chunk", RUBBLE, (0, 0.03, 0), (0.1, 0.06, 0.07), 0.2, rot=(0.2, 0.4, 0.1))
    rubble.box("chunk", RUBBLE, (0.07, 0.02, 0.04), (0.06, 0.04, 0.05), 0.2, rot=(0.1, 1.0, 0.3))
    plank = Obj("Plank")
    plank.box("plank", WOOD_D, (0, 0.025, 0), (0.05, 0.04, 1.0), 0.3)
    book = Obj("Book")
    book.box("book", BOOK, (0, 0.012, 0), (0.17, 0.024, 0.24), 0.3)
    bag = Obj("Bag")
    bag.box("bag", CLOTH, (0, 0.18, 0), (0.3, 0.36, 0.14), 0.4)
    bag.box("bag", LEATHER, (0, 0.14, 0.08), (0.24, 0.16, 0.04), 0.3)
    box = Obj("Carton")
    box.box("carton", CARD, (0, 0.15, 0), (0.4, 0.3, 0.3), 0.5)
    return [paper, brick, rubble, plank, book, bag, box]


def corridor(seed=13):
    rng = random.Random(seed)
    o = Obj("Corridor")
    x0, x1 = CORRIDOR_X
    g0, g1 = PASSAGE_X
    zn = -HZ - WALL
    zf = zn - CORRIDOR_W
    pz = zf - PASSAGE_D
    h = CORRIDOR_H
    t = 1.6
    split = 1.55
    stripe = material("stripe_dark", (0.12, 0.3, 0.2), None)
    o.rect("floor", TERR, "y", 0.0, x0, x1, zf, zn, 1, 1.2)
    o.rect("floor", TERR, "y", 0.0, g0, g1, pz, zf, 1, 1.2)
    o.rect("ceiling", C_CREAM, "y", h, x0, x1, zf, zn, -1, t)
    o.rect("ceiling", C_CREAM, "y", h, g0, g1, pz, zf, -1, t)
    ox0, ox1, oy = DOOR_X0 - 0.15, DOOR_X1 + 0.15, DOOR_H + 0.15
    for part, mat, ya, yb in (("near", C_GREEN, 0.0, split), ("near_u", C_CREAM, split, h)):
        segs = [(x0, ox0), (ox1, x1)] if ya < oy else [(x0, x1)]
        for a, b in segs:
            o.rect(part, mat, "z", zn, a, b, ya, yb, -1, t)
    o.rect("near_u", C_CREAM, "z", zn, ox0, ox1, oy, h, -1, t)
    o.rect("stripe", stripe, "z", zn, x0, x1, split - 0.03, split + 0.02, -1, t)
    for part, mat, ya, yb in (("far", C_GREEN, 0.0, split), ("far_u", C_CREAM, split, h)):
        for a, b in ((x0, g0), (g1, x1)):
            o.rect(part, mat, "z", zf, a, b, ya, yb, 1, t)
    for a, b in ((x0, g0), (g1, x1)):
        o.rect("stripe", stripe, "z", zf, a, b, split - 0.03, split + 0.02, 1, t)
    for xs, face in ((g0, 1), (g1, -1)):
        o.rect("pass", C_GREEN, "x", xs, 0.0, split, pz, zf, face, t)
        o.rect("pass_u", C_CREAM, "x", xs, split, h, pz, zf, face, t)
        o.rect("stripe", stripe, "x", xs, split - 0.03, split + 0.02, pz, zf, face, t)
    o.rect("pass", C_GREEN, "z", pz, g0, g1, 0.0, split, 1, t)
    o.rect("pass_u", C_CREAM, "z", pz, g0, g1, split, h, 1, t)
    for xe, face in ((x0, 1), (x1, -1)):
        o.rect("end", C_GREEN, "x", xe, 0.0, split, zf, zn, face, t)
        o.rect("end", C_CREAM, "x", xe, split, h, zf, zn, face, t)
    for x in (-6.0, 6.4):
        o.box("doors", C_WOOD, (x, 1.1, zn - 0.03), (1.0, 2.2, 0.06), 0.6)
        o.box("doors", WOOD_D, (x, 1.0, zn - 0.065), (0.8, 0.9, 0.012), 0.6)
        o.box("doors", WOOD_D, (x, 1.9, zn - 0.065), (0.8, 0.5, 0.012), 0.6)
        o.box("doors", STEEL, (x + 0.38, 1.05, zn - 0.09), (0.02, 0.12, 0.03), 0.2)
    for x in (-0.7, 0.9):
        o.box("doors", C_WOOD, (x, 1.1, pz + 0.03), (0.9, 2.2, 0.06), 0.6)
        o.box("doors", WOOD_D, (x, 1.0, pz + 0.065), (0.7, 0.9, 0.012), 0.6)
        o.box("doors", STEEL, (x + 0.33, 1.05, pz + 0.09), (0.02, 0.12, 0.03), 0.2)
    zc = (zf + zn) / 2
    for x in (-7.0, -3.5, 0.0, 3.5, 7.0):
        o.box("lamps", C_WOOD, (x, h - 0.04, zc), (0.7, 0.08, 0.3), 0.4)
        o.box("lamps", SHADE, (x, h - 0.095, zc), (0.62, 0.025, 0.24), 0.3)
    o.box("lamps", C_WOOD, (0.1, h - 0.04, (zf + pz) / 2), (0.7, 0.08, 0.3), 0.4)
    o.box("lamps", SHADE, (0.1, h - 0.095, (zf + pz) / 2), (0.62, 0.025, 0.24), 0.3)
    o.cylinder("extinguisher", EXT_RED, (g0 - 0.5, 0.95, zf + 0.1), 0.07, 0.42, "y", 8, 0.3)
    o.cylinder("extinguisher", BLACK, (g0 - 0.5, 1.2, zf + 0.1), 0.03, 0.08, "y", 6, 0.3)
    o.box("extinguisher", BLACK, (g0 - 0.5, 1.5, zf + 0.025), (0.3, 0.3, 0.012), 0.2)
    o.box("sign", GREEN_SIGN, (g0 + 0.03, 2.55, zf - 1.0), (0.04, 0.22, 0.6), 0.3)
    o.box("sign", WHITE, (g0 + 0.055, 2.55, zf - 1.0), (0.012, 0.06, 0.4), 0.2)
    o.box("vent", DARK, (x1 - 0.6, 2.6, zn - 0.02), (0.4, 0.2, 0.03), 0.3)
    for x, dz in ((g0 - 1.0, 0.4), (g0 - 1.5, 0.35), (g1 + 1.4, 0.4)):
        o.box("clutter", CARD, (x, 0.2, zf + dz), (0.4, 0.4, 0.4), 0.5, rot=(0, rng.uniform(-0.4, 0.4), 0))
    return o


def roof_x(o, x0, x1, z0, z1, y0, ridge):
    zm = (z0 + z1) / 2.0
    o.quad("roof", ROOF, [(x0, y0, z0), (x1, y0, z0), (x1, ridge, zm), (x0, ridge, zm)], [(0, 0), (4, 0), (4, 1), (0, 1)], (0, 0.6, -1))
    o.quad("roof", ROOF, [(x0, ridge, zm), (x1, ridge, zm), (x1, y0, z1), (x0, y0, z1)], [(0, 0), (4, 0), (4, 1), (0, 1)], (0, 0.6, 1))
    o.tri("roof", ROOF, [(x0, y0, z0), (x0, ridge, zm), (x0, y0, z1)], [(0, 0), (0.5, 0.5), (1, 0)], (-1, 0, 0))
    o.tri("roof", ROOF, [(x1, y0, z0), (x1, y0, z1), (x1, ridge, zm)], [(0, 0), (1, 0), (0.5, 0.5)], (1, 0, 0))


def yard(seed=21):
    rng = random.Random(seed)
    o = Obj("Yard")
    gx = -HX - WALL
    gy = GROUND_Y
    o.rect("ground", GRASS, "y", gy, gx - 90, gx, -90, 90, 1, 4.0)
    o.rect("ground", SOIL, "y", gy + 0.02, gx - 22, gx - 8, -13, -1.5, 1, 3.0)

    def win_x(xf, face, z0, z1, ys, ww=1.0, hh=1.3, step=2.6):
        n = max(1, int((z1 - z0) / step))
        for r in ys:
            for k in range(n):
                zz = z0 + (k + 0.5) * (z1 - z0) / n
                o.box("windows", WINDOW_GLOW, (xf + face * 0.02, r, zz), (0.04, hh, ww), 0.5)
                o.box("windows", WHITE, (xf + face * 0.03, r, zz), (0.04, 0.06, ww + 0.1), 0.3)
                o.box("windows", WHITE, (xf + face * 0.03, r, zz), (0.04, hh + 0.1, 0.06), 0.3)

    def win_z(zf, face, x0, x1, ys, ww=1.0, hh=1.3, step=2.6):
        n = max(1, int((x1 - x0) / step))
        for r in ys:
            for k in range(n):
                xx = x0 + (k + 0.5) * (x1 - x0) / n
                o.box("windows", WINDOW_GLOW, (xx, r, zf + face * 0.02), (ww, hh, 0.04), 0.5)
                o.box("windows", WHITE, (xx, r, zf + face * 0.03), (ww + 0.1, 0.06, 0.04), 0.3)
                o.box("windows", WHITE, (xx, r, zf + face * 0.03), (0.06, hh + 0.1, 0.04), 0.3)

    wx0, wx1, wz0, wz1, wh = -8.0, -21.0, 6.0, 15.0, 5.6
    o.box("wing", WING, ((wx0 + wx1) / 2, gy + wh / 2, (wz0 + wz1) / 2), (wx0 - wx1, wh, wz1 - wz0), 3.0)
    roof_x(o, wx1 - 0.4, wx0 + 0.4, wz0 - 0.5, wz1 + 0.5, gy + wh, gy + wh + 2.2)
    win_z(wz0, -1, wx1, wx0, (gy + 1.1, gy + 4.0), 1.1, 1.4, 2.8)
    win_x(wx0, 1, wz0, wz1, (gy + 1.1, gy + 4.0), 1.1, 1.4, 2.8)
    o.cylinder("pipes", RED, (wx0 - 3.4, gy + wh / 2, wz0 - 0.1), 0.06, wh, "y", 6, 0.5)
    o.cylinder("pipes", STEEL, (wx0 - 6.0, gy + 2.5, wz0 - 0.12), 0.1, 1.0, "y", 8, 0.5)
    o.cylinder("pipes", STEEL, (wx0 - 6.5, gy + 2.5, wz0 - 0.12), 0.1, 1.0, "y", 8, 0.5)
    o.box("wing", WING, (wx0 - 0.9, gy + 0.6, wz0 + 1.8), (1.8, 1.2, 3.6), 3.0)

    rx0, rx1, rz0, rz1, rh = -18.0, -24.0, -10.0, -2.5, 3.4
    cx, cz = (rx0 + rx1) / 2, (rz0 + rz1) / 2
    o.box("ruin", GRAFFITI, (rx0 - 0.2, gy + rh / 2, cz), (0.4, rh, rz1 - rz0), 3.0)
    o.box("ruin", STUCCO, (cx, gy + rh / 2, rz0 + 0.2), (rx0 - rx1, rh, 0.4), 3.0)
    o.box("ruin", STUCCO, (cx, gy + rh / 2 - 0.4, rz1 - 0.2), (rx0 - rx1, rh - 0.8, 0.4), 3.0)
    o.box("ruin", STUCCO, (rx1 + 0.2, gy + rh / 2, cz), (0.4, rh, rz1 - rz0), 3.0)
    o.rect("ruin", DARK, "y", gy + 0.05, rx1, rx0, rz0, rz1, 1, 3.0)
    for k in range(6):
        zz = rz0 + 0.8 + k * 1.1
        o.box("ruin", STUCCO, (rx0 - 0.2, gy + rh + 0.15 * rng.random(), zz), (0.4, 0.3 + 0.5 * rng.random(), 1.0), 2.0)
    o.box("door", BLUE_DOOR, (rx0 + 0.02, gy + 1.15, -6.4), (0.06, 2.1, 1.0), 1.0)
    o.box("door", DARK, (rx0 + 0.02, gy + 1.9, -8.4), (0.06, 1.2, 1.0), 1.0)
    o.box("door", BOARDS, (rx0 + 0.03, gy + 1.9, -4.2), (0.06, 1.2, 1.0), 1.0)
    o.box("door", DARK, (rx0 + 0.02, gy + 1.9, -3.0), (0.06, 1.2, 0.8), 1.0)
    o.box("brick", BRICK, (-26.4, gy + 3.0, -5.8), (0.6, 6.0, 7.0), 2.0)
    for k in range(5):
        o.box("brick", BRICK, (-26.4, gy + 6.0 + 0.3 * k, -9.0 + k * 1.4), (0.6, 0.5 + 0.4 * rng.random(), 1.3), 2.0)
    o.box("scaffold", METAL, (-25.8, gy + 4.5, -5.8), (0.08, 0.08, 7.0), 0.5)
    for k in range(6):
        o.box("scaffold", METAL, (-25.8, gy + 3.2 + 0.7 * k, -8.9 + k * 1.2), (0.08, 3.0, 0.08), 0.5)

    bx0, bx1, bz0, bz1, bh = -14.0, -25.0, -17.0, -27.0, 8.0
    o.box("house", STUCCO, ((bx0 + bx1) / 2, gy + bh / 2, (bz0 + bz1) / 2), (bx0 - bx1, bh, bz0 - bz1), 3.0)
    o.box("roof", ROOF, ((bx0 + bx1) / 2, gy + bh + 0.3, (bz0 + bz1) / 2), (bx0 - bx1 + 0.8, 0.6, bz0 - bz1 + 0.8), 2.0)
    win_x(bx0, 1, bz1, bz0, (gy + 2.2, gy + 5.4), 1.0, 1.4, 3.0)
    win_z(bz0, 1, bx1, bx0, (gy + 2.2, gy + 5.4), 1.0, 1.4, 3.0)
    o.box("shed", BRICK, (-11.5, gy + 1.1, -15.0), (4.5, 2.2, 3.4), 2.0)
    o.box("shed", ROOF, (-11.5, gy + 2.3, -15.0), (5.0, 0.2, 3.9), 2.0)
    o.box("shed", DARK, (-9.23, gy + 1.0, -15.0), (0.06, 1.8, 1.0), 1.0)

    px0 = -56.0
    o.box("block", PANELW, (px0, gy + 14.0, -4.0), (10.0, 28.0, 44.0), 4.0)
    for r in range(9):
        for k in range(14):
            zz = -24.0 + k * 3.0
            o.box("block_windows", WINDOW_GLOW, (px0 + 5.03, gy + 2.4 + r * 3.0, zz), (0.06, 1.5, 1.3), 0.5)
            o.box("block_windows", WHITE, (px0 + 5.05, gy + 1.6 + r * 3.0, zz), (0.06, 0.08, 1.6), 0.3)

    for i in range(5):
        a = rng.uniform(0, 6.28)
        r = rng.uniform(0.0, 1.0)
        o.box("bricks", BRICK, (-9.8 + math.cos(a) * r, gy + 0.18, -6.6 + math.sin(a) * r), (rng.uniform(0.6, 1.0), 0.3, rng.uniform(0.4, 0.7)), 1.0, rot=(0, rng.uniform(0, 3), 0))
    o.box("bricks", BRICK, (-9.8, gy + 0.45, -6.6), (2.4, 0.9, 1.6), 1.0, rot=(0, 0.2, 0))
    o.box("bricks", BRICK, (-9.6, gy + 0.9, -6.5), (1.6, 0.5, 1.0), 1.0, rot=(0, 0.35, 0))
    o.cylinder("stump", BARK, (-9.0, gy + 0.7, -3.0), 0.45, 1.4, "y", 8, 1.0, r_top=0.38)
    o.sphere("bush", BUSH, (-7.2, gy + 1.0, -0.4), (1.1, 1.0, 1.1), 4, 8, 2.0)
    o.sphere("bush", BUSH, (-7.6, gy + 0.8, 0.5), (0.9, 0.8, 0.9), 4, 8, 2.0)
    for i in range(14):
        x = -rng.uniform(6.0, 14.0)
        z = rng.uniform(-3.0, 10.0)
        s_ = rng.uniform(0.4, 0.9)
        o.sphere("bush", BUSH, (x, gy + s_ * 0.5, z), (s_ * 1.3, s_ * 0.7, s_ * 1.1), 3, 7, 2.0)
    for tx, tz, th in ((-12.5, -1.5, 6.5), (-15.0, 3.0, 5.5)):
        o.cylinder("trees", BARK, (tx, gy + th / 2, tz), 0.22, th, "y", 6, 1.0, r_top=0.1)
        for j in range(7):
            a = j * 0.9 + rng.uniform(0, 0.5)
            ln = rng.uniform(1.6, 2.6)
            o.box("trees", BARK, (tx + math.cos(a) * ln * 0.35, gy + th - 0.4 + rng.uniform(-0.8, 1.2), tz + math.sin(a) * ln * 0.35), (ln, 0.07, 0.07), 1.0, rot=(0, -a, rng.uniform(0.2, 0.6)))
        o.sphere("crowns", BUSH, (tx, gy + th + 0.5, tz), (1.0, 0.6, 1.0), 3, 6, 2.0)
    for i in range(10):
        o.box("rubble", RUBBLE, (-rng.uniform(10.0, 16.0), gy + 0.15, rng.uniform(-11.0, -3.0)), (rng.uniform(0.4, 0.9), 0.3, rng.uniform(0.4, 0.8)), 1.0, rot=(0, rng.uniform(0, 3), 0))
    o.v = [(x, y, -z) for x, y, z in o.v]
    return o


def desk():
    o = Obj("Desk")
    o.box("top", DESK_TOP, (0.0, 0.735, 0.0), (1.2, 0.03, 0.6), 0.6)
    o.box("edge", DESK_FRAME, (0.0, 0.715, 0.0), (1.18, 0.01, 0.58), 0.3)
    for sx in (-1, 1):
        for sz in (-1, 1):
            o.box("legs", DESK_FRAME, (sx * 0.55, 0.36, sz * 0.26), (0.035, 0.72, 0.035), 0.3)
        o.box("frame", DESK_FRAME, (sx * 0.55, 0.3, 0.0), (0.03, 0.03, 0.52), 0.3)
    for sz in (-1, 1):
        o.box("frame", DESK_FRAME, (0.0, 0.3, sz * 0.26), (1.1, 0.03, 0.03), 0.3)
    o.box("shelf", DESK_SHELF, (0.0, 0.5, 0.0), (1.06, 0.02, 0.5), 0.5)
    return o


def hangings():
    o = Obj("Hangings")
    y0, y1 = MAP_Y
    z0, z1 = MAP_Z
    xp = -HX + 0.055
    o.box("frame", WOOD_D, (-HX + 0.03, (y0 + y1) / 2, (z0 + z1) / 2), (0.04, y1 - y0 + 0.06, z1 - z0 + 0.06), 0.5, skip=("nx",))
    o.quad("map", MAP, [(xp, y0, z0), (xp, y0, z1), (xp, y1, z1), (xp, y1, z0)], [(1, 0), (0, 0), (0, 1), (1, 1)], (1, 0, 0))
    px = CABINET_X[1] - 0.3
    o.box("frame", WOOD_D, (px, 2.03, -HZ + 0.02), (0.6, 0.8, 0.03), 0.5, skip=("nz",))
    zq = -HZ + 0.04
    o.quad("portrait", PORTRAIT, [(px - 0.25, 1.67, zq), (px + 0.25, 1.67, zq), (px + 0.25, 2.39, zq), (px - 0.25, 2.39, zq)], [(0, 0), (1, 0), (1, 1), (0, 1)], (0, 0, 1))
    return o


def main():
    os.makedirs(OUT, exist_ok=True)
    objs = [walls(), wainscot(), floor(), ceiling(), windows(), blackboard(), door_frame(), door_leaf(), cabinet(), hangings(), desk(), coat_rack(), chair(), teacher_desk(), office_chair(), pigeonholes(), lamp_fixture(), torch(), corridor(), yard()] + props()
    for o in objs:
        p = o.write(OUT)
        print(os.path.basename(p), len(o.v), sum(len(f) for f in o.parts.values()))
    mtl = os.path.join(OUT, "desk.mtl")
    with open(mtl, "w", newline="\n") as f:
        for name, tex in (("Table Top", "desk_top"), ("Walls", "wood_old"), ("Chrome Dirty", "metal_black"), ("Mat.1", "metal_black"), ("default", "metal_black")):
            f.write(f"newmtl {name}\nKd 1 1 1\nmap_Kd ../textures/{tex}.png\n\n")


if __name__ == "__main__":
    main()
