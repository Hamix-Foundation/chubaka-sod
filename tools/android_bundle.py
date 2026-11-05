import argparse
import os
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo", "lib2to3", "ensurepip", "pydoc_data", "distutils", "venv", "target", "jnius", "android", "config-3.13-aarch64-linux-android"}
SKIP_SUFFIX = (".pyc", ".pyo", ".a", ".import", ".md", ".txt~")
SKIP_NAMES = {"_native.abi3.so"}


def walk(base, prefix, tar, extra_skip=()):
    count = 0
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and d not in extra_skip)
        for name in sorted(files):
            if name.endswith(SKIP_SUFFIX) or name in SKIP_NAMES:
                continue
            path = os.path.join(folder, name)
            arc = os.path.join(prefix, os.path.relpath(path, base)).replace(os.sep, "/")
            tar.add(path, arcname=arc, recursive=False)
            count += 1
    return count


def find_stdlib(prefix):
    lib = os.path.join(prefix, "lib")
    for name in sorted(os.listdir(lib)):
        if name.startswith("python3.") and os.path.isdir(os.path.join(lib, name)):
            return name, os.path.join(lib, name)
    raise SystemExit(f"no pythonX.Y directory in {lib}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pack the Python runtime and the game into the Android bundle")
    ap.add_argument("--python-prefix", required=True)
    ap.add_argument("--site-packages", default=None)
    ap.add_argument("--out", default=os.path.join(ROOT, "android", "app", "src", "main", "assets", "bundle.tar"))
    a = ap.parse_args(argv)
    version, stdlib = find_stdlib(a.python_prefix)
    site_packages = a.site_packages or os.path.join(stdlib, "site-packages")
    if not os.path.isdir(os.path.join(site_packages, "numpy")):
        raise SystemExit(f"NumPy for Android is missing from {site_packages}; set ANDROID_SITE_PACKAGES to its site-packages directory")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with tarfile.open(a.out, "w", format=tarfile.GNU_FORMAT) as tar:
        total = walk(stdlib, f"py/lib/{version}", tar, extra_skip=("site-packages",))
        if a.site_packages:
            total += walk(a.site_packages, f"py/lib/{version}/site-packages", tar)
        else:
            total += walk(site_packages, f"py/lib/{version}/site-packages", tar)
        total += walk(os.path.join(ROOT, "lysyk"), "app/lysyk", tar)
        total += walk(os.path.join(ROOT, "chubaka"), "app/chubaka", tar)
        total += walk(os.path.join(ROOT, "assets"), "app/assets", tar)
    size = os.path.getsize(a.out) / 1048576.0
    print(f"{total} files, {size:.1f} MiB -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
