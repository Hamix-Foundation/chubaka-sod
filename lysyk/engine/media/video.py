import hashlib
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from lysyk.engine._native import VideoStream
from lysyk.engine.texture import FIT_CONTAIN, draw_image

BUFFER_BYTES = 96 * 1024 * 1024
MAX_WORKERS = 4
MIN_AHEAD = 3
MAX_AHEAD = 12
START_TIMEOUT = 1.5


def decoder_count():
    return max(1, min(MAX_WORKERS, os.cpu_count() or 1))


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
        self.started = False
        self.waited = 0.0
        self.has_sound = audio is not None and bool(self.sound_path) and os.path.isfile(self.sound_path)
        if self.has_sound:
            self.audio.preload([self.sound_path])
        self.last = self.stream.frame_count - 1
        frame_bytes = max(1, self.stream.width * self.stream.height * 4)
        self.ahead = max(MIN_AHEAD, min(MAX_AHEAD, BUFFER_BYTES // frame_bytes))
        self.decoder = ThreadPoolExecutor(max_workers=decoder_count(), thread_name_prefix="lysyk-video")
        self.jobs = {}
        self.ready = {}
        self.bad = set()

    def _audio_path(self, path):
        embedded = bytes(self.stream.audio())
        if not embedded:
            legacy = os.path.splitext(path)[0] + ".ogg"
            return legacy if os.path.isfile(legacy) else ""
        digest = hashlib.sha256(embedded).hexdigest()[:24]
        if os.environ.get("LYSYK_ROOT"):
            cache_dir = os.path.join(os.environ["LYSYK_ROOT"], "cache", "video")
        else:
            cache_dir = tempfile.gettempdir()
        os.makedirs(cache_dir, exist_ok=True)
        target = os.path.join(cache_dir, "lysyk-video-" + digest + ".ogg")
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

    def _reset_buffers(self):
        for future in self.jobs.values():
            future.cancel()
        self.jobs.clear()
        self.ready.clear()
        self.bad.clear()

    def _start_audio(self):
        if self.has_sound:
            self.voice = self.audio.play(self.sound_path, self.volume, False, self.bus)

    def play(self):
        self._reset_buffers()
        self.time = 0.0
        self.frame = -1
        self.finished = False
        self.playing = True
        self.started = False
        self.waited = 0.0
        self._feed(0)

    def stop(self):
        self.playing = False
        if self.voice is not None:
            self.voice.stop()
            self.voice = None
        self._reset_buffers()

    def _collect(self):
        for index in [i for i, future in self.jobs.items() if future.done()]:
            future = self.jobs.pop(index)
            if future.cancelled() or future.exception() is not None:
                self.bad.add(index)
            else:
                self.ready[index] = future.result()

    def _feed(self, target):
        for index in [i for i in self.jobs if i < target]:
            if self.jobs[index].cancel():
                del self.jobs[index]
        end = min(self.last, target + self.ahead)
        for index in range(max(0, target), end + 1):
            if index in self.jobs or index in self.ready or index in self.bad:
                continue
            self.jobs[index] = self.decoder.submit(self.stream.decode, index)

    def _present(self, target):
        best = -1
        for index in self.ready:
            if self.frame < index <= target and index > best:
                best = index
        if best < 0:
            return
        self.texture.update(self.ready[best])
        self.frame = best
        for index in [i for i in self.ready if i <= best]:
            del self.ready[index]

    def _show(self, target):
        self._collect()
        self._feed(target)
        self._present(target)

    def _begin(self, dt):
        self._collect()
        self.waited += dt
        need = max(1, min(self.ahead // 2 + 1, self.last + 1))
        if len(self.ready) >= need or not self.jobs or self.waited >= START_TIMEOUT:
            self.started = True
            self._start_audio()
            return True
        return False

    def update(self, dt):
        if not self.playing:
            if self.finished and self.frame < self.last:
                self._show(self.last)
            return
        if not self.started and not self._begin(dt):
            return
        if self.voice is not None and not self.voice.finished:
            self.time = max(self.time, self.voice.position)
        else:
            self.time += dt
        if self.time >= self.duration:
            if self.loop:
                self.time = 0.0
                self.frame = -1
                self._reset_buffers()
                self._start_audio()
            else:
                self.playing = False
                self.finished = True
                self._show(self.last)
                return
        self._show(self.stream.frame_index(self.time))

    def draw(self, canvas, x, y, w, h, fit=FIT_CONTAIN, tint=None):
        draw_image(canvas, self.texture, x, y, w, h, fit, tint)
