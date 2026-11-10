import bisect
import time

import pytest

video = pytest.importorskip("lysyk.engine.media.video")


class FakeStream:
    def __init__(self, frames=30, fps=30.0, cost=0.0, broken=(), width=4, height=2):
        self.width = width
        self.height = height
        self.frame_count = frames
        self.fps = fps
        self.cost = cost
        self.broken = set(broken)
        self.times = [i / fps for i in range(frames)]
        self.duration = frames / fps

    def audio(self):
        return b""

    def frame_index(self, t):
        return max(0, bisect.bisect_right(self.times, t) - 1)

    def decode(self, index):
        if self.cost:
            time.sleep(self.cost)
        if index in self.broken:
            raise RuntimeError("broken frame")
        return bytes([index]) * (self.width * self.height * 4)


class FakeTexture:
    def __init__(self):
        self.shown = []

    def update(self, pixels):
        self.shown.append(pixels[0])


class FakeCanvas:
    def texture(self, width, height):
        self.last = FakeTexture()
        return self.last


def make_player(monkeypatch, **kwargs):
    stream = FakeStream(**kwargs)
    monkeypatch.setattr(video, "VideoStream", lambda path: stream)
    canvas = FakeCanvas()
    return video.VideoPlayer(canvas, "clip.lyv"), canvas.last


def run(player, limit=6.0, step=1 / 60):
    player.play()
    clock = time.perf_counter()
    while not player.finished and time.perf_counter() - clock < limit:
        time.sleep(step)
        player.update(step)
    for _ in range(40):
        player.update(step)
        time.sleep(0.005)


def test_slow_decoder_keeps_up_with_parallel_workers(monkeypatch):
    player, texture = make_player(monkeypatch, frames=36, fps=30.0, cost=0.04)
    run(player)
    assert player.finished
    assert texture.shown == sorted(texture.shown)
    assert len(set(texture.shown)) >= 0.8 * 36
    assert texture.shown[-1] == 35


def test_instant_decoder_shows_every_frame_in_order(monkeypatch):
    player, texture = make_player(monkeypatch, frames=20, fps=20.0)
    run(player)
    assert texture.shown == sorted(set(texture.shown))
    assert texture.shown[-1] == 19


def test_broken_frame_is_skipped(monkeypatch):
    player, texture = make_player(monkeypatch, frames=20, fps=20.0, broken={5, 6})
    run(player)
    assert player.finished
    assert 5 not in texture.shown and 6 not in texture.shown
    assert texture.shown[-1] == 19


def test_stop_releases_buffers(monkeypatch):
    player, texture = make_player(monkeypatch, frames=20, fps=20.0, cost=0.01)
    player.play()
    time.sleep(0.05)
    player.update(0.016)
    player.stop()
    assert not player.jobs and not player.ready and not player.playing


def test_loop_restarts_from_the_first_frame(monkeypatch):
    player, texture = make_player(monkeypatch, frames=10, fps=20.0)
    player.loop = True
    player.play()
    for _ in range(120):
        time.sleep(0.01)
        player.update(0.02)
    assert texture.shown.count(0) >= 2
    assert player.playing
    player.stop()


def test_ahead_window_respects_the_memory_budget(monkeypatch):
    player, _ = make_player(monkeypatch, frames=10, width=3840, height=2160)
    assert video.MIN_AHEAD <= player.ahead <= video.MAX_AHEAD
    assert player.ahead * 3840 * 2160 * 4 <= max(video.BUFFER_BYTES, video.MIN_AHEAD * 3840 * 2160 * 4)
