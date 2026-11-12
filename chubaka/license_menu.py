from pathlib import Path

from chubaka import asset
from chubaka.settings_ui import translate
from lysyk.engine.texture import FIT_CONTAIN, draw_image


class LicensePanel:
    def __init__(self, game, close):
        self.game = game
        self.close = close
        self.logo = game.canvas.load_texture(asset("ui", "fsf-logo.png"))
        self.portrait = game.canvas.load_texture(asset("ui", "richard-stallman-libreplanet-2019.png"))
        self.anim = 0.0
        self.closing = False
        self.closed = False
        self.page = "about"
        self.scroll = 0
        self.pressed = None
        self.touch_y = None
        self.touch_moved = False
        self.touch_remainder = 0.0
        self.license_lines = Path(asset("legal", "COPYING")).read_text(encoding="utf-8").splitlines()
        self.wrapped = None

    def t(self, key):
        return translate(self.game.settings.language, key)

    def show(self):
        self.anim = 0.0
        self.closing = False
        self.closed = False
        self.page = "about"
        self.scroll = 0

    def dismiss(self):
        self.closing = True

    def update(self, dt):
        step = max(0.0, dt) * 7.0
        if self.closing:
            self.anim = max(0.0, self.anim - step)
            self.closed = self.anim <= 0.0
        else:
            self.anim = min(1.0, self.anim + step)

    def _wrap_license(self, sc):
        if self.wrapped is not None:
            return
        width = 850
        size = 14
        rows = []
        for paragraph in self.license_lines:
            if not paragraph:
                rows.append("")
                continue
            line = ""
            for word in paragraph.split():
                candidate = word if not line else line + " " + word
                if line and sc.text_width(candidate, size) > width:
                    rows.append(line)
                    line = word
                else:
                    line = candidate
            rows.append(line)
        self.wrapped = rows

    def scroll_by(self, amount):
        if self.page != "license":
            return
        self.scroll = max(0, min(max(0, len(self.wrapped or self.license_lines) - 23), self.scroll + int(amount)))

    def scroll_wheel(self, dy):
        self.scroll_by(-round(dy * 3))

    def key_press(self, key, mods):
        from lysyk.engine import keys as K
        if key == K.ESCAPE:
            if self.page == "license":
                self.page = "about"
            else:
                self.close()
        elif self.page == "license":
            if key == K.DOWN:
                self.scroll_by(1)
            elif key == K.UP:
                self.scroll_by(-1)
            elif key == K.PAGEDOWN:
                self.scroll_by(20)
            elif key == K.PAGEUP:
                self.scroll_by(-20)
            elif key == K.HOME:
                self.scroll = 0
            elif key == K.END:
                self.scroll = max(0, len(self.wrapped or self.license_lines) - 23)

    def draw(self, sc):
        st = sc.stage
        s = st.scale
        a = self.anim
        off = (1.0 - a) * 22.0
        x = 100 + off
        raw = sc.raw
        raw.rect(0, 0, st.win_w, st.win_h, (0, 0, 0, int(198 * a)))
        raw.rect(st.ox + x * s, st.oy + 38 * s, 1080 * s, 644 * s, (0, 8, 0, int(246 * a)), 4 * s)
        raw.outline(st.ox + x * s, st.oy + 38 * s, 1080 * s, 644 * s, (185, 34, 34, int(225 * a)), 3 * s, 2 * s)
        sc.text(self.t("license_title"), 140 + off, 72, (255, 255, 255, int(255 * a)), 36, "left", "center", True, False, "zombie")
        sc.text("×", 1142 + off, 72, (255, 255, 255, int(255 * a)), 36, "center", "center", True)
        sc.rect(140 + off, 101, 1000, 2, (150, 25, 25, int(255 * a)))
        if self.page == "license":
            self._draw_license(sc, off, a)
        else:
            self._draw_about(sc, off, a)

    def _draw_about(self, sc, off, a):
        alpha = lambda color: tuple(color[:3]) + (int(color[3] * a),)
        sc.rect(140 + off, 122, 315, 310, (22, 22, 22, int(220 * a)), 4)
        draw_image(sc, self.logo, 155 + off, 162, 285, 220, FIT_CONTAIN)
        sc.rect(470 + off, 122, 405, 145, (18, 18, 18, int(205 * a)), 4)
        sc.text(self.t("fsf_title"), 490 + off, 144, alpha((250, 250, 250, 255)), 22, "left", "center", True)
        self._draw_paragraph(sc, self.t("fsf_description"), 490 + off, 174, 365, 17, alpha((220, 220, 220, 255)))
        sc.rect(470 + off, 280, 405, 152, (18, 18, 18, int(205 * a)), 4)
        sc.text(self.t("rms_title"), 490 + off, 302, alpha((250, 250, 250, 255)), 22, "left", "center", True)
        self._draw_paragraph(sc, self.t("rms_description"), 490 + off, 332, 365, 17, alpha((220, 220, 220, 255)))
        sc.rect(895 + off, 122, 245, 310, (22, 22, 22, int(220 * a)), 4)
        draw_image(sc, self.portrait, 907 + off, 127, 221, 230, FIT_CONTAIN)
        sc.text(self.t("photo_credit"), 1017 + off, 386, alpha((170, 170, 170, 255)), 9, "center", "center")
        sc.rect(140 + off, 445, 1000, 1.5, alpha((110, 30, 30, 220)))
        self._draw_paragraph(sc, self.t("license_description"), 145 + off, 465, 970, 17, alpha((220, 220, 220, 255)))
        self._draw_paragraph(sc, self.t("license_independence"), 145 + off, 545, 970, 16, alpha((180, 180, 180, 255)))
        sc.rect(405 + off, 620, 470, 42, (45, 25, 25, int(245 * a)), 4)
        sc.raw.outline(sc.stage.ox + (405 + off) * sc.stage.scale, sc.stage.oy + 620 * sc.stage.scale, 470 * sc.stage.scale, 42 * sc.stage.scale, alpha((190, 38, 38, 255)), 4 * sc.stage.scale, 1.5 * sc.stage.scale)
        sc.text(self.t("view_license"), 640 + off, 641, alpha((255, 255, 255, 255)), 20, "center", "center", True)

    def _draw_paragraph(self, sc, text, x, y, width, size, color):
        line = ""
        row = 0
        for word in text.split():
            candidate = word if not line else line + " " + word
            if line and sc.text_width(candidate, size) > width:
                sc.text(line, x, y + row * (size + 10), color, size, "left", "top")
                row += 1
                line = word
            else:
                line = candidate
        if line:
            sc.text(line, x, y + row * (size + 10), color, size, "left", "top")

    def _draw_license(self, sc, off, a):
        self._wrap_license(sc)
        alpha = lambda color: tuple(color[:3]) + (int(color[3] * a),)
        sc.text(self.t("license_reader_hint"), 145 + off, 123, alpha((185, 185, 185, 255)), 15, "left", "center")
        sc.rect(140 + off, 146, 1000, 484, (7, 7, 7, int(235 * a)), 2)
        visible = 23
        self.scroll = min(self.scroll, max(0, len(self.wrapped) - visible))
        for index, line in enumerate(self.wrapped[self.scroll:self.scroll + visible]):
            sc.text(line, 158 + off, 158 + index * 19.5, alpha((229, 229, 229, 255)), 13.5, "left", "top")
        track_y = 158
        track_h = 455
        ratio = min(1.0, visible / max(1, len(self.wrapped)))
        thumb_h = max(28.0, track_h * ratio)
        max_scroll = max(1, len(self.wrapped) - visible)
        thumb_y = track_y + (track_h - thumb_h) * self.scroll / max_scroll
        sc.rect(1115 + off, track_y, 5, track_h, (75, 75, 75, int(220 * a)), 2)
        sc.rect(1113 + off, thumb_y, 9, thumb_h, (185, 35, 35, int(240 * a)), 4)
        sc.text(self.t("back"), 150 + off, 657, alpha((240, 240, 240, 255)), 18, "left", "center", True)

    def press(self, x, y):
        self.pressed = (x, y)

    def move(self, x, y):
        if self.touch_y is not None and self.page == "license":
            delta = self.touch_y - y
            self.touch_moved = self.touch_moved or abs(delta) > 3
            self.touch_remainder += delta
            lines = int(self.touch_remainder / 19.5)
            if lines:
                self.scroll_by(lines)
                self.touch_remainder -= lines * 19.5
            self.touch_y = y

    def release(self, x, y):
        if self.pressed is None:
            return
        px, py = self.pressed
        self.pressed = None
        if px >= 1090 and py <= 110:
            self.close()
            return
        if self.page == "license":
            if py >= 635 and px <= 280:
                self.page = "about"
            elif 140 <= px <= 1140 and 146 <= py <= 630:
                if px >= 1090:
                    self.scroll = min(max(0, len(self.wrapped or []) - 23), max(0, round((py - 158) / 455 * len(self.wrapped or []))))
            return
        if 390 <= px <= 890 and 610 <= py <= 670:
            self.page = "license"
            self.scroll = 0

    def touch(self, touch_id, phase, x, y):
        if phase == "down":
            self.touch_y = y if self.page == "license" and 145 <= y <= 632 else None
            self.touch_moved = False
            self.touch_remainder = 0.0
            self.press(x, y)
        elif phase == "move":
            self.move(x, y)
        elif phase == "up":
            self.touch_y = None
            if self.touch_moved:
                self.pressed = None
            else:
                self.release(x, y)
