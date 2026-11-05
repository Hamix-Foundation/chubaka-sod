from lysyk.engine.tween import damp

WHITE = (255, 255, 255, 255)
BUTTON_TEXT = (224, 224, 224, 255)


class Button:
    def __init__(self, label, x, y, w, h, action, size=35, bold=False, text_overflow="shrink", padding=12, vertical_padding=2):
        self.label = label
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.action = action
        self.size = size
        self.hover = False
        self.down = False
        self.glow = 0.0
        self.arrow = True
        self.bold = bold
        if text_overflow not in ("shrink", "wrap", "none"):
            raise ValueError("text_overflow must be 'shrink', 'wrap', or 'none'")
        self.text_overflow = text_overflow
        self.padding = padding
        self.vertical_padding = vertical_padding

    def contains(self, px, py):
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def motion(self, px, py):
        self.hover = self.contains(px, py)

    def press(self, px, py):
        if self.contains(px, py):
            self.down = True
            return True
        return False

    def release(self, px, py):
        fire = self.down and self.contains(px, py)
        self.down = False
        if fire:
            self.action()
        return fire

    def update(self, dt):
        self.glow = damp(self.glow, 1.0 if self.hover else 0.0, 14.0, dt)

    def _wrap(self, sc, text, width, size):
        result = []
        for paragraph in text.split("\n"):
            words = paragraph.split()
            if not words:
                result.append("")
                continue
            line = ""
            for word in words:
                parts = [word]
                if sc.text_width(word, size, self.bold) > width:
                    parts = []
                    chunk = ""
                    for char in word:
                        if chunk and sc.text_width(chunk + char, size, self.bold) > width:
                            parts.append(chunk)
                            chunk = char
                        else:
                            chunk += char
                    if chunk:
                        parts.append(chunk)
                for part in parts:
                    candidate = part if not line else line + " " + part
                    if line and sc.text_width(candidate, size, self.bold) > width:
                        result.append(line)
                        line = part
                    else:
                        line = candidate
            result.append(line)
        return "\n".join(result)

    def draw(self, sc):
        base = 26
        lift = int(14 * self.glow)
        shade = base + lift - (10 if self.down else 0)
        sc.rect(self.x, self.y, self.w, self.h, (shade, shade, shade, 150 + int(40 * self.glow)), 4)
        if self.glow > 0.02:
            sc.rect(self.x, self.y, 3, self.h, (200, 30, 30, int(255 * self.glow)))
        text = ("> " if self.hover and self.arrow else "") + self.label
        col = BUTTON_TEXT if not self.hover else WHITE
        max_w = max(1.0, self.w - self.padding * 2)
        max_h = max(1.0, self.h - self.vertical_padding * 2)
        size = self.size
        if self.text_overflow == "wrap":
            text = self._wrap(sc, text, max_w, size)
        text_w = sc.text_width(text, size, self.bold)
        text_h = sc.text_height(text, size, self.bold)
        if self.text_overflow == "shrink" or self.text_overflow == "wrap":
            scale = min(1.0, max_w / max(text_w, 1.0), max_h / max(text_h, 1.0))
            size *= scale
        sc.text(text, self.x + self.w / 2, self.y + self.h / 2, col, size, "center", "center", self.bold)


class SocialButton(Button):
    def __init__(self, label, brand, x, y, w, h, action, icon):
        super().__init__(label, x, y, w, h, action, size=14, bold=True, padding=4, vertical_padding=2)
        self.brand = brand
        self.icon = icon
        self.arrow = False

    def draw(self, sc):
        inset = 2 + self.glow
        sc.rect(self.x + inset, self.y + inset, self.w - inset * 2, self.h - inset * 2, (14, 14, 14, 240), 8)
        sc.image(self.icon, self.x + inset + 2, self.y + inset + 2, self.w - inset * 2 - 4, self.h - inset * 2 - 4)
        scale = sc.stage.scale
        if self.glow > 0.02:
            x = sc.stage.ox + self.x * scale
            y = sc.stage.oy + self.y * scale
            sc.raw.outline(x, y, self.w * scale, self.h * scale, (205, 38, 38, int(255 * self.glow)), 9 * scale, 1.5 * scale)
