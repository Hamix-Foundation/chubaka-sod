#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/Chubaka_win32"
TARGET="x86_64-pc-windows-gnu"
PYVER="3.12"
PYFULL="3.12.10"
PYZIP="python-${PYFULL}-embed-amd64.zip"
WORK="$ROOT/build/.windows-work"

for tool in cargo rustup x86_64-w64-mingw32-gcc curl unzip zip python3; do
    command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 1; }
done

rustup target add "$TARGET"
mkdir -p "$WORK/python" "$WORK/wheels"
rm -rf "$OUT"
mkdir -p "$OUT/runtime/Lib/site-packages" "$OUT/game/chubaka" "$OUT/game/lysyk/engine" "$OUT/game/_internal"

if [[ ! -f "$WORK/$PYZIP" ]]; then
    curl -fL "https://www.python.org/ftp/python/${PYFULL}/${PYZIP}" -o "$WORK/$PYZIP"
fi
unzip -q "$WORK/$PYZIP" -d "$OUT/runtime"

# The embeddable distribution omits pip; use the host pip only to download Windows wheels.
python3 -m pip download --only-binary=:all: --platform win_amd64 --python-version "$PYVER" \
    --implementation cp --abi cp312 --dest "$WORK/wheels" 'numpy>=1.23' 'miniaudio>=1.60'
for wheel in "$WORK"/wheels/*.whl; do
    unzip -oq "$wheel" -d "$OUT/runtime/Lib/site-packages"
done

cat > "$OUT/runtime/python312._pth" <<'EOF'
python312.zip
.
Lib\site-packages
import site
EOF

LYSYK_RUSTC_VERSION="$(rustc --version)" RUSTFLAGS="${RUSTFLAGS:-} -C target-feature=+crt-static" \
    cargo build --manifest-path "$ROOT/lysyk/native/Cargo.toml" --release --target "$TARGET" \
    --no-default-features --features extension-module,abi3,backend-vulkan,backend-dx12

cp "$ROOT/lysyk/native/target/$TARGET/release/_native.dll" "$OUT/game/lysyk/engine/_native.pyd"
(cd "$ROOT" && find lysyk -type f -name '*.py' ! -path '*/__pycache__/*' -exec cp --parents '{}' "$OUT/game" \;)
(cd "$ROOT" && find chubaka -type f \( -name '*.py' -o -name '*.json' \) ! -path '*/__pycache__/*' -exec cp --parents '{}' "$OUT/game" \;)
cp "$ROOT/main.py" "$OUT/game/main.py"

# Ship game data in one opaque archive; runtime files are extracted outside the game folder.
mkdir -p "$WORK/assets/assets" "$WORK/assets/chubaka"
cp -a "$ROOT/assets/." "$WORK/assets/assets/"
cp -a "$ROOT/chubaka/assets/." "$WORK/assets/chubaka/"
rm -f "$OUT/game/_internal/content.pak"
(cd "$WORK/assets" && zip -qr "$OUT/game/_internal/content.pak" assets chubaka)

cat > "$OUT/game/run.py" <<'PY'
import hashlib
import os
from pathlib import Path
import sys
import zipfile

base = Path(__file__).resolve().parent
package = base / "_internal" / "content.pak"
try:
    import ctypes
    ctypes.windll.kernel32.SetFileAttributesW(str(base / "_internal"), 2)
    ctypes.windll.kernel32.SetFileAttributesW(str(package), 2)
except Exception:
    pass
local = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ChubakaSOD" / "content"
marker = local / ".content-sha256"
digest = hashlib.sha256(package.read_bytes()).hexdigest()
if not marker.exists() or marker.read_text(encoding="ascii") != digest:
    local.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as archive:
        root = local.resolve()
        for name in archive.namelist():
            destination = (local / name).resolve()
            if destination != root and root not in destination.parents:
                raise RuntimeError("Invalid game content archive")
        archive.extractall(local)
    marker.write_text(digest, encoding="ascii")
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(local), 2)
    except Exception:
        pass
os.environ["LYSYK_ASSETS_ROOT"] = str(local / "assets")
os.environ["CHUBAKA_ASSETS_ROOT"] = str(local / "chubaka")
sys.path.insert(0, str(base))
from chubaka.app import main
raise SystemExit(main())
PY

rustc --edition=2021 --target "$TARGET" -C target-feature=+crt-static \
    "$ROOT/tools/windows_launcher.rs" -o "$OUT/Chubaka.exe"

cat > "$OUT/README.txt" <<'EOF'
Chubaka: The Smell Of Death — Windows x64 build

Start the game with Chubaka.exe. Windows 10/11 x64 is required.
The build prefers Vulkan when available and keeps Direct3D 12 as a fallback; install current GPU drivers.
The first start unpacks game data into the hidden %LOCALAPPDATA%\ChubakaSOD\content folder.
That makes assets less visible in this game folder, but does not prevent extraction by a determined user.
EOF

rm -rf "$WORK/assets"
echo "Windows package created: $OUT"
