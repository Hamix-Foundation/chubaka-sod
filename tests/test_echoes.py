import random

from chubaka.echoes import ROSTER, Echo, EchoContext, EchoSpec, PlayerView, by_id
from chubaka.echoes.traits import CameraFreeze, FlashlightShy, LightEater
from chubaka.floorplan import plan


def make(spec, night=1):
    fp = plan()
    rng = random.Random(5)
    return Echo(spec, fp, rng, night), EchoContext(fp, rng)


def view(**kwargs):
    v = PlayerView()
    v.position = (4.4, 1.2, -0.5)
    for k, val in kwargs.items():
        setattr(v, k, val)
    return v


def test_roster_has_unique_ids_with_valid_start_nodes():
    fp = plan()
    ids = [s.id for s in ROSTER]
    assert len(ids) == len(set(ids)) >= 4
    for s in ROSTER:
        assert s.start in fp.nodes and s.goal in fp.nodes
        assert by_id(s.id) is s


def test_echo_walks_to_the_door_and_attacks_when_it_is_open():
    spec = EchoSpec(id="t", name="t", start="te_far", ai=20.0, interval=(0.1, 0.1), directness=1.0, door_wait=1.0)
    echo, ctx = make(spec)
    v = view(door_open=1.0)
    for _ in range(60 * 40):
        ctx.begin(v, 1 / 60)
        echo.update(1 / 60, ctx)
        if ctx.attackers:
            break
    assert echo.node == "office_door" and ctx.attackers == [echo]


def test_closed_door_makes_echo_retreat():
    spec = EchoSpec(id="t", name="t", start="office_door", give_up=2.0, door_wait=2.0)
    echo, ctx = make(spec)
    v = view(door_open=0.0)
    for _ in range(60 * 6):
        ctx.begin(v, 1 / 60)
        echo.update(1 / 60, ctx)
    assert not ctx.attackers
    assert echo.moving or echo.node != "office_door"


def test_flashlight_shy_flees():
    spec = EchoSpec(id="t", name="t", start="te_near", traits=(FlashlightShy(tolerance=0.1, steps=2, stun=2.0),), ai=0.0)
    echo, ctx = make(spec)
    echo.history = ["te_far", "te_mid", "te_near"]
    x, _, z = echo.position
    v = view(position=(x + 3.0, 1.2, z), flashlight_on=True, flashlight_dir=(-1.0, 0.0), flashlight_cone=0.5)
    for _ in range(30):
        ctx.begin(v, 1 / 60)
        echo.update(1 / 60, ctx)
    assert echo.moving or echo.node != "te_near"


def test_camera_freeze_blocks_movement_while_watched():
    fp = plan()
    spec = EchoSpec(id="t", name="t", start="te_near", ai=20.0, interval=(0.1, 0.1), traits=(CameraFreeze(include_player=False),))
    echo, ctx = make(spec)
    v = view(camera=fp.cameras[0])
    ctx.begin(v, 0.0)
    assert ctx.on_camera(echo)
    for _ in range(120):
        ctx.begin(v, 1 / 60)
        echo.update(1 / 60, ctx)
    assert echo.node == "te_near"


def test_light_eater_drains_battery():
    spec = EchoSpec(id="t", name="t", start="te_near", traits=(LightEater(radius=50.0, rate=0.1),))
    echo, ctx = make(spec)
    ctx.begin(view(flashlight_on=True), 1.0)
    echo.update(1.0, ctx)
    assert ctx.drain > 0.09


def test_ai_scales_with_night():
    spec = EchoSpec(id="t", name="t", start="room_06", ai=4.0, ai_per_night=2.0)
    assert make(spec, 1)[0].ai == 4.0
    assert make(spec, 4)[0].ai == 10.0


def test_audio_camera_hears_an_echo_in_its_room():
    from chubaka.echoes import EchoManager

    fp = plan()
    camera = next(c for c in fp.cameras if c.audio_only)
    manager = EchoManager(fp)
    manager.reset(1, specs=[EchoSpec(id="t", name="t", start=camera.zone, ai=0.0)])
    v = view(camera=camera, state="laptop")
    heard = []
    peak = 0.0
    for _ in range(60 * 8):
        manager.update(1 / 60, v)
        heard += [name for name, volume in manager.sounds]
        peak = max(peak, manager.audio_level)
    assert "creak" in heard and peak > 0.3


def test_other_cameras_hear_nothing():
    from chubaka.echoes import EchoManager

    fp = plan()
    manager = EchoManager(fp)
    manager.reset(1, specs=[EchoSpec(id="t", name="t", start="toilet_e", ai=0.0)])
    v = view(camera=fp.cameras[0], state="laptop")
    for _ in range(60 * 8):
        manager.update(1 / 60, v)
        assert not manager.sounds
    assert manager.audio_level == 0.0
