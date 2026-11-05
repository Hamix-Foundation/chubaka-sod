import math

from lysyk.engine.tween import clamp01, lerp

ANGLE_MIN = -80.0
ANGLE_MAX = 80.0
TOUCH_SPEED = 60.0
SMOOTHING = 8.0
DEAD_ZONE = 0.15


def godot_lerp_factor(smoothing, dt):
    return clamp01(smoothing * dt)


class LookController:
    def __init__(self, initial_yaw, stage_width=1280.0, center=0.0, limit=ANGLE_MAX):
        self.limit = limit
        self.center = center
        self.yaw = initial_yaw
        self.target = initial_yaw
        self.stage_width = stage_width
        self.mouse_x = stage_width * 0.5
        self.touches = {}
        self.touch_direction = 0
        self.mobile = False

    def set_mobile(self, value):
        self.mobile = value

    def mouse_motion(self, x):
        self.mouse_x = x

    def touch(self, touch_id, phase, x, y):
        if phase == "down":
            self.touches[touch_id] = x
        elif phase == "move":
            if touch_id in self.touches:
                self.touches[touch_id] = x
        else:
            self.touches.pop(touch_id, None)
        self._update_direction()

    def _update_direction(self):
        self.touch_direction = 0
        if not self.touches:
            return
        left = sum(1 for x in self.touches.values() if x < self.stage_width * 0.5)
        right = len(self.touches) - left
        if left > 0 and right == 0:
            self.touch_direction = -1
        elif right > 0 and left == 0:
            self.touch_direction = 1

    def update(self, dt):
        if self.mobile or self.touches:
            if self.touch_direction != 0:
                self.target += self.touch_direction * TOUCH_SPEED * dt
                self.target = max(self.center - self.limit, min(self.center + self.limit, self.target))
        else:
            nx = (self.mouse_x / self.stage_width) * 2.0 - 1.0
            nx = max(-1.0, min(1.0, nx))
            if abs(nx) < DEAD_ZONE:
                nx = 0.0
            else:
                nx = math.copysign((abs(nx) - DEAD_ZONE) / (1.0 - DEAD_ZONE), nx)
            self.target = self.center + max(-self.limit, min(self.limit, nx * self.limit))
        self.yaw = lerp(self.yaw, self.target, godot_lerp_factor(SMOOTHING, dt))
        return self.yaw
