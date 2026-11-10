import math

from chubaka.echoes.base import Trait


class FlashlightShy(Trait):
    def __init__(self, tolerance=0.2, steps=3, stun=5.0):
        self.tolerance = tolerance
        self.steps = steps
        self.stun = stun

    def on_lit(self, echo, ctx, dt):
        if echo.lit_time >= self.tolerance and echo.state != "attacking":
            echo.lit_time = 0.0
            echo.flee(self.steps, self.stun)


class CameraFreeze(Trait):
    def __init__(self, include_player=True, rush=1.0):
        self.include_player = include_player
        self.rush = rush

    def can_move(self, echo, ctx):
        if ctx.on_camera(echo):
            return False
        return not (self.include_player and ctx.seen_by_player(echo))

    def move_chance(self, echo, ctx, chance):
        return min(1.0, chance * self.rush)


class LightEater(Trait):
    def __init__(self, radius=9.0, rate=0.05):
        self.radius = radius
        self.rate = rate

    def update(self, echo, ctx, dt):
        if ctx.view.flashlight_on and ctx.distance_to_player(echo) < self.radius:
            ctx.drain += self.rate * dt


class Stalker(Trait):
    def __init__(self, dark_boost=1.8, unseen_boost=1.4):
        self.dark_boost = dark_boost
        self.unseen_boost = unseen_boost

    def move_chance(self, echo, ctx, chance):
        if not ctx.view.flashlight_on:
            chance *= self.dark_boost
        if not ctx.seen_by_player(echo):
            chance *= self.unseen_boost
        return min(1.0, chance)


class DoorBreaker(Trait):
    def __init__(self, factor=1.6):
        self.factor = factor

    def door_pressure(self, echo, ctx):
        return self.factor


class Sprinter(Trait):
    def __init__(self, multiplier=1.8):
        self.multiplier = multiplier

    def attach(self, echo):
        echo.speed_scale = self.multiplier


class Footsteps(Trait):
    def __init__(self, sound="step", hearing=18.0, volume=0.5):
        self.sound = sound
        self.hearing = hearing
        self.volume = volume

    def on_arrive(self, echo, ctx):
        d = ctx.distance_to_player(echo)
        if d < self.hearing:
            ctx.play(self.sound, self.volume * (1.0 - d / self.hearing))


class Unrecorded(Trait):
    def visible_on_camera(self, echo, ctx):
        return False


class Shadowed(Trait):
    def visible_to_player(self, echo, ctx):
        return ctx.view.flashlight_on or echo.node == echo.spec.goal


class Patient(Trait):
    def __init__(self, extra_wait=2.5):
        self.extra_wait = extra_wait

    def can_attack(self, echo, ctx):
        return echo.door_time >= echo.spec.door_wait + self.extra_wait
