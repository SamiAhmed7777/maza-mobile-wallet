#!/usr/bin/env bash
# Compile the crypto package with plain javac and run SelfTest on the
# desktop JVM (no android.jar, no Android deps). One PASS/FAIL line per
# check; exits nonzero if any check fails.
#
# Usage: bash android/selftest.sh
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

command -v javac >/dev/null || { echo "javac missing (JDK required)" >&2; exit 1; }

echo "Compiling android/src/com/mazawallet/crypto ..."
javac --release 11 -nowarn -d "$OUT" \
  $(find "$REPO/android/src/com/mazawallet/crypto" -name '*.java')

echo "Running SelfTest ..."
echo
java -cp "$OUT" com.mazawallet.crypto.SelfTest \
  "$REPO/android/res/raw/bip39_english.txt"
