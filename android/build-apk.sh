#!/usr/bin/env bash
# Build the MAZA wallet bench APK with the raw Android toolchain
# (aapt2 -> javac -> d8 -> zip -> apksigner). No Gradle, no AGP, no external
# libraries — a single-Activity app that only touches android.jar.
#
# Stage [1/6] is the crypto selftest gate: the FIRST build stage (only
# variable/path resolution precedes it — it runs before any Android
# SDK/toolchain check; selftest.sh self-checks javac), and the build
# REFUSES to continue unless every vector check passes (BIP39/BIP32/
# RIPEMD-160/MAZA profile/tx sign+verify). A broken crypto
# package can never reach an APK.
#
# Usage:  bash android/build-apk.sh [output.apk]
# Env:    ANDROID_SDK (default /opt/android-sdk)
set -euo pipefail

SDK="${ANDROID_SDK:-/opt/android-sdk}"
BT="$SDK/build-tools/34.0.0"
PLATFORM="$SDK/platforms/android-34/android.jar"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$REPO/android/maza-wallet-bench.apk}"

echo "[1/6] crypto selftest (gate — any FAIL aborts the build before packaging)"
if ! bash "$REPO/android/selftest.sh"; then
  echo "FATAL: crypto selftest FAILED — build aborted, no APK written" >&2
  exit 1
fi

command -v javac >/dev/null || { echo "javac missing (JDK required)" >&2; exit 1; }
[ -x "$BT/aapt2" ] || { echo "aapt2 missing — install build-tools;34.0.0" >&2; exit 1; }
[ -f "$PLATFORM" ] || { echo "platform android-34 missing" >&2; exit 1; }

BTMP="$(mktemp -d)"
trap 'rm -rf "$BTMP"' EXIT

KS="$REPO/android/debug.keystore"
if [ ! -f "$KS" ]; then
  keytool -genkeypair -alias mazabench -keyalg RSA -keysize 2048 \
    -validity 10000 -storepass mazabench -keypass mazabench \
    -dname "CN=mazabench" -keystore "$KS" >/dev/null 2>&1
  echo "generated debug keystore"
fi

echo "[2/6] aapt2 compile"
"$BT/aapt2" compile --dir "$REPO/android/res" -o "$BTMP/res.zip"
echo "[3/6] aapt2 link"
"$BT/aapt2" link -I "$PLATFORM" --manifest "$REPO/android/AndroidManifest.xml" \
  --java "$BTMP/gen" -o "$BTMP/base.apk" --auto-add-overlay "$BTMP/res.zip"
echo "[4/6] javac"
mkdir -p "$BTMP/classes"
javac --release 11 -nowarn -classpath "$PLATFORM" \
  -d "$BTMP/classes" $(find "$REPO/android/src" -name '*.java') \
  $(find "$BTMP/gen" -name '*.java' 2>/dev/null || true)
echo "[5/6] d8"
mkdir -p "$BTMP/dex"
"$BT/d8" --release --lib "$PLATFORM" --output "$BTMP/dex" \
  $(find "$BTMP/classes" -name '*.class')
(cd "$BTMP/dex" && zip -q -uj "$BTMP/base.apk" classes.dex)
echo "[6/6] apksigner"
"$BT/apksigner" sign --ks "$KS" --ks-key-alias mazabench \
  --ks-pass pass:mazabench --key-pass pass:mazabench \
  --out "$OUT" "$BTMP/base.apk"
"$BT/apksigner" verify "$OUT" && echo "SIGNED OK: $OUT ($(stat -c%s "$OUT") bytes)"
