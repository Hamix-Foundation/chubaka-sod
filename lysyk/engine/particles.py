from lysyk.engine._native import MeshBuilder, ParticlePool

_meshes = {}


def puff_mesh():
    if "puff" not in _meshes:
        b = MeshBuilder()
        b.ellipsoid((0, 0, 0), (1, 1, 1), (255, 255, 255), paint=1.0, rings=3, segments=7)
        _meshes["puff"] = b.build()
    return _meshes["puff"]


def spark_mesh():
    if "spark" not in _meshes:
        b = MeshBuilder()
        b.box((0, 0, 0), (1, 1, 1), (255, 255, 255), paint=1.0)
        _meshes["spark"] = b.build()
    return _meshes["spark"]


__all__ = ["ParticlePool", "puff_mesh", "spark_mesh"]
