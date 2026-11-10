#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-release}"
case "$MODE" in
    debug|release) ;;
    *) printf 'Usage: %s [debug|release]\n' "$0" >&2; exit 2 ;;
esac

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
APP="$HERE/app/src/main"
NATIVE_DIR="$ROOT/lysyk/native"
ABI="arm64-v8a"
NDK_VERSION="27.2.12479018"
ANDROID_API="35"

fail() {
    printf 'Android build: %s\n' "$1" >&2
    exit 1
}

find_sdk() {
    local candidate local_sdk
    local_sdk="$(sed -n 's/^sdk\.dir=//p' "$HERE/local.properties" 2>/dev/null | head -n 1 | sed 's/\\:/\:/g')"
    for candidate in "${ANDROID_SDK_ROOT:-}" "${ANDROID_HOME:-}" "$local_sdk" "$HOME/Android/Sdk" "$HOME/Android/sdk" "$HOME/.buildozer/android/platform/android-sdk" /opt/android-sdk /usr/lib/android-sdk /usr/share/android-sdk; do
        if [[ -n "$candidate" && -d "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

if [[ -z "${ANDROID_SDK_ROOT:-}" ]]; then
    ANDROID_SDK_ROOT="$(find_sdk)" || fail "Android SDK not found. Install Android Studio or set ANDROID_SDK_ROOT."
fi
export ANDROID_SDK_ROOT
export ANDROID_HOME="${ANDROID_HOME:-$ANDROID_SDK_ROOT}"

SDKMANAGER=""
for candidate in "$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager" "$ANDROID_SDK_ROOT/cmdline-tools/lysyk/bin/sdkmanager" "$ANDROID_SDK_ROOT/cmdline-tools/bin/sdkmanager"; do
    if [[ -x "$candidate" ]]; then SDKMANAGER="$candidate"; break; fi
done
if [[ -z "$SDKMANAGER" ]]; then
    command -v curl >/dev/null 2>&1 || fail "curl is required to install current Android SDK Command-line Tools"
    command -v unzip >/dev/null 2>&1 || fail "unzip is required to install Android SDK Command-line Tools"
    command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required to verify Android SDK Command-line Tools"
    TOOLS_ZIP="$HOME/.cache/lysyk/commandlinetools-linux-15859902_latest.zip"
    mkdir -p "$(dirname "$TOOLS_ZIP")"
    if [[ ! -f "$TOOLS_ZIP" ]]; then
        curl -fL --retry 3 https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip -o "$TOOLS_ZIP"
    fi
    echo "4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583  $TOOLS_ZIP" | sha256sum -c -
    TOOLS_TMP="$(mktemp -d)"
    unzip -q "$TOOLS_ZIP" -d "$TOOLS_TMP"
    TOOLS_DEST="$ANDROID_SDK_ROOT/cmdline-tools/latest"
    if [[ -e "$TOOLS_DEST" ]]; then TOOLS_DEST="$ANDROID_SDK_ROOT/cmdline-tools/lysyk"; fi
    mkdir -p "$(dirname "$TOOLS_DEST")"
    mv "$TOOLS_TMP/cmdline-tools" "$TOOLS_DEST"
    rmdir "$TOOLS_TMP"
    SDKMANAGER="$TOOLS_DEST/bin/sdkmanager"
fi

if [[ -z "${ANDROID_NDK_HOME:-}" ]]; then
    if [[ -d "$ANDROID_SDK_ROOT/ndk/$NDK_VERSION" ]]; then
        ANDROID_NDK_HOME="$ANDROID_SDK_ROOT/ndk/$NDK_VERSION"
    else
        for candidate in "$ANDROID_SDK_ROOT"/ndk/* "$HOME"/.buildozer/android/platform/android-ndk-*; do
            if [[ -x "$candidate/ndk-build" && -f "$candidate/source.properties" ]]; then
                ANDROID_NDK_HOME="$candidate"
                break
            fi
        done
    fi
fi
if [[ -z "${ANDROID_NDK_HOME:-}" ]]; then
    NDK_VERSION="27.2.12479018"
    "$SDKMANAGER" --sdk_root="$ANDROID_SDK_ROOT" --install "ndk;$NDK_VERSION"
    ANDROID_NDK_HOME="$ANDROID_SDK_ROOT/ndk/$NDK_VERSION"
fi
[[ -d "$ANDROID_NDK_HOME" ]] || fail "NDK not found at $ANDROID_NDK_HOME"
NDK_VERSION="$(sed -n 's/^Pkg.Revision[[:space:]]*=[[:space:]]*//p' "$ANDROID_NDK_HOME/source.properties" | head -n 1)"
[[ -n "$NDK_VERSION" ]] || fail "Cannot determine the NDK version in $ANDROID_NDK_HOME"
export ANDROID_NDK_VERSION="$NDK_VERSION"
export ANDROID_NDK_HOME

SDK_PACKAGES=()
[[ -d "$ANDROID_SDK_ROOT/platforms/android-$ANDROID_API" ]] || SDK_PACKAGES+=("platforms;android-$ANDROID_API")
[[ -d "$ANDROID_SDK_ROOT/build-tools/35.0.0" ]] || SDK_PACKAGES+=("build-tools;35.0.0")
[[ -x "$ANDROID_SDK_ROOT/platform-tools/adb" ]] || SDK_PACKAGES+=(platform-tools)
if [[ ${#SDK_PACKAGES[@]} -gt 0 ]]; then "$SDKMANAGER" --sdk_root="$ANDROID_SDK_ROOT" --install "${SDK_PACKAGES[@]}"; fi

command -v rustup >/dev/null 2>&1 || fail "Rust is missing. Install rustup and retry."
command -v cargo >/dev/null 2>&1 || fail "Cargo is missing. Install Rust and retry."
rustup target add aarch64-linux-android
command -v rustc >/dev/null 2>&1 || fail "rustc is missing. Install a Rust toolchain and retry."
export LYSYK_RUSTC_VERSION="$(rustc --version)"
if ! command -v cargo-ndk >/dev/null 2>&1; then
    cargo install cargo-ndk
fi

if [[ -z "${ANDROID_PYTHON_PREFIX:-}" ]]; then
    for candidate in "$ROOT/.android/python" "$ANDROID_SDK_ROOT/python" "$HOME/.android/python"; do
        if [[ -n "$candidate" && -d "$candidate/lib" ]] && compgen -G "$candidate/lib/libpython3.*.so" >/dev/null; then
            ANDROID_PYTHON_PREFIX="$candidate"
            break
        fi
    done
fi
if [[ -z "${ANDROID_PYTHON_PREFIX:-}" ]]; then
    command -v python3 >/dev/null 2>&1 || fail "Python 3 is required to prepare the Android runtime"
    command -v git >/dev/null 2>&1 || fail "Git is required to prepare the Android runtime"
    P4A_ROOT="$ROOT/.android/p4a"
    P4A_VENV="$ROOT/.android/p4a-venv"
    P4A_STORAGE="$P4A_ROOT/storage"
    mkdir -p "$P4A_ROOT"
    if [[ ! -x "$P4A_VENV/bin/p4a" ]]; then
        python3 -m venv "$P4A_VENV"
        "$P4A_VENV/bin/python" -m pip install --upgrade pip
        "$P4A_VENV/bin/python" -m pip install python-for-android
    fi
    "$P4A_VENV/bin/python" - <<'PY'
from pathlib import Path
import pythonforandroid

recipe = Path(pythonforandroid.__file__).parent / "recipes" / "android" / "__init__.py"
source = recipe.read_text()
if 'extra_build_args = ["--no-isolation"]' not in source:
    marker = "    version = None\n"
    if marker not in source:
        raise SystemExit(f"Cannot patch python-for-android Android recipe: {recipe}")
    recipe.write_text(source.replace(marker, marker + '    extra_build_args = ["--no-isolation"]\n', 1))
PY
    "$P4A_VENV/bin/p4a" create \
        --dist-name lysykandroid \
        --requirements python3,numpy \
        --bootstrap service_only \
        --arch "$ABI" \
        --sdk-dir "$ANDROID_SDK_ROOT" \
        --ndk-dir "$ANDROID_NDK_HOME" \
        --android-api "$ANDROID_API" \
        --ndk-api 26 \
        --storage-dir "$P4A_STORAGE" \
        --skip-prebuilt \
        --ignore-setup-py
    ANDROID_PYTHON_PREFIX="$(find "$P4A_STORAGE/build/other_builds/python3" -type d -path '*/android-build/android-root' -print -quit 2>/dev/null)"
    [[ -n "$ANDROID_PYTHON_PREFIX" ]] || fail "python-for-android did not produce an Android Python runtime"
    PYTHON_VERSION_DIR="$(find "$ANDROID_PYTHON_PREFIX/lib" -maxdepth 1 -type d -name 'python3.*' -print -quit)"
    [[ -n "$PYTHON_VERSION_DIR" ]] || fail "Android Python standard library is missing from $ANDROID_PYTHON_PREFIX"
    SITE_PACKAGES="$P4A_STORAGE/build/python-installs/lysykandroid/$ABI"
    [[ -d "$SITE_PACKAGES/numpy" ]] || fail "python-for-android did not produce Android NumPy"
    mkdir -p "$PYTHON_VERSION_DIR/site-packages"
    cp -a "$SITE_PACKAGES/." "$PYTHON_VERSION_DIR/site-packages/"
    export ANDROID_PYTHON_PREFIX
fi
[[ -d "$ANDROID_PYTHON_PREFIX/lib" ]] || fail "ANDROID_PYTHON_PREFIX has no lib directory: $ANDROID_PYTHON_PREFIX"

shopt -s nullglob
PYTHON_LIBS=("$ANDROID_PYTHON_PREFIX"/lib/libpython3.*.so)
shopt -u nullglob
[[ ${#PYTHON_LIBS[@]} -eq 1 ]] || fail "Expected exactly one libpython3.X.so in $ANDROID_PYTHON_PREFIX/lib"
LIBPY="${PYTHON_LIBS[0]}"
PYVER="$(basename "$LIBPY" .so | sed 's/^libpython//')"

export PYO3_CROSS=1
export PYO3_CROSS_LIB_DIR="$ANDROID_PYTHON_PREFIX/lib"
export PYO3_CROSS_PYTHON_VERSION="$PYVER"
export PYO3_CROSS_PYTHON_IMPLEMENTATION=CPython

PROFILE_FLAG=(--release)
if [[ "$MODE" == debug ]]; then PROFILE_FLAG=(); fi

mkdir -p "$APP/jniLibs/$ABI"
(cd "$NATIVE_DIR" && cargo ndk -t "$ABI" -o "$APP/jniLibs" build \
    "${PROFILE_FLAG[@]}" \
    --no-default-features \
    --features backend-vulkan,backend-gl,android-host)

cp "$LIBPY" "$APP/jniLibs/$ABI/"
if [[ -n "${P4A_STORAGE:-}" ]]; then
    P4A_LIBS="$P4A_STORAGE/dists/lysykandroid/libs/$ABI"
    if [[ -d "$P4A_LIBS" ]]; then cp -a "$P4A_LIBS/." "$APP/jniLibs/$ABI/"; fi
fi

BUNDLE_ARGS=(--python-prefix "$ANDROID_PYTHON_PREFIX")
if [[ -z "${ANDROID_SITE_PACKAGES:-}" ]]; then
    ANDROID_SITE_PACKAGES="$ROOT/.android/p4a/storage/dists/lysykandroid/_python_bundle__${ABI}/_python_bundle/site-packages"
fi
if [[ -d "$ANDROID_SITE_PACKAGES/numpy" ]]; then
    BUNDLE_ARGS+=(--site-packages "$ANDROID_SITE_PACKAGES")
else
    fail "Android site-packages not found at $ANDROID_SITE_PACKAGES"
fi
python3 "$ROOT/tools/android_bundle.py" "${BUNDLE_ARGS[@]}"

if [[ "$MODE" == release && -z "${CHUBAKA_KEYSTORE:-}" && ! -f "$HERE/app/debug.keystore" ]]; then
    keytool -genkeypair -keystore "$HERE/app/debug.keystore" -storepass android -keypass android \
        -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
fi

cd "$HERE"
if [[ -x ./gradlew ]]; then
    GRADLE=(./gradlew)
else
    GRADLE_HOME_LOCAL="$HOME/.cache/lysyk/gradle-8.9"
    GRADLE_BIN="$GRADLE_HOME_LOCAL/bin/gradle"
    if [[ ! -x "$GRADLE_BIN" ]]; then
        if command -v gradle >/dev/null 2>&1 && gradle --version 2>/dev/null | grep -Eq 'Gradle 8\.'; then
            GRADLE_BIN="$(command -v gradle)"
        else
            command -v curl >/dev/null 2>&1 || fail "curl is required to download Gradle 8.9"
            command -v unzip >/dev/null 2>&1 || fail "unzip is required to install Gradle 8.9"
            mkdir -p "$HOME/.cache/lysyk"
            curl -fL --retry 3 https://services.gradle.org/distributions/gradle-8.9-bin.zip -o "$HOME/.cache/lysyk/gradle-8.9-bin.zip"
            unzip -q -o "$HOME/.cache/lysyk/gradle-8.9-bin.zip" -d "$HOME/.cache/lysyk"
        fi
    fi
    GRADLE=("$GRADLE_BIN")
fi

if [[ "$MODE" == debug ]]; then
    "${GRADLE[@]}" --no-daemon assembleDebug
    APK="$HERE/app/build/outputs/apk/debug/app-debug.apk"
else
    "${GRADLE[@]}" --no-daemon assembleRelease
    APK="$HERE/app/build/outputs/apk/release/app-release.apk"
fi

mkdir -p "$ROOT/build/android"
OUTPUT="$ROOT/build/android/chubaka-$MODE.apk"
cp "$APK" "$OUTPUT"
printf '\nAPK: %s\n' "$OUTPUT"
