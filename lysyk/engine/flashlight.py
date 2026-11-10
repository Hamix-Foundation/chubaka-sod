import math
import random

from lysyk.engine.lighting import PointLight
from lysyk.engine.tween import damp


class Flashlight:
    def __init__(self, lighting, color=(1.0, 0.93, 0.78), intensity=2.4, radius=11.0, cone=0.84, drain=0.012, seed=3):
        self.light = PointLight((0.0, 0.0, 0.0), color, 0.0, radius, (0.0, 0.0, 1.0), cone)
        self.light.enabled = False
        lighting.add_light(self.light)
        self.intensity = intensity
        self.radius = radius
        self.cone = cone
        self.drain = drain
        self.battery = 1.0
        self.on = False
        self.level = 0.0
        self.rand = random.Random(seed)
        self.time = 0.0
        self.offset = (0.0, -0.18, 0.0)

    @property
    def usable(self):
        return self.battery > 0.0

    def set(self, value):
        self.on = bool(value) and self.usable

    def toggle(self):
        self.set(not self.on)
        return self.on

    def update(self, dt, eye, forward):
        self.time += dt
        if self.on:
            self.battery = max(0.0, self.battery - self.drain * dt)
            if self.battery <= 0.0:
                self.on = False
        target = 1.0 if self.on else 0.0
        if self.on and self.battery < 0.15:
            target *= 0.55 + 0.45 * (math.sin(self.time * 41.0) * math.sin(self.time * 13.0) > -0.2)
        self.level = damp(self.level, target, 40.0, dt)
        self.light.enabled = self.level > 0.01
        self.light.intensity = self.intensity * self.level
        self.light.position = (eye[0] + forward[0] * 0.15 + self.offset[0], eye[1] + self.offset[1], eye[2] + forward[2] * 0.15 + self.offset[2])
        self.light.direction = (float(forward[0]), float(forward[1]), float(forward[2]))
