import math

import numpy as np

VERTEX_DTYPE = np.dtype([("p", "<f4", (3,)), ("c", "u1", (4,))])
VERTEX_STRIDE = VERTEX_DTYPE.itemsize

_registry = []


def mesh_by_gid(gid):
    return _registry[gid]


class Mesh:
    def __init__(self, vertices, colors, faces):
        self.vertices = np.ascontiguousarray(vertices, dtype=np.float32).reshape(-1, 3)
        self.colors = np.ascontiguousarray(colors, dtype=np.uint8).reshape(-1, 4)
        self.faces = np.ascontiguousarray(faces, dtype=np.uint32).reshape(-1, 3)
        self.gid = len(_registry)
        _registry.append(self)
        lo = self.vertices.min(axis=0)
        hi = self.vertices.max(axis=0)
        self.center = ((lo + hi) * 0.5).astype(np.float32)
        self.radius_c = float(np.sqrt(((self.vertices - self.center) ** 2).sum(axis=1).max()))
        self.radius_o = float(np.sqrt((self.vertices.astype(np.float64) ** 2).sum(axis=1).max()))

    def vertex_bytes(self):
        packed = np.empty(len(self.vertices), dtype=VERTEX_DTYPE)
        packed["p"] = self.vertices
        packed["c"] = self.colors
        return packed


def _orient_by_center(v, f, center):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    mid = (a + b + c) / 3.0
    flip = np.einsum("ij,ij->i", n, mid - center) < 0
    out = f.copy()
    out[flip] = out[flip][:, [0, 2, 1]]
    return out


def _orient_by_facing(v, f, facing):
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    n = np.cross(b - a, c - a)
    flip = np.einsum("ij,ij->i", n, facing) < 0
    out = f.copy()
    out[flip] = out[flip][:, [0, 2, 1]]
    return out


_BOX_FACES = np.array(
    [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
     [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]],
    dtype=np.int64,
)


class MeshBuilder:
    def __init__(self):
        self._v = []
        self._c = []
        self._f = []
        self._n = 0
        self._tf = None

    def begin_transform(self, offset, yaw=0.0):
        self._tf = (np.asarray(offset, dtype=np.float32), float(yaw))

    def end_transform(self):
        self._tf = None

    def _push(self, v, f, color, paint):
        v = np.asarray(v, dtype=np.float32).reshape(-1, 3)
        if self._tf is not None:
            offset, yaw = self._tf
            c, s = math.cos(yaw), math.sin(yaw)
            x, z = v[:, 0].copy(), v[:, 2].copy()
            v = v.copy()
            v[:, 0] = c * x + s * z
            v[:, 2] = -s * x + c * z
            v = v + offset
        col = np.asarray(color, dtype=np.float32)
        rgba = np.empty((len(v), 4), dtype=np.uint8)
        rgba[:, :3] = np.clip(col, 0, 255) if col.ndim == 2 else np.clip(col, 0, 255)[None, :]
        rgba[:, 3] = 255 if paint is True else int(round(float(paint) * 255))
        self._v.append(v)
        self._c.append(rgba)
        self._f.append(np.asarray(f, dtype=np.int64) + self._n)
        self._n += len(v)

    def hull(self, bottom, top, color, paint=0.0):
        v = np.array(list(bottom) + list(top), dtype=np.float32)
        f = _orient_by_center(v, _BOX_FACES, v.mean(axis=0))
        self._push(v, f, color, paint)

    def prism(self, base, bottom, top, height, color, paint=0.0, shift=0.0, shift_x=0.0):
        x, y, z = base
        bw, bl = bottom
        tw, tl = top

        def ring(cx, cy, cz, w, l):
            return [(cx - w / 2, cy, cz - l / 2), (cx + w / 2, cy, cz - l / 2),
                    (cx + w / 2, cy, cz + l / 2), (cx - w / 2, cy, cz + l / 2)]

        self.hull(ring(x, y, z, bw, bl), ring(x + shift_x, y + height, z + shift, tw, tl), color, paint)

    def box(self, center, size, color, paint=0.0):
        cx, cy, cz = center
        sx, sy, sz = size
        self.prism((cx, cy - sy / 2, cz), (sx, sz), (sx, sz), sy, color, paint)

    def cylinder(self, center, radius, length, axis, color, paint=0.0, segments=12, radius_top=None):
        r1 = radius if radius_top is None else radius_top
        ang = np.linspace(0, 2 * math.pi, segments, endpoint=False)
        cs, sn = np.cos(ang), np.sin(ang)
        h = length / 2.0
        bot = np.stack([radius * cs, np.full(segments, -h), radius * sn], axis=1)
        top = np.stack([r1 * cs, np.full(segments, h), r1 * sn], axis=1)
        v = np.concatenate([bot, top, [[0, -h, 0]], [[0, h, 0]]]).astype(np.float32)
        cb, ct = 2 * segments, 2 * segments + 1
        f = []
        for i in range(segments):
            j = (i + 1) % segments
            f += [[i, j, segments + j], [i, segments + j, segments + i], [cb, j, i], [ct, segments + i, segments + j]]
        if axis == "x":
            v = v[:, [1, 0, 2]]
        elif axis == "z":
            v = v[:, [0, 2, 1]]
        v = v + np.asarray(center, dtype=np.float32)
        f = _orient_by_center(v, np.array(f, dtype=np.int64), np.asarray(center, dtype=np.float32))
        self._push(v, f, color, paint)

    def ellipsoid(self, center, radii, color, paint=0.0, rings=4, segments=8, inside=False, jitter=0.0, rng=None):
        verts = [[0, radii[1], 0]]
        for r in range(1, rings):
            phi = math.pi * r / rings
            for s in range(segments):
                th = 2 * math.pi * s / segments
                verts.append([radii[0] * math.sin(phi) * math.cos(th), radii[1] * math.cos(phi),
                              radii[2] * math.sin(phi) * math.sin(th)])
        verts.append([0, -radii[1], 0])
        v = np.array(verts, dtype=np.float32)
        if jitter > 0.0 and rng is not None:
            v = v * (1.0 + jitter * (rng.random((len(v), 1)) - 0.5)).astype(np.float32)
        f = []
        for s in range(segments):
            f.append([0, 1 + s, 1 + (s + 1) % segments])
        for r in range(rings - 2):
            a = 1 + r * segments
            b = a + segments
            for s in range(segments):
                t = (s + 1) % segments
                f += [[a + s, b + s, b + t], [a + s, b + t, a + t]]
        last = len(v) - 1
        a = 1 + (rings - 2) * segments
        for s in range(segments):
            f.append([last, a + (s + 1) % segments, a + s])
        v = v + np.asarray(center, dtype=np.float32)
        f = _orient_by_center(v, np.array(f, dtype=np.int64), np.asarray(center, dtype=np.float32))
        if inside:
            f = f[:, [0, 2, 1]]
        self._push(v, f, color, paint)

    def quads(self, q, colors, facing, paint=0.0):
        q = np.asarray(q, dtype=np.float32)
        n = len(q)
        if n == 0:
            return
        v = q.reshape(-1, 3)
        base = np.arange(n, dtype=np.int64) * 4
        f = np.empty((n * 2, 3), dtype=np.int64)
        f[0::2] = np.stack([base, base + 1, base + 2], axis=1)
        f[1::2] = np.stack([base, base + 2, base + 3], axis=1)
        fac = np.asarray(facing, dtype=np.float32)
        fac = np.repeat(fac, 2, axis=0) if fac.ndim == 2 else np.broadcast_to(fac, (n * 2, 3))
        f = _orient_by_facing(v, f, fac)
        col = np.asarray(colors, dtype=np.float32)
        col = np.repeat(col, 4, axis=0) if col.ndim == 2 else col
        self._push(v, f, col, paint)

    def add_mesh(self, mesh, offset=(0, 0, 0), yaw=0.0, scale=1.0, tint=None):
        v = mesh.vertices * np.float32(scale)
        if yaw:
            c, s = math.cos(yaw), math.sin(yaw)
            x, z = v[:, 0].copy(), v[:, 2].copy()
            v[:, 0] = c * x + s * z
            v[:, 2] = -s * x + c * z
        v = v + np.asarray(offset, dtype=np.float32)
        col = mesh.colors.astype(np.float32)
        if tint is not None:
            m = col[:, 3] > 0
            col[m, :3] *= np.asarray(tint, dtype=np.float32) / 255.0
            col[:, 3] = 0
        self._v.append(v)
        self._c.append(np.clip(col, 0, 255).astype(np.uint8))
        self._f.append(mesh.faces.astype(np.int64) + self._n)
        self._n += len(v)

    def heightfield(self, xs, zs, heights, colors):
        nx, nz = len(xs), len(zs)
        gx, gz = np.meshgrid(xs, zs, indexing="ij")
        v = np.stack([gx, heights, gz], axis=-1).reshape(-1, 3).astype(np.float32)
        ix, iz = np.meshgrid(np.arange(nx - 1), np.arange(nz - 1), indexing="ij")
        ix, iz = ix.ravel(), iz.ravel()
        a = ix * nz + iz
        b = (ix + 1) * nz + iz
        c = (ix + 1) * nz + iz + 1
        d = ix * nz + iz + 1
        even = ((ix + iz) % 2 == 0)[:, None]
        t1 = np.where(even, np.stack([a, b, c], axis=1), np.stack([a, b, d], axis=1))
        t2 = np.where(even, np.stack([a, c, d], axis=1), np.stack([b, c, d], axis=1))
        f = np.concatenate([t1, t2]).astype(np.int64)
        f = _orient_by_facing(v, f, np.broadcast_to(np.array([0.0, 1.0, 0.0], dtype=np.float32), (len(f), 3)))
        self._push(v, f, np.asarray(colors, dtype=np.float32).reshape(-1, 3), 0.0)

    def add_instances(self, mesh, positions, scales, tints, yaws=None):
        t = len(positions)
        if t == 0:
            return
        v = mesh.vertices[None, :, :] * (scales[:, None, None] if scales.ndim == 1 else scales[:, None, :])
        if yaws is not None:
            c = np.cos(yaws)[:, None].astype(np.float32)
            s = np.sin(yaws)[:, None].astype(np.float32)
            x, z = v[:, :, 0].copy(), v[:, :, 2].copy()
            v[:, :, 0] = c * x + s * z
            v[:, :, 2] = -s * x + c * z
        v = v + positions[:, None, :]
        col = np.broadcast_to(mesh.colors.astype(np.float32), (t,) + mesh.colors.shape).copy()
        paint = col[:, :, 3] > 0
        col[:, :, :3] = np.where(paint[:, :, None], col[:, :, :3] * tints[:, None, :] / 255.0, col[:, :, :3])
        col[:, :, 3] = 0
        nv = len(mesh.vertices)
        f = mesh.faces.astype(np.int64)[None, :, :] + (np.arange(t, dtype=np.int64) * nv)[:, None, None] + self._n
        self._v.append(v.reshape(-1, 3).astype(np.float32))
        self._c.append(np.clip(col, 0, 255).reshape(-1, 4).astype(np.uint8))
        self._f.append(f.reshape(-1, 3))
        self._n += t * nv

    def build(self):
        return Mesh(np.concatenate(self._v), np.concatenate(self._c), np.concatenate(self._f))


class TiledBuilder:
    def __init__(self, tile=256.0):
        self.tile = float(tile)
        self.cells = {}

    def _key(self, x, z, glow):
        return (int(math.floor(x / self.tile)), int(math.floor(z / self.tile)), bool(glow))

    def at(self, x, z, glow=False):
        key = self._key(x, z, glow)
        b = self.cells.get(key)
        if b is None:
            b = MeshBuilder()
            self.cells[key] = b
        return b

    def _split(self, centers, glow):
        t = self.tile
        tx = np.floor(centers[:, 0] / t).astype(np.int64)
        tz = np.floor(centers[:, 1] / t).astype(np.int64)
        code = tx * 100003 + tz
        for u in np.unique(code):
            sel = np.flatnonzero(code == u)
            i = sel[0]
            yield sel, self.at(float(centers[i, 0]), float(centers[i, 1]), glow)

    def quads(self, q, colors, facing, paint=0.0, glow=False):
        q = np.asarray(q, dtype=np.float32)
        if len(q) == 0:
            return
        colors = np.asarray(colors, dtype=np.float32)
        facing = np.asarray(facing, dtype=np.float32)
        centers = q.mean(axis=1)[:, [0, 2]]
        for sel, b in self._split(centers, glow):
            c = colors[sel] if colors.ndim == 2 and len(colors) == len(q) else colors
            f = facing[sel] if facing.ndim == 2 and len(facing) == len(q) else facing
            b.quads(q[sel], c, f, paint)

    def instances(self, mesh, positions, scales, tints, yaws=None, glow=False):
        positions = np.asarray(positions, dtype=np.float32)
        if len(positions) == 0:
            return
        scales = np.asarray(scales, dtype=np.float32)
        tints = np.asarray(tints, dtype=np.float32)
        for sel, b in self._split(positions[:, [0, 2]], glow):
            b.add_instances(mesh, positions[sel], scales[sel], tints[sel], None if yaws is None else np.asarray(yaws, dtype=np.float32)[sel])

    def build(self):
        out = []
        for (tx, tz, glow), b in self.cells.items():
            if b._v:
                out.append(((tx, tz), glow, b.build()))
        return out
