import hashlib
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

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
        self.sound_path = self._audio_path(path)
        self.time = 0.0
        self.frame = -1
        self.playing = False
        self.finished = False
        self.has_sound = audio is not None and bool(self.sound_path) and os.path.isfile(self.sound_path)
        if self.has_sound:
            self.audio.preload([self.sound_path])
        self.decoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lysyk-video")
        self.decode_future = None
        self.decode_index = -1

    def _audio_path(self, path):
        embedded = bytes(self.stream.audio())
        if not embedded:
            legacy = os.path.splitext(path)[0] + ".ogg"
            return legacy if os.path.isfile(legacy) else ""
        digest = hashlib.sha256(embedded).hexdigest()[:24]
        target = os.path.join(tempfile.gettempdir(), "lysyk-video-" + digest + ".ogg")
        if not os.path.isfile(target):
            temporary = target + ".tmp"
            with open(temporary, "wb") as output:
                output.write(embedded)
            os.replace(temporary, target)
        return target

    @property
    def duration(self):
        audio_duration = self.voice.sound.duration if self.voice is not None else 0.0
        return max(self.stream.duration, audio_duration)

    @property
    def width(self):
        return self.stream.width

    @property
    def height(self):
        return self.stream.height

    def play(self):
        if self.decode_future is not None:
            self.decode_future.cancel()
        self.time = 0.0
        self.frame = -1
        self.finished = False
        self.playing = True
        self.decode_index = 0
        self.decode_future = self.decoder.submit(self.stream.decode, 0)
        if self.has_sound:
            self.voice = self.audio.play(self.sound_path, self.volume, False, self.bus)

    def stop(self):
        self.playing = False
        if self.voice is not None:
            self.voice.stop()
            self.voice = None

    def _show(self, index):
        if index == self.frame:
            return
        if self.decode_future is None:
            self.decode_index = index
            self.decode_future = self.decoder.submit(self.stream.decode, index)
            return
        if not self.decode_future.done():
            return
        decoded_index = self.decode_index
        pixels = self.decode_future.result()
        self.decode_future = None
        if decoded_index <= index:
            self.texture.update(pixels)
            self.frame = decoded_index
        if self.frame != index:
            self.decode_index = index
            self.decode_future = self.decoder.submit(self.stream.decode, index)

    def update(self, dt):
        if not self.playing:
            if self.finished:
                self._show(self.stream.frame_count - 1)
            return
        if self.voice is not None and not self.voice.finished:
            self.time = max(self.time, self.voice.position)
        else:
            self.time += dt
        if self.time >= self.duration:
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
