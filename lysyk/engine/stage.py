class Stage:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.scale = 1.0
        self.ox = 0.0
        self.oy = 0.0
        self.win_w = width
        self.win_h = height

    def fit(self, win_w, win_h):
        self.win_w = max(1, win_w)
        self.win_h = max(1, win_h)
        self.scale = min(self.win_w / self.width, self.win_h / self.height)
        self.ox = (self.win_w - self.width * self.scale) / 2.0
        self.oy = (self.win_h - self.height * self.scale) / 2.0

    def to_stage(self, x, y):
        return (x - self.ox) / self.scale, (y - self.oy) / self.scale

    def to_screen(self, x, y):
        return self.ox + x * self.scale, self.oy + y * self.scale

    def contains(self, x, y, rx, ry, rw, rh):
        return rx <= x <= rx + rw and ry <= y <= ry + rh


class StageCanvas:
    def __init__(self, canvas, stage):
        self.raw = canvas
        self.stage = stage

    def rect(self, x, y, w, h, color, radius=0.0, color2=None):
        s = self.stage
        self.raw.rect(s.ox + x * s.scale, s.oy + y * s.scale, w * s.scale, h * s.scale, color, radius * s.scale, color2)

    def text(self, text, x, y, color, size=14.0, anchor_x="left", anchor_y="top", bold=False, shadow=False, font=None):
        s = self.stage
        self.raw.text(text, s.ox + x * s.scale, s.oy + y * s.scale, color, size * s.scale, anchor_x, anchor_y, bold, shadow, font)

    def text_width(self, text, size=14.0, bold=False, font=None):
        return self.raw.text_width(text, size * self.stage.scale, bold, font) / self.stage.scale

    def text_height(self, text, size=14.0, bold=False, font=None):
        return self.raw.text_height(text, size * self.stage.scale, bold, font) / self.stage.scale

    def image(self, tex, x, y, w, h, tint=None, uv=None):
        s = self.stage
        self.raw.image(tex, s.ox + x * s.scale, s.oy + y * s.scale, w * s.scale, h * s.scale, tint, uv)

    def letterbox(self):
        s = self.stage
        black = (0, 0, 0, 255)
        if s.oy > 0.5:
            self.raw.rect(0, 0, s.win_w, s.oy, black)
            self.raw.rect(0, s.win_h - s.oy, s.win_w, s.oy + 1, black)
        if s.ox > 0.5:
            self.raw.rect(0, 0, s.ox, s.win_h, black)
            self.raw.rect(s.win_w - s.ox, 0, s.ox + 1, s.win_h, black)
