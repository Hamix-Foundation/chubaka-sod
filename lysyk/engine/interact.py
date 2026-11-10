import math

import numpy as np


def forward_components(yaw, pitch=0.0):
    cp = math.cos(pitch)
    return math.sin(yaw) * cp, -math.sin(pitch), math.cos(yaw) * cp


def forward_vector(yaw, pitch=0.0):
    return np.array(forward_components(yaw, pitch), dtype=np.float64)


class Hotspot:
    def __init__(self, name, position, radius, action=None, enabled=True, max_distance=0.0):
        self.name = name
        self.position = np.array(position, dtype=np.float64)
        self.coords = (float(position[0]), float(position[1]), float(position[2]))
        self.radius = radius
        self.action = action
        self.enabled = enabled
        self.max_distance = max_distance
        self.angle = math.pi


class Interaction:
    def __init__(self, margin_degrees=3.0):
        self.spots = []
        self.hover = None
        self.margin = math.radians(margin_degrees)

    def add(self, spot):
        self.spots.append(spot)
        return spot

    def update(self, eye, yaw, pitch=0.0):
        fx, fy, fz = forward_components(yaw, pitch)
        ex, ey, ez = float(eye[0]), float(eye[1]), float(eye[2])
        best = None
        best_angle = math.pi
        for s in self.spots:
            s.angle = math.pi
            if not s.enabled:
                continue
            vx, vy, vz = s.coords[0] - ex, s.coords[1] - ey, s.coords[2] - ez
            dist = math.sqrt(vx * vx + vy * vy + vz * vz)
            if dist < 1e-6 or (s.max_distance > 0.0 and dist > s.max_distance):
                continue
            angle = math.acos(max(-1.0, min(1.0, (fx * vx + fy * vy + fz * vz) / dist)))
            s.angle = angle
            if angle <= math.atan2(s.radius, dist) + self.margin and angle < best_angle:
                best = s
                best_angle = angle
        self.hover = best
        return best

    def click(self):
        spot = self.hover
        if spot is None or spot.action is None:
            return False
        spot.action()
        return True
