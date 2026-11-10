import math
import random

import numpy as np

from chubaka.floorplan import DOOR_H, GROUND, GUARD_CLIP, HEIGHT, WINDOW_DATA, plan, rect_difference
from chubaka.geometry import Batch
from lysyk.engine.mesh import Mesh

WALL_LOW = (86, 172, 144)
WALL_HIGH = (178, 214, 172)
CEILING = (214, 218, 206)
GROUND_COLOR = (44, 48, 38)
DOOR_COLOR = (92, 64, 44)
RAIL_COLOR = (50, 158, 98)
BASE_COLOR = (74, 68, 68)
GLASS_COLOR = (58, 78, 112)
FRAME_COLOR = (226, 224, 214)
CURTAIN_COLOR = (238, 196, 158)
RADIATOR_COLOR = (228, 228, 222)
WALL_TONES = {
    "channel": ((198, 144, 134), (228, 178, 162)),
    "toilet": ((150, 192, 198), (212, 228, 228)),
    "archive": ((146, 126, 98), (192, 178, 150)),
    "room": ((104, 156, 126), (204, 200, 174)),
}
FLOORS = {
    "corridor": (96, 90, 90),
    "room": (104, 76, 40),
    "toilet": (150, 160, 154),
    "archive": (84, 62, 44),
}
BAND = 1.55
RAIL_H = 0.1
RAIL_OUT = 0.05
SILL = 0.98
HEAD = 2.7
GUARD_SILL = 0.92
GUARD_HEAD = 2.97
GUARD_LINTEL = 2.45
CORRIDOR_FLOORS = {
    "corr_top_w": (100, 92, 88),
    "corr_mid": (96, 92, 92),
    "corr_top_e": (104, 92, 88),
    "lobby": (92, 92, 100),
    "corr_west": (84, 92, 104),
    "corr_east": (108, 88, 86),
    "corr_bottom": (88, 100, 90),
    "channel": (108, 90, 100),
}
PLATE = (30, 30, 34)
DIGIT = (240, 234, 206)
DIGIT_W = 0.26
DIGIT_H = 0.44
DIGIT_T = 0.055
DIGIT_GAP = 0.1
PLATE_W = 0.92
PLATE_H = 0.62
PLATE_Y = 2.72
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
    "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg",
}


class Building:
    def __init__(self, structure, props, ground, doors, glass=None):
        self.structure = structure
        self.props = props
        self.ground = ground
        self.doors = doors
        self.glass = glass

    @property
    def triangles(self):
        return sum(m.triangle_count for m in (self.structure, self.props, self.ground, self.glass) if m is not None)


def shade_by_height(mesh, floor=0.6, height=1.2):
    v = np.asarray(mesh.vertices)
    c = np.asarray(mesh.colors).copy()
    k = floor + (1.0 - floor) * np.clip(v[:, 1] / height, 0.0, 1.0)
    c[:, :3] = np.clip(c[:, :3].astype(np.float32) * k[:, None], 0, 255).astype(np.uint8)
    return Mesh(v, c, np.asarray(mesh.faces))


def box_rect(batch, rect, y0, y1, color):
    x0, x1, z0, z1 = rect
    batch.box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0), color)


def region_nodes(fp, name):
    return [n.position for nid, n in fp.nodes.items() if fp.node_region.get(nid) is not None and fp.node_region[nid].name == name]


def door_centers(fp, region):
    out = []
    x0, x1, z0, z1 = region.rect
    for cut in fp.cuts:
        if cut.kind != "door":
            continue
        cx0, cx1, cz0, cz1 = cut.rect
        if cx1 >= x0 - 0.6 and cx0 <= x1 + 0.6 and cz1 >= z0 - 0.6 and cz0 <= z1 + 0.6:
            out.append(((cx0 + cx1) / 2, (cz0 + cz1) / 2))
    return out


def clear_of(point, others, radius):
    return all(math.hypot(point[0] - o[0], point[1] - o[1]) > radius for o in others)


def furnish_classroom(fp, region, props, rng, models):
    x0, x1, z0, z1 = region.rect
    avoid = [(p[0], p[2]) for p in region_nodes(fp, region.name)] + door_centers(fp, region)
    w, d = x1 - x0, z1 - z0
    if w < 4.0 or d < 4.0:
        return
    if models is not None:
        desks = models.arrays("Desk")
        chairs = models.arrays("Chair")
    box_x = x1 - 0.03
    props.box((box_x, 1.55, (z0 + z1) / 2), (0.05, 1.1, min(3.2, d - 1.0)), (34, 54, 44))
    x = x0 + 1.4
    while x < x1 - 2.4:
        z = z0 + 1.1
        while z < z1 - 1.0:
            if clear_of((x, z), avoid, 1.5):
                px, pz = x + rng.uniform(-0.05, 0.05), z + rng.uniform(-0.04, 0.04)
                yaw = -math.pi / 2 + rng.uniform(-0.03, 0.03)
                if models is not None:
                    for v, c, f in desks:
                        props.mesh_arrays(v, c, f, (px, 0.0, pz), (0.0, yaw, 0.0))
                    if rng.random() < 0.7:
                        for v, c, f in chairs:
                            props.mesh_arrays(v, c, f, (px - 0.68, 0.0, pz + rng.uniform(-0.3, 0.3)), (0.0, math.pi / 2 + rng.uniform(-0.3, 0.3), 0.0))
                else:
                    props.box((px, 0.4, pz), (0.6, 0.8, 1.2), (110, 80, 50))
            z += 1.25
        x += 1.9


def furnish_toilet(region, props):
    x0, x1, z0, z1 = region.rect
    n = max(2, int((x1 - x0) / 1.1))
    for i in range(n):
        x = x0 + 0.5 + i * ((x1 - x0 - 1.0) / max(1, n - 1))
        props.box((x, 0.9, z1 - 1.0), (0.05, 1.8, 1.8), (180, 190, 186))
        props.box((x, 0.25, z1 - 0.35), (0.4, 0.5, 0.5), (220, 224, 222))
    props.box(((x0 + x1) / 2, 0.85, z0 + 0.25), (min(2.4, x1 - x0 - 1.0), 0.12, 0.45), (210, 214, 212))


def furnish_archive(region, props, rng):
    x0, x1, z0, z1 = region.rect
    for z in (z0 + 0.35, z1 - 0.35):
        props.box(((x0 + x1) / 2, 1.1, z), (x1 - x0 - 0.8, 2.2, 0.4), (72, 54, 40))
        for i in range(6):
            props.box((x0 + 0.7 + i * (x1 - x0 - 1.4) / 5, 1.2, z + (0.22 if z < (z0 + z1) / 2 else -0.22)), (0.3, 1.8, 0.05), (rng.randint(60, 150), rng.randint(60, 120), rng.randint(50, 100)))


def digit_boxes(ch):
    t, w, h = DIGIT_T, DIGIT_W, DIGIT_H
    parts = {
        "a": (0.0, h / 2 - t / 2, w, t),
        "b": (w / 2 - t / 2, h / 4, t, h / 2),
        "c": (w / 2 - t / 2, -h / 4, t, h / 2),
        "d": (0.0, -h / 2 + t / 2, w, t),
        "e": (-w / 2 + t / 2, -h / 4, t, h / 2),
        "f": (-w / 2 + t / 2, h / 4, t, h / 2),
        "g": (0.0, 0.0, w, t),
    }
    return [parts[s] for s in SEGMENTS[ch]]


def door_plate(batch, center, normal, label):
    nx, nz = normal
    rx, rz = -nz, nx
    along_x = abs(rx) > 0.5

    def put(u, v, depth, width, height, thick, color):
        px = center[0] + rx * u + nx * depth
        pz = center[1] + rz * u + nz * depth
        size = (width, height, thick) if along_x else (thick, height, width)
        batch.box((px, PLATE_Y + v, pz), size, color)

    put(0.0, 0.0, 0.02, PLATE_W, PLATE_H, 0.04, PLATE)
    pitch = DIGIT_W + DIGIT_GAP
    for i, ch in enumerate(label):
        cu = (i - (len(label) - 1) / 2.0) * pitch
        for su, sv, sw, sh in digit_boxes(ch):
            put(cu + su, sv, 0.055, sw, sh, DIGIT_T, DIGIT)


def plate_pose(cut, corridor):
    x0, x1, z0, z1 = cut.rect
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    rx0, rx1, rz0, rz1 = corridor.rect
    if cut.axis == "e":
        sign = 1.0 if (rx0 + rx1) / 2 > cx else -1.0
        return (rx0 if sign > 0 else rx1, cz), (sign, 0.0)
    sign = 1.0 if (rz0 + rz1) / 2 > cz else -1.0
    return (cx, rz0 if sign > 0 else rz1), (0.0, sign)


def door_plates(fp, batch):
    for a, b, cut in fp.links:
        ra, rb = fp.regions[a], fp.regions[b]
        for room, corridor in ((ra, rb), (rb, ra)):
            if corridor.kind == "corridor" and room.name.startswith("room_"):
                center, normal = plate_pose(cut, corridor)
                door_plate(batch, center, normal, room.name[5:])


def wall_tones(fp, owner):
    region = fp.regions.get(owner)
    if region is None:
        return WALL_TONES.get("room")
    if owner in WALL_TONES:
        return WALL_TONES[owner]
    if region.kind in WALL_TONES:
        return WALL_TONES[region.kind]
    return (WALL_LOW, WALL_HIGH)


def wall_box(batch, rect, low, high, y0=GROUND, y1=HEIGHT + 0.12):
    if y0 < BAND:
        box_rect(batch, rect, y0, min(BAND, y1), low)
    if y1 > BAND:
        box_rect(batch, rect, max(BAND, y0), y1, high)


def seg_rect(kind, rect, a0, a1):
    e0, e1, n0, n1 = rect
    if kind == "h":
        return (a0, a1, n0, n1)
    return (e0, e1, a0, a1)


def rail_rect(kind, rect, a0, a1):
    e0, e1, n0, n1 = seg_rect(kind, rect, a0, a1)
    if kind == "h":
        return (e0, e1, n0 - RAIL_OUT, n1 + RAIL_OUT)
    return (e0 - RAIL_OUT, e1 + RAIL_OUT, n0, n1)


def rail_boxes(s, kind, rect, a0, a1):
    for piece in rect_difference(rail_rect(kind, rect, a0, a1), GUARD_CLIP):
        box_rect(s, piece, BAND - RAIL_H / 2, BAND + RAIL_H / 2, RAIL_COLOR)


def window_specs(rect, kind):
    e0, e1, n0, n1 = rect
    lo, hi = (n0, n1) if kind == "h" else (e0, e1)
    out = []
    for k, wlo, whi, centers, width, furnished in WINDOW_DATA:
        if k != kind or abs(lo - wlo) > 0.03 or hi > whi + 0.03:
            continue
        a0, a1 = (e0, e1) if kind == "h" else (n0, n1)
        for c in centers:
            if a0 <= c - width / 2 and c + width / 2 <= a1:
                out.append((c, width, furnished))
    return sorted(out)


def inside_sign(fp, owner, kind, rect):
    region = fp.regions.get(owner)
    e0, e1, n0, n1 = rect
    if region is None:
        return 1.0
    ce, cn = region.center
    if kind == "h":
        return 1.0 if cn > (n0 + n1) / 2 else -1.0
    return 1.0 if ce > (e0 + e1) / 2 else -1.0


def window_dressing(props, glass, kind, rect, sign, c, width, furnished):
    e0, e1, n0, n1 = rect
    thin0, thin1 = (n0, n1) if kind == "h" else (e0, e1)
    mid = (thin0 + thin1) / 2
    face = thin1 if sign > 0 else thin0
    sill, head = (SILL, HEAD) if furnished else (GUARD_SILL, GUARD_HEAD)

    def put(u, y, depth, w, h, off, color, target):
        t = face + sign * off if furnished else mid
        if kind == "h":
            target.box((c + u, y, t), (w, h, depth), color)
        else:
            target.box((t, y, c + u), (depth, h, w), color)

    pane_t = mid if furnished else thin0 + 0.06
    ymid = (sill + head) / 2
    if kind == "h":
        glass.box((c, ymid, pane_t), (width, head - sill, 0.04), GLASS_COLOR)
    else:
        glass.box((pane_t, ymid, c), (0.04, head - sill, width), GLASS_COLOR)
    if not furnished:
        return
    h = head - sill
    put(0.0, sill - 0.02, 0.24, width + 0.24, 0.05, 0.12, FRAME_COLOR, props)
    put(0.0, head + 0.03, 0.06, width + 0.12, 0.06, 0.03, FRAME_COLOR, props)
    put(-width / 2 - 0.03, sill + h / 2, 0.06, 0.06, h, 0.03, FRAME_COLOR, props)
    put(width / 2 + 0.03, sill + h / 2, 0.06, 0.06, h, 0.03, FRAME_COLOR, props)
    put(0.0, 0.52, 0.1, min(1.1, width - 0.2), 0.62, 0.1, RADIATOR_COLOR, props)
    for side in (-1.0, 1.0):
        put(side * (width / 2 - 0.2), (sill + head) / 2 + 0.1, 0.07, 0.42, h + 0.4, 0.14, CURTAIN_COLOR, props)
    put(0.0, head + 0.3, 0.05, width + 0.5, 0.04, 0.16, (120, 96, 70), props)


def build_walls(fp, s, props, glass):
    for rect, owner in fp.visible_slabs():
        low, high = wall_tones(fp, owner)
        e0, e1, n0, n1 = rect
        kind = "h" if (n1 - n0) <= (e1 - e0) else "v"
        windows = window_specs(rect, kind)
        a0, a1 = (e0, e1) if kind == "h" else (n0, n1)
        sign = inside_sign(fp, owner, kind, rect)
        cursor = a0
        for c, width, furnished in windows:
            w0, w1 = c - width / 2, c + width / 2
            if w0 - cursor > 1e-6:
                wall_box(s, seg_rect(kind, rect, cursor, w0), low, high)
                rail_boxes(s, kind, rect, cursor, w0)
            sill, head = (SILL, HEAD) if furnished else (GUARD_SILL, GUARD_HEAD)
            wall_box(s, seg_rect(kind, rect, w0, w1), low, high, GROUND, sill)
            wall_box(s, seg_rect(kind, rect, w0, w1), low, high, head, HEIGHT + 0.12)
            window_dressing(props, glass, kind, rect, sign, c, width, furnished)
            cursor = w1
        if a1 - cursor > 1e-6:
            wall_box(s, seg_rect(kind, rect, cursor, a1), low, high)
            rail_boxes(s, kind, rect, cursor, a1)


def build_columns(fp, s):
    for e0, e1, n0, n1 in fp.columns:
        rect = (e0, e1, n0, n1)
        grow = 0.08
        box_rect(s, (e0 - grow, e1 + grow, n0 - grow, n1 + grow), 0.0, 0.14, BASE_COLOR)
        box_rect(s, rect, 0.0, BAND, WALL_LOW)
        box_rect(s, rect, BAND, HEIGHT, WALL_HIGH)
        box_rect(s, (e0 - RAIL_OUT, e1 + RAIL_OUT, n0 - RAIL_OUT, n1 + RAIL_OUT), BAND - RAIL_H / 2, BAND + RAIL_H / 2, RAIL_COLOR)


def build(models=None, seed=11):
    fp = plan()
    rng = random.Random(seed)
    s = Batch()
    props = Batch()
    ground = Batch()
    glass = Batch()
    ground.box((0.0, GROUND - 0.15, -20.0), (420.0, 0.2, 420.0), GROUND_COLOR)
    for region in fp.regions.values():
        if region.external:
            continue
        floor = CORRIDOR_FLOORS.get(region.name) or FLOORS.get(region.kind, FLOORS["room"])
        box_rect(s, region.rect, -0.12, 0.0, floor)
        box_rect(s, region.rect, HEIGHT, HEIGHT + 0.12, CEILING)
    build_walls(fp, s, props, glass)
    build_columns(fp, s)
    doors = []
    for cut in fp.cuts:
        x0, x1, z0, z1 = cut.rect
        if cut.kind != "guard":
            box_rect(s, cut.rect, -0.12, 0.0, FLOORS["corridor"])
            box_rect(s, cut.rect, HEIGHT, HEIGHT + 0.12, CEILING)
        if cut.kind == "guard":
            box_rect(s, (x0, x1, z0, min(z1, GUARD_CLIP[2])), GUARD_LINTEL, HEIGHT + 0.12, WALL_HIGH)
        elif cut.kind == "door":
            box_rect(s, cut.rect, DOOR_H, HEIGHT + 0.12, WALL_HIGH)
        if cut.kind != "door":
            continue
        if cut.leaf:
            length = (z1 - z0 if cut.axis == "e" else x1 - x0) - 0.1
            if cut.axis == "e":
                props.box(((x0 + x1) / 2 + length / 2, 1.1, z0 + 0.05), (length, 2.2, 0.05), DOOR_COLOR)
            else:
                props.box((x0 + 0.05, 1.1, (z0 + z1) / 2 + length / 2), (0.05, 2.2, length), DOOR_COLOR)
            doors.append(cut)
        else:
            for i in range(3):
                if cut.axis == "n":
                    props.box(((x0 + x1) / 2, -0.15 * (i + 1), z0 - 0.35 * (i + 1)), (x1 - x0 + 0.4, 0.15, 0.4), (120, 118, 110))
    for region in fp.regions.values():
        if region.external:
            continue
        if region.kind == "room":
            furnish_classroom(fp, region, props, rng, models)
        elif region.kind == "toilet":
            furnish_toilet(region, props)
        elif region.kind == "archive":
            furnish_archive(region, props, rng)
        elif region.kind == "corridor":
            x0, x1, z0, z1 = region.rect
            if z1 - z0 > 3.0 and x1 - x0 > 6.0:
                for x in np.arange(x0 + 3.0, x1 - 2.0, 6.0):
                    props.box((float(x), HEIGHT - 0.06, (z0 + z1) / 2), (0.1, 0.05, 1.2), (236, 232, 205))
    door_plates(fp, props)
    structure = shade_by_height(s.build())
    return Building(structure, props.build() if not props.empty else None, ground.build(), doors, glass.build() if not glass.empty else None)
