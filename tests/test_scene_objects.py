import numpy as np

from lysyk.engine import store
from lysyk.engine.mesh import MeshBuilder
from lysyk.engine.objects import MODE_GLOW, Camera, GameObject, camera_matrix, euler_from_matrix, rot_x, rot_y, rot_z
from lysyk.engine.particles import ParticlePool, puff_mesh
from lysyk.engine.scene import Scene
from tests.reference import objects as ref_objects


def cube():
    b = MeshBuilder()
    b.box((0, 0, 0), (1, 1, 1), (200, 200, 200))
    return b.build()


def test_object_views_write_through():
    o = GameObject(cube(), (10, 20, 30), position=(1, 2, 3), scale=(2, 2, 2), cast=True, gloss=0.5)
    assert tuple(o.position) == (1, 2, 3)
    o.position[1] = 9.0
    assert store.data[o.slot, 1] == 9.0
    o.place(4, 5, 6, 0.1, 0.2)
    np.testing.assert_allclose(o.rotation, (0.1, 0.2, 0.0), atol=1e-6)
    assert o.color == (10, 20, 30)
    o.color = (1, 2, 3)
    assert o.color == (1, 2, 3)
    assert abs(o.gloss - 0.5) < 0.01
    o.gloss = 0.0
    assert o.gloss == 0.0 and o.color == (1, 2, 3)
    assert o.cast and o.visible
    o.visible = False
    assert store.data[o.slot, 11] == 0.0
    o.mode = MODE_GLOW
    assert o.mode == MODE_GLOW


def test_slots_are_recycled():
    before = store.live()
    objs = [GameObject(cube()) for _ in range(50)]
    assert store.live() == before + 50
    del objs
    assert store.live() == before


def test_scene_bookkeeping():
    scene = Scene()
    m = cube()
    objs = [GameObject(m) for _ in range(5)]
    scene.extend(objs)
    assert scene.count == 5
    scene.remove(objs[0])
    assert scene.count == 4
    scene.remove_many(objs[1:3])
    assert scene.count == 2
    scene.add(GameObject(None))
    assert scene.count == 2
    scene.clear()
    assert scene.count == 0


def test_matrix_helpers_match_reference():
    for a in (0.3, -1.2, 2.5):
        np.testing.assert_allclose(rot_x(a), ref_objects.rot_x(a))
        np.testing.assert_allclose(rot_y(a), ref_objects.rot_y(a))
        np.testing.assert_allclose(rot_z(a), ref_objects.rot_z(a))
    r = (0.4, -0.8, 0.1)
    np.testing.assert_allclose(camera_matrix(r), ref_objects.camera_matrix(np.array(r)))
    m = rot_y(0.7) @ rot_x(-0.3) @ rot_z(0.2)
    np.testing.assert_allclose(euler_from_matrix(m), ref_objects.euler_from_matrix(m), atol=1e-12)


def test_set_matrix():
    o = GameObject(cube())
    m = rot_y(0.5) @ rot_x(0.2)
    o.set_matrix(m, (1.0, 2.0, 3.0))
    np.testing.assert_allclose(o.position, (1, 2, 3))
    np.testing.assert_allclose(o.rotation, euler_from_matrix(m), atol=1e-6)


def test_camera_inplace_and_look_at():
    c = Camera(fov=60.0)
    c.position[0] = 5.0
    assert c.position[0] == 5.0
    c.position = (1, 2, 3)
    assert tuple(c.position) == (1, 2, 3)
    c.position = (0, 0, 0)
    c.look_at(0, 0, 10)
    np.testing.assert_allclose(c.rotation, (0, 0, 0), atol=1e-9)
    c.look_at(10, 0, 0)
    assert abs(c.rotation[1] - np.pi / 2) < 1e-9
    assert c.fov == 60.0


def test_particles_lifecycle():
    scene = Scene()
    pool = ParticlePool(scene, puff_mesh(), 20, gravity=1.0, drag=0.5, grow=1.0)
    assert scene.count == 20 and pool.alive == 0
    pool.emit(np.array([[0, 0, 0], [1, 1, 1]]), np.array([0.0, 1.0, 0.0]), 1.0, 0.5, (255, 0, 0), (0, 0, 255))
    assert pool.alive == 2
    pool.update(0.5)
    visible = [o for o in pool.objects if o.visible]
    assert len(visible) == 2
    assert visible[0].position[1] != 0.0
    pool.update(1.0)
    assert not any(o.visible for o in pool.objects)
    pool.emit((0, 0, 0), (0, 0, 0), 1.0, 1.0, (1, 2, 3))
    pool.clear()
    assert pool.alive == 0
    pool.destroy()
    assert scene.count == 0
