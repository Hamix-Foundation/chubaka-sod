import math
import os

import numpy as np

from lysyk.engine.mesh import Mesh


class ObjPart:
    def __init__(self, name, mesh, bounds):
        self.name = name
        self.mesh = mesh
        self.bounds = bounds


def _read_mtl(path):
    mats = {}
    cur = None
    if not os.path.isfile(path):
        return mats
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.split()
            if not t:
                continue
            if t[0] == "newmtl" and len(t) > 1:
                cur = t[1]
            elif t[0] == "Kd" and cur is not None and len(t) >= 4:
                mats[cur] = tuple(max(0, min(255, int(round(float(x) * 255)))) for x in t[1:4])
    return mats


def load_obj(path, scale=1.0, flip_z=True, colors=None, default_color=(255, 255, 255), paint=0.0, offset=(0.0, 0.0, 0.0), matrix=None):
    colors = colors or {}
    base = os.path.dirname(path)
    verts = []
    mats = {}
    parts = []
    current = None
    material = None

    def start(name):
        parts.append({"name": name, "pos": [], "col": [], "idx": []})
        return parts[-1]

    alpha = int(round(max(0.0, min(1.0, paint)) * 255))
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.split()
            if not t:
                continue
            tag = t[0]
            if tag == "v":
                verts.append((float(t[1]), float(t[2]), float(t[3])))
            elif tag in ("o", "g"):
                current = start(t[1] if len(t) > 1 else "part")
            elif tag == "mtllib" and len(t) > 1:
                mats.update(_read_mtl(os.path.join(base, t[1])))
            elif tag == "usemtl" and len(t) > 1:
                material = t[1]
            elif tag == "f":
                if current is None:
                    current = start("part")
                corners = []
                for tok in t[1:]:
                    i = int(tok.split("/")[0])
                    corners.append(verts[i - 1] if i > 0 else verts[len(verts) + i])
                rgb = colors.get(current["name"]) or colors.get(material) or mats.get(material) or default_color
                base_i = len(current["pos"])
                for c in corners:
                    current["pos"].append(c)
                    current["col"].append((rgb[0], rgb[1], rgb[2], alpha))
                for k in range(1, len(corners) - 1):
                    current["idx"].append((base_i, base_i + k, base_i + k + 1))

    out = []
    off = np.array(offset, dtype=np.float32)
    for p in parts:
        if not p["idx"]:
            continue
        v = np.array(p["pos"], dtype=np.float32) * scale
        if matrix is not None:
            v = v @ np.asarray(matrix, dtype=np.float32).T
        v = v + off
        if flip_z:
            v[:, 2] *= -1.0
        mesh = Mesh(v, np.array(p["col"], dtype=np.uint8), np.array(p["idx"], dtype=np.uint32))
        out.append(ObjPart(p["name"], mesh, (v.min(axis=0), v.max(axis=0))))
    return out


def bounds_of(parts):
    lo = np.min([p.bounds[0] for p in parts], axis=0)
    hi = np.max([p.bounds[1] for p in parts], axis=0)
    return lo, hi


class TextureData:
    def __init__(self, rgba):
        rgb = np.ascontiguousarray(rgba[..., :3]).astype(np.float32)
        self.levels = [rgb]
        while min(self.levels[-1].shape[:2]) > 2:
            a = self.levels[-1]
            h, w = a.shape[0] // 2 * 2, a.shape[1] // 2 * 2
            self.levels.append(a[:h, :w].reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3)))

    @property
    def size(self):
        return self.levels[0].shape[1]

    def sample(self, uv, level=0):
        a = self.levels[min(level, len(self.levels) - 1)]
        h, w = a.shape[:2]
        x = uv[..., 0] * w - 0.5
        y = uv[..., 1] * h - 0.5
        x0 = np.floor(x)
        y0 = np.floor(y)
        fx = (x - x0)[..., None]
        fy = (y - y0)[..., None]
        xi0 = x0.astype(np.int64) % w
        yi0 = y0.astype(np.int64) % h
        xi1 = (xi0 + 1) % w
        yi1 = (yi0 + 1) % h
        top = a[yi0, xi0] * (1.0 - fx) + a[yi0, xi1] * fx
        bot = a[yi1, xi0] * (1.0 - fx) + a[yi1, xi1] * fx
        return top * (1.0 - fy) + bot * fy


_TEXTURES = {}


def load_texture_data(path):
    data = _TEXTURES.get(path)
    if data is None:
        from lysyk.engine._native import read_png

        data = TextureData(read_png(path))
        _TEXTURES[path] = data
    return data


def read_materials(path):
    mats = {}
    cur = None
    if not os.path.isfile(path):
        return mats
    base = os.path.dirname(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.split(None, 1)
            if len(t) < 2:
                continue
            tag, rest = t[0], t[1].strip()
            if tag == "newmtl":
                cur = rest
                mats[cur] = {"kd": (1.0, 1.0, 1.0), "map": None}
            elif tag == "Kd" and cur is not None:
                v = rest.split()
                mats[cur]["kd"] = (float(v[0]), float(v[1]), float(v[2]))
            elif tag == "map_Kd" and cur is not None:
                mats[cur]["map"] = os.path.normpath(os.path.join(base, rest))
    return mats


def _tessellate_quads(P, T, step):
    out_p, out_t, out_f = [], [], []
    e_u = np.maximum(np.linalg.norm(P[:, 1] - P[:, 0], axis=1), np.linalg.norm(P[:, 2] - P[:, 3], axis=1))
    e_v = np.maximum(np.linalg.norm(P[:, 3] - P[:, 0], axis=1), np.linalg.norm(P[:, 2] - P[:, 1], axis=1))
    nu = np.clip(np.ceil(e_u / step), 1, 48).astype(np.int32)
    nv = np.clip(np.ceil(e_v / step), 1, 48).astype(np.int32)
    keys = nu.astype(np.int64) * 100 + nv
    for key in np.unique(keys):
        sel = np.nonzero(keys == key)[0]
        gu, gv = int(key // 100), int(key % 100)
        s, t = np.meshgrid(np.linspace(0.0, 1.0, gu + 1), np.linspace(0.0, 1.0, gv + 1))
        s, t = s.ravel().astype(np.float32), t.ravel().astype(np.float32)
        w = np.stack([(1 - s) * (1 - t), s * (1 - t), s * t, (1 - s) * t], axis=1)
        out_p.append(np.einsum("vk,nkc->nvc", w, P[sel]))
        out_t.append(np.einsum("vk,nkc->nvc", w, T[sel]))
        ii, jj = np.meshgrid(np.arange(gu), np.arange(gv))
        a = (jj * (gu + 1) + ii).ravel()
        b, c, d = a + 1, a + gu + 2, a + gu + 1
        cell = np.concatenate([np.stack([a, b, c], axis=1), np.stack([a, c, d], axis=1)])
        out_f.append((cell, len(sel), (gu + 1) * (gv + 1)))
    return out_p, out_t, out_f


def _tessellate_tris(P, T, step):
    out_p, out_t, out_f = [], [], []
    e = np.maximum.reduce([np.linalg.norm(P[:, 1] - P[:, 0], axis=1), np.linalg.norm(P[:, 2] - P[:, 1], axis=1), np.linalg.norm(P[:, 0] - P[:, 2], axis=1)])
    n_all = np.clip(np.ceil(e / step), 1, 32).astype(np.int32)
    for n in np.unique(n_all):
        n = int(n)
        sel = np.nonzero(n_all == n)[0]
        lat = [(i, j) for j in range(n + 1) for i in range(n + 1 - j)]
        index = {ij: k for k, ij in enumerate(lat)}
        bi = np.array([[1 - (i + j) / n, i / n, j / n] for i, j in lat], dtype=np.float32)
        out_p.append(np.einsum("vk,nkc->nvc", bi, P[sel]))
        out_t.append(np.einsum("vk,nkc->nvc", bi, T[sel]))
        cell = []
        for j in range(n):
            for i in range(n - j):
                cell.append((index[(i, j)], index[(i + 1, j)], index[(i, j + 1)]))
                if i + j < n - 1:
                    cell.append((index[(i + 1, j)], index[(i + 1, j + 1)], index[(i, j + 1)]))
        out_f.append((np.array(cell, dtype=np.int64), len(sel), len(lat)))
    return out_p, out_t, out_f


def _planar_uv(P, size):
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    axis = np.argmax(np.abs(n), axis=1)
    T = np.empty(P.shape[:2] + (2,), dtype=np.float32)
    for ax, (a, b) in enumerate(((1, 2), (0, 2), (0, 1))):
        m = axis == ax
        T[m, :, 0] = P[m][:, :, a] / size
        T[m, :, 1] = P[m][:, :, b] / size
    return T


def _bake(P, T, kd, tex, step, alpha):
    if len(P) == 0:
        return None
    if P.shape[1] == 4:
        pp, tt, ff = _tessellate_quads(P, T, step)
    else:
        pp, tt, ff = _tessellate_tris(P, T, step)
    verts, cols, faces = [], [], []
    base = 0
    for p, t, (cell, n, per) in zip(pp, tt, ff):
        flat_p = p.reshape(-1, 3)
        flat_t = t.reshape(-1, 2)
        if tex is not None:
            span = np.abs(t[:, -1] - t[:, 0]).max() / max(1.0, math.sqrt(per))
            texels = float(span) * tex.size
            level = int(max(0.0, math.floor(math.log2(max(texels, 1.0)))))
            rgb = tex.sample(flat_t, level) * np.asarray(kd, dtype=np.float32)
        else:
            rgb = np.tile(np.asarray(kd, dtype=np.float32) * 255.0, (len(flat_p), 1))
        col = np.empty((len(flat_p), 4), dtype=np.uint8)
        col[:, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
        col[:, 3] = alpha
        offs = (np.arange(n, dtype=np.int64) * per + base)[:, None, None]
        f = (cell[None, :, :] + offs).reshape(-1, 3)
        verts.append(flat_p)
        cols.append(col)
        faces.append(f)
        base += n * per
    return np.concatenate(verts), np.concatenate(cols), np.concatenate(faces)


_OBJ_CACHE = {}


def _parse_obj(path):
    cached = _OBJ_CACHE.get(path)
    if cached is not None:
        return cached
    base = os.path.dirname(path)
    verts, uvs = [], []
    mats = {}
    parts = {}
    order = []
    cur = None
    mat = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.split()
            if not t:
                continue
            tag = t[0]
            if tag == "v":
                verts.append((float(t[1]), float(t[2]), float(t[3])))
            elif tag == "vt":
                uvs.append((float(t[1]), float(t[2])))
            elif tag in ("o", "g"):
                cur = t[1] if len(t) > 1 else "part"
                if cur not in parts:
                    parts[cur] = []
                    order.append(cur)
            elif tag == "mtllib" and len(t) > 1:
                mats.update(read_materials(os.path.join(base, t[1])))
            elif tag == "usemtl" and len(t) > 1:
                mat = " ".join(t[1:])
            elif tag == "f":
                if cur is None:
                    cur = "part"
                    parts[cur] = []
                    order.append(cur)
                vi, ti = [], []
                for tok in t[1:]:
                    bits = tok.split("/")
                    i = int(bits[0])
                    vi.append(i - 1 if i > 0 else len(verts) + i)
                    if len(bits) > 1 and bits[1]:
                        j = int(bits[1])
                        ti.append(j - 1 if j > 0 else len(uvs) + j)
                parts[cur].append((mat, vi, ti if len(ti) == len(vi) else None))
    V = np.asarray(verts, dtype=np.float32)
    U = np.asarray(uvs, dtype=np.float32) if uvs else np.zeros((1, 2), dtype=np.float32)
    cached = (V, U, mats, parts, order)
    _OBJ_CACHE[path] = cached
    return cached


def load_textured(path, step=0.12, scale=1.0, flip_z=False, paint=0.0, uv_size=0.6, offset=(0.0, 0.0, 0.0), only=None):
    base_V, U, mats, parts, order = _parse_obj(path)
    V = base_V * scale + np.asarray(offset, dtype=np.float32)
    if flip_z:
        V[:, 2] *= -1.0
    alpha = int(round(max(0.0, min(1.0, paint)) * 255))
    out = []
    for name in order:
        if only is not None and name not in only:
            continue
        groups = {}
        for m, vi, ti in parts[name]:
            if len(vi) < 3:
                continue
            groups.setdefault(m, {"q": [], "t": []})
            if len(vi) == 4:
                groups[m]["q"].append((vi, ti))
            else:
                for k in range(1, len(vi) - 1):
                    groups[m]["t"].append(((vi[0], vi[k], vi[k + 1]), None if ti is None else (ti[0], ti[k], ti[k + 1])))
        vs, cs, fs = [], [], []
        base_i = 0
        for m, g in groups.items():
            info = mats.get(m, {"kd": (1.0, 1.0, 1.0), "map": None})
            tex = load_texture_data(info["map"]) if info["map"] and os.path.isfile(info["map"]) else None
            kd = info["kd"]
            for kind in ("q", "t"):
                items = g[kind]
                if not items:
                    continue
                P = V[np.asarray([i[0] for i in items], dtype=np.int64)]
                if all(i[1] is not None for i in items):
                    T = U[np.asarray([i[1] for i in items], dtype=np.int64)]
                else:
                    T = _planar_uv(P, uv_size)
                res = _bake(P, T, kd, tex, step, alpha)
                if res is None:
                    continue
                v, c, f = res
                vs.append(v)
                cs.append(c)
                fs.append(f + base_i)
                base_i += len(v)
        if not vs:
            continue
        v = np.concatenate(vs).astype(np.float32)
        out.append(ObjPart(name, Mesh(v, np.concatenate(cs), np.concatenate(fs).astype(np.uint32)), (v.min(axis=0), v.max(axis=0))))
    return out
