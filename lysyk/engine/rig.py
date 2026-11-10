import math

from lysyk.engine.tween import ease_in_out_sine, lerp


class Pose:
    def __init__(self, position, yaw, pitch=0.0):
        self.position = tuple(position)
        self.yaw = yaw
        self.pitch = pitch

    def copy(self):
        return Pose(self.position, self.yaw, self.pitch)


def shortest_angle(a, b):
    d = (b - a + 180.0) % 360.0 - 180.0
    return a + d


class PoseRig:
    def __init__(self, pose):
        self.pose = pose.copy()
        self.roll = 0.0
        self.path = None
        self.time = 0.0
        self.duration = 0.0
        self.bob = 0.0
        self.steps = 0.0
        self.on_done = None
        self.ease = ease_in_out_sine
        self.start_yaw = pose.yaw
        self.end_yaw = pose.yaw
        self.start_pitch = pose.pitch
        self.end_pitch = pose.pitch
        self.lengths = []
        self.total = 0.0

    @property
    def busy(self):
        return self.path is not None

    def place(self, pose):
        self.pose = pose.copy()
        self.path = None

    def travel(self, waypoints, duration, yaw, pitch=0.0, bob=0.0, steps=0.0, on_done=None, ease=ease_in_out_sine):
        pts = [self.pose.position] + [tuple(p) for p in waypoints]
        self.path = pts
        self.lengths = []
        total = 0.0
        for a, b in zip(pts, pts[1:]):
            total += math.dist(a, b)
            self.lengths.append(total)
        self.total = max(total, 1e-6)
        self.time = 0.0
        self.duration = max(duration, 1e-6)
        self.bob = bob
        self.steps = steps
        self.on_done = on_done
        self.ease = ease
        self.start_yaw = self.pose.yaw
        self.end_yaw = shortest_angle(self.pose.yaw, yaw)
        self.start_pitch = self.pose.pitch
        self.end_pitch = pitch

    def _sample(self, u):
        d = u * self.total
        prev = 0.0
        for i, upto in enumerate(self.lengths):
            if d <= upto or i == len(self.lengths) - 1:
                a, b = self.path[i], self.path[i + 1]
                span = max(upto - prev, 1e-9)
                k = max(0.0, min(1.0, (d - prev) / span))
                return tuple(lerp(a[j], b[j], k) for j in range(3))
            prev = upto
        return self.path[-1]

    def update(self, dt):
        if self.path is None:
            return self.pose
        self.time += dt
        raw = min(1.0, self.time / self.duration)
        u = self.ease(raw)
        pos = self._sample(u)
        env = math.sin(math.pi * raw)
        phase = raw * self.steps * math.tau
        y = pos[1] + math.sin(phase) * self.bob * env
        self.roll = math.cos(phase * 0.5) * self.bob * 0.6 * env
        self.pose = Pose((pos[0], y, pos[2]), lerp(self.start_yaw, self.end_yaw, u), lerp(self.start_pitch, self.end_pitch, u))
        if raw >= 1.0:
            end = self.path[-1]
            self.pose = Pose(end, self.end_yaw, self.end_pitch)
            self.roll = 0.0
            self.path = None
            done, self.on_done = self.on_done, None
            if done is not None:
                done()
        return self.pose
