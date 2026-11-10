class Scene:
    def __init__(self, game):
        self.game = game

    def enter(self, **kwargs):
        pass

    def exit(self):
        pass

    def update(self, dt):
        pass

    def draw(self, sc):
        pass

    def key_press(self, key, mods):
        pass

    def key_release(self, key, mods):
        pass

    def mouse_motion(self, x, y):
        pass

    def mouse_press(self, x, y, button):
        pass

    def mouse_release(self, x, y, button):
        pass

    def touch(self, touch_id, phase, x, y):
        pass

    def suspend(self):
        pass

    def resume(self):
        pass


class SceneManager:
    def __init__(self, game):
        self.game = game
        self.scenes = {}
        self.current = None
        self.current_name = None
        self.pending = None
        self.fade = 0.0
        self.fade_speed = 0.0
        self.fade_color = (0, 0, 0)
        self.phase = "idle"

    def register(self, name, scene):
        self.scenes[name] = scene

    def switch(self, name, **kwargs):
        if self.current is not None:
            self.current.exit()
        self.current = self.scenes[name]
        self.current_name = name
        self.current.enter(**kwargs)

    def goto(self, name, fade=0.5, color=(0, 0, 0), **kwargs):
        if fade <= 0.0 or self.current is None:
            self.switch(name, **kwargs)
            self.phase = "idle"
            self.fade = 0.0
            return
        self.pending = (name, kwargs)
        self.fade_color = color
        self.fade_speed = 2.0 / fade
        self.phase = "out"

    @property
    def busy(self):
        return self.phase != "idle"

    def update(self, dt):
        if self.phase == "out":
            self.fade += self.fade_speed * dt
            if self.fade >= 1.0:
                self.fade = 1.0
                name, kwargs = self.pending
                self.pending = None
                self.switch(name, **kwargs)
                self.phase = "in"
        elif self.phase == "in":
            self.fade -= self.fade_speed * dt
            if self.fade <= 0.0:
                self.fade = 0.0
                self.phase = "idle"
        if self.current is not None:
            self.current.update(dt)

    def draw(self, sc):
        if self.current is not None:
            self.current.draw(sc)
        if self.fade > 0.0:
            st = sc.stage
            c = self.fade_color
            sc.raw.rect(0, 0, st.win_w, st.win_h, (c[0], c[1], c[2], int(255 * min(1.0, self.fade))))

    def route(self, method, *args):
        if self.current is not None and not (self.phase == "out" and method not in ("key_press", "key_release")):
            getattr(self.current, method)(*args)
