#!/usr/bin/env bash
# Build the MAZA wallet APK with the raw Android toolchain
# (aapt2 -> javac -> d8 -> zip -> [zipalign] -> apksigner). No Gradle, no AGP,
# no external libraries — a single-Activity app that only touches android.jar.
#
# Stage [1/6] (bench) / [1/7] (release) is the crypto selftest gate: the FIRST
# build stage (only variable/path resolution precedes it — it runs before any
# Android SDK/toolchain check; selftest.sh self-checks javac), and the build
# REFUSES to continue unless every vector check passes (BIP39/BIP32/
# RIPEMD-160/MAZA profile/tx sign+verify). A broken crypto package can never
# reach an APK.
#
# Usage:
#   bash android/build-apk.sh [output.apk]         bench/debug build (debug
#       keystore, manifest versions; behavior identical to pre-M5 builds)
#   bash android/build-apk.sh --release [out.apk]  release build: mazarelease
#       keystore, versionCode/versionName from android/release.properties,
#       zipaligned, written to android/releases/ by default
#
# Env:  ANDROID_SDK (default /opt/android-sdk)
#       MAZA_RELEASE_KEYSTORE      (default ~/.maza-wallet/release.keystore)
#       MAZA_RELEASE_KEYSTORE_PASS (default ~/.maza-wallet/release.keystore.pass)
#       RELEASE_VERSION_CODE / RELEASE_VERSION_NAME override release.properties
set -euo pipefail

MODE=bench
if [ "${1:-}" = "--release" ]; then MODE=release; shift; fi

SDK="${ANDROID_SDK:-/opt/android-sdk}"
BT="$SDK/build-tools/34.0.0"
PLATFORM="$SDK/platforms/android-34/android.jar"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-}"
if [ "$MODE" = bench ] && [ -z "$OUT" ]; then OUT="$REPO/android/maza-wallet-bench.apk"; fi

# Release mode has one extra stage (zipalign): stages are [N/6] bench,
# [N/7] release.
TOTAL=6
if [ "$MODE" = release ]; then TOTAL=7; fi
stage() { echo "[$1/$TOTAL] $2"; }

stage 1 "crypto selftest (gate — any FAIL aborts the build before packaging)"
if ! bash "$REPO/android/selftest.sh"; then
  echo "FATAL: crypto selftest FAILED — build aborted, no APK written" >&2
  exit 1
fi

command -v javac >/dev/null || { echo "javac missing (JDK required)" >&2; exit 1; }
[ -x "$BT/aapt2" ] || { echo "aapt2 missing — install build-tools;34.0.0" >&2; exit 1; }
[ -f "$PLATFORM" ] || { echo "platform android-34 missing" >&2; exit 1; }

# ---- release-mode inputs (resolve BEFORE any packaging; fail loud, never
# ---- auto-generate a release signing key) -------------------------------
KS_RELEASE=""
KP_RELEASE=""
VC=""
VN=""
if [ "$MODE" = release ]; then
  KS_RELEASE="${MAZA_RELEASE_KEYSTORE:-$HOME/.maza-wallet/release.keystore}"
  KP_RELEASE="${MAZA_RELEASE_KEYSTORE_PASS:-$HOME/.maza-wallet/release.keystore.pass}"
  [ -f "$KS_RELEASE" ] || {
    echo "FATAL: release keystore not found at $KS_RELEASE — create it once with:" >&2
    printf '%s\n' \
      "  openssl rand -base64 30 | tr -d \"\\n\" > $KP_RELEASE && chmod 600 $KP_RELEASE" \
      '  PW="$(head -n1 '"$KP_RELEASE"')" && printf "%s\n%s\n" "$PW" "$PW" > '"$KP_RELEASE"'  # 2 lines: ks + key password (apksigner file: reads lines sequentially)' \
      '  keytool -genkeypair -alias mazarelease -keyalg RSA -keysize 2048 -validity 10000 \' \
      "    -dname \"CN=mazawallet-release\" -keystore $KS_RELEASE \\" \
      '  -storepass "$(head -n1 '"$KP_RELEASE"')" -keypass "$(head -n1 '"$KP_RELEASE"')"  # head -n1: keytool needs the SINGLE password, not the two-line file' >&2
    exit 1
  }
  [ -f "$KP_RELEASE" ] || { echo "FATAL: release keystore password file missing at $KP_RELEASE" >&2; exit 1; }
  for f in "$KS_RELEASE" "$KP_RELEASE"; do
    p="$(stat -c %a "$f")"
    case "$p" in 600|400) ;; *) echo "FATAL: $f must be mode 0600/0400 (is $p) — refusing to use an exposed signing credential" >&2; exit 1;; esac
  done
  RELPROPS="$REPO/android/release.properties"
  [ -f "$RELPROPS" ] || { echo "FATAL: $RELPROPS missing — release line version identity is required" >&2; exit 1; }
  VC="${RELEASE_VERSION_CODE:-$(sed -n 's/^versionCode=//p' "$RELPROPS" | tr -d '[:space:]')}"
  VN="${RELEASE_VERSION_NAME:-$(sed -n 's/^versionName=//p' "$RELPROPS" | tr -d '[:space:]')}"
  case "$VC" in ''|*[!0-9]*) echo "FATAL: invalid versionCode '$VC' for release build" >&2; exit 1;; esac
  case "$VN" in ''|*[!0-9.]*) echo "FATAL: invalid versionName '$VN' for release build" >&2; exit 1;; esac
  if ! printf '%s' "$VN" | grep -qE '^[0-9]+([.][0-9]+)*$'; then
    echo "FATAL: invalid versionName '$VN' — must be digit-led dotted segments (e.g. 1.0.0; rejects '.', '1..0', '.1', '1.')" >&2
    exit 1
  fi
  [ -x "$BT/zipalign" ] || { echo "zipalign missing — install build-tools;34.0.0" >&2; exit 1; }
  if [ -z "$OUT" ]; then
    mkdir -p "$REPO/android/releases"
    OUT="$REPO/android/releases/maza-wallet-v$VN.apk"
  fi
fi

BTMP="$(mktemp -d)"
trap 'rm -rf "$BTMP"' EXIT

if [ "$MODE" = bench ]; then
  KS="$REPO/android/debug.keystore"
  if [ ! -f "$KS" ]; then
    keytool -genkeypair -alias mazabench -keyalg RSA -keysize 2048 \
      -validity 10000 -storepass mazabench -keypass mazabench \
      -dname "CN=mazabench" -keystore "$KS" >/dev/null 2>&1
    echo "generated debug keystore"
  fi
fi

stage 2 "aapt2 compile"
"$BT/aapt2" compile --dir "$REPO/android/res" -o "$BTMP/res.zip"
stage 3 "aapt2 link"
if [ "$MODE" = release ]; then
  "$BT/aapt2" link -I "$PLATFORM" --manifest "$REPO/android/AndroidManifest.xml" \
    --java "$BTMP/gen" -o "$BTMP/base.apk" --auto-add-overlay "$BTMP/res.zip" \
    --version-code "$VC" --version-name "$VN" --replace-version
else
  "$BT/aapt2" link -I "$PLATFORM" --manifest "$REPO/android/AndroidManifest.xml" \
    --java "$BTMP/gen" -o "$BTMP/base.apk" --auto-add-overlay "$BTMP/res.zip"
fi
stage 4 "javac"
mkdir -p "$BTMP/classes"
mapfile -t -d '' JAVA_FILES < <(find "$REPO/android/src" -name '*.java' -print0; find "$BTMP/gen" -name '*.java' -print0 2>/dev/null || true)
javac --release 11 -nowarn -classpath "$PLATFORM" \
  -d "$BTMP/classes" "${JAVA_FILES[@]}"
stage 5 "d8"
mkdir -p "$BTMP/dex"
mapfile -t -d '' CLASS_FILES < <(find "$BTMP/classes" -name '*.class' -print0)
"$BT/d8" --release --lib "$PLATFORM" --output "$BTMP/dex" "${CLASS_FILES[@]}"
(cd "$BTMP/dex" && zip -q -uj "$BTMP/base.apk" classes.dex)

if [ "$MODE" = release ]; then
  stage 6 "zipalign"
  "$BT/zipalign" -f -p 4 "$BTMP/base.apk" "$BTMP/aligned.apk"
  stage 7 "apksigner (mazarelease)"
  "$BT/apksigner" sign --ks "$KS_RELEASE" --ks-key-alias mazarelease \
    --ks-pass "file:$KP_RELEASE" --key-pass "file:$KP_RELEASE" \
    --out "$OUT" "$BTMP/aligned.apk"
  "$BT/apksigner" verify --verbose "$OUT" >"$BTMP/verify.txt" 2>&1 \
    && head -5 "$BTMP/verify.txt"
  "$BT/apksigner" verify --print-certs "$OUT" 2>/dev/null | grep -E "SHA-256 digest" || true
  echo "SIGNED OK: $OUT ($(stat -c%s "$OUT") bytes, versionCode=$VC versionName=$VN)"
  sha256sum "$OUT"
else
  stage 6 "apksigner"
  "$BT/apksigner" sign --ks "$KS" --ks-key-alias mazabench \
    --ks-pass pass:mazabench --key-pass pass:mazabench \
    --out "$OUT" "$BTMP/base.apk"
  "$BT/apksigner" verify "$OUT" && echo "SIGNED OK: $OUT ($(stat -c%s "$OUT") bytes)"
fi
