import math

import numpy as np

MAX_LIGHTS = 8

_KEYS = (
    (0.0, dict(zenith=(5, 8, 22), horizon=(18, 24, 52), fog=(14, 20, 42), sun=(0.42, 0.52, 0.95, 0.55), sky=(0.10, 0.13, 0.26), ground=(0.05, 0.06, 0.12), stars=1.0, glow=0.2)),
    (5.0, dict(zenith=(12, 16, 40), horizon=(40, 50, 86), fog=(34, 42, 74), sun=(0.42, 0.52, 0.95, 0.5), sky=(0.12, 0.15, 0.3), ground=(0.06, 0.07, 0.13), stars=0.8, glow=0.3)),
    (6.4, dict(zenith=(70, 80, 140), horizon=(255, 160, 110), fog=(214, 150, 128), sun=(1.0, 0.62, 0.38, 0.9), sky=(0.42, 0.42, 0.55), ground=(0.28, 0.24, 0.24), stars=0.15, glow=1.0)),
    (8.0, dict(zenith=(86, 142, 224), horizon=(196, 218, 240), fog=(184, 208, 232), sun=(1.0, 0.86, 0.7, 1.15), sky=(0.52, 0.6, 0.76), ground=(0.34, 0.33, 0.3), stars=0.0, glow=0.6)),
    (12.5, dict(zenith=(58, 120, 214), horizon=(172, 208, 240), fog=(172, 206, 238), sun=(1.0, 0.96, 0.88, 1.35), sky=(0.55, 0.64, 0.82), ground=(0.36, 0.34, 0.3), stars=0.0, glow=0.45)),
    (17.0, dict(zenith=(70, 118, 206), horizon=(236, 200, 160), fog=(226, 196, 164), sun=(1.0, 0.82, 0.58, 1.25), sky=(0.52, 0.56, 0.7), ground=(0.34, 0.3, 0.26), stars=0.0, glow=0.9)),
    (18.6, dict(zenith=(62, 58, 134), horizon=(255, 138, 70), fog=(232, 140, 96), sun=(1.0, 0.56, 0.28, 1.05), sky=(0.5, 0.42, 0.55), ground=(0.32, 0.22, 0.2), stars=0.05, glow=1.2)),
    (19.8, dict(zenith=(26, 30, 80), horizon=(142, 82, 112), fog=(104, 70, 100), sun=(0.8, 0.42, 0.5, 0.55), sky=(0.26, 0.26, 0.42), ground=(0.14, 0.12, 0.2), stars=0.5, glow=0.8)),
    (21.5, dict(zenith=(8, 12, 30), horizon=(28, 36, 70), fog=(22, 30, 58), sun=(0.42, 0.52, 0.95, 0.52), sky=(0.12, 0.15, 0.28), ground=(0.06, 0.07, 0.13), stars=0.95, glow=0.3)),
    (24.0, dict(zenith=(5, 8, 22), horizon=(18, 24, 52), fog=(14, 20, 42), sun=(0.42, 0.52, 0.95, 0.55), sky=(0.10, 0.13, 0.26), ground=(0.05, 0.06, 0.12), stars=1.0, glow=0.2)),
)


def _lerp(a, b, t):
    if isinstance(a, tuple):
        return tuple(x + (y - x) * t for x, y in zip(a, b))
    return a + (b - a) * t


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


class PointLight:
    __slots__ = ("position", "color", "intensity", "radius", "direction", "cone", "enabled")

    def __init__(self, position=(0.0, 0.0, 0.0), color=(1.0, 0.95, 0.85), intensity=1.0, radius=30.0, direction=None, cone=None):
        self.position = np.array(position, dtype=np.float64)
        self.color = tuple(color)
        self.intensity = intensity
        self.radius = radius
        self.direction = None if direction is None else np.array(direction, dtype=np.float64)
        self.cone = cone
        self.enabled = True


class Lighting:
    def __init__(self):
        self.shadows = True
        self.hour = 12.0
        self.azimuth = 215.0
        self.fog_density = 0.0021
        self.fog_tint = (1.0, 1.0, 1.0)
        self.sky_tint = (1.0, 1.0, 1.0)
        self.sun_scale = 1.0
        self.ambient_scale = 1.0
        self.exposure = 1.0
        self.shadow_strength = 0.82
        self.water_color = (18, 78, 118)
        self.fog_scatter = 1.0
        self.stars_scale = 1.0
        self.elevation = 45.0
        self.night_factor = 0.0
        self.lights = []
        self.static_pos = np.zeros((0, 3), dtype=np.float64)
        self.static_color = np.zeros((0, 3), dtype=np.float64)
        self.static_intensity = 1.0
        self.static_radius = 30.0
        self.static_enabled = True
        self.manual = None
        self._cache = None
        self.set_hour(12.0)

    def set_hour(self, hour):
        self.hour = hour % 24.0
        self.manual = None
        self._resolve()

    def advance(self, hours):
        self.set_hour(self.hour + hours)

    def set_manual(self, zenith, horizon, fog, sun_color, sun_intensity, sky_ambient, ground_ambient, elevation, azimuth, stars=0.0, glow=0.3):
        self.manual = dict(zenith=zenith, horizon=horizon, fog=fog, sun=(sun_color[0], sun_color[1], sun_color[2], sun_intensity),
                           sky=sky_ambient, ground=ground_ambient, stars=stars, glow=glow)
        self.elevation = elevation
        self.azimuth = azimuth
        self.night_factor = 0.0
        self._resolve(manual=True)

    def _resolve(self, manual=False):
        if manual and self.manual is not None:
            k = self.manual
        else:
            h = self.hour
            for i in range(len(_KEYS) - 1):
                h0, k0 = _KEYS[i]
                h1, k1 = _KEYS[i + 1]
                if h0 <= h <= h1:
                    t = _smooth((h - h0) / (h1 - h0))
                    k = {name: _lerp(k0[name], k1[name], t) for name in k0}
                    break
            e = 62.0 * math.sin(math.pi * (h - 6.0) / 13.0)
            w = _smooth(min(1.0, max(0.0, (e + 6.0) / 10.0)))
            self.night_factor = 1.0 - w
            day_e = max(e, 9.0)
            moon_e = 42.0
            self.elevation = day_e * w + moon_e * (1.0 - w)
        self._k = k
        self._sky = tuple(c * t for c, t in zip(k["zenith"], self.sky_tint))
        self._hor = tuple(c * t for c, t in zip(k["horizon"], self.sky_tint))
        self._fog = tuple(c * t for c, t in zip(k["fog"], self.fog_tint))

    def refresh(self):
        self._resolve(manual=self.manual is not None)

    def sun_direction(self):
        az = math.radians(self.azimuth)
        el = math.radians(self.elevation)
        c = math.cos(el)
        return (c * math.sin(az), math.sin(el), c * math.cos(az))

    def colors(self):
        k = self._k
        sun = k["sun"]
        sun_rgb = tuple(sun[i] * sun[3] * self.sun_scale for i in range(3))
        sky = tuple(c * self.ambient_scale for c in k["sky"])
        ground = tuple(c * self.ambient_scale for c in k["ground"])
        return dict(
            zenith=tuple(c / 255.0 for c in self._sky),
            horizon=tuple(c / 255.0 for c in self._hor),
            fog=tuple(c / 255.0 for c in self._fog),
            sun=sun_rgb, sky=sky, ground=ground,
            stars=k["stars"] * self.stars_scale, glow=k["glow"],
        )

    def clear_color(self):
        return tuple(int(c) for c in self._fog)

    def add_light(self, light):
        self.lights.append(light)
        return light

    def remove_light(self, light):
        try:
            self.lights.remove(light)
        except ValueError:
            pass

    def clear_lights(self):
        self.lights.clear()

    def set_static(self, positions, color, intensity, radius):
        self.static_pos = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
        self.static_color = np.asarray(color, dtype=np.float64)
        self.static_intensity = intensity
        self.static_radius = radius

    def clear_static(self):
        self.static_pos = np.zeros((0, 3), dtype=np.float64)

    def gather(self, cam):
        out = []
        for l in self.lights:
            if l.enabled:
                out.append((l.position, l.color, l.intensity, l.radius, l.direction, l.cone))
        room = MAX_LIGHTS - len(out)
        if room > 0 and self.static_enabled and len(self.static_pos):
            d = ((self.static_pos - cam) ** 2).sum(axis=1)
            near = np.flatnonzero(d < (self.static_radius * 2.2) ** 2)
            if len(near) > room:
                near = near[np.argpartition(d[near], room - 1)[:room]]
            for i in near:
                out.append((self.static_pos[i], self.static_color, self.static_intensity, self.static_radius, None, None))
        return out[:MAX_LIGHTS]
