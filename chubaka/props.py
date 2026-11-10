import math

from chubaka.geometry import Batch

BODY = (24, 24, 26)
KEY = (14, 14, 16)
SILVER = (150, 152, 156)
RED = (200, 24, 24)
SCREEN = (36, 120, 96)
TILT = math.radians(14.0)
BASE_W = 0.33
BASE_D = 0.23
BASE_H = 0.018
LID_L = 0.215
LID_T = 0.008


def laptop_body():
    b = Batch()
    b.box((0.0, BASE_H / 2, 0.0), (BASE_W, BASE_H, BASE_D), BODY)
    kx0 = -BASE_W / 2 + 0.02
    cols, rows = 14, 5
    kw = (BASE_W - 0.04) / cols
    for r in range(rows):
        for c in range(cols):
            b.box((kx0 + (c + 0.5) * kw, BASE_H + 0.0015, -BASE_D / 2 + 0.03 + r * 0.021), (kw - 0.003, 0.003, 0.017), KEY)
    b.box((0.0, BASE_H + 0.002, -BASE_D / 2 + 0.03 + 2.0 * 0.021), (0.01, 0.006, 0.01), RED)
    b.box((0.0, BASE_H + 0.0008, BASE_D / 2 - 0.045), (0.11, 0.0016, 0.055), (34, 34, 38))
    b.box((-0.06, BASE_H + 0.0016, BASE_D / 2 - 0.1), (0.02, 0.003, 0.004), RED)
    hinge = (0.0, BASE_H, -BASE_D / 2)
    d = (0.0, math.cos(TILT), -math.sin(TILT))
    center = (hinge[0], hinge[1] + d[1] * LID_L / 2, hinge[2] + d[2] * LID_L / 2)
    b.box(center, (BASE_W, LID_L, LID_T), BODY, rot=(-TILT, 0.0, 0.0))
    b.box((0.0, BASE_H / 2, -BASE_D / 2 - 0.002), (BASE_W * 0.9, 0.012, 0.01), (10, 10, 12))
    n = (0.0, math.sin(TILT), math.cos(TILT))
    out = LID_T / 2 + 0.001
    logo = (center[0] + 0.09 - 0.0, center[1] + d[1] * -0.06 - n[1] * out, center[2] + d[2] * -0.06 - n[2] * out)
    b.box(logo, (0.06, 0.009, 0.001), SILVER, rot=(-TILT, 0.0, 0.0))
    b.box((logo[0] + 0.036, logo[1] + 0.006, logo[2]), (0.004, 0.004, 0.0012), RED, rot=(-TILT, 0.0, 0.0))
    return b.build()


def laptop_screen():
    b = Batch()
    hinge = (0.0, BASE_H, -BASE_D / 2)
    d = (0.0, math.cos(TILT), -math.sin(TILT))
    n = (0.0, math.sin(TILT), math.cos(TILT))
    off = LID_T / 2 + 0.0015
    center = (hinge[0], hinge[1] + d[1] * LID_L / 2 + n[1] * off, hinge[2] + d[2] * LID_L / 2 + n[2] * off)
    b.box(center, (BASE_W - 0.03, LID_L - 0.03, 0.001), SCREEN, rot=(-TILT, 0.0, 0.0))
    return b.build()


def laptop_hotspot_offset():
    return (0.0, 0.14, -0.1)
