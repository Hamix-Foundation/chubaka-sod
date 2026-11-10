from chubaka.settings_ui import translate
from chubaka.widgets import Button


class PauseMenu:
    HUD_X = 1124
    HUD_Y = 78
    HUD_W = 132
    HUD_H = 56

    def __init__(self, game):
        self.game = game
        self.anim = 0.0
        self.resume_button = Button("", 465, 337, 350, 62, game.resume_game, 28, True)
        self.menu_button = Button("", 465, 414, 350, 62, game.return_to_title, 24, True)
        self.refresh_labels()

    def t(self, key):
        return translate(self.game.settings.language, key)

    def refresh_labels(self):
        self.resume_button.label = self.t("resume")
        self.menu_button.label = self.t("main_menu")

    def update(self, dt):
        self.anim = min(1.0, self.anim + max(0.0, dt) * 7.0)
        self.resume_button.update(dt)
        self.menu_button.update(dt)

    def draw_hud(self, sc):
        x, y, w, h = self.HUD_X, self.HUD_Y, self.HUD_W, self.HUD_H
        sc.rect(x, y, w, h, (8, 9, 10, 218), 8)
        sc.raw.outline(sc.stage.ox + x * sc.stage.scale, sc.stage.oy + y * sc.stage.scale, w * sc.stage.scale, h * sc.stage.scale, (190, 44, 38, 235), 8 * sc.stage.scale, 1.5 * sc.stage.scale)
        sc.text("Ⅱ", x + 29, y + h / 2, (255, 255, 255, 255), 27, "center", "center", True)
        sc.text(self.t("pause_button"), x + 80, y + h / 2, (242, 242, 242, 255), 15, "center", "center", True)

    def draw(self, sc):
        a = self.anim
        st = sc.stage
        sc.raw.rect(0, 0, st.win_w, st.win_h, (0, 0, 0, int(190 * a)))
        x = 420 + (1.0 - a) * 22
        sc.rect(x, 215, 440, 315, (0, 8, 0, int(246 * a)), 4)
        sc.raw.outline(st.ox + x * st.scale, st.oy + 215 * st.scale, 440 * st.scale, 315 * st.scale, (185, 34, 34, int(225 * a)), 3 * st.scale, 2 * st.scale)
        sc.text(self.t("paused"), 640 + (1.0 - a) * 22, 270, (255, 255, 255, int(255 * a)), 42, "center", "center", True, False, "zombie")
        self.resume_button.x = 465 + (1.0 - a) * 22
        self.menu_button.x = 465 + (1.0 - a) * 22
        self.resume_button.draw(sc)
        self.menu_button.draw(sc)

    def motion(self, x, y):
        self.resume_button.motion(x, y)
        self.menu_button.motion(x, y)

    def press(self, x, y):
        self.resume_button.press(x, y)
        self.menu_button.press(x, y)

    def release(self, x, y):
        if self.resume_button.release(x, y):
            self.menu_button.down = False
            return
        self.menu_button.release(x, y)
