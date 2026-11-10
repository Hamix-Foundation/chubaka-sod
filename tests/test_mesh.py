import numpy as np
import pytest

from lysyk.engine.mesh import Mesh, MeshBuilder, TiledBuilder
from tests.reference import mesh as ref


def same(native, reference):
    np.testing.assert_allclose(native.vertices, reference.vertices, atol=1e-4)
    np.testing.assert_array_equal(native.faces, reference.faces)
    diff = np.abs(native.colors.astype(int) - reference.colors.astype(int))
    assert diff.max() <= 1


def both(fn):
    a, b = MeshBuilder(), ref.MeshBuilder()
    fn(a)
    fn(b)
    return a.build(), b.build()


def test_box_hull_prism():
    def build(b):
        b.box((1, 2, 3), (2, 1, 4), (200, 100, 50), paint=1.0)
        b.hull([(0, 0, 0), (2, 0, 0), (2, 0, 3), (0, 0, 3)], [(0.2, 1, 0.2), (1.8, 1.2, 0.2), (1.8, 1.4, 2.5), (0.2, 1, 2.5)], (10, 20, 30), paint=0.3)
        b.prism((5, 0, 5), (2, 4), (1, 2), 1.5, (255, 0, 128), shift=0.4, shift_x=-0.3)

    same(*both(build))


def test_transform_and_cylinder_ellipsoid():
    def build(b):
        b.begin_transform((3, 1, -2), 0.7)
        b.cylinder((0, 1, 0), 0.5, 2.0, "x", (90, 90, 90), segments=10, radius_top=0.3)
        b.cylinder((1, 0, 0), 0.5, 2.0, "y", (90, 90, 90), paint=0.5)
        b.cylinder((0, 0, 2), 0.5, 2.0, "z", (10, 90, 90), segments=7)
        b.end_transform()
        b.ellipsoid((0, 2, 0), (1, 0.5, 2), (50, 60, 70), rings=5, segments=9)
        b.ellipsoid((0, 2, 0), (1, 0.5, 2), (50, 60, 70), inside=True)

    same(*both(build))


def test_ellipsoid_jitter_uses_rng():
    def build(b):
        rng = np.random.default_rng(5)
        b.ellipsoid((0, 0, 0), (2, 2, 2), (60, 120, 60), rings=4, segments=8, jitter=0.4, rng=rng)

    same(*both(build))


def test_quads_and_heightfield():
    rng = np.random.default_rng(2)
    q = rng.uniform(-5, 5, (12, 4, 3)).astype(np.float32)
    cols = rng.integers(0, 255, (12, 3)).astype(np.float32)
    facing = rng.uniform(-1, 1, (12, 3)).astype(np.float32)
    xs = np.linspace(-10, 10, 7, dtype=np.float32)
    zs = np.linspace(-6, 6, 5, dtype=np.float32)
    h = rng.uniform(0, 3, (7, 5)).astype(np.float32)
    hc = rng.integers(0, 255, (7, 5, 3)).astype(np.float32)

    def build(b):
        b.quads(q, cols, facing, paint=0.5)
        b.quads(q, (10, 200, 30), (0, 1, 0))
        b.heightfield(xs, zs, h, hc)

    same(*both(build))


def test_add_mesh_and_instances():
    rng = np.random.default_rng(3)

    def inner(b):
        b.box((0, 0.5, 0), (1, 1, 1), (200, 200, 200), paint=1.0)
        b.box((0, 1.5, 0), (0.5, 1, 0.5), (50, 50, 50))

    ma, mb = both(inner)
    pos = rng.uniform(-30, 30, (9, 3)).astype(np.float32)
    sc = rng.uniform(0.5, 2, 9).astype(np.float32)
    sc3 = rng.uniform(0.5, 2, (9, 3)).astype(np.float32)
    tint = rng.uniform(40, 255, (9, 3)).astype(np.float32)
    yaw = rng.uniform(0, 6, 9).astype(np.float32)

    a, b = MeshBuilder(), ref.MeshBuilder()
    a.add_mesh(ma, (1, 2, 3), 0.4, 1.5, (255, 128, 64))
    b.add_mesh(mb, (1, 2, 3), 0.4, 1.5, (255, 128, 64))
    a.add_mesh(ma)
    b.add_mesh(mb)
    a.add_instances(ma, pos, sc, tint, yaw)
    b.add_instances(mb, pos, sc, tint, yaw)
    a.add_instances(ma, pos, sc3, tint)
    b.add_instances(mb, pos, sc3, tint)
    same(a.build(), b.build())


def test_tiled_builder_order_and_content():
    rng = np.random.default_rng(4)
    q = rng.uniform(-600, 600, (40, 4, 3)).astype(np.float32)
    cols = rng.integers(0, 255, (40, 3)).astype(np.float32)
    inner = MeshBuilder()
    inner.box((0, 0.5, 0), (1, 1, 1), (200, 200, 200), paint=1.0)
    inner = inner.build()
    rinner = ref.MeshBuilder()
    rinner.box((0, 0.5, 0), (1, 1, 1), (200, 200, 200), paint=1.0)
    rinner = rinner.build()
    pos = rng.uniform(-600, 600, (30, 3)).astype(np.float32)
    sc = np.ones(30, dtype=np.float32)
    tint = np.full((30, 3), 255.0, dtype=np.float32)

    ta, tb = TiledBuilder(256.0), ref.TiledBuilder(256.0)
    for t, m in ((ta, inner), (tb, rinner)):
        t.quads(q, cols, (0, 1, 0), paint=0.2)
        t.instances(m, pos, sc, tint, None, glow=True)
        t.at(10, 10).box((10, 0, 10), (1, 1, 1), (1, 2, 3))
    ra, rb = ta.build(), tb.build()
    assert [(k, g) for k, g, _ in ra] == [(k, g) for k, g, _ in rb]
    for (_, _, ma), (_, _, mb) in zip(ra, rb):
        same(ma, mb)


def test_errors():
    with pytest.raises(ValueError):
        MeshBuilder().build()
    with pytest.raises(ValueError):
        Mesh(np.zeros((3, 3), np.float32), np.zeros((2, 4), np.uint8), np.zeros((1, 3), np.uint32))
