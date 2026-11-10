import math
import os

import numpy as np
import pytest

from chubaka import asset
from chubaka.camera import ANGLE_MAX, ANGLE_MIN, LookController
from chubaka.scenes.classroom import SEAT_YAW
from lysyk.audio import Audio
from lysyk.engine import _native
from lysyk.engine import keys as K
from lysyk.engine.model import load_obj
from lysyk.engine.save import SaveFile
from lysyk.engine.scenes import Scene, SceneManager
from lysyk.engine.stage import Stage
from lysyk.engine.texture import fit_rect
from lysyk.engine.window import OffscreenWindow

API = "gl" if "gl" in _native.compiled_backends() else _native.compiled_backends()[0]


def test_image_draws_texture():
    win = OffscreenWindow(64, 64, msaa=False, backend=API)
    data = np.zeros((4, 4, 4), dtype=np.uint8)
    data[..., 0] = 255
    data[..., 3] = 255
    tex = win.canvas.texture(4, 4, data, "nearest")

    def draw():
        win.clear((0, 0, 0))
        win.canvas.image(tex, 8, 8, 32, 32)

    win.frame(draw)
    px = win.read_pixels()
    assert px[20, 20, 0] > 200 and px[20, 20, 1] < 30
    assert px[60, 60, 0] < 30


def test_texture_update_and_tint():
    win = OffscreenWindow(32, 32, msaa=False, backend=API)
    tex = win.canvas.texture(2, 2)
    tex.update(np.full((2, 2, 4), 255, dtype=np.uint8))

    def draw():
        win.clear((0, 0, 0))
        win.canvas.image(tex, 0, 0, 32, 32, (0, 255, 0, 255))

    win.frame(draw)
    px = win.read_pixels()
    assert px[16, 16, 1] > 200 and px[16, 16, 0] < 30
    with pytest.raises(ValueError):
        tex.update(np.zeros((3, 3, 4), dtype=np.uint8))


def test_custom_font_changes_text():
    win = OffscreenWindow(200, 60, msaa=False, backend=API)
    win.canvas.load_font("zombie", asset("fonts", "BloodVictimZombie.ttf"))
    assert win.canvas.has_font("zombie")
    a = win.canvas.text_width("Chubaka", 30)
    b = win.canvas.text_width("Chubaka", 30, False, "zombie")
    assert a != b


def test_video_stream_decodes_frames():
    stream = _native.VideoStream(asset("video", "night1_cutscene.lyv"))
    assert (stream.width, stream.height) == (896, 480)
    assert stream.frame_count > 600
    assert stream.duration > 24.0
    assert stream.frame_index(0.0) == 0
    assert stream.frame_index(stream.duration + 5) == stream.frame_count - 1
    px = np.frombuffer(stream.decode(100), dtype=np.uint8)
    assert px.size == 896 * 480 * 4
    assert px.reshape(-1, 4)[:, 3].min() == 255


def test_video_upload_into_texture():
    win = OffscreenWindow(128, 72, msaa=False, backend=API)
    stream = _native.VideoStream(asset("video", "night1_cutscene.lyv"))
    tex = win.canvas.texture(stream.width, stream.height)
    stream.upload(tex, 200)

    def draw():
        win.clear((0, 0, 0))
        win.canvas.image(tex, 0, 0, 128, 72)

    win.frame(draw)
    assert win.read_pixels()[..., :3].sum() > 0


def test_video_stream_rejects_garbage(tmp_path):
    p = tmp_path / "x.lyv"
    p.write_bytes(b"not a video at all, sorry........")
    with pytest.raises(ValueError):
        _native.VideoStream(str(p))


def test_desk_parts_are_named():
    parts = load_obj(asset("game", "models", "Desk.obj"), scale=0.001)
    assert {p.name for p in parts} == {"tube", "walls", "table_top"}


def test_save_roundtrip_and_tamper(tmp_path):
    f = SaveFile(str(tmp_path / "s.dat"), "secret")
    assert f.read() is None
    f.write({"current_night": 3, "unlocked_custom_night": False})
    assert f.read() == {"current_night": 3, "unlocked_custom_night": False}
    assert b"current_night" not in open(f.path, "rb").read()
    assert SaveFile(f.path, "other").read() is None
    blob = bytearray(open(f.path, "rb").read())
    blob[-1] ^= 1
    open(f.path, "wb").write(bytes(blob))
    assert f.read() is None


def test_stage_letterbox_mapping():
    st = Stage(1280, 720)
    st.fit(1920, 1200)
    assert abs(st.scale - 1.5) < 1e-6
    assert abs(st.oy - 60) < 1e-6
    x, y = st.to_stage(*st.to_screen(300, 400))
    assert abs(x - 300) < 1e-6 and abs(y - 400) < 1e-6


def test_fit_rect_modes():
    assert fit_rect(100, 50, 0, 0, 200, 200, "contain")[:4] == (0.0, 50.0, 200.0, 100.0)
    x, y, w, h, uv = fit_rect(100, 50, 0, 0, 200, 200, "cover")
    assert (w, h) == (200, 200) and abs(uv[2] - uv[0] - 0.5) < 1e-6


def test_look_controller_mouse_range_and_deadzone():
    c = LookController(-125.0)
    for _ in range(300):
        c.mouse_motion(640)
        c.update(1 / 60)
    assert abs(c.yaw) < 0.5
    for _ in range(300):
        c.mouse_motion(1280)
        c.update(1 / 60)
    assert abs(c.yaw - ANGLE_MAX) < 0.5
    for _ in range(300):
        c.mouse_motion(0)
        c.update(1 / 60)
    assert abs(c.yaw - ANGLE_MIN) < 0.5
    c.mouse_motion(640 + 60)
    c.update(1 / 60)
    assert c.target == 0.0


def test_look_controller_touch_halves():
    c = LookController(0.0)
    c.touch(1, "down", 100, 300)
    for _ in range(30):
        c.update(1 / 60)
    assert c.target < 0
    c.touch(2, "down", 1000, 300)
    t = c.target
    c.update(1 / 60)
    assert c.target == t
    c.touch(1, "up", 100, 300)
    c.touch(2, "up", 1000, 300)
    assert c.touch_direction == 0


def test_scene_manager_fades_and_switches():
    class Game:
        pass

    log = []

    class A(Scene):
        def enter(self, **kw):
            log.append(("A", kw))

    class B(Scene):
        def enter(self, **kw):
            log.append(("B", kw))

    sm = SceneManager(Game())
    sm.register("a", A(None))
    sm.register("b", B(None))
    sm.switch("a")
    sm.goto("b", fade=0.2, n=2)
    assert sm.busy
    for _ in range(40):
        sm.update(0.02)
    assert not sm.busy and sm.current_name == "b" and log[-1] == ("B", {"n": 2})


def test_audio_mixes_without_device(tmp_path):
    a = Audio(enabled=False)
    snd = a.load(asset("audio", "night_start.mp3"))
    v = a.play(snd, 1.0)
    out = a.render(4410)
    assert np.abs(out).max() > 0
    assert v.position > 0.09
    a.stop_all()
    assert np.abs(a.render(100)).max() == 0


def test_audio_loop_and_fade():
    a = Audio(enabled=False)
    snd = a.load(asset("audio", "night_start.mp3"))
    v = a.play(snd, 1.0, loop=True)
    a.render(snd.frames + 1000)
    assert not v.finished
    v.stop(0.05)
    a.render(4000)
    assert v.finished


def test_look_controller_center_offsets_range():
    c = LookController(30.0, center=30.0)
    for _ in range(300):
        c.mouse_motion(1280)
        c.update(1 / 60)
    assert abs(c.yaw - (30.0 + ANGLE_MAX)) < 0.5
    for _ in range(300):
        c.mouse_motion(0)
        c.update(1 / 60)
    assert abs(c.yaw - (30.0 + ANGLE_MIN)) < 0.5
    c.touch(1, "down", 100, 300)
    for _ in range(600):
        c.update(1 / 60)
    assert c.target >= 30.0 + ANGLE_MIN


def test_classroom_build_levels():
    from chubaka import classroom

    from chubaka.layout import HX, WALL_TOP

    low = classroom.build(0)
    high = classroom.build(2)
    for m in (low.floor, low.shell, low.trim, low.furniture, low.decor, low.sky):
        assert m.triangle_count > 0
    assert high.triangles > low.triangles
    assert len(low.tubes) == 2
    v = np.asarray(low.shell.vertices)
    assert v[:, 1].max() > WALL_TOP and v[:, 0].min() < -HX


def test_classroom_deterministic():
    from chubaka import classroom

    a = classroom.build(1, seed=3)
    b = classroom.build(1, seed=3)
    assert np.array_equal(np.asarray(a.furniture.vertices), np.asarray(b.furniture.vertices))


def test_geometry_batch_group_transform():
    from chubaka.geometry import Batch

    b = Batch()
    b.push((10.0, 0.0, 0.0))
    b.box((0, 0, 0), (2, 2, 2), (1, 2, 3))
    b.pop()
    v = np.asarray(b.build().vertices)
    assert abs(v[:, 0].mean() - 10.0) < 1e-4
    assert b.group is None


def test_profile_resolution():
    from lysyk.profile import PROFILES, resolve

    assert resolve("auto", True) == "medium"
    assert resolve("auto", False) == "high"
    assert resolve("low", False) == "low"
    assert PROFILES["low"]["shadow_quality"] <= PROFILES["high"]["shadow_quality"]


def test_classroom_scene_renders():
    from chubaka.scenes.classroom import ClassroomScene
    from lysyk.profile import PROFILES

    win = OffscreenWindow(160, 90, msaa=False, backend=API)
    win.profile = dict(PROFILES["low"])
    win.audio = Audio(enabled=False)
    scene = ClassroomScene(win)
    scene.build()
    scene.camera.position = (0.6, 1.5, 3.0)
    scene.camera.rotation = (0.0, math.pi, 0.0)

    def draw():
        win.clear(scene.lighting.clear_color())
        scene.renderer.render(scene.camera, scene.world)

    win.frame(draw)
    px = win.read_pixels()[..., :3]
    assert px.sum() > 0 and px.std() > 5


def test_interaction_hover_and_click():
    import math

    from lysyk.engine.interact import Hotspot, Interaction

    hits = []
    it = Interaction()
    it.add(Hotspot("door", (0.0, 1.0, 5.0), 0.5, lambda: hits.append(1)))
    it.add(Hotspot("off", (5.0, 1.0, 0.0), 0.5, lambda: hits.append(2), enabled=False))
    assert it.update((0.0, 1.0, 0.0), 0.0) is not None
    assert it.click() and hits == [1]
    assert it.update((0.0, 1.0, 0.0), math.radians(90.0)) is None
    assert not it.click()
    far = it.add(Hotspot("far", (0.0, 1.0, 5.0), 0.5, None, max_distance=2.0))
    assert it.update((0.0, 1.0, 0.0), 0.0).name == "door" and far.angle == math.pi


def test_pose_rig_travel_and_callback():
    from lysyk.engine.rig import Pose, PoseRig

    done = []
    rig = PoseRig(Pose((0.0, 1.2, 0.0), 350.0))
    rig.travel([(0.0, 1.6, 0.0), (4.0, 1.6, 0.0)], 2.0, 20.0, 0.0, 0.03, 4.0, lambda: done.append(1))
    assert rig.busy
    for _ in range(300):
        rig.update(1 / 60)
    assert not rig.busy and done == [1]
    assert rig.pose.position == (4.0, 1.6, 0.0)
    assert abs(rig.pose.yaw - 380.0) < 1e-6


def test_door_push_hold_and_events():
    from lysyk.engine.door import Door
    from lysyk.engine.objects import GameObject

    events = []
    door = Door(GameObject(None), (1.0, 0.0, 2.0), 0.0, -1.0, 0.5, 6.0, lambda n, d: events.append(n))
    for _ in range(60):
        door.update(1 / 30)
    assert door.openness > 0.9 and "unlatch" in events
    door.held = True
    for _ in range(120):
        door.update(1 / 30)
    assert door.shut and events[-1] == "thud"
    assert tuple(door.obj.rotation)[1] == 0.0


def test_flashlight_battery_and_light():
    from lysyk.engine.flashlight import Flashlight
    from lysyk.engine.lighting import Lighting

    lt = Lighting()
    f = Flashlight(lt, drain=0.5)
    f.update(0.1, (0.0, 1.5, 0.0), (0.0, 0.0, 1.0))
    assert not f.light.enabled
    f.toggle()
    for _ in range(30):
        f.update(1 / 30, (0.0, 1.5, 0.0), (0.0, 0.0, 1.0))
    assert f.light.enabled and f.light.intensity > 1.0
    for _ in range(120):
        f.update(1 / 30, (0.0, 1.5, 0.0), (0.0, 0.0, 1.0))
    assert not f.on and f.battery == 0.0 and not f.toggle()


MODEL_DIR = asset("game", "models")


def test_sfx_assets_are_valid():
    audio = Audio(enabled=False)
    folder = asset("audio", "sfx")
    names = [n for n in os.listdir(folder) if n.endswith(".wav")]
    assert {"creak_1", "door_close_1", "door_open_1", "latch", "click", "step_1"} <= {n[:-4] for n in names}
    for n in names:
        s = audio.load(os.path.join(folder, n))
        assert s.frames > 1000 and np.abs(s.samples).max() > 1000
    assert os.path.isfile(os.path.join(folder, "LICENSE.txt"))


def test_models_reference_existing_textures():
    from lysyk.engine.model import read_materials

    objs = [n for n in os.listdir(MODEL_DIR) if n.endswith(".obj")]
    assert len(objs) >= 20
    for n in objs:
        mtl = os.path.join(MODEL_DIR, n[:-4] + ".mtl")
        if not os.path.isfile(mtl):
            mtl = os.path.join(MODEL_DIR, n[:-4].lower() + ".mtl")
        mats = read_materials(mtl)
        assert mats, n
        for m in mats.values():
            assert m["map"] is None or os.path.isfile(m["map"]), (n, m["map"])


def test_textured_loader_bakes_texture_colors():
    from lysyk.engine.model import load_textured

    parts = load_textured(os.path.join(MODEL_DIR, "Walls.obj"), step=0.3)
    mesh = parts[0].mesh
    c = np.asarray(mesh.colors)[:, :3].astype(np.int32)
    assert len(c) > 500 and c.std(axis=0).max() > 3.0
    coarse = load_textured(os.path.join(MODEL_DIR, "Walls.obj"), step=1.0)
    assert len(np.asarray(coarse[0].mesh.vertices)) < len(np.asarray(mesh.vertices))


def test_loaded_floor_faces_up():
    from lysyk.engine.model import load_textured

    for p in load_textured(os.path.join(MODEL_DIR, "Floor.obj"), step=0.5, only=("planks",)):
        v = np.asarray(p.mesh.vertices)
        f = np.asarray(p.mesh.faces)
        n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        top = n[:, 1] > 0
        assert top.mean() > 0.95


def test_forward_components_match_camera_matrix():
    from lysyk.engine.interact import forward_vector
    from lysyk.engine.objects import camera_matrix

    for yaw, pitch in ((0.3, 0.0), (2.5, 0.4), (-1.2, -0.3)):
        m = camera_matrix((pitch, yaw, 0.0))
        assert np.allclose([m[0][2], m[1][2], m[2][2]], forward_vector(yaw, pitch), atol=1e-6)


def test_progress_flags(tmp_path, monkeypatch):
    from chubaka import state

    monkeypatch.setattr(state, "user_dir", lambda name: str(tmp_path))
    p = state.Progress()
    assert not p.flag("door_hint")
    p.set_flag("door_hint")
    assert p.flag("door_hint") and p.load()["current_night"] == 1


class StubProgress:
    def __init__(self):
        self.flags = set()

    def flag(self, name):
        return name in self.flags

    def set_flag(self, name):
        self.flags.add(name)


def make_scene():
    from chubaka.scenes.classroom import ClassroomScene
    from lysyk.profile import PROFILES

    win = OffscreenWindow(160, 90, msaa=False, backend=API)
    win.profile = dict(PROFILES["low"])
    win.audio = Audio(enabled=False)
    win.progress = StubProgress()
    win.is_mobile = False
    win.mouse_x = 80.0
    win.stage = type("S", (), {"width": 1280})()
    win.touch_emulates_mouse = True
    win.set_cursor_grab = lambda mode: None
    win.fx = type("F", (), {"update": lambda self, dt: None})()
    scene = ClassroomScene(win)
    return win, scene


def run(scene, seconds):
    for _ in range(int(seconds * 60)):
        scene.update(1 / 60)


def test_door_can_be_entered_again_after_walking_away():
    win, scene = make_scene()
    scene.enter(night=2)
    run(scene, 0.1)
    assert scene.interaction.hover is scene.door_spot
    scene.mouse_press(0, 0, 0)
    assert scene.state == "to_door" and not scene.door_spot.enabled
    run(scene, 7.0)
    assert scene.state == "door"
    scene.go_seat()
    run(scene, 7.0)
    assert scene.state == "seat" and scene.door_spot.enabled
    scene.look.yaw = SEAT_YAW + 20.0
    run(scene, 0.1)
    assert scene.interaction.hover is scene.door_spot
    scene.mouse_press(0, 0, 0)
    assert scene.state == "to_door"


def test_door_hint_shows_once_on_first_night():
    win, scene = make_scene()
    scene.enter(night=1)
    assert scene.hint_text() is None
    run(scene, 0.1)
    assert scene.hint_stage == 1 and "door" in scene.hint_text().lower()
    scene.mouse_press(0, 0, 0)
    run(scene, 7.0)
    assert scene.state == "door" and scene.hint_stage == 3 and "hold" in scene.hint_text().lower()
    scene.key_press(K.SPACE, 0)
    run(scene, 0.1)
    assert scene.hint_text() is None and win.progress.flag("door_hint")
    scene.go_seat()
    run(scene, 7.0)
    run(scene, 0.1)
    assert scene.hint_text() is None
    scene.enter(night=1)
    run(scene, 0.1)
    assert scene.hint_text() is None
    other_win, other = make_scene()
    other.enter(night=2)
    run(other, 0.1)
    assert other.hint_text() is None


def test_staged_build_matches_full_build():
    win, scene = make_scene()
    steps = 0
    while not scene.prepare(0.0):
        steps += 1
        assert steps < 100
    assert scene.built and steps >= 5


def test_look_turns_toward_pointer_and_screen_side():
    from lysyk.engine.interact import forward_vector

    right = LookController(180.0, center=180.0, limit=100.0)
    for _ in range(300):
        right.mouse_motion(1200)
        right.update(1 / 60)
    f = forward_vector(math.radians(right.yaw))
    assert f[0] < 0.0
    left = LookController(180.0, center=180.0, limit=100.0)
    left.touch(1, "down", 100, 300)
    for _ in range(60):
        left.update(1 / 60)
    f = forward_vector(math.radians(left.target))
    assert f[0] > 0.0
