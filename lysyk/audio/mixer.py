import threading
import os

import numpy as np

SAMPLE_RATE = 44100


class Sound:
    def __init__(self, samples, path="", native_id=None, native_duration=0.0):
        self.samples = samples
        self.path = path
        self.native_id = native_id
        self.native_duration = native_duration

    @property
    def frames(self):
        return len(self.samples)

    @property
    def duration(self):
        return self.native_duration if self.native_duration else len(self.samples) / SAMPLE_RATE


class Voice:
    def __init__(self, sound, volume, loop, bus):
        self.sound = sound
        self.volume = volume
        self.loop = loop
        self.bus = bus
        self.cursor = 0
        self.finished = False
        self.paused = False
        self.fade_rate = 0.0
        self.fade_gain = 1.0
        self.stop_after_fade = False

    @property
    def position(self):
        return self.cursor / SAMPLE_RATE

    def stop(self, fade=0.0):
        if fade > 0.0:
            self.fade_rate = -self.fade_gain / fade
            self.stop_after_fade = True
        else:
            self.finished = True

    def fade_in(self, seconds):
        self.fade_gain = 0.0
        self.fade_rate = 1.0 / max(seconds, 1e-3)
        self.stop_after_fade = False

    def mix_into(self, out, gain):
        n = len(out)
        if self.finished or self.paused:
            return
        total = self.sound.frames
        if total == 0:
            self.finished = True
            return
        written = 0
        while written < n:
            if self.cursor >= total:
                if self.loop:
                    self.cursor = 0
                else:
                    self.finished = True
                    return
            take = min(n - written, total - self.cursor)
            chunk = self.sound.samples[self.cursor:self.cursor + take]
            if chunk.dtype == np.int16:
                chunk = chunk.astype(np.float32) * (1.0 / 32768.0)
            g = self.volume * gain
            if self.fade_rate != 0.0:
                ramp = self.fade_gain + self.fade_rate * (np.arange(take, dtype=np.float32) / SAMPLE_RATE)
                ramp = np.clip(ramp, 0.0, 1.0)
                out[written:written + take] += chunk * (ramp[:, None] * g)
                self.fade_gain = float(ramp[-1])
                if self.fade_rate > 0.0 and self.fade_gain >= 1.0:
                    self.fade_rate = 0.0
                elif self.fade_rate < 0.0 and self.fade_gain <= 0.0:
                    self.fade_rate = 0.0
                    if self.stop_after_fade:
                        self.finished = True
            else:
                out[written:written + take] += chunk * (self.fade_gain * g)
            self.cursor += take
            written += take
            if self.finished:
                return


class Audio:
    def __init__(self, enabled=True, buffer_ms=50):
        self.buffer_ms = buffer_ms
        self.paused = False
        self.lock = threading.Lock()
        self.voices = []
        self.cache = {}
        self.master = 1.0
        self.buses = {"sfx": 1.0, "music": 1.0, "voice": 1.0}
        self.device = None
        self.android_pool = None
        self.android_classes = None
        self._gen = None
        if enabled:
            self._open()

    @property
    def has_device(self):
        return self.device is not None

    def _open(self):
        if "LYSYK_ROOT" in os.environ or ("ANDROID_ROOT" in os.environ and "ANDROID_DATA" in os.environ):
            try:
                from jnius import autoclass
                AudioAttributes = autoclass("android.media.AudioAttributes")
                AudioAttributesBuilder = autoclass("android.media.AudioAttributes$Builder")
                SoundPoolBuilder = autoclass("android.media.SoundPool$Builder")
                attributes = AudioAttributesBuilder().setUsage(AudioAttributes.USAGE_GAME).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build()
                pool = SoundPoolBuilder().setMaxStreams(16).setAudioAttributes(attributes).build()
                self.android_pool = pool
                self.android_classes = autoclass
                return
            except Exception:
                self.android_pool = None
                self.android_classes = None
        try:
            import miniaudio
            device = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.FLOAT32, nchannels=2, sample_rate=SAMPLE_RATE, buffersize_msec=self.buffer_ms
            )
            self._gen = self._stream()
            next(self._gen)
            device.start(self._gen)
            self.device = device
        except Exception:
            self.device = None
            self._gen = None

    def _stream(self):
        required = yield b""
        while True:
            data = self.render(required)
            required = yield data.astype(np.float32).tobytes()

    def render(self, frames):
        out = np.zeros((frames, 2), dtype=np.float32)
        with self.lock:
            for v in self.voices:
                v.mix_into(out, self.master * self.buses.get(v.bus, 1.0))
            self.voices = [v for v in self.voices if not v.finished]
        np.clip(out, -1.0, 1.0, out=out)
        return out

    def load(self, path):
        snd = self.cache.get(path)
        if snd is None:
            if self.android_pool is not None:
                try:
                    sound_id = self.android_pool.load(path, 1)
                    duration = 0.0
                    try:
                        MediaMetadataRetriever = self.android_classes("android.media.MediaMetadataRetriever")
                        metadata = MediaMetadataRetriever()
                        metadata.setDataSource(path)
                        duration_ms = metadata.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                        duration = float(duration_ms or 0) / 1000.0
                        metadata.release()
                    except Exception:
                        pass
                    snd = Sound(None, path, sound_id, duration)
                except Exception:
                    snd = Sound(np.zeros((0, 2), dtype=np.int16), path)
                self.cache[path] = snd
                return snd
            try:
                import miniaudio
                dec = miniaudio.decode_file(
                    path, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=2, sample_rate=SAMPLE_RATE
                )
                snd = Sound(np.frombuffer(dec.samples, dtype=np.int16).reshape(-1, 2).copy(), path)
            except Exception:
                snd = Sound(np.zeros((0, 2), dtype=np.int16), path)
            self.cache[path] = snd
        return snd

    def preload(self, paths):
        pending = [p for p in paths if p not in self.cache]
        if not pending:
            return None

        def work():
            for p in pending:
                self.load(p)

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread

    def play(self, sound, volume=1.0, loop=False, bus="sfx", fade_in=0.0):
        if isinstance(sound, str):
            sound = self.load(sound)
        if self.android_pool is not None and sound.native_id is not None:
            stream = self.android_pool.play(sound.native_id, 0.0, 0.0, 1, -1 if loop else 0, 1.0)
            voice = AndroidVoice(sound, volume, loop, bus, stream, fade_in)
            with self.lock:
                self.voices.append(voice)
            return voice
        voice = Voice(sound, volume, loop, bus)
        if fade_in > 0.0:
            voice.fade_in(fade_in)
        with self.lock:
            self.voices.append(voice)
        return voice

    def stop_bus(self, bus, fade=0.0):
        with self.lock:
            for v in self.voices:
                if v.bus == bus:
                    v.stop(fade)

    def stop_all(self):
        with self.lock:
            for v in self.voices:
                v.finished = True
            self.voices = []

    def pause(self):
        self.paused = True
        if self.android_pool is not None:
            try:
                self.android_pool.autoPause()
            except Exception:
                pass
        if self.device is not None:
            try:
                self.device.stop()
            except Exception:
                pass

    def resume(self):
        self.paused = False
        if self.android_pool is not None:
            try:
                self.android_pool.autoResume()
            except Exception:
                pass
        if self.device is not None and self._gen is not None:
            try:
                self._gen = self._stream()
                next(self._gen)
                self.device.start(self._gen)
            except Exception:
                pass

    def update(self, dt):
        if self.paused:
            return
        if self.android_pool is not None:
            with self.lock:
                for voice in self.voices:
                    if isinstance(voice, AndroidVoice):
                        voice.update(dt, self.master * self.buses.get(voice.bus, 1.0), self.android_pool)
                self.voices = [v for v in self.voices if not v.finished]
            return
        if self.device is None and dt > 0.0:
            self.render(int(min(dt, 0.25) * SAMPLE_RATE))

    def close(self):
        if self.android_pool is not None:
            try:
                self.android_pool.release()
            except Exception:
                pass
            self.android_pool = None
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None


class AndroidVoice:
    def __init__(self, sound, volume, loop, bus, stream, fade_in):
        self.sound = sound
        self.volume = volume
        self.loop = loop
        self.bus = bus
        self.stream = stream
        self.finished = False
        self.paused = False
        self.gain = 0.0 if fade_in > 0 else 1.0
        self.target = 1.0
        self.rate = 1.0 / fade_in if fade_in > 0 else 0.0
        self.elapsed = 0.0

    def stop(self, fade=0.0):
        if fade > 0:
            self.target = 0.0
            self.rate = 1.0 / fade
        else:
            self.finished = True

    def update(self, dt, bus_gain, pool):
        if self.finished:
            if self.stream:
                pool.stop(self.stream)
                self.stream = 0
            return
        self.elapsed += dt
        if not self.loop and self.sound.duration > 0 and self.elapsed > self.sound.duration + 0.5:
            self.finished = True
            return
        if self.gain != self.target:
            step = self.rate * min(dt, 0.1)
            self.gain = min(self.target, self.gain + step) if self.target > self.gain else max(self.target, self.gain - step)
            if self.gain == 0.0 and self.target == 0.0:
                self.finished = True
        gain = max(0.0, min(1.0, self.volume * bus_gain * self.gain))
        if self.stream:
            try:
                pool.setVolume(self.stream, gain, gain)
            except Exception:
                self.finished = True
        elif self.sound.native_id is not None:
            self.stream = pool.play(self.sound.native_id, gain, gain, 1, -1 if self.loop else 0, 1.0)

    def pause(self):
        if self.stream and not self.paused:
            self.paused = True

    def resume(self):
        if self.paused:
            self.paused = False
