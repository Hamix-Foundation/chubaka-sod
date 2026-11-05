import gc
import math
import random
import time

from chubaka import asset, classroom
from chubaka.camera import LookController
from chubaka.layout import DOOR_X0, DOOR_X1, DOOR_Z, HZ, TEACHER_CHAIR
from chubaka.widgets import Button
from chubaka.settings_ui import translate
from lysyk.engine import keys as K
from lysyk.engine.door import Door
from lysyk.engine.flashlight import Flashlight
from lysyk.engine.interact import Hotspot, Interaction, forward_vector
from lysyk.engine.lighting import Lighting, PointLight
from lysyk.engine.objects import MODE_GLOW, MODE_SKY, Camera, GameObject
from lysyk.engine.particles import ParticlePool, spark_mesh
from lysyk.engine.renderer import Renderer
from lysyk.engine.rig import Pose, PoseRig
from lysyk.engine.scene import Scene as World
from lysyk.engine.scenes import Scene
from lysyk.engine.tween import damp

SEAT = Pose((TEACHER_CHAIR[0], 1.2, TEACHER_CHAIR[1]), 140.0)
STANDING = 1.62
DOOR_CENTER = (DOOR_X0 + DOOR_X1) / 2.0
LANE = 1.46
DOOR_STAND = Pose((DOOR_CENTER - 0.1, STANDING, -HZ + 1.5), 180.0)
WALK_OUT = [SEAT.position[:1] + (STANDING,) + SEAT.position[2:], (-2.6, STANDING, 2.8), (LANE, STANDING, 2.8), (LANE, STANDING, -0.8), DOOR_STAND.position]
WALK_BACK = [(LANE, STANDING, -0.8), (LANE, STANDING, 2.8), (-2.6, STANDING, 2.8), SEAT.position[:1] + (STANDING,) + SEAT.position[2:], SEAT.position]
WALK_OUT_TIME = 5.5
WALK_BACK_TIME = 5.0
STEP_INTERVAL = 0.5
HINT_HOLD_TIME = 6.0
SEAT_LOOK = 100.0
DOOR_LOOK = 24.0
SUN_ELEVATION = 18.0
SUN_AZIMUTH = 262.0
TUBE_COLOR = (255, 244, 214)
HUD_WHITE = (255, 255, 255, 255)
TAP_TIME = 0.35
TAP_MOVE = 40.0


def configure_lighting(lighting):
    lighting.shadows = True
    lighting.set_manual(
        (58.0, 64.0, 72.0), (102.0, 108.0, 114.0), (86.0, 92.0, 98.0), (0.75, 0.8, 0.9), 0.55,
        (0.075, 0.085, 0.1), (0.04, 0.036, 0.032), SUN_ELEVATION, SUN_AZIMUTH, 0.0, 0.3,
    )
    lighting.fog_density = 0.02
    lighting.fog_scatter = 1.0


class ClassroomScene(Scene):
    def __init__(self, game):
        super().__init__(game)
        self.built = False
        self.night = 1
        self.time = 0.0
        self.state = "seat"
        self.look = LookController(SEAT.yaw, center=SEAT.yaw, limit=SEAT_LOOK)
        self.rig = PoseRig(SEAT)
        self.camera = Camera(62.0)
        self.interaction = Interaction()
        self.light_button = Button("", 1060, 640, 200, 56, self.toggle_light, 28)
        self.light_button.arrow = False
        self.back_button = Button("", 20, 20, 180, 56, self.go_seat, 28)
        self.back_button.arrow = False
        self.buttons = [self.light_button, self.back_button]
        self.touch_buttons = {}
        self.touch_hold = set()
        self.touch_start = {}
        self.mouse_hold = False
        self.key_hold = False
        self.power = 100
        self.clock = "24 PM"
        self.flicker = [1.0, 1.0]
        self.rand = random.Random(5)
        self.dust_clock = 0.0
        self.sfx = None
        self.eye = Pose(SEAT.position, SEAT.yaw)
        self.steps = None
        self.warmed = False
        self.step_clock = 0.0
        self.tutorial = False
        self.hint_stage = 0
        self.hint_timer = 0.0
        self.last_creak = -1

    def make_build(self):
        game = self.game
        profile = game.profile
        data, steps = classroom.build_steps(profile["detail"])
        self.data = data
        for step in steps:
            yield step
        yield lambda: self.assemble(data)

    def prepare(self, budget=0.008):
        if self.built:
            return True
        if self.steps is None:
            self.steps = self.make_build()
        start = time.perf_counter()
        while not self.built:
            step = next(self.steps, None)
            if step is None:
                break
            step()
            if time.perf_counter() - start >= budget:
                break
        return self.built

    def build(self):
        while not self.prepare(1e9):
            pass

    def warm(self):
        if self.warmed or not self.built:
            return
        self.warmed = True
        self.apply_camera(SEAT.position, SEAT.yaw, 0.0)
        self.game.clear(self.lighting.clear_color())
        self.renderer.render(self.camera, self.world)

    def assemble(self, data):
        game = self.game
        profile = game.profile
        self.lighting = Lighting()
        configure_lighting(self.lighting)
        self.renderer = Renderer(game, self.lighting)
        for key, value in (("shadow_quality", profile["shadow_quality"]), ("shadow_range", profile["shadow_range"])):
            if hasattr(self.renderer, key):
                setattr(self.renderer, key, value)
        self.world = World()
        self.world.add(GameObject(data.sky, mode=MODE_SKY))
        self.world.add(GameObject(data.outside, mode=MODE_GLOW))
        self.world.add(GameObject(data.floor, cast=False, gloss=0.1))
        self.world.add(GameObject(data.shell, cast=True))
        self.world.add(GameObject(data.trim, cast=False))
        self.world.add(GameObject(data.furniture, cast=True, gloss=0.1))
        self.world.add(GameObject(data.decor, cast=False))
        self.world.add(GameObject(data.corridor, cast=True))
        self.torch = GameObject(data.torch, position=(-4.15, 0.795, 2.55), rotation=(0.0, 1.3, 0.0), gloss=0.3)
        self.world.add(self.torch)
        self.tube_objects = []
        self.tube_lights = []
        for x, y, z in data.tubes:
            obj = GameObject(data.tube_mesh, TUBE_COLOR, position=(x, y, z), mode=MODE_GLOW)
            self.world.add(obj)
            self.tube_objects.append(obj)
            light = PointLight((x, y - 0.4, z), (0.78, 0.92, 1.0), 0.6, 5.0)
            self.lighting.add_light(light)
            self.tube_lights.append(light)
        self.lighting.add_light(PointLight((-0.5, 2.4, 0.4), (0.45, 0.55, 0.95), 0.14, 6.0))
        self.lighting.add_light(PointLight((DOOR_CENTER - 1.0, 2.7, DOOR_Z - 2.4), (0.6, 0.75, 0.65), 0.2, 4.5))
        self.flashlight = Flashlight(self.lighting, intensity=3.4, radius=14.0)
        leaf = GameObject(data.door_leaf, cast=True, gloss=0.05)
        self.world.add(leaf)
        self.door = Door(leaf, data.door_hinge, 0.0, -1.0, 0.12, 5.0, self.door_event)
        self.door_spot = self.interaction.add(Hotspot("Door", (DOOR_CENTER, 1.2, DOOR_Z), 1.1, self.go_door, True, 14.0))
        self.dust = None
        if profile["particles"] > 0:
            self.dust = ParticlePool(self.world, spark_mesh(), profile["particles"], True, 0.0, 0.2, 0.0, 0.0, 1.0)
        self.sfx = {}
        for name, count in (("creak", 3), ("door_close", 4), ("door_open", 2), ("step", 4)):
            self.sfx[name] = [game.audio.load(asset("audio", "sfx", f"{name}_{i}.wav")) for i in range(1, count + 1)]
        for name in ("latch", "click"):
            self.sfx[name] = [game.audio.load(asset("audio", "sfx", f"{name}.wav"))]
        self.built = True
        gc.collect()
        gc.freeze()

    def enter(self, night=1, **kwargs):
        self.light_button.label = translate(self.game.settings.language, "light")
        self.back_button.label = translate(self.game.settings.language, "back")
        if not self.built:
            self.build()
        self.night = night
        self.time = 0.0
        self.state = "seat"
        self.tutorial = night == 1 and not self.game.progress.flag("door_hint")
        self.hint_stage = 0
        self.hint_timer = 0.0
        self.step_clock = 0.0
        self.door_spot.enabled = True
        self.rig.place(SEAT)
        self.look = LookController(SEAT.yaw, center=SEAT.yaw, limit=SEAT_LOOK)
        self.look.mouse_x = self.game.mouse_x / max(1.0, self.game.width) * self.game.stage.width
        self.look.set_mobile(self.game.is_mobile)
        self.mouse_hold = self.key_hold = False
        self.touch_hold.clear()
        self.touch_buttons.clear()
        self.touch_start.clear()
        self.door.angle = 0.0
        self.door.held = False
        self.door.was_closed = True
        self.flashlight.battery = 1.0
        self.flashlight.set(False)
        self.game.touch_emulates_mouse = False
        self.game.set_cursor_grab("confined")
        for b in self.buttons:
            b.hover = False
            b.down = False

    def exit(self):
        self.game.touch_emulates_mouse = True
        self.game.set_cursor_grab("none")
        self.flashlight.set(False)

    def play(self, name, volume=1.0):
        if self.sfx is None:
            return
        variants = self.sfx[name]
        index = self.rand.randrange(len(variants))
        if name == "creak" and len(variants) > 1 and index == self.last_creak:
            index = (index + 1) % len(variants)
        if name == "creak":
            self.last_creak = index
        self.game.audio.play(variants[index], volume, False, "sfx")

    def door_event(self, name, door):
        near = 1.0 if self.state in ("door", "to_door") else 0.45
        if name == "creak":
            self.play("creak", 0.55 * near)
        elif name == "thud":
            self.play("door_close", 0.9 * near)
        elif name == "unlatch":
            self.play("door_open", 0.4 * near)
        else:
            self.play("latch", 0.6 * near)

    def toggle_light(self):
        if self.flashlight.toggle() or not self.flashlight.on:
            self.play("click", 0.6)

    def go_door(self):
        if self.state != "seat":
            return
        self.state = "to_door"
        self.door_spot.enabled = False
        self.step_clock = 0.0
        if self.hint_stage < 2:
            self.hint_stage = 2
        self.rig.place(Pose(self.rig.pose.position, self.look.yaw))
        self.rig.travel(WALK_OUT, WALK_OUT_TIME, DOOR_STAND.yaw, 0.0, 0.035, 5.0, self.arrive_door)

    def arrive_door(self):
        self.state = "door"
        self.look = LookController(self.rig.pose.yaw, center=DOOR_STAND.yaw, limit=DOOR_LOOK)
        self.look.mouse_x = self.game.mouse_x / max(1.0, self.game.width) * self.game.stage.width
        self.look.set_mobile(False)
        if self.tutorial and self.hint_stage == 2:
            self.hint_stage = 3
            self.hint_timer = HINT_HOLD_TIME

    def go_seat(self):
        if self.state != "door":
            return
        self.state = "to_seat"
        self.mouse_hold = self.key_hold = False
        self.touch_hold.clear()
        self.rig.place(Pose(self.rig.pose.position, self.look.yaw))
        self.step_clock = 0.0
        self.rig.travel(WALK_BACK, WALK_BACK_TIME, SEAT.yaw, 0.0, 0.035, 5.0, self.arrive_seat)

    def arrive_seat(self):
        self.state = "seat"
        self.door_spot.enabled = True
        self.look = LookController(self.rig.pose.yaw, center=SEAT.yaw, limit=SEAT_LOOK)
        self.look.mouse_x = self.game.mouse_x / max(1.0, self.game.width) * self.game.stage.width
        self.look.set_mobile(self.game.is_mobile)

    @property
    def holding(self):
        return self.state == "door" and (self.mouse_hold or self.key_hold or bool(self.touch_hold))

    def emit_dust(self, dt):
        if self.dust is None:
            return
        self.dust_clock += dt
        while self.dust_clock > 0.25:
            self.dust_clock -= 0.25
            r = self.rand
            pos = [(r.uniform(-4.3, 4.3), r.uniform(0.6, 3.0), r.uniform(-2.9, 2.9))]
            vel = [(r.uniform(-0.03, 0.05), r.uniform(-0.02, 0.03), r.uniform(-0.04, 0.04))]
            self.dust.emit(pos, vel, [r.uniform(6.0, 12.0)], [0.012], [(255, 190, 120)], [(255, 150, 90)])

    def eye_pose(self):
        if self.rig.busy:
            return self.rig.pose
        base = SEAT if self.state == "seat" else DOOR_STAND
        return Pose(base.position, self.look.yaw)

    def update_tutorial(self, dt):
        if not self.tutorial:
            return
        if self.hint_stage == 0 and self.state == "seat" and self.interaction.hover is self.door_spot:
            self.hint_stage = 1
        elif self.hint_stage == 1 and self.interaction.hover is not self.door_spot:
            self.hint_stage = 0
        elif self.hint_stage == 3:
            self.hint_timer -= dt
            if self.holding or self.hint_timer <= 0.0:
                self.hint_stage = 4
                self.tutorial = False
                self.game.progress.set_flag("door_hint")

    def update_steps(self, dt):
        if not self.rig.busy or self.state not in ("to_door", "to_seat"):
            return
        self.step_clock += dt
        if self.step_clock >= STEP_INTERVAL:
            self.step_clock -= STEP_INTERVAL
            self.play("step", 0.35)

    def update(self, dt):
        self.time += dt
        if self.rig.busy:
            self.rig.update(dt)
        else:
            self.look.set_mobile(self.game.is_mobile and self.state == "seat")
            self.look.update(dt)
        for b in self.buttons:
            b.update(dt)
        pose = self.eye_pose()
        self.eye = pose
        eye = (pose.position[0], pose.position[1] + math.sin(self.time * 0.9) * 0.004, pose.position[2])
        yaw = math.radians(pose.yaw)
        self.interaction.update(eye, yaw)
        self.update_tutorial(dt)
        self.update_steps(dt)
        self.door.held = self.holding
        self.door.update(dt)
        self.flashlight.update(dt, eye, forward_vector(yaw))
        self.power = int(round(self.flashlight.battery * 100))
        self.torch.visible = self.state == "seat"
        t = self.time
        n = math.sin(t * 23.0) * 0.5 + math.sin(t * 7.3 + 1.7) * 0.5
        gate = math.sin(t * 0.9) * math.sin(t * 2.3 + 0.4)
        targets = (0.25 if gate > 0.9 else 1.0, 0.1 if math.sin(t * 1.7) * math.sin(t * 5.1 + 2.0) > 0.45 else 0.85)
        for i in range(len(self.tube_lights)):
            self.flicker[i] = damp(self.flicker[i], targets[i % 2] * (0.94 + 0.06 * n), 30.0, dt)
            self.tube_lights[i].intensity = 0.6 * self.flicker[i]
            k = 0.35 + 0.65 * self.flicker[i]
            self.tube_objects[i].color = (TUBE_COLOR[0] * k, TUBE_COLOR[1] * k, TUBE_COLOR[2] * k)
        self.emit_dust(dt)
        if self.dust is not None:
            self.dust.update(dt)
        self.game.fx.update(dt)

    def active_buttons(self):
        return [self.light_button] + ([self.back_button] if self.state == "door" else [])

    def key_press(self, key, mods):
        if key == K.F:
            self.toggle_light()
        elif key in (K.SPACE, K.E):
            self.key_hold = True
        elif key in (K.S, K.DOWN, K.BACKSPACE):
            self.go_seat()

    def key_release(self, key, mods):
        if key in (K.SPACE, K.E):
            self.key_hold = False

    def mouse_motion(self, x, y):
        self.look.mouse_motion(x)
        for b in self.buttons:
            b.motion(x, y)

    def mouse_press(self, x, y, button):
        if button == 1:
            self.toggle_light()
            return
        if button != 0:
            return
        for b in self.active_buttons():
            if b.press(x, y):
                return
        if self.state == "seat":
            self.interaction.click()
        elif self.state == "door":
            self.mouse_hold = True

    def mouse_release(self, x, y, button):
        if button != 0:
            return
        self.mouse_hold = False
        for b in self.buttons:
            b.release(x, y)

    def touch(self, touch_id, phase, x, y):
        if phase == "down":
            for b in self.active_buttons():
                if b.press(x, y):
                    self.touch_buttons[touch_id] = b
                    return
            if self.state == "door":
                self.touch_hold.add(touch_id)
                return
            self.touch_start[touch_id] = (self.time, x, y)
        elif phase == "move":
            if touch_id in self.touch_buttons or touch_id in self.touch_hold:
                return
        else:
            button = self.touch_buttons.pop(touch_id, None)
            if button is not None:
                button.release(x, y)
                return
            if touch_id in self.touch_hold:
                self.touch_hold.discard(touch_id)
                return
            start = self.touch_start.pop(touch_id, None)
            if phase == "up" and start is not None and self.state == "seat":
                if self.time - start[0] < TAP_TIME and math.hypot(x - start[1], y - start[2]) < TAP_MOVE:
                    self.interaction.click()
        if self.state == "seat":
            self.look.touch(touch_id, phase, x, y)

    def suspend(self):
        self.mouse_hold = self.key_hold = False
        self.touch_hold.clear()
        self.touch_buttons.clear()

    def apply_camera(self, position, yaw, roll):
        t = self.time
        cam = self.camera
        cam.position = (position[0], position[1] + math.sin(t * 0.9) * 0.004, position[2])
        cam.rotation = (math.sin(t * 0.6) * 0.004, math.radians(yaw), roll + math.sin(t * 0.45) * 0.002)

    def hint_text(self):
        touch = self.game.is_mobile
        if self.hint_stage == 1:
            return translate(self.game.settings.language, "hint_tap" if touch else "hint_click")
        if self.hint_stage == 3:
            return translate(self.game.settings.language, "hint_hold_touch" if touch else "hint_hold")
        return None

    def draw(self, sc):
        pose = self.eye
        self.apply_camera(pose.position, pose.yaw, self.rig.roll)
        self.game.clear(self.lighting.clear_color())
        self.renderer.render(self.camera, self.world)
        sc.text(self.clock, 1275, 7, HUD_WHITE, 32, "right", "top", False, True)
        sc.text(f"{translate(self.game.settings.language, 'night')} {self.night}", 1275, 45, HUD_WHITE, 20, "right", "top", False, True)
        sc.text(f"{translate(self.game.settings.language, 'power')}: {self.power}%", 17, 621, HUD_WHITE, 30, "left", "top", False, True)
        sc.text(f"{translate(self.game.settings.language, 'usage')}:", 16, 667, HUD_WHITE, 30, "left", "top", False, True)
        text = self.hint_text() if self.tutorial else None
        if text is not None:
            if self.hint_stage == 1:
                sc.rect(634, 354, 12, 12, (255, 255, 255, 210), 6)
                sc.text(text, 640, 380, HUD_WHITE, 26, "center", "top", False, True)
            else:
                sc.text(text, 640, 585, HUD_WHITE, 26, "center", "top", False, True)
        if self.state == "door":
            self.back_button.draw(sc)
        self.light_button.label = "Light: on" if self.flashlight.on else "Light: off"
        self.light_button.draw(sc)
        self.game.fx.draw(sc, grain=0.045, scanlines=0.04, vignette=0.0 if self.game.quality == "low" else 0.7, glitch_bars=False)
