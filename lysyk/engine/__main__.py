import argparse
import os
import sys

from lysyk.engine import _native


def _info(args):
    print(f"lysyk engine {_native.__version__}  (wgpu {_native.WGPU_VERSION}, winit {_native.WINIT_VERSION})")
    print("compiled backends:", ", ".join(_native.compiled_backends()))
    adapters = _native.enumerate_adapters(args.api)
    if not adapters:
        print("no adapters found")
        return 1
    for a in adapters:
        print(f"\n[{a['api']}] {a['name']}")
        print(f"  type: {a['adapter_type']}   driver: {a['driver']} {a['driver_info']}".rstrip())
        print(f"  max texture: {a['max_texture_2d']}   MSAA x4: {'yes' if a['msaa4'] else 'no'}")
    return 0


def _probe(args):
    ok = True
    for api in ("vulkan", "gl"):
        if api not in _native.compiled_backends():
            continue
        try:
            win = __import__("lysyk.engine.window", fromlist=["x"]).OffscreenWindow(64, 64, msaa=False, backend=api)
            info = win.gpu_info()
            print(f"{api:7s} OK   {info['name']}")
        except Exception as exc:
            ok = False
            print(f"{api:7s} FAIL {exc}")
    return 0 if ok else 1


def _dump(args):
    os.makedirs(args.directory, exist_ok=True)
    for name, text in _native.shader_sources():
        with open(os.path.join(args.directory, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"shaders written to {args.directory}")
    print(f"run the game with LYSYK_SHADERS={args.directory} to hot-reload edits (F3 shows compile errors)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m lysyk.engine", description="Lysyk engine developer tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info", help="list graphics adapters per API")
    s.add_argument("--api", default="auto", choices=["auto", "vulkan", "gl"])
    s.set_defaults(fn=_info)
    s = sub.add_parser("probe", help="try to create a device on every compiled API")
    s.set_defaults(fn=_probe)
    s = sub.add_parser("dump-shaders", help="write the built-in WGSL shaders to a directory for hot-reload editing")
    s.add_argument("directory")
    s.set_defaults(fn=_dump)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
