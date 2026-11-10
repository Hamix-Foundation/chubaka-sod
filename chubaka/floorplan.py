import math
from collections import deque
from dataclasses import dataclass

T = 0.45
DOOR_W = 1.4
HEIGHT = 3.2
DOOR_H = 2.3
GROUND = -1.8
EYE = 1.5
GUARD_INTERIOR = (-4.8, 4.8, -3.4, 3.4)
GUARD_RECESS = 0.02
GUARD_CLIP = (GUARD_INTERIOR[0] - GUARD_RECESS, GUARD_INTERIOR[1] + GUARD_RECESS, GUARD_INTERIOR[2] - GUARD_RECESS, GUARD_INTERIOR[3] + GUARD_RECESS)
COLUMN_SIZE = 1.1


@dataclass
class Region:
    name: str
    kind: str
    e0: float
    e1: float
    n0: float
    n1: float
    open: tuple = ()
    external: bool = False
    title: str = ""

    @property
    def rect(self):
        return (self.e0, self.e1, self.n0, self.n1)

    def contains(self, x, z, margin=0.0):
        x0, x1, z0, z1 = self.rect
        return x0 - margin <= x <= x1 + margin and z0 - margin <= z <= z1 + margin

    @property
    def center(self):
        x0, x1, z0, z1 = self.rect
        return ((x0 + x1) / 2.0, (z0 + z1) / 2.0)


@dataclass
class Cut:
    e0: float
    e1: float
    n0: float
    n1: float
    kind: str = "door"
    axis: str = "e"
    leaf: bool = True

    @property
    def rect(self):
        return (self.e0, self.e1, self.n0, self.n1)


@dataclass
class Node:
    id: str
    e: float
    n: float
    title: str = ""

    @property
    def position(self):
        return (self.e, 0.0, self.n)


@dataclass
class CameraSpec:
    id: int
    label: str
    title: str
    e: float
    n: float
    heading: float
    height: float = 2.85
    pitch: float = 0.16
    fov: float = 74.0
    audio_only: bool = False
    zone: str = ""

    @property
    def position(self):
        return (self.e, self.height, self.n)

    @property
    def yaw(self):
        return self.heading % 360.0

    @property
    def forward(self):
        a = math.radians(self.yaw)
        return (math.sin(a), math.cos(a))

    @property
    def half_fov(self):
        return math.atan(math.tan(math.radians(self.fov) * 0.5) * 16.0 / 9.0)


REGION_DATA = (
    ("room_06", "room", -24.3, -14.7, -3.4, 3.4, (), False, "Кімната 06"),
    ("room_07", "room", -14.25, -5.25, -3.4, 3.4, (), False, "Кімната 07"),
    ("room_08", "guard", -4.8, 4.8, -3.4, 3.4, (), True, "Кімната 08"),
    ("room_09", "room", 5.25, 14.4, -3.4, 3.4, (), False, "Кімната 09"),
    ("room_10", "room", 14.85, 28.95, -3.4, 3.4, (), False, "Кімната 10"),
    ("room_11", "room", 29.4, 34.8, -7.45, 3.4, (), False, "Кімната 11"),
    ("corr_top_w", "corridor", -24.3, -10.1, -7.45, -3.85, ("e1",), False, "Коридор"),
    ("corr_mid", "corridor", -10.1, 8.7, -7.45, -3.85, ("e0", "e1", "n0", "n1"), False, "Коридор"),
    ("corr_top_e", "corridor", 8.7, 28.95, -7.45, -3.85, ("e0",), False, "Коридор"),
    ("lobby", "corridor", -10.1, 8.7, -13.55, -7.45, ("n1",), False, "Хол"),
    ("corr_west", "corridor", -24.3, -20.7, -39.9, -7.9, (), False, "Західний коридор"),
    ("corr_east", "corridor", 25.35, 28.95, -39.9, -7.9, (), False, "Східний коридор"),
    ("corr_bottom", "corridor", -20.7, 25.35, -29.55, -25.95, ("e0", "e1"), False, "Нижній коридор"),
    ("channel", "corridor", -2.2, 0.8, -25.5, -13.55, ("n1",), False, "Центральний прохід"),
    ("room_05", "room", -32.2, -24.75, -13.8, -7.9, (), False, "Кімната 05"),
    ("room_04", "room", -32.2, -24.75, -20.75, -14.25, (), False, "Кімната 04"),
    ("room_03", "room", -32.2, -24.75, -25.5, -21.2, (), False, "Кімната 03"),
    ("room_02", "room", -32.2, -24.75, -35.05, -25.95, (), False, "Кімната 02"),
    ("room_12", "room", 29.4, 36.85, -16.6, -7.9, (), False, "Кімната 12"),
    ("room_13", "room", 29.4, 36.85, -19.25, -17.05, (), False, "Кімната 13"),
    ("room_14", "room", 29.4, 36.85, -25.5, -19.7, (), False, "Кімната 14"),
    ("room_15", "room", 29.4, 36.85, -35.05, -25.95, (), False, "Кімната 15"),
    ("toilet_w", "toilet", -10.1, -2.65, -19.0, -14.0, (), False, "Туалет"),
    ("toilet_e", "toilet", 1.25, 8.7, -19.0, -14.0, (), False, "Туалет"),
    ("toilet_w2", "toilet", -10.1, -2.65, -25.5, -20.3, (), False, "Туалет"),
    ("archive", "archive", -14.9, -10.55, -25.5, -20.3, (), False, "Архів"),
    ("room_01", "room", -20.25, -11.05, -36.3, -30.0, (), False, "Кімната 01"),
    ("room_16", "room", 12.25, 24.9, -36.3, -30.0, (), False, "Кімната 16"),
)

GAP_DATA = (
    (-24.3, -20.7, -7.9, -7.45),
    (25.35, 28.95, -7.9, -7.45),
    (-20.7 - T, -20.7, -29.55, -25.95),
    (25.35, 25.35 + T, -29.55, -25.95),
    (-2.2, 0.8, -14.0, -13.55),
    (-2.2, 0.8, -25.95, -25.5),
    (-20.7, -20.25, -29.55, -25.95),
    (24.9, 25.35, -29.55, -25.95),
)

LINK_DATA = (
    ("room_11", "corr_top_e", -5.65),
    ("room_06", "corr_top_w", -19.5),
    ("room_07", "corr_top_w", -11.0),
    ("room_09", "corr_top_e", 10.0),
    ("room_10", "corr_top_e", 21.9),
    ("room_05", "corr_west", -10.85),
    ("room_04", "corr_west", -17.5),
    ("room_03", "corr_west", -23.35),
    ("room_02", "corr_west", -29.5),
    ("room_12", "corr_east", -12.25),
    ("room_13", "corr_east", -18.15),
    ("room_14", "corr_east", -22.6),
    ("room_15", "corr_east", -29.5),
    ("toilet_w", "channel", -16.5),
    ("toilet_e", "channel", -16.5),
    ("toilet_w2", "channel", -22.9),
    ("toilet_w2", "archive", -22.9),
    ("room_01", "corr_bottom", -15.6),
    ("room_16", "corr_bottom", 18.5),
)

EXIT_DATA = (
    ("corr_west", "n0", -22.5),
)

GUARD_DOOR_DATA = (0.65, 2.35, -3.85, -3.4)

SOLID_DATA = (
    ("guard_front", (-4.8, 4.8, -3.85, -3.4)),
    ("guard_north", (-4.8, 4.8, 3.4, 3.85)),
)

COLUMN_DATA = ((-4.7, -9.0), (3.3, -9.0), (-4.7, -12.0), (3.3, -12.0))

WINDOW_DATA = (
    ("h", -7.9, -7.45, (-18.5, -15.3, -12.1), 1.4, True),
    ("h", -7.9, -7.45, (11.5, 14.7, 17.9, 21.1), 1.4, True),
    ("v", -10.55, -10.1, (-9.2, -11.8), 1.4, True),
    ("v", 8.7, 9.15, (-9.2, -11.8), 1.4, True),
    ("v", -20.7, -20.25, (-10.8, -14.4, -18.0, -21.6), 1.4, True),
    ("v", 24.9, 25.35, (-10.8, -14.4, -18.0, -21.6), 1.4, True),
    ("v", -5.25, -4.8, (0.2,), 3.7, False),
)

NODE_DATA = (
    ("room_06", -19.5, 0.0, "Кімната 06"),
    ("room_07", -11.0, 0.0, "Кімната 07"),
    ("room_09", 10.0, 0.0, "Кімната 09"),
    ("room_10", 21.9, 0.0, "Кімната 10"),
    ("room_11", 32.0, -5.65, "Кімната 11"),
    ("tw_nw", -22.6, -5.65, "Західний кут"),
    ("tw_far", -19.5, -5.65, "Коридор біля 06"),
    ("tw_mid", -11.0, -5.65, "Коридор біля 07"),
    ("tw_near", -6.0, -5.65, "Коридор на захід від 08"),
    ("office_door", 1.5, -4.9, "Двері охоронця"),
    ("t_cross", 1.5, -6.3, "Перехрестя"),
    ("te_near", 5.0, -5.65, "Коридор на схід від 08"),
    ("te_mid", 10.0, -5.65, "Коридор біля 09"),
    ("te_far", 21.9, -5.65, "Коридор біля 10"),
    ("te_end", 27.5, -5.65, "Східний кут"),
    ("lob_n", -0.7, -9.4, "Хол, північ"),
    ("lob_w", -7.0, -10.5, "Хол, захід"),
    ("lob_e", 6.2, -10.5, "Хол, схід"),
    ("ch_n", -0.7, -14.6, "Прохід, північ"),
    ("ch_mid", -0.7, -16.5, "Прохід, туалети"),
    ("ch_s", -0.7, -22.9, "Прохід, південь"),
    ("w_top", -22.5, -8.8, "Західний коридор, північ"),
    ("w_05", -22.5, -10.85, "Біля 05"),
    ("w_04", -22.5, -17.5, "Біля 04"),
    ("w_03", -22.5, -23.35, "Біля 03"),
    ("w_cb", -22.5, -27.75, "Західний кут, південь"),
    ("w_02", -22.5, -29.5, "Біля 02"),
    ("w_exit", -22.5, -36.0, "Західний вихід"),
    ("e_top", 27.1, -8.8, "Східний коридор, північ"),
    ("e_12", 27.1, -12.25, "Біля 12"),
    ("e_13", 27.1, -18.15, "Біля 13"),
    ("e_14", 27.1, -22.6, "Біля 14"),
    ("e_cb", 27.1, -27.75, "Східний кут, південь"),
    ("e_15", 27.1, -29.5, "Біля 15"),
    ("e_exit", 27.1, -36.0, "Східний коридор, глухий кут"),
    ("b_w", -17.8, -27.75, "Нижній коридор, захід"),
    ("b_1", -15.6, -27.75, "Біля 01"),
    ("b_hw", -6.6, -27.75, "Нижній коридор, захід від проходу"),
    ("b_mid", -0.7, -27.75, "Нижній коридор, центр"),
    ("b_he", 3.0, -27.75, "Нижній коридор, схід від проходу"),
    ("b_e", 15.3, -27.75, "Нижній коридор, схід"),
    ("b_16", 18.5, -27.75, "Біля 16"),
    ("room_05", -28.5, -10.85, "Кімната 05"),
    ("room_04", -28.5, -17.5, "Кімната 04"),
    ("room_03", -28.5, -23.35, "Кімната 03"),
    ("room_02", -28.5, -29.5, "Кімната 02"),
    ("room_12", 33.1, -12.25, "Кімната 12"),
    ("room_13", 33.1, -18.15, "Кімната 13"),
    ("room_14", 33.1, -22.6, "Кімната 14"),
    ("room_15", 33.1, -29.5, "Кімната 15"),
    ("toilet_w", -6.4, -16.5, "Туалет"),
    ("toilet_e", 4.9, -16.5, "Туалет"),
    ("toilet_w2", -6.4, -22.9, "Туалет"),
    ("archive", -12.7, -22.9, "Архів"),
    ("room_01", -15.6, -33.2, "Кімната 01"),
    ("room_16", 18.5, -33.2, "Кімната 16"),
)

EDGE_DATA = (
    ("tw_nw", "tw_far"), ("tw_far", "tw_mid"), ("tw_mid", "tw_near"), ("tw_near", "t_cross"),
    ("t_cross", "te_near"), ("office_door", "t_cross"), ("office_door", "tw_near"), ("office_door", "te_near"),
    ("te_near", "te_mid"), ("te_mid", "te_far"), ("te_far", "te_end"), ("te_end", "e_top"), ("tw_nw", "w_top"),
    ("t_cross", "lob_n"), ("lob_n", "lob_w"), ("lob_n", "lob_e"), ("lob_n", "ch_n"),
    ("ch_n", "ch_mid"), ("ch_mid", "ch_s"), ("ch_s", "b_mid"),
    ("w_top", "w_05"), ("w_05", "w_04"), ("w_04", "w_03"), ("w_03", "w_cb"), ("w_cb", "w_02"), ("w_02", "w_exit"),
    ("e_top", "e_12"), ("e_12", "e_13"), ("e_13", "e_14"), ("e_14", "e_cb"), ("e_cb", "e_15"), ("e_15", "e_exit"),
    ("w_cb", "b_w"), ("b_w", "b_1"), ("b_1", "b_hw"), ("b_hw", "b_mid"), ("b_mid", "b_he"), ("b_he", "b_e"),
    ("b_e", "b_16"), ("b_16", "e_cb"),
    ("room_06", "tw_far"), ("room_07", "tw_mid"), ("room_09", "te_mid"), ("room_10", "te_far"), ("room_11", "te_end"),
    ("room_05", "w_05"), ("room_04", "w_04"), ("room_03", "w_03"), ("room_02", "w_02"),
    ("room_12", "e_12"), ("room_13", "e_13"), ("room_14", "e_14"), ("room_15", "e_15"),
    ("toilet_w", "ch_mid"), ("toilet_e", "ch_mid"), ("toilet_w2", "ch_s"), ("toilet_w2", "archive"),
    ("room_01", "b_1"), ("room_16", "b_16"),
)

CAMERA_DATA = (
    ("1A", "Північний коридор, східний кінець", 26.0, -5.65, 270.0),
    ("1B", "Північний коридор, західний кінець", -22.0, -5.65, 90.0),
    ("2A", "Хол, північна стіна", -0.7, -7.9, 180.0),
    ("2B", "Центральний прохід, південний кінець", -0.7, -24.5, 0.0),
    ("3A", "Західний коридор, північний кінець", -22.5, -12.0, 180.0),
    ("3B", "Західний коридор, південний кінець", -22.5, -34.5, 0.0),
    ("4A", "Східний коридор, північний кінець", 27.1, -12.0, 180.0),
    ("4B", "Східний коридор, південний кінець", 27.1, -34.5, 0.0),
    ("5A", "Нижній коридор, західний кінець", -19.5, -27.75, 90.0),
    ("5B", "Нижній коридор, східний кінець", 23.5, -27.75, 270.0),
)

AUDIO_CAMERA_DATA = (
    ("6", "Туалет", 4.9, -16.5, 0.0, "toilet_e"),
)

SPOT_OFFSETS = ((0.0, 0.0), (0.7, 0.45), (-0.7, 0.45), (0.0, -0.8))


def rect_difference(rect, cut):
    ax0, ax1, az0, az1 = rect
    bx0, bx1, bz0, bz1 = cut
    if bx0 >= ax1 or bx1 <= ax0 or bz0 >= az1 or bz1 <= az0:
        return [rect]
    out = []
    if bx0 > ax0:
        out.append((ax0, bx0, az0, az1))
    if bx1 < ax1:
        out.append((bx1, ax1, az0, az1))
    lo, hi = max(ax0, bx0), min(ax1, bx1)
    if bz0 > az0:
        out.append((lo, hi, az0, bz0))
    if bz1 < az1:
        out.append((lo, hi, bz1, az1))
    return [r for r in out if r[1] - r[0] > 1e-6 and r[3] - r[2] > 1e-6]


def region_slabs(region):
    o = set(region.open)
    e0, e1, n0, n1 = region.rect
    ext0 = 0.0 if "e0" in o else T
    ext1 = 0.0 if "e1" in o else T
    out = []
    if "n0" not in o:
        out.append((e0 - ext0, e1 + ext1, n0 - T, n0))
    if "n1" not in o:
        out.append((e0 - ext0, e1 + ext1, n1, n1 + T))
    if "e0" not in o:
        out.append((e0 - T, e0, n0, n1))
    if "e1" not in o:
        out.append((e1, e1 + T, n0, n1))
    return out


def carve(piece_list, cuts):
    for cut in cuts:
        piece_list = [p for piece in piece_list for p in rect_difference(piece, cut)]
    return piece_list


def column_rect(e, n):
    h = COLUMN_SIZE / 2.0
    return (e - h, e + h, n - h, n + h)


def segment_hits_rect(a, b, rect):
    x0, x1, z0, z1 = rect
    dx, dz = b[0] - a[0], b[1] - a[1]
    tmin, tmax = 0.0, 1.0
    for p, d, lo, hi in ((a[0], dx, x0, x1), (a[1], dz, z0, z1)):
        if abs(d) < 1e-12:
            if p < lo or p > hi:
                return False
        else:
            t1, t2 = (lo - p) / d, (hi - p) / d
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin > tmax:
                return False
    return True


class FloorPlan:
    def __init__(self):
        self.regions = {}
        for name, kind, e0, e1, n0, n1, opn, ext, title in REGION_DATA:
            self.regions[name] = Region(name, kind, e0, e1, n0, n1, tuple(opn), ext, title)
        self.cuts = []
        for e0, e1, n0, n1 in GAP_DATA:
            self.cuts.append(Cut(e0, e1, n0, n1, "gap", "e", False))
        self.guard_door = GUARD_DOOR_DATA
        self.cuts.append(Cut(*GUARD_DOOR_DATA, "guard", "n", False))
        self.links = []
        for a, b, at in LINK_DATA:
            cut = self.make_link(self.regions[a], self.regions[b], at)
            self.cuts.append(cut)
            self.links.append((a, b, cut))
        for name, side, at in EXIT_DATA:
            self.cuts.append(self.make_exit(self.regions[name], side, at))
        self.nodes = {}
        for nid, e, n, title in NODE_DATA:
            self.nodes[nid] = Node(nid, e, n, title)
        self.adjacency = {nid: [] for nid in self.nodes}
        for a, b in EDGE_DATA:
            self.adjacency[a].append(b)
            self.adjacency[b].append(a)
        self.cameras = [CameraSpec(i + 1, *row) for i, row in enumerate(CAMERA_DATA)]
        for label, title, e, n, heading, zone in AUDIO_CAMERA_DATA:
            self.cameras.append(CameraSpec(len(self.cameras) + 1, label, title, e, n, heading, audio_only=True, zone=zone))
        self.columns = [column_rect(e, n) for e, n in COLUMN_DATA]
        self.slabs = self.build_slabs()
        self.los_walls = [w for w, owner in self.slabs] + list(self.columns)
        self.path_cache = {}
        self.node_region = {nid: self.region_at(n.e, n.n) for nid, n in self.nodes.items()}

    def visible_slabs(self):
        out = []
        for rect, owner in self.slabs:
            for piece in rect_difference(rect, GUARD_CLIP):
                out.append((piece, owner))
        return out

    def make_link(self, a, b, at):
        w = DOOR_W
        for first, second in ((a, b), (b, a)):
            gap = second.e0 - first.e1
            if -1e-6 <= gap <= T + 0.06 and min(first.n1, second.n1) - max(first.n0, second.n0) > w:
                return Cut(first.e1 - 0.02, second.e0 + 0.02, at - w / 2, at + w / 2, "door", "e")
        for first, second in ((a, b), (b, a)):
            gap = second.n0 - first.n1
            if -1e-6 <= gap <= T + 0.06 and min(first.e1, second.e1) - max(first.e0, second.e0) > w:
                return Cut(at - w / 2, at + w / 2, first.n1 - 0.02, second.n0 + 0.02, "door", "n")
        raise ValueError(f"no shared wall between {a.name} and {b.name}")

    def make_exit(self, region, side, at):
        w = DOOR_W + 0.6
        e0, e1, n0, n1 = region.rect
        if side == "n0":
            return Cut(at - w / 2, at + w / 2, n0 - T - 0.02, n0 + 0.02, "door", "n", False)
        if side == "e1":
            return Cut(e1 - 0.02, e1 + T + 0.02, at - w / 2, at + w / 2, "door", "e", False)
        if side == "e0":
            return Cut(e0 - T - 0.02, e0 + 0.02, at - w / 2, at + w / 2, "door", "e", False)
        return Cut(at - w / 2, at + w / 2, n1 - 0.02, n1 + T + 0.02, "door", "n", False)

    def build_slabs(self):
        seen = set()
        out = []
        cut_rects = [c.rect for c in self.cuts]
        sources = []
        for region in self.regions.values():
            if not region.external:
                sources.extend((slab, region.name) for slab in region_slabs(region))
        sources.extend((rect, name) for name, rect in SOLID_DATA)
        for slab, owner in sources:
            for p in carve([slab], cut_rects):
                key = tuple(round(v, 2) for v in p)
                if key not in seen:
                    seen.add(key)
                    out.append((p, owner))
        return out

    def region_at(self, x, z, margin=0.0):
        best = None
        for region in self.regions.values():
            if region.external and region.name != "room_08":
                continue
            if region.contains(x, z, margin):
                if best is None or region.kind == "guard":
                    best = region
                elif best.kind != "guard" and (region.rect[1] - region.rect[0]) * (region.rect[3] - region.rect[2]) < (best.rect[1] - best.rect[0]) * (best.rect[3] - best.rect[2]):
                    best = region
        if best is None:
            for region in self.regions.values():
                if region.external and region.contains(x, z, margin):
                    return region
        return best

    def node_position(self, node_id):
        return self.nodes[node_id].position

    def neighbors(self, node_id):
        return list(self.adjacency[node_id])

    def spot(self, node_id, index):
        dx, dz = SPOT_OFFSETS[index % len(SPOT_OFFSETS)]
        x, y, z = self.nodes[node_id].position
        return (x + dx, y, z + dz)

    def path(self, start, goal):
        key = (start, goal)
        if key in self.path_cache:
            return self.path_cache[key]
        prev = {start: None}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            if cur == goal:
                break
            for nxt in self.adjacency[cur]:
                if nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)
        route = []
        if goal in prev:
            cur = goal
            while cur is not None:
                route.append(cur)
                cur = prev[cur]
            route.reverse()
        self.path_cache[key] = route
        return route

    def distance_map(self, goal):
        dist = {goal: 0}
        queue = deque([goal])
        while queue:
            cur = queue.popleft()
            for nxt in self.adjacency[cur]:
                if nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        return dist

    def line_of_sight(self, a, b, extra=()):
        pa, pb = (a[0], a[-1]), (b[0], b[-1])
        for rect in self.los_walls:
            if segment_hits_rect(pa, pb, rect):
                return False
        for rect in extra:
            if segment_hits_rect(pa, pb, rect):
                return False
        return True

    def ray_distance(self, ox, oz, dx, dz, limit):
        best = limit
        for x0, x1, z0, z1 in self.los_walls:
            lo, hi = 0.0, best
            if abs(dx) < 1e-12:
                if ox < x0 or ox > x1:
                    continue
            else:
                a, b = (x0 - ox) / dx, (x1 - ox) / dx
                if a > b:
                    a, b = b, a
                lo, hi = max(lo, a), min(hi, b)
                if lo > hi:
                    continue
            if abs(dz) < 1e-12:
                if oz < z0 or oz > z1:
                    continue
            else:
                a, b = (z0 - oz) / dz, (z1 - oz) / dz
                if a > b:
                    a, b = b, a
                lo, hi = max(lo, a), min(hi, b)
                if lo > hi:
                    continue
            best = lo
        return best

    def camera_sees(self, camera, position, max_distance=34.0, extra=()):
        if camera.audio_only:
            return False
        cx, _, cz = camera.position
        dx, dz = position[0] - cx, position[-1] - cz
        dist = math.hypot(dx, dz)
        if dist > max_distance or dist < 0.2:
            return False
        yaw = math.radians(camera.yaw)
        fx, fz = math.sin(yaw), math.cos(yaw)
        cos_angle = (dx * fx + dz * fz) / dist
        half = math.radians(camera.fov * 16.0 / 9.0 * 0.5 * 0.82)
        if cos_angle < math.cos(min(half, math.radians(80.0))):
            return False
        return self.line_of_sight((cx, 0, cz), position, extra)

    def bounds(self):
        xs, zs = [], []
        for region in self.regions.values():
            x0, x1, z0, z1 = region.rect
            xs += [x0, x1]
            zs += [z0, z1]
        return min(xs), max(xs), min(zs), max(zs)



_PLAN = None


def plan():
    global _PLAN
    if _PLAN is None:
        _PLAN = FloorPlan()
    return _PLAN
