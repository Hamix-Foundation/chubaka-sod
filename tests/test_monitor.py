import numpy as np

from chubaka.floorplan import plan
from chubaka.monitor import MAP_BOX, PANEL, CameraMonitor


def test_cone_covers_the_view_and_stops_behind_the_camera():
    fp = plan()
    monitor = CameraMonitor("uk", fp)
    for index, cam in enumerate(fp.cameras):
        pixels = monitor.cone_array(index)
        assert pixels.shape == (MAP_BOX[3], MAP_BOX[2], 4)
        assert pixels.dtype == np.uint8
        assert int((pixels[..., 3] > 0).sum()) > 200, cam.label
        if cam.audio_only:
            continue
        mx, my = monitor.marker_center(cam)
        fx, fz = cam.forward
        bx = int(mx - MAP_BOX[0] - fx * 14.0)
        by = int(my - MAP_BOX[1] + fz * 14.0)
        if 0 <= bx < MAP_BOX[2] and 0 <= by < MAP_BOX[3]:
            assert pixels[by, bx, 3] == 0, cam.label


def test_cone_points_the_way_the_camera_looks():
    fp = plan()
    monitor = CameraMonitor("uk", fp)
    for index, cam in enumerate(fp.cameras):
        if cam.audio_only:
            continue
        pixels = monitor.cone_array(index)
        mx, my = monitor.marker_center(cam)
        fx, fz = cam.forward
        ahead = int(my - MAP_BOX[1] - fz * 30.0), int(mx - MAP_BOX[0] + fx * 30.0)
        behind = int(my - MAP_BOX[1] + fz * 30.0), int(mx - MAP_BOX[0] - fx * 30.0)
        a = pixels[ahead[0], ahead[1], 3] if 0 <= ahead[0] < MAP_BOX[3] and 0 <= ahead[1] < MAP_BOX[2] else 0
        b = pixels[behind[0], behind[1], 3] if 0 <= behind[0] < MAP_BOX[3] and 0 <= behind[1] < MAP_BOX[2] else 0
        assert a >= b, cam.label


def test_map_is_not_mirrored():
    monitor = CameraMonitor("uk", plan())
    west = monitor.map_point(-20.0, -10.0)[0]
    east = monitor.map_point(20.0, -10.0)[0]
    north = monitor.map_point(0.0, 0.0)[1]
    south = monitor.map_point(0.0, -30.0)[1]
    assert west < east and north < south


def test_cone_is_cached():
    monitor = CameraMonitor("uk", plan())
    assert monitor.cone_array(0) is monitor.cone_array(0)


def test_select_prepares_the_cone():
    monitor = CameraMonitor("uk", plan())
    monitor.select(3)
    assert 3 in monitor.cone_data


def test_audio_camera_marks_its_room_not_a_view():
    fp = plan()
    monitor = CameraMonitor("uk", fp)
    index = next(i for i, c in enumerate(fp.cameras) if c.audio_only)
    pixels = monitor.cone_array(index)
    zone = fp.regions[fp.cameras[index].zone]
    x, y, w, h = monitor.region_rect(zone)
    cx, cy = int(x + w / 2 - MAP_BOX[0]), int(y + h / 2 - MAP_BOX[1])
    assert pixels[cy, cx, 3] > 0


def test_markers_are_selectable_and_do_not_overlap():
    fp = plan()
    monitor = CameraMonitor("uk", fp)
    centers = [monitor.marker_center(c) for c in fp.cameras]
    for i, a in enumerate(centers):
        assert monitor.marker_at(*a) == i
        for b in centers[i + 1:]:
            assert ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 > 26.0


def test_panel_buttons_switch_cameras():
    monitor = CameraMonitor("uk", plan())
    px, py, pw, ph = PANEL
    monitor.press(px + 20, py + 20)
    monitor.release(px + 20, py + 20)
    assert monitor.index == len(monitor.plan.cameras) - 1
    monitor.press(px + pw - 20, py + 20)
    monitor.release(px + pw - 20, py + 20)
    assert monitor.index == 0


def test_pointer_layer_covers_every_video_camera():
    fp = plan()
    monitor = CameraMonitor("uk", fp)
    pixels = monitor.pointer_array()
    assert pixels.shape == (MAP_BOX[3], MAP_BOX[2], 4)
    assert int((pixels[..., 3] > 0).sum()) > 100
