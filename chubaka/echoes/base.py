import copy
import math
import random
from dataclasses import dataclass, field

from chubaka.floorplan import segment_hits_rect

DOOR_SHUT = 0.12


class Trait:
    def attach(self, echo):
        pass

    def update(self, echo, ctx, dt):
        pass

    def can_move(self, echo, ctx):
        return True

    def move_chance(self, echo, ctx, chance):
        return chance

    def on_lit(self, echo, ctx, dt):
        pass

    def on_arrive(self, echo, ctx):
        pass

    def door_pressure(self, echo, ctx):
        return 1.0

    def can_attack(self, echo, ctx):
        return True

    def visible_on_camera(self, echo, ctx):
        return True

    def visible_to_player(self, echo, ctx):
        return True


@dataclass
class JumpscareSpec:
    video: str = ""
    sound: str = ""
    duration: float = 1.6
    shake: float = 1.0
    flash: tuple = (255, 255, 255)


@dataclass
class EchoSpec:
    id: str
    name: str
    start: str
    sprite: str = ""
    height: float = 1.85
    columns: int = 56
    shape: str = "wraith"
    color: tuple = (70, 76, 92)
    eyes: tuple = (255, 60, 60)
    ai: float = 5.0
    ai_per_night: float = 1.5
    interval: tuple = (4.0, 8.0)
    walk_speed: float = 1.5
    directness: float = 0.55
    goal: str = "office_door"
    habitats: tuple = ()
    door_threshold: float = 0.3
    door_wait: float = 3.5
    give_up: float = 7.0
    retreat_steps: int = 3
    retreat_speed: float = 3.0
    traits: tuple = ()
    jumpscare: JumpscareSpec = field(default_factory=JumpscareSpec)


class PlayerView:
    def __init__(self):
        self.position = (0.0, 1.2, 0.0)
        self.yaw = 0.0
        self.state = "seat"
        self.camera = None
        self.flashlight_on = False
        self.flashlight_dir = (0.0, 1.0)
        self.flashlight_cone = 0.84
        self.flashlight_radius = 14.0
        self.flashlight_battery = 1.0
        self.door_open = 0.0
        self.door_held = False
        self.fov = math.radians(70.0)


class EchoContext:
    def __init__(self, plan, rng):
        self.plan = plan
        self.rng = rng
        self.time = 0.0
        self.night = 1
        self.view = PlayerView()
        self.drain = 0.0
        self.attackers = []
        self.sounds = []
        self.extra = ()

    def begin(self, view, dt):
        self.view = view
        self.time += dt
        self.drain = 0.0
        self.extra = (self.plan.guard_door,) if view.door_open < DOOR_SHUT else ()

    def distance_to_player(self, echo):
        p = self.view.position
        e = echo.position
        return math.hypot(e[0] - p[0], e[2] - p[2])

    def lit(self, echo):
        v = self.view
        if not v.flashlight_on or v.state == "laptop":
            return False
        e = echo.position
        dx, dz = e[0] - v.position[0], e[2] - v.position[2]
        dist = math.hypot(dx, dz)
        if dist > v.flashlight_radius or dist < 0.05:
            return False
        if (dx * v.flashlight_dir[0] + dz * v.flashlight_dir[1]) / dist < v.flashlight_cone:
            return False
        return self.plan.line_of_sight(v.position, e, self.extra)

    def seen_by_player(self, echo, half_angle=None):
        v = self.view
        if v.state in ("laptop",):
            return False
        e = echo.position
        dx, dz = e[0] - v.position[0], e[2] - v.position[2]
        dist = math.hypot(dx, dz)
        if dist > 30.0 or dist < 0.05:
            return False
        half = half_angle if half_angle is not None else v.fov * 0.5 * 1.3
        if (dx * math.sin(v.yaw) + dz * math.cos(v.yaw)) / dist < math.cos(half):
            return False
        return self.plan.line_of_sight(v.position, e, self.extra)

    def on_camera(self, echo):
        cam = self.view.camera
        if cam is None:
            return False
        return self.plan.camera_sees(cam, echo.position, extra=self.extra)

    def watched(self, echo):
        return self.on_camera(echo) or self.seen_by_player(echo)

    def play(self, name, volume=1.0):
        self.sounds.append((name, volume))


class Echo:
    def __init__(self, spec, plan, rng, night=1):
        self.spec = spec
        self.id = spec.id
        self.name = spec.name
        self.plan = plan
        self.rng = rng
        self.node = spec.start
        self.history = [spec.start]
        self.route = []
        self.move_from = None
        self.move_to = None
        self.segment = 1.0
        self.progress = 0.0
        self.state = "idle"
        self.timer = rng.uniform(*spec.interval)
        self.stun = 0.0
        self.lit_time = 0.0
        self.door_time = 0.0
        self.away_time = 0.0
        self.speed_scale = 1.0
        self.slot = 0
        self.fleeing = False
        self.ai = min(20.0, spec.ai + spec.ai_per_night * (night - 1))
        self.traits = [copy.deepcopy(t) for t in spec.traits]
        self.position = plan.spot(spec.start, 0)
        for t in self.traits:
            t.attach(self)

    @property
    def at_goal(self):
        return self.node == self.spec.goal and self.state != "walking"

    @property
    def moving(self):
        return self.state == "walking"

    def allowed(self, node):
        habitats = self.spec.habitats
        return node == self.spec.goal or not habitats or node in habitats

    def begin_segment(self, target):
        self.move_from = self.plan.node_position(self.node)
        self.move_to = self.plan.node_position(target)
        self.segment = max(0.5, math.dist(self.move_from, self.move_to))
        self.progress = 0.0
        self.state = "walking"
        self.next_node = target

    def go_route(self, route, fleeing=False):
        route = [n for n in route if n != self.node]
        if not route:
            return
        self.route = route[1:]
        self.fleeing = fleeing
        self.begin_segment(route[0])

    def jump_to(self, node):
        self.node = node
        self.history.append(node)
        self.state = "idle"
        self.route = []
        self.position = self.plan.spot(node, self.slot)

    def choose_next(self):
        options = [n for n in self.plan.neighbors(self.node) if self.allowed(n)]
        if not options:
            return None
        dist = self.plan.distance_map(self.spec.goal)
        best = min(options, key=lambda n: dist.get(n, 999))
        if self.rng.random() < self.spec.directness:
            return best
        previous = self.history[-2] if len(self.history) > 1 else None
        pool = [n for n in options if n != previous] or options
        return self.rng.choice(pool)

    def step(self):
        nxt = self.choose_next()
        if nxt is not None:
            self.go_route([nxt])

    def retreat(self, steps=None, node=None):
        steps = self.spec.retreat_steps if steps is None else steps
        if node is None:
            idx = max(0, len(self.history) - 1 - steps)
            node = self.history[idx]
            if node == self.node:
                node = self.spec.start
            if node == self.node:
                options = self.plan.neighbors(self.node)
                node = self.rng.choice(options) if options else self.node
        route = self.plan.path(self.node, node)
        self.door_time = 0.0
        self.away_time = 0.0
        self.go_route(route, True)

    def flee(self, steps=3, stun=3.0):
        self.stun = stun
        self.state = "stunned" if self.state != "walking" else self.state
        self.retreat(steps)

    def arrive(self, ctx):
        self.node = self.next_node
        self.history.append(self.node)
        if len(self.history) > 24:
            self.history = self.history[-24:]
        self.position = self.plan.spot(self.node, self.slot)
        if self.route:
            self.begin_segment(self.route.pop(0))
            return
        self.state = "idle"
        self.fleeing = False
        self.timer = self.rng.uniform(*self.spec.interval)
        for t in self.traits:
            t.on_arrive(self, ctx)

    def advance(self, dt, ctx):
        speed = self.spec.retreat_speed if self.fleeing else self.spec.walk_speed
        self.progress += speed * self.speed_scale * dt / self.segment
        t = min(1.0, self.progress)
        a, b = self.move_from, self.move_to
        self.position = (a[0] + (b[0] - a[0]) * t, 0.0, a[2] + (b[2] - a[2]) * t)
        if self.progress >= 1.0:
            self.arrive(ctx)

    def update_door(self, dt, ctx):
        spec = self.spec
        if ctx.view.door_open >= spec.door_threshold:
            pressure = 1.0
            for t in self.traits:
                pressure *= t.door_pressure(self, ctx)
            self.door_time += dt * pressure
            self.away_time = 0.0
            if self.door_time >= spec.door_wait and all(t.can_attack(self, ctx) for t in self.traits):
                self.state = "attacking"
                ctx.attackers.append(self)
        else:
            self.door_time = max(0.0, self.door_time - dt)
            self.away_time += dt
            if self.away_time >= spec.give_up:
                self.retreat()

    def update(self, dt, ctx):
        for t in self.traits:
            t.update(self, ctx, dt)
        if self.state == "attacking":
            return
        if ctx.lit(self):
            self.lit_time += dt
            for t in self.traits:
                t.on_lit(self, ctx, dt)
        else:
            self.lit_time = max(0.0, self.lit_time - dt * 2.0)
        if self.state == "walking":
            self.advance(dt, ctx)
            return
        if self.stun > 0.0:
            self.stun -= dt
            if self.stun <= 0.0:
                self.state = "idle"
            return
        if self.at_goal:
            self.update_door(dt, ctx)
            return
        self.timer -= dt
        if self.timer > 0.0:
            return
        self.timer = self.rng.uniform(*self.spec.interval)
        if not all(t.can_move(self, ctx) for t in self.traits):
            return
        chance = self.ai / 20.0
        for t in self.traits:
            chance = t.move_chance(self, ctx, chance)
        if self.rng.random() < chance:
            self.step()

    def visible_on_camera(self, ctx):
        return all(t.visible_on_camera(self, ctx) for t in self.traits)

    def visible_to_player(self, ctx):
        return all(t.visible_to_player(self, ctx) for t in self.traits)
