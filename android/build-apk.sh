#!/usr/bin/env bash
# Build the MAZA wallet bench APK with the raw Android toolchain
# (aapt2 -> javac -> d8 -> zip -> apksigner). No Gradle, no AGP, no external
# libraries — a single-Activity app that only touches android.jar.
#
# Usage:  bash android/build-apk.sh [output.apk]
# Env:    ANDROID_SDK (default /opt/android-sdk)
set -euo pipefail

SDK="${ANDROID_SDK:-/opt/android-sdk}"
BT="$SDK/build-tools/34.0.0"
PLATFORM="$SDK/platforms/android-34/android.jar"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$REPO/android/maza-wallet-bench.apk}"

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

echo "[1/5] aapt2 compile"
"$BT/aapt2" compile --dir "$REPO/android/res" -o "$BTMP/res.zip"
echo "[2/5] aapt2 link"
"$BT/aapt2" link -I "$PLATFORM" --manifest "$REPO/android/AndroidManifest.xml" \
  --java "$BTMP/gen" -o "$BTMP/base.apk" --auto-add-overlay "$BTMP/res.zip"
echo "[3/5] javac"
mkdir -p "$BTMP/classes"
javac --release 11 -nowarn -classpath "$PLATFORM" \
  -d "$BTMP/classes" $(find "$REPO/android/src" -name '*.java') \
  $(find "$BTMP/gen" -name '*.java' 2>/dev/null || true)
echo "[4/5] d8"
mkdir -p "$BTMP/dex"
"$BT/d8" --release --lib "$PLATFORM" --output "$BTMP/dex" \
  $(find "$BTMP/classes" -name '*.class')
(cd "$BTMP/dex" && zip -q -uj "$BTMP/base.apk" classes.dex)
echo "[5/5] apksigner"
"$BT/apksigner" sign --ks "$KS" --ks-key-alias mazabench \
  --ks-pass pass:mazabench --key-pass pass:mazabench \
  --out "$OUT" "$BTMP/base.apk"
"$BT/apksigner" verify "$OUT" && echo "SIGNED OK: $OUT ($(stat -c%s "$OUT") bytes)"
