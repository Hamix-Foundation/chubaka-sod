import math


def clamp01(t):
    return 0.0 if t < 0.0 else 1.0 if t > 1.0 else t


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = clamp01(t)
    return t * t * (3.0 - 2.0 * t)


def ease_out_cubic(t):
    t = clamp01(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_sine(t):
    return -(math.cos(math.pi * clamp01(t)) - 1.0) / 2.0


def damp(current, target, rate, dt):
    return lerp(current, target, 1.0 - math.exp(-rate * dt))


class Tween:
    def __init__(self, start, end, duration, ease=smoothstep, delay=0.0):
        self.start = start
        self.end = end
        self.duration = max(duration, 1e-6)
        self.ease = ease
        self.delay = delay
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.value

    @property
    def value(self):
        k = (self.t - self.delay) / self.duration
        return lerp(self.start, self.end, self.ease(k))

    @property
    def done(self):
        return self.t - self.delay >= self.duration


class Timeline:
    def __init__(self):
        self.t = 0.0
        self.events = []

    def at(self, time, fn):
        self.events.append([time, fn, False])
        return self

    def update(self, dt):
        self.t += dt
        for e in self.events:
            if not e[2] and self.t >= e[0]:
                e[2] = True
                e[1]()

    @property
    def done(self):
        return all(e[2] for e in self.events)
