import math
import random

from chubaka import asset
from chubaka.echoes import art
from chubaka.echoes.base import Echo, EchoContext, PlayerView
from chubaka.echoes.roster import active_for_night
from chubaka.floorplan import plan as default_plan
from lysyk.engine.objects import MODE_GLOW, MODE_LIT
from lysyk.engine.sprite import Billboard, BillboardLayer, Sprite, load_rgba

LISTEN_STEP = 0.55
LISTEN_IDLE = (2.2, 4.8)
LEVEL_DECAY = 2.4
CAMERA_TINT = (205, 210, 205)
NORMAL_TINT = (255, 255, 255)


class EchoManager:
    def __init__(self, plan=None, seed=21):
        self.plan = plan or default_plan()
        self.rng = random.Random(seed)
        self.ctx = EchoContext(self.plan, self.rng)
        self.echoes = []
        self.billboards = {}
        self.sprites = {}
        self.layer = BillboardLayer()
        self.world = None
        self.night = 1
        self.attacker = None
        self.drain = 0.0
        self.sounds = []
        self.camera_view = False
        self.audio_level = 0.0
        self.listen_timers = {}
        self.in_zone = set()

    def attach(self, world):
        self.world = world
        self.layer = BillboardLayer(world)
        self.billboards.clear()

    def sprite_for(self, spec):
        if spec.id in self.sprites:
            return self.sprites[spec.id]
        path = spec.sprite and asset(spec.sprite)
        image = None
        if path:
            try:
                image = load_rgba(path)
            except Exception:
                image = None
        if image is None:
            found = art.sprite_path(spec.id)
            if found:
                image = load_rgba(found)
        if image is None:
            image = art.placeholder_rgba(spec.shape, spec.color, spec.eyes, seed=sum(map(ord, spec.id)))
        self.sprites[spec.id] = Sprite(image, spec.height, spec.columns)
        return self.sprites[spec.id]

    def placeholder_image(self, spec):
        return art.placeholder_rgba(spec.shape, spec.color, spec.eyes, seed=sum(map(ord, spec.id)))

    def reset(self, night=1, specs=None):
        self.night = night
        self.attacker = None
        self.audio_level = 0.0
        self.listen_timers.clear()
        self.in_zone.clear()
        for echo in self.echoes:
            board = self.billboards.pop(echo.id, None)
            if board is not None:
                self.layer.remove(board)
        specs = specs if specs is not None else active_for_night(night)
        self.echoes = [Echo(spec, self.plan, self.rng, night) for spec in specs]
        self.ctx = EchoContext(self.plan, self.rng)
        self.ctx.night = night
        if self.world is not None:
            for echo in self.echoes:
                board = Billboard(self.sprite_for(echo.spec), echo.position)
                self.billboards[echo.id] = board
                self.layer.add(board)
        self.assign_slots()
        for echo in self.echoes:
            echo.position = self.plan.spot(echo.node, echo.slot)

    def assign_slots(self):
        counts = {}
        for echo in self.echoes:
            if echo.state == "walking":
                continue
            echo.slot = counts.get(echo.node, 0)
            counts[echo.node] = echo.slot + 1
            echo.position = self.plan.spot(echo.node, echo.slot)

    def update(self, dt, view):
        self.ctx.begin(view, dt)
        self.ctx.attackers.clear()
        self.ctx.sounds.clear()
        for echo in self.echoes:
            echo.update(dt, self.ctx)
        self.assign_slots()
        self.drain = self.ctx.drain
        self.sounds = list(self.ctx.sounds)
        if self.ctx.attackers and self.attacker is None:
            self.attacker = self.ctx.attackers[0]
        self.camera_view = view.camera is not None
        self.listen(dt, view.camera)
        self.sync(view)

    def listen(self, dt, camera):
        self.audio_level = max(0.0, self.audio_level - dt * LEVEL_DECAY)
        if camera is None or not camera.audio_only:
            self.listen_timers.clear()
            self.in_zone.clear()
            return
        for echo in self.echoes:
            region = self.plan.region_at(echo.position[0], echo.position[2])
            inside = region is not None and region.name == camera.zone
            if not inside:
                if echo.id in self.in_zone:
                    self.in_zone.discard(echo.id)
                    self.hear("door_close", 0.7)
                self.listen_timers.pop(echo.id, None)
                continue
            if echo.id not in self.in_zone:
                self.in_zone.add(echo.id)
                self.hear("door_open", 0.7)
                self.listen_timers[echo.id] = LISTEN_STEP
            timer = self.listen_timers.get(echo.id, 0.0) - dt
            if timer <= 0.0:
                if echo.moving:
                    self.hear("step", 0.85)
                    timer = LISTEN_STEP
                else:
                    self.hear("creak", 0.6)
                    timer = self.rng.uniform(*LISTEN_IDLE)
            self.listen_timers[echo.id] = timer

    def hear(self, name, volume):
        self.sounds.append((name, volume))
        self.audio_level = max(self.audio_level, volume)

    def sync(self, view):
        eye = view.position
        target = view.camera.position if view.camera is not None else eye
        for echo in self.echoes:
            board = self.billboards.get(echo.id)
            if board is None:
                continue
            visible = True
            if view.camera is not None:
                visible = echo.visible_on_camera(self.ctx)
            else:
                visible = echo.visible_to_player(self.ctx)
            board.visible = visible
            if not visible:
                continue
            board.position = echo.position
            board.mode = MODE_GLOW if view.camera is not None else MODE_LIT
            board.tint = CAMERA_TINT if view.camera is not None else NORMAL_TINT
            board.face(target)

    def echo_at(self, node):
        return [e for e in self.echoes if e.node == node and e.state != "walking"]

    def locations(self):
        return {e.id: e.node for e in self.echoes}
