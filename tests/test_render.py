import numpy as np
import pytest

from lysyk.engine import _native
from lysyk.engine.lighting import Lighting, PointLight
from lysyk.engine.mesh import MeshBuilder
from lysyk.engine.objects import MODE_SKY, Camera, GameObject
from lysyk.engine.renderer import Renderer
from lysyk.engine.scene import Scene
from lysyk.engine.window import OffscreenWindow

APIS = [a for a in ("vulkan", "gl") if a in _native.compiled_backends() and _native.enumerate_adapters(a)]


def make_world():
    g = MeshBuilder()
    g.box((0, -0.5, 0), (80, 1, 80), (90, 150, 80), paint=0.0)
    ground = g.build()
    c = MeshBuilder()
    c.box((0, 1, 0), (2, 2, 2), (220, 60, 50), paint=1.0)
    cube = c.build()
    s = MeshBuilder()
    s.ellipsoid((0, 0, 0), (1, 1, 1), (255, 255, 255), rings=6, segments=12, inside=True)
    sky = s.build()
    scene = Scene()
    scene.add(GameObject(ground))
    scene.add(GameObject(cube, (220, 60, 50), position=(0, 0, 8), cast=True, gloss=0.4))
    scene.add(GameObject(cube, (60, 80, 220), position=(5, 0, 12), rotation=(0, 0.6, 0), cast=True))
    scene.add(GameObject(sky, (255, 255, 255), scale=(900, 900, 900), mode=MODE_SKY))
    return scene


def render(api, msaa=True, shadows=True, size=(320, 200)):
    win = OffscreenWindow(*size, msaa=msaa, backend=api)
    lt = Lighting()
    lt.shadows = shadows
    lt.set_hour(14.0)
    lt.add_light(PointLight((2, 3, 6), (1, 0.8, 0.5), 2.0, 20.0))
    r = Renderer(win, lt)
    cam = Camera()
    cam.position = (0, 4, -6)
    cam.look_at(0, 1, 8)
    scene = make_world()

    def draw():
        win.clear(lt.clear_color())
        r.render(cam, scene)
        win.canvas.rect(10, 10, 60, 20, (255, 255, 255, 200), 4)
        win.canvas.text("Hello", 80, 12, (255, 255, 0), 14)

    win.frame(draw)
    return win.read_pixels(), r, win


@pytest.mark.parametrize("api", APIS)
def test_scene_renders(api):
    px, r, win = render(api)
    assert px.shape == (200, 320, 4)
    assert len(np.unique(px.reshape(-1, 4), axis=0)) > 50
    assert px[..., 3].min() == 255
    stats = r.stats
    assert stats["visible"] == 4 and stats["draws"] >= 2 and stats["shadow_draws"] >= 1
    assert px[15, 20, 0] > 200
    assert win.api.lower() == {"vulkan": "vulkan", "gl": "opengl"}[api]


@pytest.mark.parametrize("api", APIS)
def test_msaa_toggle_and_shadows_change_image(api):
    a, _, _ = render(api, msaa=True, shadows=True)
    b, _, _ = render(api, msaa=False, shadows=True)
    c, _, _ = render(api, msaa=True, shadows=False)
    assert np.abs(a.astype(int) - b.astype(int)).sum() > 0
    assert np.abs(a.astype(int) - c.astype(int)).sum() > 0


@pytest.mark.skipif(len(APIS) < 2, reason="needs both Vulkan and OpenGL")
def test_vulkan_and_gl_agree():
    a, _, _ = render("vulkan", msaa=False)
    b, _, _ = render("gl", msaa=False)
    diff = np.abs(a.astype(int) - b.astype(int)).mean()
    assert diff < 6.0, diff


@pytest.mark.parametrize("api", APIS)
def test_text_is_drawn(api):
    win = OffscreenWindow(200, 60, msaa=False, backend=api)
    cv = win.canvas
    w = cv.text_width("Hello", 14)
    assert w > 20

    def draw():
        win.clear((0, 0, 0))
        cv.text("Hello", 5, 5, (255, 255, 255), 14)

    win.frame(draw)
    px = win.read_pixels()
    assert px[..., :3].max() > 200 and px[..., :3].sum() > 5000


def test_png_roundtrip(tmp_path):
    arr = (np.random.default_rng(0).integers(0, 255, (9, 7, 4))).astype(np.uint8)
    _native.save_png(str(tmp_path / "a.png"), arr)
    np.testing.assert_array_equal(_native.read_png(str(tmp_path / "a.png")), arr)


@pytest.mark.parametrize("api", APIS)
def test_shader_hot_reload(api, tmp_path):
    win = OffscreenWindow(64, 64, msaa=False, backend=api)
    r = Renderer(win, Lighting())
    for name, text in _native.shader_sources():
        (tmp_path / name).write_text(text)
    r.watch_shaders(str(tmp_path))
    assert r.shader_error is None and r.stats["shader_reloads"] == 1
    (tmp_path / "main.wgsl").write_text("this is not wgsl")
    r.reload_shaders()
    assert r.shader_error
    assert r.stats["shader_reloads"] == 1
    (tmp_path / "main.wgsl").write_text(dict(_native.shader_sources())["main.wgsl"])
    r.reload_shaders()
    assert r.shader_error is None and r.stats["shader_reloads"] == 2
