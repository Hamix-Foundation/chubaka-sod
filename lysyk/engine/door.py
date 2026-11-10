import math

from lysyk.engine.tween import damp


class Door:
    def __init__(self, obj, hinge, closed=0.0, opened=-1.0, push_speed=0.22, hold_rate=5.0, on_event=None):
        self.obj = obj
        self.hinge = tuple(hinge)
        self.closed = closed
        self.opened = opened
        self.push_speed = push_speed
        self.hold_rate = hold_rate
        self.on_event = on_event
        self.angle = closed
        self.speed = 0.0
        self.held = False
        self.pushing = True
        self.creak_clock = 0.0
        self.was_closed = True
        self.obj.position = self.hinge
        self.obj.rotation = (0.0, self.angle, 0.0)

    @property
    def openness(self):
        span = self.opened - self.closed
        return 0.0 if span == 0.0 else max(0.0, min(1.0, (self.angle - self.closed) / span))

    @property
    def shut(self):
        return self.openness < 0.01

    def emit(self, name):
        if self.on_event is not None:
            self.on_event(name, self)

    def update(self, dt):
        before = self.angle
        if self.held:
            self.angle = damp(self.angle, self.closed, self.hold_rate, dt)
            if abs(self.angle - self.closed) < 0.004:
                self.angle = self.closed
        elif self.pushing:
            step = self.push_speed * dt
            direction = 1.0 if self.opened > self.closed else -1.0
            self.angle += direction * step
            lo, hi = sorted((self.closed, self.opened))
            self.angle = max(lo, min(hi, self.angle))
        self.speed = (self.angle - before) / max(dt, 1e-6)
        moving = abs(self.speed) > 0.05
        self.creak_clock = max(0.0, self.creak_clock - dt)
        if moving and self.creak_clock <= 0.0 and 0.02 < self.openness < 0.98:
            self.creak_clock = 0.9 if self.held else 1.6
            self.emit("creak")
        closed_now = self.shut
        if closed_now and not self.was_closed:
            self.emit("thud" if self.held else "latch")
        elif not closed_now and self.was_closed:
            self.emit("unlatch")
        self.was_closed = closed_now
        self.obj.rotation = (0.0, self.angle, 0.0)
        return self.angle
