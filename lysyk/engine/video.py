import os

from lysyk.engine._native import VideoStream
from lysyk.engine.texture import FIT_CONTAIN, draw_image


class VideoPlayer:
    def __init__(self, canvas, path, audio=None, loop=False, volume=1.0, bus="sfx"):
        self.stream = VideoStream(path)
        self.texture = canvas.texture(self.stream.width, self.stream.height)
        self.audio = audio
        self.loop = loop
        self.volume = volume
        self.bus = bus
        self.voice = None
        self.sound_path = os.path.splitext(path)[0] + ".ogg"
        self.time = 0.0
        self.frame = -1
        self.playing = False
        self.finished = False
        self.has_sound = audio is not None and os.path.isfile(self.sound_path)

    @property
    def duration(self):
        return self.stream.duration

    @property
    def width(self):
        return self.stream.width

    @property
    def height(self):
        return self.stream.height

    def play(self):
        self.time = 0.0
        self.frame = -1
        self.finished = False
        self.playing = True
        if self.has_sound:
            self.voice = self.audio.play(self.sound_path, self.volume, False, self.bus)
        self._show(0)

    def stop(self):
        self.playing = False
        if self.voice is not None:
            self.voice.stop()
            self.voice = None

    def _show(self, index):
        if index != self.frame:
            self.stream.upload(self.texture, index)
            self.frame = index

    def update(self, dt):
        if not self.playing:
            return
        if self.voice is not None and not self.voice.finished:
            self.time = max(self.time, self.voice.position)
        else:
            self.time += dt
        if self.time >= self.stream.duration:
            if self.loop:
                self.time = 0.0
                if self.has_sound:
                    self.voice = self.audio.play(self.sound_path, self.volume, False, self.bus)
            else:
                self.playing = False
                self.finished = True
                self._show(self.stream.frame_count - 1)
                return
        self._show(self.stream.frame_index(self.time))

    def draw(self, canvas, x, y, w, h, fit=FIT_CONTAIN, tint=None):
        draw_image(canvas, self.texture, x, y, w, h, fit, tint)
