import numpy as np

_M = np.uint64(0xFFFFFFFF)


def _hash(ix, iz, seed):
    h = (ix.astype(np.uint64) * np.uint64(374761393) + iz.astype(np.uint64) * np.uint64(668265263) + np.uint64(seed * 2246822519 & 0xFFFFFFFF)) & _M
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & _M
    h = h ^ (h >> np.uint64(16))
    return (h & np.uint64(0xFFFFFF)).astype(np.float64) / float(0x1000000)


def value(x, z, seed=0):
    x = np.asarray(x, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    fx, fz = np.floor(x), np.floor(z)
    ix, iz = fx.astype(np.int64), fz.astype(np.int64)
    tx, tz = x - fx, z - fz
    tx = tx * tx * (3.0 - 2.0 * tx)
    tz = tz * tz * (3.0 - 2.0 * tz)
    a = _hash(ix, iz, seed)
    b = _hash(ix + 1, iz, seed)
    c = _hash(ix, iz + 1, seed)
    d = _hash(ix + 1, iz + 1, seed)
    return (a + (b - a) * tx) * (1.0 - tz) + (c + (d - c) * tx) * tz


def fbm(x, z, octaves=4, seed=0, lacunarity=2.0, gain=0.5):
    total = 0.0
    amp = 1.0
    norm = 0.0
    fx = 1.0
    for o in range(octaves):
        total = total + amp * value(np.asarray(x) * fx, np.asarray(z) * fx, seed + o * 17)
        norm += amp
        amp *= gain
        fx *= lacunarity
    return total / norm


def ridged(x, z, octaves=4, seed=0):
    return 1.0 - np.abs(2.0 * fbm(x, z, octaves, seed) - 1.0)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
