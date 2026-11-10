import math
import os

import numpy as np

MATS = {}


def material(name, kd=(1.0, 1.0, 1.0), tex=None):
    MATS[name] = (kd, tex)
    return name


def rotation(rx=0.0, ry=0.0, rz=0.0):
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return my @ mx @ mz


class Obj:
    def __init__(self, name):
        self.name = name
        self.v = []
        self.vt = []
        self.vi = {}
        self.ti = {}
        self.parts = {}
        self.used = set()

    def _v(self, p):
        key = (round(float(p[0]), 5), round(float(p[1]), 5), round(float(p[2]), 5))
        i = self.vi.get(key)
        if i is None:
            self.v.append(key)
            i = len(self.v)
            self.vi[key] = i
        return i

    def _t(self, t):
        key = (round(float(t[0]), 4), round(float(t[1]), 4))
        i = self.ti.get(key)
        if i is None:
            self.vt.append(key)
            i = len(self.vt)
            self.ti[key] = i
        return i

    def quad(self, part, mat, pts, uvs, facing=None):
        p = [np.asarray(q, dtype=np.float64) for q in pts]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if np.linalg.norm(n) < 1e-12:
            n = np.cross(p[2] - p[0], p[3] - p[0])
        if facing is not None and float(np.dot(n, facing)) < 0.0:
            p = p[::-1]
            uvs = uvs[::-1]
        self.used.add(mat)
        self.parts.setdefault(part, []).append((mat, [(self._v(a), self._t(b)) for a, b in zip(p, uvs)]))

    def tri(self, part, mat, pts, uvs, facing=None):
        p = [np.asarray(q, dtype=np.float64) for q in pts]
        n = np.cross(p[1] - p[0], p[2] - p[0])
        if facing is not None and float(np.dot(n, facing)) < 0.0:
            p = p[::-1]
            uvs = uvs[::-1]
        self.used.add(mat)
        self.parts.setdefault(part, []).append((mat, [(self._v(a), self._t(b)) for a, b in zip(p, uvs)]))

    def rect(self, part, mat, axis, value, a0, a1, b0, b1, facing, tile=1.0, uvo=(0.0, 0.0)):
        o = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}[axis]
        if axis == "y":
            o = (0, 2)
        ia, ib = o

        def pt(a, b):
            q = [0.0, 0.0, 0.0]
            q[("xyz".index(axis))] = value
            q[ia] = a
            q[ib] = b
            return q

        pts = [pt(a0, b0), pt(a1, b0), pt(a1, b1), pt(a0, b1)]
        uvs = [(a0 / tile + uvo[0], b0 / tile + uvo[1]), (a1 / tile + uvo[0], b0 / tile + uvo[1]), (a1 / tile + uvo[0], b1 / tile + uvo[1]), (a0 / tile + uvo[0], b1 / tile + uvo[1])]
        f = [0.0, 0.0, 0.0]
        f["xyz".index(axis)] = facing
        self.quad(part, mat, pts, uvs, f)

    def box(self, part, mat, c, size, tile=1.0, rot=None, skip=(), uvo=(0.0, 0.0), mats=None, pivot=None):
        sx, sy, sz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
        R = rotation(*rot) if rot is not None and any(rot) else None
        c = np.asarray(c, dtype=np.float64)

        def place(p):
            q = np.asarray(p, dtype=np.float64)
            if R is not None:
                q = R @ q
            return q + c

        faces = {
            "px": ((sx, -sy, -sz), (sx, -sy, sz), (sx, sy, sz), (sx, sy, -sz), (1, 0, 0), 2, 1),
            "nx": ((-sx, -sy, sz), (-sx, -sy, -sz), (-sx, sy, -sz), (-sx, sy, sz), (-1, 0, 0), 2, 1),
            "py": ((-sx, sy, -sz), (sx, sy, -sz), (sx, sy, sz), (-sx, sy, sz), (0, 1, 0), 0, 2),
            "ny": ((-sx, -sy, sz), (sx, -sy, sz), (sx, -sy, -sz), (-sx, -sy, -sz), (0, -1, 0), 0, 2),
            "pz": ((-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz), (0, 0, 1), 0, 1),
            "nz": ((sx, -sy, -sz), (-sx, -sy, -sz), (-sx, sy, -sz), (sx, sy, -sz), (0, 0, -1), 0, 1),
        }
        for key, (p0, p1, p2, p3, nrm, ia, ib) in faces.items():
            if key in skip:
                continue
            m = mats.get(key, mat) if mats else mat
            local = [p0, p1, p2, p3]
            uvs = [(q[ia] / tile + uvo[0], q[ib] / tile + uvo[1]) for q in local]
            n = np.asarray(nrm, dtype=np.float64)
            if R is not None:
                n = R @ n
            self.quad(part, m, [place(q) for q in local], uvs, n)

    def cylinder(self, part, mat, c, r, h, axis="y", seg=8, tile=1.0, r_top=None, caps=True, rot=None):
        r_top = r if r_top is None else r_top
        R = rotation(*rot) if rot is not None and any(rot) else None
        c = np.asarray(c, dtype=np.float64)
        order = {"y": (0, 1, 2), "x": (1, 0, 2), "z": (0, 2, 1)}[axis]

        def place(a, b, d):
            local = np.zeros(3)
            local[order[0]] = a
            local[order[1]] = b
            local[order[2]] = d
            if R is not None:
                local = R @ local
            return local + c

        for i in range(seg):
            a0 = 2 * math.pi * i / seg
            a1 = 2 * math.pi * (i + 1) / seg
            p0 = place(math.cos(a0) * r, -h / 2, math.sin(a0) * r)
            p1 = place(math.cos(a1) * r, -h / 2, math.sin(a1) * r)
            p2 = place(math.cos(a1) * r_top, h / 2, math.sin(a1) * r_top)
            p3 = place(math.cos(a0) * r_top, h / 2, math.sin(a0) * r_top)
            mid = place(math.cos((a0 + a1) / 2), 0.0, math.sin((a0 + a1) / 2)) - c
            u0, u1 = a0 * r / tile, a1 * r / tile
            self.quad(part, mat, [p0, p1, p2, p3], [(u0, -h / 2 / tile), (u1, -h / 2 / tile), (u1, h / 2 / tile), (u0, h / 2 / tile)], mid)
            if caps:
                top = place(0.0, h / 2, 0.0)
                bot = place(0.0, -h / 2, 0.0)
                up = place(0.0, 1.0, 0.0) - c
                self.tri(part, mat, [top, p3, p2], [(0, 0), (math.cos(a0), math.sin(a0)), (math.cos(a1), math.sin(a1))], up)
                self.tri(part, mat, [bot, p0, p1], [(0, 0), (math.cos(a0), math.sin(a0)), (math.cos(a1), math.sin(a1))], -up)

    def sphere(self, part, mat, c, radii, rings=5, seg=8, tile=1.0):
        c = np.asarray(c, dtype=np.float64)
        rx, ry, rz = radii

        def pt(i, j):
            th = math.pi * i / rings
            ph = 2 * math.pi * j / seg
            return np.array([rx * math.sin(th) * math.cos(ph), ry * math.cos(th), rz * math.sin(th) * math.sin(ph)])

        for i in range(rings):
            for j in range(seg):
                a, b, cc, d = pt(i, j), pt(i, j + 1), pt(i + 1, j + 1), pt(i + 1, j)
                uv = lambda q: (q[0] / tile + q[2] / tile * 0.5, q[1] / tile)
                mid = (a + b + cc + d) / 4.0
                if i == 0:
                    self.tri(part, mat, [a + c, cc + c, d + c], [uv(a), uv(cc), uv(d)], mid)
                elif i == rings - 1:
                    self.tri(part, mat, [a + c, b + c, d + c], [uv(a), uv(b), uv(d)], mid)
                else:
                    self.quad(part, mat, [a + c, b + c, cc + c, d + c], [uv(a), uv(b), uv(cc), uv(d)], mid)

    def prism_roof(self, part, mat, x0, x1, z0, z1, y0, ridge, tile=2.0):
        xm = (x0 + x1) / 2.0
        self.quad(part, mat, [(x0, y0, z0), (xm, ridge, z0), (xm, ridge, z1), (x0, y0, z1)], [(0, 0), (1, 0), (1, 1), (0, 1)], (-0.6, 1, 0))
        self.quad(part, mat, [(xm, ridge, z0), (x1, y0, z0), (x1, y0, z1), (xm, ridge, z1)], [(0, 0), (1, 0), (1, 1), (0, 1)], (0.6, 1, 0))
        self.tri(part, mat, [(x0, y0, z0), (x1, y0, z0), (xm, ridge, z0)], [(0, 0), (1, 0), (0.5, 0.5)], (0, 0, -1))
        self.tri(part, mat, [(x0, y0, z1), (x1, y0, z1), (xm, ridge, z1)], [(0, 0), (1, 0), (0.5, 0.5)], (0, 0, 1))

    def write(self, directory):
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, self.name + ".obj")
        with open(path, "w", newline="\n") as f:
            f.write(f"mtllib {self.name}.mtl\n")
            for x, y, z in self.v:
                f.write(f"v {x:g} {y:g} {z:g}\n")
            for u, v in self.vt:
                f.write(f"vt {u:g} {v:g}\n")
            for part, faces in self.parts.items():
                f.write(f"o {part}\n")
                cur = None
                for mat, idx in faces:
                    if mat != cur:
                        f.write(f"usemtl {mat}\n")
                        cur = mat
                    f.write("f " + " ".join(f"{a}/{b}" for a, b in idx) + "\n")
        with open(os.path.join(directory, self.name + ".mtl"), "w", newline="\n") as f:
            for name in sorted(self.used):
                kd, tex = MATS[name]
                f.write(f"newmtl {name}\nKd {kd[0]:g} {kd[1]:g} {kd[2]:g}\n")
                if tex:
                    f.write(f"map_Kd ../textures/{tex}.png\n")
                f.write("\n")
        return path
