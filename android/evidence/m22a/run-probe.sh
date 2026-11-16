#!/usr/bin/env bash
# M22a guard-semantics regression probe runner. Run from the repo root.
# Exit 0 = all assertions PASS.
set -euo pipefail
cd "$(dirname "$0")/../../.."   # repo root
OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
javac -d /tmp/m22a-probe android/evidence/m22a/SelectTabGuardProbe.java
java -cp /tmp/m22a-probe SelectTabGuardProbe android/src/com/mazawallet/MainActivity.java | tee "$OUT"
grep -q "ALL CHECKS PASSED" "$OUT"
