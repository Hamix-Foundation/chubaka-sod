import numpy as np

from chubaka.echoes.art import placeholder_rgba
from lysyk.engine.sprite import Billboard, BillboardLayer, Sprite, downsample, facing_yaw, sprite_arrays


def test_transparent_cells_are_dropped():
    img = np.zeros((16, 16, 4), dtype=np.uint8)
    img[4:12, 4:12] = (200, 30, 30, 255)
    v, c, f, width = sprite_arrays(img, height=2.0, columns=16)
    assert len(v) == 4 and len(f) == 4
    assert np.allclose(width, 2.0)
    assert v[:, 1].min() >= 0.0 and v[:, 1].max() <= 2.0
    assert tuple(c[0][:3]) == (200, 30, 30)


def test_identical_rows_are_merged():
    img = np.full((32, 32, 4), 255, dtype=np.uint8)
    v, c, f, w = sprite_arrays(img, columns=32, double_sided=False)
    assert len(v) == 4 and len(f) == 2


def test_single_sided_has_half_the_faces():
    img = placeholder_rgba()
    a = sprite_arrays(img, double_sided=True)[2]
    b = sprite_arrays(img, double_sided=False)[2]
    assert len(a) == 2 * len(b)


def test_pivot_centers_horizontally():
    img = np.full((8, 8, 4), 255, dtype=np.uint8)
    v = sprite_arrays(img, height=1.0, columns=8)[0]
    assert np.isclose(v[:, 0].min(), -v[:, 0].max())


def test_downsample_premultiplies_alpha():
    img = np.zeros((2, 2, 4), dtype=np.uint8)
    img[0, 0] = (255, 0, 0, 255)
    rgb, cover = downsample(img, 1, 1)
    assert tuple(rgb[0, 0]) == (255, 0, 0) and np.isclose(cover[0, 0], 0.25)


def test_facing_yaw_points_at_target():
    assert np.isclose(facing_yaw((0, 0, 0), (0, 0, 5)), 0.0)
    assert np.isclose(facing_yaw((0, 0, 0), (5, 0, 0)), np.pi / 2)


def test_billboard_faces_target_and_layer_updates_visible_only():
    sprite = Sprite(placeholder_rgba(), 1.8, 24)
    a = Billboard(sprite, (0.0, 0.0, 0.0))
    b = Billboard(sprite, (0.0, 0.0, 0.0))
    b.visible = False
    layer = BillboardLayer()
    layer.add(a)
    layer.add(b)
    layer.face_all((4.0, 0.0, 0.0))
    assert np.isclose(a.object.rotation[1], np.pi / 2)
    assert np.isclose(b.object.rotation[1], 0.0)


def test_placeholders_are_distinct_per_shape():
    a = placeholder_rgba("child")
    b = placeholder_rgba("tall")
    assert a.shape == b.shape and not np.array_equal(a, b)
    assert a[..., 3].max() == 255
