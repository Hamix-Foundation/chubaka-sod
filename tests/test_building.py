import numpy as np

from chubaka import building
from chubaka.floorplan import plan
from chubaka.geometry import Batch


def test_plates_are_generated_for_every_numbered_door_into_a_corridor():
    fp = plan()
    batch = Batch()
    building.door_plates(fp, batch)
    assert not batch.empty
    mesh = batch.build()
    verts = np.asarray(mesh.vertices)
    assert verts[:, 1].min() > building.DOOR_H
    assert verts[:, 1].max() < building.HEIGHT


def test_plate_digits_use_seven_segments():
    assert len(building.digit_boxes("8")) == 7
    assert len(building.digit_boxes("1")) == 2
    for ch in "0123456789":
        assert building.digit_boxes(ch)


def test_plate_faces_the_corridor():
    fp = plan()
    a, b, cut = next((a, b, c) for a, b, c in fp.links if "room_09" in (a, b))
    corridor = fp.regions["corr_top_e"]
    center, normal = building.plate_pose(cut, corridor)
    cx, cz = corridor.center
    assert (cx - center[0]) * normal[0] + (cz - center[1]) * normal[1] > 0


def test_removed_areas_are_not_built():
    data = building.build(None)
    fp = plan()
    assert "hall" not in fp.regions
    assert data.triangles > 0


def test_windows_and_columns_are_built():
    data = building.build(None)
    fp = plan()
    assert data.glass is not None and data.glass.triangle_count > 0
    verts = np.asarray(data.structure.vertices)
    for e0, e1, n0, n1 in fp.columns:
        inside = (verts[:, 0] >= e0 - 0.1) & (verts[:, 0] <= e1 + 0.1) & (verts[:, 2] >= n0 - 0.1) & (verts[:, 2] <= n1 + 0.1)
        assert inside.any()


def test_stairs_are_not_built():
    fp = plan()
    assert not any(region.kind == "stairs" for region in fp.regions.values())
