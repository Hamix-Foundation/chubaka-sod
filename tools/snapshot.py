import argparse
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lysyk.engine import _native
from lysyk.engine.lighting import Lighting
from lysyk.engine.objects import Camera
from lysyk.engine.renderer import Renderer
from lysyk.engine.scene import Scene
from lysyk.engine.window import OffscreenWindow
from lysyk.engine.mesh import MeshBuilder
from lysyk.engine.objects import MODE_LIT, GameObject
from lysyk.engine.lighting import PointLight


def build_scene():
    scene = Scene()
    g = MeshBuilder()
    g.box((0, -0.5, 0), (60, 1, 60), (90, 120, 90), paint=0.0)
    scene.add(GameObject(g.build()))
    for i, color in enumerate([(220, 60, 50), (60, 90, 220), (230, 200, 60)]):
        b = MeshBuilder()
        b.box((0, 1, 0), (2, 2, 2), color)
        scene.add(GameObject(b.build(), color, position=(i * 5 - 5, 0, 8 + i), rotation=(0, 0.4 * i, 0), cast=True))
    return scene


def render(window, renderer, lighting, camera, scene, hour=None):
    camera.position = (0, 3.5, -4)
    camera.look_at(0, 1, 8)
    if hour is not None:
        lighting.set_hour(hour)

    def draw():
        window.clear(lighting.clear_color())
        renderer.render(camera, scene)

    window.frame(draw)
    return window.read_pixels()


def main(argv=None):
    p = argparse.ArgumentParser(description="Render a reference scene headlessly; optionally compare with golden images")
    p.add_argument("--out", default="snapshots", help="output directory")
    p.add_argument("--api", default="auto", choices=["auto", "vulkan", "gl"])
    p.add_argument("--size", default="640x360")
    p.add_argument("--no-msaa", action="store_true")
    p.add_argument("--hour", type=float, default=None)
    p.add_argument("--compare", metavar="DIR", help="compare against PNGs in DIR and fail on differences")
    p.add_argument("--tolerance", type=float, default=2.0, help="allowed mean absolute difference (0-255)")
    args = p.parse_args(argv)

    w, h = (int(v) for v in args.size.lower().split("x"))
    os.makedirs(args.out, exist_ok=True)
    window = OffscreenWindow(w, h, msaa=not args.no_msaa, backend=args.api)
    lighting = Lighting()
    renderer = Renderer(window, lighting)
    camera = Camera()
    failures = 0
    lighting.add_light(PointLight((2, 3, 4), (1, 0.8, 0.5), 2.0, 20.0))
    print(f"{window.api}: {window.gpu_info()['name']}")
    scene = build_scene()
    pixels = render(window, renderer, lighting, camera, scene, args.hour)
    path = os.path.join(args.out, "scene.png")
    _native.save_png(path, pixels)
    line = f"scene: {path}  visible={renderer.stats['visible']} draws={renderer.stats['draws']}"
    if args.compare:
        golden = os.path.join(args.compare, "scene.png")
        if os.path.exists(golden):
            ref = _native.read_png(golden)
            diff = float(np.abs(ref.astype(int) - pixels.astype(int))[..., :3].mean()) if ref.shape == pixels.shape else 255.0
            ok = diff <= args.tolerance
            failures += 0 if ok else 1
            line += f"  diff={diff:.3f} {'ok' if ok else 'FAIL'}"
        else:
            line += "  (no golden image)"
    print(line)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
