import math
import random

import numpy as np

from chubaka.floorplan import plan as default_plan
from chubaka.settings_ui import translate
from chubaka.widgets import Button

PANEL = (760, 290, 490, 340)
HEADER_H = 44
MAP_BOX = (768, 338, 474, 284)
MAP_PAD = 10
MARKER_R = 10.0
ACTIVE_R = 13.0
HIT_R = 16.0
WHITE = (255, 255, 255, 255)
GREY = (168, 168, 168, 255)
DARK = (10, 10, 10, 255)
PANEL_FILL = (8, 10, 10, 220)
PANEL_LINE = (255, 255, 255, 170)
ROOM_FILL = (14, 14, 14, 255)
CAM_FILL = (72, 72, 72, 255)
CAM_ACTIVE = (150, 186, 0, 255)
SHORT = {"toilet": "WC", "archive": "АРХ", "guard": ""}
CONE_RANGE = 34.0
CONE_RAYS = 96
CONE_COLOR = (178, 226, 36)
CONE_BRIGHT = (236, 255, 132)
AUDIO_COLOR = (255, 176, 64)
POINTER_COLOR = (206, 206, 206)


class CameraMonitor:
    def __init__(self, language="uk", floor=None, on_close=None, on_switch=None):
        self.plan = floor or default_plan()
        self.language = language
        self.on_close = on_close
        self.on_switch = on_switch
        self.index = 0
        self.time = 0.0
        px, py, pw, ph = PANEL
        self.close_button = Button("", 326, 628, 420, 36, self.close, 22)
        self.close_button.arrow = False
        self.prev_button = Button("◀", px + 8, py + 6, 48, 32, lambda: self.cycle(-1), 20)
        self.next_button = Button("▶", px + pw - 56, py + 6, 48, 32, lambda: self.cycle(1), 20)
        for b in (self.prev_button, self.next_button):
            b.arrow = False
        self.touch_buttons = {}
        self.cone_data = {}
        self.cones = {}
        self.pointer_data = None
        self.pointer_tex = None
        self.fit_map()

    @property
    def buttons(self):
        return [self.close_button, self.prev_button, self.next_button]

    def fit_map(self):
        self.e_min, self.e_max, self.n_min, self.n_max = self.plan.bounds()
        bx, by, bw, bh = MAP_BOX
        iw, ih = bw - MAP_PAD * 2, bh - MAP_PAD * 2
        self.k = min(iw / (self.e_max - self.e_min), ih / (self.n_max - self.n_min))
        self.ox = bx + MAP_PAD + (iw - (self.e_max - self.e_min) * self.k) / 2
        self.oy = by + MAP_PAD + (ih - (self.n_max - self.n_min) * self.k) / 2

    def map_point(self, e, n):
        return (self.ox + (e - self.e_min) * self.k, self.oy + (self.n_max - n) * self.k)

    @property
    def camera(self):
        return self.plan.cameras[self.index]

    def open(self):
        self.time = 0.0
        self.close_button.label = "▼  " + translate(self.language, "close_cameras")
        for b in self.buttons:
            b.hover = False
            b.down = False
        self.touch_buttons.clear()
        self.cone_array(self.index)

    def select(self, index):
        if not 0 <= index < len(self.plan.cameras):
            return
        self.cone_array(index)
        if index != self.index and self.on_switch is not None:
            self.on_switch(index)
        self.index = index

    def cycle(self, step):
        self.select((self.index + step) % len(self.plan.cameras))

    def close(self):
        if self.on_close is not None:
            self.on_close()

    def update(self, dt):
        self.time += dt
        for b in self.buttons:
            b.update(dt)

    def grid(self):
        bx, by, bw, bh = MAP_BOX
        px, py = np.meshgrid(np.arange(bw, dtype=np.float32) + (bx + 0.5), np.arange(bh, dtype=np.float32) + (by + 0.5))
        return px, py, self.e_min + (px - self.ox) / self.k, self.n_max - (py - self.oy) / self.k

    def cone_pixels(self, cam):
        bx, by, bw, bh = MAP_BOX
        px, py, e, n = self.grid()
        cx, _, cz = cam.position
        out = np.zeros((bh, bw, 4), dtype=np.uint8)
        if cam.audio_only:
            return self.audio_pixels(cam, out, e, n, cx, cz)
        fx, fz = cam.forward
        half = cam.half_fov
        angles = np.linspace(-half, half, CONE_RAYS)
        reach = np.array([
            self.plan.ray_distance(cx, cz, fx * math.cos(a) + fz * math.sin(a), fz * math.cos(a) - fx * math.sin(a), CONE_RANGE)
            for a in angles
        ], dtype=np.float32)
        dx, dz = e - cx, n - cz
        dist = np.hypot(dx, dz)
        u = dx * fx + dz * fz
        v = dx * fz - dz * fx
        rel = np.arctan2(v, u)
        index = np.clip(np.rint((rel + half) / (2.0 * half) * (CONE_RAYS - 1)).astype(np.int32), 0, CONE_RAYS - 1)
        limit = reach[index]
        inside = (np.abs(rel) <= half) & (dist <= limit) & (dist > 0.4)
        alpha = 26.0 + 84.0 * (1.0 - np.clip(dist / CONE_RANGE, 0.0, 1.0))
        rim = inside & (((half - np.abs(rel)) * dist * self.k < 1.5) | ((limit - dist) * self.k < 1.3))
        axis_len = float(reach[CONE_RAYS // 2])
        axis = (np.abs(v) * self.k < 1.1) & (u > 0.9) & (u < axis_len - 1.6)
        head = (u >= axis_len - 2.2) & (u <= axis_len - 0.1) & (np.abs(v) <= (axis_len - u) * 0.6) if axis_len > 4.0 else np.zeros_like(inside)
        bright = rim | axis | head
        mask = inside | axis | head
        out[..., 0] = np.where(bright, CONE_BRIGHT[0], CONE_COLOR[0])
        out[..., 1] = np.where(bright, CONE_BRIGHT[1], CONE_COLOR[1])
        out[..., 2] = np.where(bright, CONE_BRIGHT[2], CONE_COLOR[2])
        out[..., 3] = np.where(mask, np.where(bright, 235.0, np.clip(alpha, 0.0, 255.0)), 0.0).astype(np.uint8)
        mx, my = self.map_point(cx, cz)
        self.stamp_pointer(out, px, py, mx, my, fx, fz, ACTIVE_R, CAM_ACTIVE[:3], 1.25)
        return out

    def audio_pixels(self, cam, out, e, n, cx, cz):
        zone = self.plan.regions.get(cam.zone)
        dist = np.hypot(e - cx, n - cz)
        mask = np.zeros(dist.shape, dtype=bool)
        alpha = np.zeros(dist.shape, dtype=np.float32)
        if zone is not None:
            e0, e1, n0, n1 = zone.rect
            area = (e >= e0) & (e <= e1) & (n >= n0) & (n <= n1)
            mask |= area
            alpha = np.where(area, 58.0, alpha)
        for radius, strength in ((1.5, 230.0), (3.0, 170.0), (4.5, 110.0)):
            ring = np.abs(dist - radius) * self.k < 1.0
            mask |= ring
            alpha = np.where(ring, strength, alpha)
        out[..., 0] = AUDIO_COLOR[0]
        out[..., 1] = AUDIO_COLOR[1]
        out[..., 2] = AUDIO_COLOR[2]
        out[..., 3] = np.where(mask, alpha, 0.0).astype(np.uint8)
        return out

    def stamp_pointer(self, out, px, py, mx, my, fx, fz, radius, color, scale=1.0):
        sx, sy = fx, -fz
        along = (px - mx) * sx + (py - my) * sy
        across = -(px - mx) * sy + (py - my) * sx
        tip = radius + 11.0 * scale
        base = radius + 2.0
        shape = (along >= base) & (along <= tip) & (np.abs(across) <= (tip - along) * (4.8 * scale / (tip - base)))
        for i in range(3):
            out[..., i] = np.where(shape, color[i], out[..., i])
        out[..., 3] = np.where(shape, 255, out[..., 3])

    def cone_array(self, index):
        pixels = self.cone_data.get(index)
        if pixels is None:
            pixels = self.cone_pixels(self.plan.cameras[index])
            self.cone_data[index] = pixels
        return pixels

    def cone_texture(self, sc, index):
        tex = self.cones.get(index)
        if tex is None:
            pixels = self.cone_array(index)
            tex = sc.raw.texture(pixels.shape[1], pixels.shape[0], pixels, "linear", False)
            self.cones[index] = tex
        return tex

    def pointer_array(self):
        if self.pointer_data is None:
            bx, by, bw, bh = MAP_BOX
            px, py, e, n = self.grid()
            out = np.zeros((bh, bw, 4), dtype=np.uint8)
            for cam in self.plan.cameras:
                if cam.audio_only:
                    continue
                mx, my = self.marker_center(cam)
                fx, fz = cam.forward
                self.stamp_pointer(out, px, py, mx, my, fx, fz, MARKER_R, POINTER_COLOR)
            self.pointer_data = out
        return self.pointer_data

    def pointer_texture(self, sc):
        if self.pointer_tex is None:
            pixels = self.pointer_array()
            self.pointer_tex = sc.raw.texture(pixels.shape[1], pixels.shape[0], pixels, "linear", False)
        return self.pointer_tex

    def marker_center(self, cam):
        return self.map_point(cam.position[0], cam.position[2])

    def marker_at(self, x, y):
        best, best_d = None, HIT_R
        for i, cam in enumerate(self.plan.cameras):
            mx, my = self.marker_center(cam)
            d = math.hypot(x - mx, y - my)
            if d <= best_d:
                best, best_d = i, d
        return best

    def motion(self, x, y):
        for b in self.buttons:
            b.motion(x, y)

    def press(self, x, y):
        for b in self.buttons:
            if b.press(x, y):
                return b
        index = self.marker_at(x, y)
        if index is not None:
            self.select(index)
            return True
        return None

    def release(self, x, y):
        for b in self.buttons:
            b.release(x, y)

    def touch(self, touch_id, phase, x, y):
        if phase == "down":
            self.motion(x, y)
            hit = self.press(x, y)
            if isinstance(hit, Button):
                self.touch_buttons[touch_id] = hit
        elif phase in ("up", "cancel"):
            b = self.touch_buttons.pop(touch_id, None)
            if b is not None:
                b.release(x, y)

    def region_rect(self, region, grow=0.0):
        return self.rect_box(region.rect, grow)

    def rect_box(self, rect, grow=0.0):
        e0, e1, n0, n1 = rect
        ax, ay = self.map_point(e0, n1)
        bx, by = self.map_point(e1, n0)
        return (ax - grow, ay - grow, bx - ax + grow * 2, by - ay + grow * 2)

    def draw_panel(self, sc, cam):
        px, py, pw, ph = PANEL
        sc.rect(px, py, pw, ph, PANEL_FILL)
        sc.rect(px, py, pw, 2, PANEL_LINE)
        sc.rect(px, py + ph - 2, pw, 2, PANEL_LINE)
        sc.rect(px, py, 2, ph, PANEL_LINE)
        sc.rect(px + pw - 2, py, 2, ph, PANEL_LINE)
        sc.rect(px, py + HEADER_H, pw, 1, PANEL_LINE)
        name = f"{translate(self.language, 'cam')} {cam.label}"
        counter = f"{self.index + 1} / {len(self.plan.cameras)}"
        cx = px + pw / 2
        sc.text(name, cx, py + HEADER_H / 2, WHITE, 24, "center", "center", True)
        sc.text(counter, px + pw - 66, py + HEADER_H / 2, GREY, 14, "right", "center")
        sc.text(f"{translate(self.language, 'north_short')} ↑", px + 66, py + HEADER_H / 2, GREY, 14, "left", "center", True)
        self.prev_button.draw(sc)
        self.next_button.draw(sc)

    def draw_map(self, sc):
        bx, by, bw, bh = MAP_BOX
        regions = list(self.plan.regions.values())
        for region in regions:
            sc.rect(*self.region_rect(region, 1.6), WHITE)
        for region in regions:
            sc.rect(*self.region_rect(region), ROOM_FILL)
        for rect in self.plan.columns:
            sc.rect(*self.rect_box(rect), WHITE)
        sc.image(self.pointer_texture(sc), bx, by, bw, bh)
        sc.image(self.cone_texture(sc, self.index), bx, by, bw, bh)
        for region in regions:
            x, y, w, h = self.region_rect(region)
            if region.kind == "guard":
                sc.rect(x + w / 2 - 6, y + h / 2 - 6, 12, 12, WHITE)
                continue
            if region.kind == "corridor":
                continue
            label = SHORT.get(region.kind) or region.name.replace("room_", "")
            sc.text(label, x + w / 2, y + h / 2, GREY, 10, "center", "center")
        gx, gy, gw, gh = self.region_rect(self.plan.regions["room_08"])
        sc.text(translate(self.language, "you"), gx + gw / 2, gy - 8, WHITE, 11, "center", "center", True)
        for i, cam in enumerate(self.plan.cameras):
            mx, my = self.marker_center(cam)
            active = i == self.index
            r = ACTIVE_R if active else MARKER_R
            radius = 4.0 if cam.audio_only else r + 2
            sc.rect(mx - r - 1.5, my - r - 1.5, (r + 1.5) * 2, (r + 1.5) * 2, WHITE, radius + 1.5)
            sc.rect(mx - r, my - r, r * 2, r * 2, CAM_ACTIVE if active else CAM_FILL, radius)
            sc.text(cam.label, mx, my, DARK if active else WHITE, 13 if active else 11, "center", "center", True)

    def draw_static(self, sc, w, h):
        rng = random.Random(int(self.time * 24.0))
        sc.rect(0, 0, w, h, (78, 80, 80, 255))
        for _ in range(420):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            g = rng.randint(20, 235)
            sc.rect(x, y, rng.uniform(4, 40), rng.uniform(2, 7), (g, g, g, rng.randint(90, 230)))
        for _ in range(6):
            g = rng.randint(150, 255)
            sc.rect(0, rng.uniform(0, h), w, rng.uniform(2, 10), (g, g, g, rng.randint(40, 110)))

    def draw(self, sc, clock, night, power=100):
        st = sc.stage
        w, h = st.width, st.height
        cam = self.camera
        if not cam.audio_only:
            sc.rect(0, 0, w, h, (12, 12, 12, 38))
        if cam.audio_only:
            self.draw_static(sc, w, h)
        sc.rect(22, 20, w - 44, 2, WHITE)
        sc.rect(22, h - 58, w - 44, 2, WHITE)
        sc.rect(22, 20, 2, h - 76, WHITE)
        sc.rect(w - 24, 20, 2, h - 76, WHITE)
        if int(self.time * 1.6) % 2 == 0:
            sc.rect(56, 44, 38, 38, (232, 24, 24, 255), 19)
        sc.text(f"{translate(self.language, 'cam')} {cam.label}", 110, 40, WHITE, 40, "left", "top", True, True)
        sc.text(cam.title, 56, 98, WHITE, 22, "left", "top", False, True)
        sc.text(clock, w - 52, 38, WHITE, 48, "right", "top", True, True)
        sc.text(f"{translate(self.language, 'night')} {night}", w - 52, 92, WHITE, 26, "right", "top", False, True)
        sc.text(f"{translate(self.language, 'power')}: {power}%", 52, h - 112, WHITE, 28, "left", "top", True, True)
        sc.rect(0, 0, w, 10, (6, 6, 8, 255))
        sc.rect(0, 0, 10, h, (6, 6, 8, 255))
        sc.rect(w - 10, 0, 10, h, (6, 6, 8, 255))
        sc.rect(0, h - 34, w, 34, (6, 6, 8, 255))
        sc.text("ThinkPad", w / 2, h - 28, (120, 120, 126, 255), 14, "center", "top", True)
        sc.rect(w / 2 + 40, h - 25, 5, 5, (210, 30, 30, 255), 2)
        self.draw_panel(sc, cam)
        self.draw_map(sc)
        self.close_button.draw(sc)
