import math

from lysyk.engine import keys as K

ACCENT = (72, 196, 255)
ACCENT2 = (128, 118, 255)
GOLD = (255, 206, 84)
GOOD = (96, 224, 150)
BAD = (255, 100, 112)
TEXT = (240, 244, 252)
DIM = (150, 162, 186)
PANEL = (12, 16, 30, 206)
PANEL_TOP = (22, 28, 50, 214)
EDGE = (255, 255, 255, 36)
ROW = (255, 255, 255, 14)
ROW_EDGE = (255, 255, 255, 26)


def resolve(value):
    return value() if callable(value) else value


def mix(a, b, t):
    t = min(1.0, max(0.0, t))
    n = max(len(a), len(b))
    a = tuple(a) + (255,) * (n - len(a))
    b = tuple(b) + (255,) * (n - len(b))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(n))


def with_alpha(c, a):
    return (c[0], c[1], c[2], int(a))


class Item:
    enabled = True

    def __init__(self, label):
        self.label = label
        self.anim = 0.0

    def text(self):
        return resolve(self.label)


class Button(Item):
    def __init__(self, label, action, accent=False):
        super().__init__(label)
        self.action = action
        self.accent = accent


class Choice(Item):
    def __init__(self, label, options, get, set_):
        super().__init__(label)
        self.options = options
        self.get = get
        self.set = set_

    def values(self):
        return resolve(self.options)

    def step(self, d):
        vals = self.values()
        if vals:
            self.set((self.get() + d) % len(vals))

    def display(self):
        vals = self.values()
        return vals[self.get() % len(vals)] if vals else "-"


class Slider(Item):
    def __init__(self, label, lo, hi, step, get, set_, fmt=None):
        super().__init__(label)
        self.lo, self.hi, self.stepv = lo, hi, step
        self.get = get
        self.set = set_
        self.fmt = fmt or (lambda v: f"{int(round(v * 100))}%")

    def nudge(self, d):
        v = min(self.hi, max(self.lo, self.get() + d * self.stepv))
        self.set(round(v / self.stepv) * self.stepv)

    def fraction(self):
        return (self.get() - self.lo) / (self.hi - self.lo)

    def set_fraction(self, f):
        f = min(1.0, max(0.0, f))
        v = self.lo + f * (self.hi - self.lo)
        self.set(min(self.hi, max(self.lo, round(v / self.stepv) * self.stepv)))


class Menu:
    def __init__(self, items, sound=None, horizontal=False, on_back=None):
        self.items = items
        self.sound = sound or (lambda name: None)
        self.horizontal = horizontal
        self.on_back = on_back
        self.selected = 0
        self.rects = []
        self.bars = []
        self._drag = -1

    def _hit(self, x, y):
        for i, (rx, ry, rw, rh) in enumerate(self.rects):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return i
        return -1

    def _move_selection(self, d):
        n = len(self.items)
        for _ in range(n):
            self.selected = (self.selected + d) % n
            if self.items[self.selected].enabled:
                break
        self.sound("hover")

    def _activate(self, item, direction=1):
        if not item.enabled:
            return
        if isinstance(item, Button):
            self.sound("select")
            item.action()
        elif isinstance(item, Choice):
            item.step(direction)
            self.sound("click")
        elif isinstance(item, Slider):
            item.nudge(direction)
            self.sound("hover")

    def key(self, key):
        prev, nxt = (K.LEFT, K.RIGHT) if self.horizontal else (K.UP, K.DOWN)
        if key == prev or (not self.horizontal and key == K.W):
            self._move_selection(-1)
        elif key == nxt or (not self.horizontal and key == K.S):
            self._move_selection(1)
        elif key in (K.ENTER, K.KP_ENTER, K.SPACE):
            self._activate(self.items[self.selected])
        elif not self.horizontal and key in (K.LEFT, K.A):
            self._activate(self.items[self.selected], -1)
        elif not self.horizontal and key in (K.RIGHT, K.D):
            self._activate(self.items[self.selected], 1)
        elif key == K.ESCAPE and self.on_back:
            self.sound("back")
            self.on_back()
        else:
            return False
        return True

    def move(self, x, y):
        if self._drag >= 0:
            self._set_slider(self._drag, x)
            return
        i = self._hit(x, y)
        if i >= 0 and i != self.selected and self.items[i].enabled:
            self.selected = i
            self.sound("hover")

    def _set_slider(self, i, x):
        rx, ry, rw, rh = self.bars[i]
        self.items[i].set_fraction((x - rx) / rw)

    def press(self, x, y):
        i = self._hit(x, y)
        if i < 0 or not self.items[i].enabled:
            return
        self.selected = i
        item = self.items[i]
        if isinstance(item, Slider):
            self._drag = i
            self._set_slider(i, x)
            self.sound("hover")
        elif isinstance(item, Choice):
            rx, ry, rw, rh = self.rects[i]
            self._activate(item, -1 if x < rx + rw * 0.5 else 1)
        else:
            self._activate(item)

    def release(self):
        self._drag = -1

    def draw(self, canvas, x, y, width, s, row_h=48, gap=10):
        self.rects = []
        self.bars = []
        rh = row_h * s
        g = gap * s
        n = len(self.items)
        radius = min(rh * 0.5, 16 * s)
        k = min(1.0, canvas.dt * 16.0)
        if self.horizontal:
            cw = (width - g * (n - 1)) / n
        for i, item in enumerate(self.items):
            sel = i == self.selected and item.enabled
            item.anim += ((1.0 if sel else 0.0) - item.anim) * k
            a = item.anim
            if self.horizontal:
                rx, ry, rw = x + i * (cw + g), y, cw
            else:
                rx, ry, rw = x + 0.0, y + i * (rh + g), width
            self.rects.append((rx, ry, rw, rh))
            lift = 2.0 * s * a
            ry -= lift
            if item.enabled:
                fill = mix(ROW, (72, 196, 255, 64), a)
                fill2 = mix(ROW, (128, 118, 255, 64), a)
                edge = mix(ROW_EDGE, (140, 214, 255, 200), a)
            else:
                fill = fill2 = (255, 255, 255, 8)
                edge = (255, 255, 255, 14)
            if a > 0.02:
                canvas.shadow(rx, ry + 4 * s, rw, rh, radius, 14 * s, (72, 150, 255, int(70 * a)))
            canvas.rect(rx, ry, rw, rh, fill, radius, fill2)
            canvas.outline(rx, ry, rw, rh, edge, radius, 1.2)
            color = TEXT if item.enabled else (110, 120, 140)
            size = 13.5 * s
            cy = ry + rh / 2
            if isinstance(item, Button):
                col = mix(color, ACCENT, 0.0)
                if item.accent and item.enabled:
                    col = mix(TEXT, (170, 226, 255), 1.0)
                    canvas.rect(rx + rw * 0.5 - 28 * s, ry + rh - 5 * s, 56 * s, 2.5 * s, ACCENT, 1.2 * s)
                canvas.text(item.text(), rx + rw / 2, cy, col, size=size, anchor_x="center", anchor_y="center", bold=True)
                self.bars.append(None)
            elif isinstance(item, Choice):
                canvas.text(item.text(), rx + 22 * s, cy, color, size=size, anchor_y="center")
                arrow = mix(DIM, ACCENT, a)
                vx = rx + rw - 150 * s
                canvas.text("‹", vx - 116 * s, cy - 1 * s, arrow, size=size * 1.7, anchor_x="center", anchor_y="center", bold=True)
                canvas.text(item.display(), vx, cy, mix(TEXT, (170, 226, 255), a) if item.enabled else color, size=size, anchor_x="center", anchor_y="center", bold=True)
                canvas.text("›", vx + 116 * s, cy - 1 * s, arrow, size=size * 1.7, anchor_x="center", anchor_y="center", bold=True)
                self.bars.append(None)
            else:
                canvas.text(item.text(), rx + 22 * s, cy, color, size=size, anchor_y="center")
                bw = 200 * s
                bx = rx + rw - bw - 84 * s
                th = 6 * s
                by = cy - th / 2
                fr = item.fraction()
                canvas.rect(bx, by, bw, th, (255, 255, 255, 34), th / 2)
                canvas.rect(bx, by, max(th, bw * fr), th, ACCENT, th / 2, ACCENT2)
                kr = (7 + 2 * a) * s
                canvas.shadow(bx + bw * fr - kr, cy - kr + 2 * s, 2 * kr, 2 * kr, kr, 6 * s, (0, 0, 0, 120))
                canvas.circle(bx + bw * fr, cy, kr, (255, 255, 255))
                canvas.text(item.fmt(item.get()), rx + rw - 18 * s, cy, TEXT, size=size * 0.92, anchor_x="right", anchor_y="center")
                self.bars.append((bx, by, bw, th))
        return len(self.items) * (rh + g)


def dim_screen(canvas, w, h, alpha=150):
    canvas.rect(0, 0, w, h, (4, 6, 14, alpha))


def vignette(canvas, w, h, strength=150):
    canvas.rect(0, 0, w, h * 0.22, (0, 0, 0, strength), 0.0, (0, 0, 0, 0))
    canvas.rect(0, h * 0.72, w, h * 0.28, (0, 0, 0, 0), 0.0, (0, 0, 0, int(strength * 1.1)))


def glass(canvas, x, y, w, h, s, radius=18, edge=True):
    canvas.panel(x, y, w, h, radius * s, PANEL, EDGE if edge else None, blur=22 * s, drop=0.4, top=PANEL_TOP)


def bar(canvas, x, y, w, h, fraction, color, color2=None, back=(255, 255, 255, 30)):
    r = h / 2
    canvas.rect(x, y, w, h, back, r)
    fw = w * min(1.0, max(0.0, fraction))
    if fw > 0.5:
        canvas.rect(x, y, max(fw, h), h, color, r, color2 or color)


def chip(canvas, x, y, text, s, color=ACCENT, size=10.5, pad=10, h=22, anchor="left"):
    tw = canvas.text_width(text, size * s, True)
    w = tw + 2 * pad * s
    hh = h * s
    if anchor == "right":
        x -= w
    elif anchor == "center":
        x -= w / 2
    canvas.rect(x, y, w, hh, with_alpha(color, 46), hh / 2)
    canvas.outline(x, y, w, hh, with_alpha(color, 150), hh / 2, 1.0)
    canvas.text(text, x + w / 2, y + hh / 2, mix(color, (255, 255, 255), 0.35), size=size * s, anchor_x="center", anchor_y="center", bold=True)
    return w


def wrap_text(canvas, text, size, width, bold=False):
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = word if not cur else cur + " " + word
            if cur and canvas.text_width(trial, size, bold) > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        lines.append(cur)
    return "\n".join(lines)


def title(canvas, x, y, text, s, size=28, color=TEXT):
    canvas.text(text, x, y, color, size=size * s, bold=True, shadow=True)
    canvas.rect(x, y + (size * 1.75) * s, 46 * s, 3.5 * s, ACCENT, 2 * s, ACCENT2)
