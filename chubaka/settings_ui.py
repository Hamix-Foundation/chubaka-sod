import platform
import sys
import json
from pathlib import Path

from lysyk.engine import keys as K


LOCALE_DIR = Path(__file__).with_name("locales")
LOCALES = {language: json.loads((LOCALE_DIR / f"{language}.json").read_text(encoding="utf-8")) for language in ("uk", "en")}


def translate(language, key):
    return LOCALES.get(language, LOCALES["uk"]).get(key, key)


class SettingsPanel:
    def __init__(self, game, close):
        self.game = game
        self.close = close
        self.section = "game"
        self.about = False
        self.pressed = None
        self.anim = 0.0
        self.closing = False
        self.closed = False
        self.hover_index = -1
        self.row_glow = []
        self.ray_tracing_supported = False
        self.ray_tracing = False
        from chubaka.state import load_game_config
        self.game_config = load_game_config()
        self.version = self.game_config.get("version", "unknown")
        try:
            from lysyk.engine import _native
            self.rust_version = _native.rustc_version()
        except Exception:
            self.rust_version = "unknown"
        try:
            gpu = game.gpu_info()
            self.gpu_name = gpu.get("name", "unknown")
            self.gpu_api = gpu.get("api", "unknown")
            self.ray_tracing_supported = gpu.get("ray_tracing_supported", False)
            self.ray_tracing = bool(game.settings.ray_tracing and self.ray_tracing_supported)
        except Exception:
            self.gpu_name = "unknown"
            self.gpu_api = "unknown"

    def t(self, key):
        return translate(self.game.settings.language, key)

    def show(self):
        self.anim = 0.0
        self.closing = False
        self.closed = False

    def dismiss(self):
        self.closing = True

    def update(self, dt):
        step = max(0.0, dt) * 7.0
        if self.closing:
            self.anim = max(0.0, self.anim - step)
            self.closed = self.anim <= 0.0
        else:
            self.anim = min(1.0, self.anim + step)
        rows = self.rows() if not self.about else []
        if len(self.row_glow) != len(rows):
            self.row_glow = [0.0] * len(rows)
        for i in range(len(self.row_glow)):
            target = 1.0 if i == self.hover_index else 0.0
            self.row_glow[i] += (target - self.row_glow[i]) * min(1.0, step * 2.0)

    def choices(self, key):
        choices = {
            "language": ["uk", "en"], "quality": ["auto", "potato", "low", "medium", "high", "ultra"],
            "fps_limit": [0, 30, 45, 60], "vsync": [False, True], "msaa": [False, True], "graphics_api": ["auto", "vulkan", "gl"],
        }
        if sys.platform == "win32":
            choices["graphics_api"].append("dx12")
        return choices[key]

    def value(self, key):
        value = getattr(self.game.settings, key)
        if key == "language":
            return self.t("ukrainian" if value == "uk" else "english")
        if key == "quality":
            return self.t({"auto": "automatic", "potato": "potato", "low": "low", "medium": "medium", "high": "high", "ultra": "ultra"}.get(value, "automatic"))
        if key == "ray_tracing":
            return self.t("on" if value else "off")
        if key == "fps_limit":
            return self.t("automatic") if value == 0 else str(value)
        if key == "vsync":
            return self.t("on" if value else "off")
        if key == "msaa":
            return self.t("on" if value else "off")
        if key == "graphics_api":
            return self.t({"auto": "automatic", "vulkan": "vulkan", "gl": "gl", "dx12": "DirectX 12"}.get(value, "automatic"))
        if key == "show_fps":
            return self.t("fps_on" if value else "fps_off")
        return f"{int(value * 100)}%"

    def rows(self):
        if self.about:
            return [
                (self.t("version"), self.version), (self.t("python"), platform.python_version()),
                (self.t("python_compiler"), platform.python_compiler() or sys.implementation.name),
                (self.t("rust"), self.rust_version), (self.t("engine"), "Lysyk Engine 1.0"),
                (self.t("graphics_device"), self.gpu_name), (self.t("api"), self.gpu_api),
            ]
        if self.section == "game":
            return [("language", self.t("language"), "language"), ("show_fps", self.t("show_fps"), "show_fps"), (None, self.t("about_open"), "about")]
        if self.section == "graphics":
            return [("quality", self.t("quality"), "quality"), ("fps_limit", self.t("fps"), "fps_limit"), ("vsync", self.t("vsync"), "vsync"), ("msaa", self.t("msaa"), "msaa"), ("graphics_api", self.t("api"), "graphics_api"), ("ray_tracing", self.t("ray_tracing"), "ray_tracing")]
        return [(key, self.t(label), key) for key, label in (("master", "master"), ("music", "music"), ("sfx", "sfx"))]

    def row_spacing(self):
        return 72 if self.section == "graphics" else 84

    def fitted_size(self, sc, text, size, width, height, bold=False, font=None):
        tw = sc.text_width(text, size, bold, font)
        th = sc.text_height(text, size, bold, font)
        return size * min(1.0, width / max(tw, 1.0), height / max(th, 1.0))

    def draw(self, sc):
        raw = sc.raw
        st = sc.stage
        s = st.scale
        a = self.anim
        off = (1.0 - a) * 18.0
        x0 = 150 + off
        alpha = lambda color, f=a: tuple(color[:3]) + (int(color[3] * f),)
        raw.rect(0, 0, st.win_w, st.win_h, (0, 0, 0, int(190 * a)))
        raw.rect(st.ox + x0 * s, st.oy + 65 * s, 980 * s, 590 * s, (0, 9, 0, int(242 * a)), 3 * s)
        raw.outline(st.ox + x0 * s, st.oy + 65 * s, 980 * s, 590 * s, (180, 32, 32, int(220 * a)), 3 * s, 2 * s)
        sc.text(self.t("settings"), 195 + off, 96, alpha((255, 255, 255, 255)), 38, "left", "center", True, False, "zombie")
        sc.text("×", 1080 + off, 95, alpha((255, 255, 255, 255)), 38, "center", "center", True)
        sc.rect(190 + off, 127, 900, 2, alpha((150, 25, 25, 255)), 0)
        nav = [("game", self.t("game")), ("graphics", self.t("graphics")), ("sound", self.t("sound"))]
        for i, (name, label) in enumerate(nav):
            y = 155 + i * 68
            selected = not self.about and self.section == name
            sc.rect(190 + off, y, 200, 54, alpha((33, 33, 33, 225) if selected else (18, 18, 18, 180)), 3)
            if selected:
                sc.rect(190 + off, y, 3, 54, alpha((185, 27, 27, 255)), 0)
            sc.text(label, 215 + off, y + 27, alpha((255, 255, 255, 255)), 22, "left", "center", True)
        sc.rect(412 + off, 145, 1.5, 485, alpha((120, 25, 25, 180)), 0)
        if self.about:
            sc.text("‹  " + self.t("back"), 440 + off, 164, alpha((230, 230, 230, 255)), 23, "left", "center", True)
            sc.text(self.t("about_title"), 440 + off, 218, alpha((255, 255, 255, 255)), 29, "left", "center", True, False, "zombie")
            sc.text(f"{self.t('version')}: {self.version}", 440 + off, 258, alpha((190, 190, 190, 255)), 19, "left", "center")
            details = self.rows()
            for i, (label, value) in enumerate(details[1:]):
                y = 292 + i * 58
                sc.rect(435 + off, y, 650, 48, (22, 22, 22, int(210 * a)), 3)
                sc.rect(435 + off, y, 3, 48, alpha((150, 25, 25, 255)), 0)
                label_size = self.fitted_size(sc, label, 17, 205, 38)
                value_size = self.fitted_size(sc, value, 17, 390, 38)
                sc.text(label, 453 + off, y + 24, alpha((170, 170, 170, 255)), label_size, "left", "center")
                sc.text(value, 1068 + off, y + 24, alpha((250, 250, 250, 255)), value_size, "right", "center")
            legal_footer = f"© {self.game_config.get('copyright_year', 2026)} {self.game_config.get('publisher', 'Hamix Foundation')} · {self.game_config.get('license', 'GNU GPL v3.0')}"
            sc.text(legal_footer, 760 + off, 640, alpha((150, 150, 150, 255)), 14, "center", "center")
            return
        spacing = self.row_spacing()
        for i, row in enumerate(self.rows()):
            key, label, action = row
            y = 155 + i * spacing
            glow = self.row_glow[i] if i < len(self.row_glow) else 0.0
            ray_unavailable = key == "ray_tracing" and not self.ray_tracing_supported
            row_color = (24, 24, 24, 160) if ray_unavailable else (26 + int(13 * glow), 26, 26, int((190 + 45 * glow) * a))
            sc.rect(435 + off, y, 650, 64, alpha(row_color), 3)
            if glow > 0.02:
                sc.rect(435 + off, y, 3, 64, (190, 25, 25, int(255 * glow * a)), 0)
            label_size = self.fitted_size(sc, label, 21, 330, 50)
            label_color = (130, 130, 130, 255) if ray_unavailable else (240, 240, 240, 255)
            sc.text(label, 458 + off, y + 32, alpha(label_color), label_size, "left", "center")
            if key == "ray_tracing":
                badge_x, badge_y = 604 + off, y + 22
                badge_color = (76, 76, 76, 220) if ray_unavailable else (118, 75, 31, 240)
                badge_text = (148, 148, 148, 255) if ray_unavailable else (255, 210, 139, 255)
                sc.rect(badge_x, badge_y, 115, 20, alpha(badge_color), 5)
                sc.text(self.t("experimental"), badge_x + 57.5, badge_y + 10, alpha(badge_text), 11, "center", "center", True)
            if key in ("master", "music", "sfx"):
                value = getattr(self.game.settings, key)
                bx, bw = 800 + off, 160
                sc.rect(bx, y + 29, bw, 6, alpha((92, 92, 92, 255)), 3)
                sc.rect(bx, y + 29, max(6, bw * value), 6, alpha((185, 35, 35, 255)), 3)
                sc.raw.circle(sc.stage.ox + (bx + bw * value) * s, sc.stage.oy + (y + 32) * s, 8 * s, alpha((235, 235, 235, 255)))
                sc.text(f"{int(value * 100)}%", 1055 + off, y + 32, alpha((255, 255, 255, 255)), 18, "right", "center")
            elif key in ("show_fps", "vsync", "msaa", "ray_tracing"):
                checked = bool(getattr(self.game.settings, key))
                cx, cy = 1040 + off, y + 32
                box_color = (28, 28, 28, 180) if ray_unavailable else (36, 36, 36, 255)
                border_color = (92, 92, 92, 255) if ray_unavailable else (170, 170, 170, 255)
                sc.raw.rect(st.ox + (cx - 12) * s, st.oy + (cy - 12) * s, 24 * s, 24 * s, alpha(box_color), 2 * s)
                sc.raw.outline(st.ox + (cx - 12) * s, st.oy + (cy - 12) * s, 24 * s, 24 * s, alpha(border_color), 2 * s, 1.5 * s)
                if checked:
                    sc.text("✓", cx, cy, alpha((200, 35, 35, 255)), 22, "center", "center", True)
            elif action != "about":
                value = self.value(key)
                sc.text("‹", 885 + off, y + 32, alpha((205, 205, 205, 255)), 30, "center", "center", True)
                value_size = self.fitted_size(sc, value, 18, 120, 48, True)
                sc.text(value, 970 + off, y + 32, alpha((255, 255, 255, 255)), value_size, "center", "center", True)
                sc.text("›", 1055 + off, y + 32, alpha((205, 205, 205, 255)), 30, "center", "center", True)

    def press(self, x, y):
        self.pressed = (x, y)
        if self.section == "sound" and x >= 780 and 155 <= y <= 375:
            i = int((y - 155) // 84)
            if 0 <= i < 3:
                self.drag_key = ("master", "music", "sfx")[i]
                self.set_slider(self.drag_key, x)

    def move(self, x, y):
        if getattr(self, "drag_key", None):
            self.set_slider(self.drag_key, x)
            return
        spacing = self.row_spacing()
        self.hover_index = int((y - 155) // spacing) if x >= 435 and 155 <= y <= 155 + len(self.rows()) * spacing else -1

    def set_slider(self, key, x):
        value = min(1.0, max(0.0, (x - 800 - (1.0 - self.anim) * 18.0) / 160))
        setattr(self.game.settings, key, round(value, 2))
        self.game.audio.master = self.game.settings.master
        self.game.audio.buses["music"] = self.game.settings.music
        self.game.audio.buses["sfx"] = self.game.settings.sfx

    def release(self, x, y):
        if self.pressed is None:
            return
        px, py = self.pressed
        self.pressed = None
        if getattr(self, "drag_key", None):
            self.set_slider(self.drag_key, x)
            self.drag_key = None
            self.game.settings.save("ChubakaSOD")
            return
        if not (150 <= px <= 1130 and 65 <= py <= 655):
            return
        if px >= 1030 and py < 125:
            self.close()
            return
        if self.about:
            if py < 190:
                self.about = False
            return
        if py >= 585 and px >= 980:
            self.close()
            return
        if 150 <= py <= 353 and 180 <= px <= 400:
            idx = min(2, max(0, int((py - 155) // 68)))
            self.section = ("game", "graphics", "sound")[idx]
            return
        if px < 420:
            return
        row_index = int((py - 155) // self.row_spacing())
        rows = self.rows()
        if row_index < 0 or row_index >= len(rows):
            return
        key, _, action = rows[row_index]
        if key == "ray_tracing":
            if not self.ray_tracing_supported:
                return
            self.game.settings.ray_tracing = not self.game.settings.ray_tracing
            self.game.ray_tracing_enabled = self.game.settings.ray_tracing
            self.game.settings.save("ChubakaSOD")
            return
        if action == "about":
            self.about = True
        elif key in ("master", "music", "sfx"):
            self.set_slider(key, px)
        elif key == "show_fps":
            self.game.settings.show_fps = not self.game.settings.show_fps
            self.game.overlay = self.game.settings.show_fps
        else:
            values = self.choices(key)
            current = getattr(self.game.settings, key)
            index = values.index(current) if current in values else 0
            direction = -1 if px < 915 else 1
            setattr(self.game.settings, key, values[(index + direction) % len(values)])
            self.apply(key)
        self.game.settings.save("ChubakaSOD")

    def apply(self, key):
        settings = self.game.settings
        if key in ("master", "music", "sfx"):
            return
        if key == "vsync":
            self.game.set_vsync(settings.vsync)
        elif key == "show_fps":
            self.game.overlay = settings.show_fps
        elif key == "ray_tracing":
            self.game.ray_tracing_enabled = settings.ray_tracing and self.ray_tracing_supported
        elif key == "msaa":
            self.game.set_msaa(settings.msaa)
        elif key == "quality":
            from lysyk.profile import quality_profile, resolve
            from lysyk.engine.fx import FilmFx
            self.game.quality = resolve(settings.quality, self.game.is_mobile)
            self.game.profile = quality_profile(self.game.quality, self.game.is_mobile)
            self.game.set_render_scale(self.game.profile["render_scale"])
            self.game.fx = FilmFx(self.game.canvas, grain=self.game.profile["grain"] > 0.0, scanlines=self.game.profile["scanlines"] > 0.0)
            from lysyk.profile import frame_limit
            self.game.set_fps_limit(frame_limit(settings.quality, self.game.is_mobile, settings.fps_limit))
        elif key == "fps_limit":
            from lysyk.profile import frame_limit
            self.game.set_fps_limit(frame_limit(settings.quality, self.game.is_mobile, settings.fps_limit))
        elif key == "language":
            self.game.scenes.current.refresh_labels()
