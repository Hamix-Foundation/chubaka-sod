import numpy as np

from lysyk.engine import _native


def _prepare(x, z):
    x, z = np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(z, dtype=np.float64))
    shape = x.shape
    return np.ascontiguousarray(x).reshape(-1), np.ascontiguousarray(z).reshape(-1), shape


def _finish(out, shape):
    out = out.reshape(shape)
    return out[()] if shape == () else out


def value(x, z, seed=0):
    xf, zf, shape = _prepare(x, z)
    return _finish(_native.value_flat(xf, zf, int(seed)), shape)


def fbm(x, z, octaves=4, seed=0, lacunarity=2.0, gain=0.5):
    xf, zf, shape = _prepare(x, z)
    return _finish(_native.fbm_flat(xf, zf, int(octaves), int(seed), float(lacunarity), float(gain)), shape)


def ridged(x, z, octaves=4, seed=0):
    xf, zf, shape = _prepare(x, z)
    return _finish(_native.ridged_flat(xf, zf, int(octaves), int(seed)), shape)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
