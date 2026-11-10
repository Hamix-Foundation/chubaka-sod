from chubaka.echoes.base import EchoSpec, JumpscareSpec
from chubaka.echoes.traits import (
    CameraFreeze, DoorBreaker, FlashlightShy, Footsteps, LightEater, Patient, Shadowed, Sprinter, Stalker, Unrecorded,
)

GROUP_NAME = "Відлуння"

ROSTER = []


def register(spec):
    ROSTER.append(spec)
    return spec


def by_id(echo_id):
    for spec in ROSTER:
        if spec.id == echo_id:
            return spec
    return None


register(EchoSpec(
    id="lilia", name="Лілія", start="room_06", shape="child", color=(150, 150, 170), eyes=(120, 200, 255),
    ai=5.0, interval=(4.0, 7.0), walk_speed=1.3, traits=(FlashlightShy(tolerance=0.2, steps=3, stun=5.0),),
    jumpscare=JumpscareSpec(video="video/jumpscares/lilia.lyv", duration=1.5),
))

register(EchoSpec(
    id="starosta", name="Староста", start="room_10", shape="tall", color=(80, 90, 70), eyes=(255, 210, 80),
    ai=6.0, interval=(5.0, 9.0), walk_speed=1.6, traits=(CameraFreeze(include_player=True, rush=1.5),),
    jumpscare=JumpscareSpec(video="video/jumpscares/starosta.lyv", duration=1.5),
))

register(EchoSpec(
    id="dzvinok", name="Дзвінок", start="w_exit", shape="wide", color=(110, 70, 60), eyes=(255, 90, 40),
    ai=4.0, interval=(6.0, 10.0), walk_speed=1.6, directness=0.7,
    traits=(Sprinter(1.8), Footsteps(), DoorBreaker(1.6)),
    jumpscare=JumpscareSpec(video="video/jumpscares/dzvinok.lyv", duration=1.5, shake=1.6),
))

register(EchoSpec(
    id="tin", name="Тінь", start="room_02", shape="hunched", color=(30, 34, 44), eyes=(255, 255, 255),
    ai=5.0, interval=(5.0, 8.0), walk_speed=1.2, traits=(LightEater(radius=9.0, rate=0.05), Stalker(), Shadowed()),
    jumpscare=JumpscareSpec(video="video/jumpscares/tin.lyv", duration=1.5),
))

register(EchoSpec(
    id="movchun", name="Мовчун", start="toilet_e", shape="wraith", color=(120, 120, 112), eyes=(80, 255, 140),
    ai=5.0, interval=(5.0, 9.0), walk_speed=1.4, directness=0.6, traits=(Unrecorded(), Footsteps(volume=0.3), Patient(2.5)),
    jumpscare=JumpscareSpec(video="video/jumpscares/movchun.lyv", duration=1.5),
))


def active_for_night(night):
    count = min(len(ROSTER), 2 + max(0, night - 1))
    return ROSTER[:count]
