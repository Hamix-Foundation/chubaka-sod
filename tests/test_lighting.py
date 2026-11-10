import numpy as np
import pytest

from lysyk.engine.lighting import Lighting, PointLight
from tests.reference import lighting as ref


@pytest.mark.parametrize("hour", [0.0, 3.3, 6.0, 7.2, 12.0, 17.9, 19.0, 21.6, 23.9])
def test_sky_matches_reference(hour):
    a, b = Lighting(), ref.Lighting()
    for lt in (a, b):
        lt.sky_tint = (0.9, 1.0, 1.1)
        lt.fog_tint = (1.0, 0.8, 0.9)
        lt.set_hour(hour)
    assert a.elevation == pytest.approx(b.elevation)
    assert a.night_factor == pytest.approx(b.night_factor)
    np.testing.assert_allclose(a.sun_direction(), b.sun_direction(), atol=1e-12)
    assert tuple(a.clear_color()) == tuple(b.clear_color())
    ca, cb = a.colors(), b.colors()
    for key in ca:
        np.testing.assert_allclose(np.asarray(ca[key], float), np.asarray(cb[key], float), atol=1e-9)


def test_manual_sky():
    a = Lighting()
    a.set_manual((10, 20, 30), (40, 50, 60), (70, 80, 90), (1, 1, 1), 1.0, (0.3, 0.3, 0.3), (0.1, 0.1, 0.1), 30.0, 100.0)
    assert a.manual and a.night_factor == 0.0
    a.set_hour(5.0)
    assert not a.manual


def test_light_gathering():
    lt = Lighting()
    near = lt.add_light(PointLight((0, 1, 0), (1, 0, 0), 2.0, 20.0))
    near.position[:] = (3, 3, 3)
    assert tuple(near.position) == (3, 3, 3)
    off = lt.add_light(PointLight((1, 1, 1)))
    off.enabled = False
    spot = lt.add_light(PointLight((0, 0, 0), (1, 1, 1), 1.0, 30.0, (0, -1, 0), 0.7))
    got = lt.gather((0, 0, 0))
    assert len(got) == 2 and got[1][4] is not None
    pts = np.array([[i * 10.0, 0, 0] for i in range(40)])
    lt.set_static(pts, (1, 1, 1), 1.0, 30.0)
    got = lt.gather((0, 0, 0))
    assert len(got) == 8
    lt.static_enabled = False
    assert len(lt.gather((0, 0, 0))) == 2
    lt.remove_light(near)
    assert len(lt.lights) == 2
    lt.clear_lights()
    assert len(lt.lights) == 0
