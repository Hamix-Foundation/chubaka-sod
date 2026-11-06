"""Profile Python and PyO3 calls while running a game or tool entry point.

Examples:
    python tools/profile_python.py --module chubaka.__main__
    python tools/profile_python.py --script tools/snapshot.py -- --size 320x180
"""

import argparse
import cProfile
import pstats
import runpy
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--module", help="Python module to run as __main__")
    target.add_argument("--script", help="Python script to run")
    parser.add_argument("--output", default="python-profile.prof", help="cProfile output file")
    parser.add_argument("--limit", type=int, default=30, help="number of entries in each summary")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments passed to the target after --")
    options = parser.parse_args(argv)

    target_args = options.args
    if target_args and target_args[0] == "--":
        target_args = target_args[1:]
    sys.argv = ([options.module] if options.module else [options.script]) + target_args

    profiler = cProfile.Profile()
    try:
        if options.module:
            profiler.runcall(runpy.run_module, options.module, run_name="__main__", alter_sys=True)
        else:
            profiler.runcall(runpy.run_path, options.script, run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise
    finally:
        profiler.dump_stats(options.output)

    stats = pstats.Stats(profiler)
    native = {
        key: value
        for key, value in stats.stats.items()
        if key[0] == "~" and value[2] > 0 and any(token in key[2].lower() for token in ("canvas", "renderer", "scene", "texture", "camera", "light", "particle", "video", "mesh"))
    }
    print(f"Profile saved to {options.output}")
    print("\nPyO3/native calls (self time):")
    if native:
        native_stats = pstats.Stats(profiler, stream=sys.stdout)
        native_stats.stats = native
        native_stats.strip_dirs().sort_stats("tottime").print_stats(options.limit)
    else:
        print("No matching PyO3 calls recorded. Keep in mind cProfile attributes native call time to callers on some Python builds.")
    print("\nPython functions:")
    stats.strip_dirs().sort_stats("tottime").print_stats(options.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
