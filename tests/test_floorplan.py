import math

from chubaka.floorplan import DOOR_H, EDGE_DATA, FloorPlan, plan, segment_hits_rect


def test_plan_has_every_labelled_room():
    fp = plan()
    for n in range(1, 19):
        assert f"room_{n:02d}" in fp.regions
    assert "archive" in fp.regions
    assert fp.regions["room_08"].kind == "guard"


def test_removed_areas_are_gone():
    fp = plan()
    for name in ("hall", "vestibule", "block_a", "block_b", "stairs_nw", "stairs_e"):
        assert name not in fp.regions, name
    for nid in ("hall_c", "hall_w", "hall_e", "hall_back", "vestibule", "block_a", "block_b", "stairs_nw", "stairs_e"):
        assert nid not in fp.nodes, nid
    assert "stairs_w" not in fp.regions
    assert "stairs_w" not in fp.nodes
    assert len(fp.cameras) == 11
    assert not any("зал" in cam.title.lower() or "вестибюль" in cam.title.lower() for cam in fp.cameras)


def test_guard_room_matches_existing_classroom():
    x0, x1, z0, z1 = plan().regions["room_08"].rect
    assert (round(x0, 2), round(x1, 2), round(z0, 2), round(z1, 2)) == (-4.8, 4.8, -3.4, 3.4)


def test_every_edge_is_walkable_and_reachable():
    fp = plan()
    for a, b in EDGE_DATA:
        assert fp.line_of_sight(fp.node_position(a), fp.node_position(b)), (a, b)
    reach = fp.distance_map("office_door")
    assert set(reach) == set(fp.nodes)


def test_every_node_is_inside_a_region():
    fp = plan()
    for nid in fp.nodes:
        assert fp.node_region[nid] is not None, nid


def test_walls_do_not_intrude_into_rooms():
    fp = plan()
    for rect, owner in fp.slabs:
        for region in fp.regions.values():
            if region.external or region.name == owner:
                continue
            x0, x1, z0, z1 = rect
            rx0, rx1, rz0, rz1 = region.rect
            assert min(x1, rx1) - max(x0, rx0) < 0.02 or min(z1, rz1) - max(z0, rz0) < 0.02, (owner, region.name)


def test_walls_block_sight():
    fp = plan()
    a, b = fp.node_position("room_06"), fp.node_position("room_07")
    assert not fp.line_of_sight(a, b)


def test_cameras_each_see_something():
    fp = plan()
    assert len(fp.cameras) >= 10
    for cam in fp.cameras:
        if cam.audio_only:
            continue
        assert any(fp.camera_sees(cam, n.position) for n in fp.nodes.values()), cam.title


def test_camera_yaw_points_along_compass():
    fp = plan()
    assert round(fp.cameras[0].yaw) == 270
    assert round(fp.cameras[1].yaw) == 90
    assert round(fp.cameras[2].yaw) == 180


def test_door_height_fits_under_ceiling():
    assert DOOR_H < 3.2


def test_segment_hits_rect():
    assert segment_hits_rect((0, 0), (2, 2), (0.5, 1.5, 0.5, 1.5))
    assert not segment_hits_rect((0, 0), (2, 0), (0.5, 1.5, 0.5, 1.5))


def test_path_ends_at_goal():
    fp = plan()
    route = fp.path("w_exit", "office_door")
    assert route[0] == "w_exit" and route[-1] == "office_door"
    for a, b in zip(route, route[1:]):
        assert b in fp.neighbors(a)


def test_fresh_plan_is_deterministic():
    a, b = FloorPlan(), FloorPlan()
    assert len(a.slabs) == len(b.slabs) and math.isclose(a.bounds()[0], b.bounds()[0])


def test_camera_forward_matches_heading():
    fp = plan()
    forward = {cam.label: cam.forward for cam in fp.cameras}
    assert forward["1A"][0] < -0.99 and abs(forward["1A"][1]) < 1e-6
    assert forward["1B"][0] > 0.99
    assert forward["2A"][1] < -0.99
    assert forward["2B"][1] > 0.99
    assert forward["5A"][0] > 0.99 and forward["5B"][0] < -0.99
    for cam in fp.cameras:
        assert math.isclose(math.hypot(*cam.forward), 1.0)


def test_world_is_not_mirrored():
    fp = plan()
    assert fp.guard_door[0] > 0.0 and fp.guard_door[1] > fp.guard_door[0]
    assert fp.regions["room_07"].e1 < fp.regions["room_08"].e0
    assert fp.regions["room_09"].e0 > fp.regions["room_08"].e1
    assert fp.regions["room_06"].e0 < fp.regions["room_10"].e0
    assert fp.cameras[0].e > fp.cameras[1].e
    assert fp.node_position("room_12")[0] > 0.0
    assert fp.node_position("room_05")[0] < 0.0


def test_central_hall_has_four_columns_and_two_toilets():
    fp = plan()
    assert len(fp.columns) == 4
    lobby = fp.regions["lobby"]
    for e0, e1, n0, n1 in fp.columns:
        assert lobby.e0 < e0 < e1 < lobby.e1 and lobby.n0 < n0 < n1 < lobby.n1
    assert fp.regions["toilet_w"].kind == fp.regions["toilet_e"].kind == "toilet"
    assert fp.line_of_sight(fp.node_position("lob_n"), fp.node_position("ch_s"))


def test_columns_block_sight():
    fp = plan()
    e0, e1, n0, n1 = fp.columns[0]
    a = ((e0 + e1) / 2 - 3.0, 0.0, (n0 + n1) / 2)
    b = ((e0 + e1) / 2 + 3.0, 0.0, (n0 + n1) / 2)
    assert not fp.line_of_sight(a, b)


def test_audio_camera_hears_but_never_sees():
    fp = plan()
    cams = [c for c in fp.cameras if c.audio_only]
    assert len(cams) == 1
    cam = cams[0]
    assert cam.zone in fp.regions and fp.regions[cam.zone].kind == "toilet"
    assert fp.regions[cam.zone].contains(cam.position[0], cam.position[2])
    assert not any(fp.camera_sees(cam, n.position) for n in fp.nodes.values())


def test_visible_walls_stay_behind_guard_room_surface():
    fp = plan()
    for rect, owner in fp.visible_slabs():
        x0, x1, z0, z1 = rect
        assert min(x1, 4.8) - max(x0, -4.8) < 0.0199 or min(z1, 3.4) - max(z0, -3.4) < 0.0199, owner


def test_ray_distance_stops_at_walls():
    fp = plan()
    cam = fp.cameras[7]
    cx, _, cz = cam.position
    fx, fz = cam.forward
    reach = fp.ray_distance(cx, cz, fx, fz, 80.0)
    assert 20.0 < reach < 35.0
    assert fp.ray_distance(cx, cz, -fx, -fz, 80.0) < 6.0


def test_every_camera_has_a_visible_cone():
    fp = plan()
    for cam in fp.cameras:
        if cam.audio_only:
            continue
        cx, _, cz = cam.position
        fx, fz = cam.forward
        assert fp.ray_distance(cx, cz, fx, fz, 34.0) > 3.0, cam.label
