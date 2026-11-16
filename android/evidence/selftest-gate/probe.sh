#!/usr/bin/env bash
# M4 evidence probe — auditable end-to-end proof of the build selftest gate.
#
# Sequence (every step prints the command it runs plus its REAL output):
#   0. refuse to start AT ALL if SelfTest.java has uncommitted changes —
#      hard exit BEFORE any mutation (no assertion-then-continue)
#   1. baseline APK md5
#   2. back up SelfTest.java byte-for-byte, install a restore trap, corrupt
#      ONE character of an expected RIPEMD-160 vector
#   3. run build-apk.sh — MUST exit 1 at stage [1/6] with the FATAL line
#   4. APK md5 MUST be unchanged (nothing was packaged)
#   5. restore SelfTest.java from the byte backup (never git checkout —)
#      and verify the restore byte-for-byte
#   6. run build-apk.sh again — MUST exit 0 with 19 PASS lines and SIGNED OK
#   7. run the walletbench test suite — MUST report OK; transcript written
#      to suite-transcript.log next to this script
# The restore trap fires on EXIT/INT/TERM and restores the byte backup if a
# verified restore has not happened yet, so an interruption can never leave
# SelfTest.java corrupted. Beyond SelfTest.java (restored in-run), the probe
# WRITES: suite-transcript.log (step 7), a fresh APK + .idsig sidecar via
# the green build, and its temp files (removed by the trap).
# NOT part of the shipped build pipeline — evidence generator only.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SELFTEST_JAVA="$REPO/android/src/com/mazawallet/crypto/SelfTest.java"
BUILD_LOG="$(mktemp)"
BACKUP="$(mktemp)"
RESTORED=0
GOOD='8eb208f7e05d987a9b044a8e98c6b087f15a0bfc'
BAD='8eb208f7e05d987a9b044a8e98c6b087f15a0bfd'
FAILS=0

restore_or_die() {
  if [ "$RESTORED" -eq 0 ] && [ -s "$BACKUP" ]; then
    cp "$BACKUP" "$SELFTEST_JAVA"
    echo "TRAP: SelfTest.java restored from byte backup" >&2
  fi
  rm -f "$BUILD_LOG" "$BACKUP"
}
trap restore_or_die EXIT
trap 'restore_or_die; exit 90' INT TERM

assert() { # assert <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then
    echo "ASSERT PASS: $1 (expected=$2 actual=$3)"
  else
    echo "ASSERT FAIL: $1 (expected=$2 actual=$3)"
    FAILS=$((FAILS+1))
  fi
}

echo "## probe start $(date -u '+%Y-%m-%dT%H:%M:%SZ') repo=$REPO"

echo
echo "### CMD: git status --porcelain -- android/src/com/mazawallet/crypto/SelfTest.java"
DIRTY="$(git -C "$REPO" status --porcelain -- android/src/com/mazawallet/crypto/SelfTest.java)"
echo "${DIRTY:-<empty>}"
if [ -n "$DIRTY" ]; then
  echo "FATAL: SelfTest.java has uncommitted changes — probe refuses to start;" \
       "no mutation performed (restore path uses a byte backup, not git, so" \
       "uncommitted work must never be present to lose)" >&2
  exit 1
fi
echo "ASSERT PASS: SelfTest.java clean before probe (refused-to-start guard)"

echo
echo "### CMD: md5sum android/maza-wallet-bench.apk"
MD5_BEFORE="$(md5sum "$REPO/android/maza-wallet-bench.apk" | awk '{print $1}')"
echo "$MD5_BEFORE  android/maza-wallet-bench.apk"

echo
echo "### CMD: cp SelfTest.java -> byte backup (fault-injection safety)"
cp "$SELFTEST_JAVA" "$BACKUP"
cmp "$SELFTEST_JAVA" "$BACKUP" && echo "backup verified byte-identical"

echo
echo "### CMD: sed -i s/$GOOD/$BAD/ android/src/com/mazawallet/crypto/SelfTest.java"
sed -i "s/$GOOD/$BAD/" "$SELFTEST_JAVA"
grep -n "$BAD" "$SELFTEST_JAVA" | sed "s|^|replaced -> |"

echo
echo "### CMD: bash android/build-apk.sh   (expected to FAIL the gate)"
bash "$REPO/android/build-apk.sh" >"$BUILD_LOG" 2>&1
RC1=$?
echo "BUILD_EXIT_CODE=$RC1"
cat "$BUILD_LOG"

echo
echo "### CMD: md5sum android/maza-wallet-bench.apk   (must be unchanged)"
MD5_MID="$(md5sum "$REPO/android/maza-wallet-bench.apk" | awk '{print $1}')"
echo "$MD5_MID  android/maza-wallet-bench.apk"
assert "forced-fail build exit code" "1" "$RC1"
assert "gate FATAL line present" "1" "$(grep -c '^FATAL: crypto selftest FAILED' "$BUILD_LOG")"
assert "no packaging stage ran (no [6/6])" "0" "$(grep -c '^\[6/6\]' "$BUILD_LOG")"
assert "APK md5 unchanged after aborted build" "$MD5_BEFORE" "$MD5_MID"

echo
echo "### CMD: cp byte backup -> SelfTest.java (restore; git never used)"
cp "$BACKUP" "$SELFTEST_JAVA"

echo
echo "### CMD: cmp backup vs SelfTest.java; grep vector counts"
if cmp "$BACKUP" "$SELFTEST_JAVA"; then
  echo "restore verified byte-identical to pre-probe content"
else
  echo "ASSERT FAIL: restore not byte-identical" >&2
  FAILS=$((FAILS+1))
fi
N_GOOD="$(grep -c "$GOOD" "$SELFTEST_JAVA")"
N_BAD="$(grep -c "$BAD" "$SELFTEST_JAVA" || true)"
echo "original_constant_count=$N_GOOD corrupted_constant_count=$N_BAD"
RESTORED=1
assert "original vector restored" "1" "$N_GOOD"
assert "corrupted vector gone" "0" "$N_BAD"

echo
echo "### CMD: bash android/build-apk.sh   (expected green)"
bash "$REPO/android/build-apk.sh" >"$BUILD_LOG" 2>&1
RC2=$?
echo "BUILD_EXIT_CODE=$RC2"
cat "$BUILD_LOG"

echo
echo "### CMD: md5sum android/maza-wallet-bench.apk"
MD5_AFTER="$(md5sum "$REPO/android/maza-wallet-bench.apk" | awk '{print $1}')"
echo "$MD5_AFTER  android/maza-wallet-bench.apk"

N_PASS="$(grep -cE '^PASS ' "$BUILD_LOG" || true)"
N_FAIL="$(grep -cE '^FAIL ' "$BUILD_LOG" || true)"
echo
echo "selftest counts in green build log: PASS=$N_PASS FAIL=$N_FAIL"
assert "green build exit code" "0" "$RC2"
assert "selftest PASS count" "19" "$N_PASS"
assert "selftest FAIL count" "0" "$N_FAIL"
assert "SIGNED OK present" "1" "$(grep -c '^SIGNED OK' "$BUILD_LOG")"

echo
echo "### CMD: python3 -m unittest discover -s tests   (from repo root)"
echo "(full output -> suite-transcript.log)"
(cd "$REPO" && python3 -m unittest discover -s tests) \
  > "$HERE/suite-transcript.log" 2>&1
SUITE_RC=$?
echo "SUITE_RC=$SUITE_RC"
tail -3 "$HERE/suite-transcript.log"
assert "walletbench suite exit code" "0" "$SUITE_RC"
assert "suite OK line present" "1" "$(grep -c '^OK' "$HERE/suite-transcript.log")"

echo
echo "## probe summary: FAILS=$FAILS"
echo "md5 before=$MD5_BEFORE after-abort=$MD5_MID after-green=$MD5_AFTER"
if [ "$FAILS" -eq 0 ]; then
  echo "PROBE RESULT: ALL ASSERTIONS PASS"
  exit 0
fi
echo "PROBE RESULT: FAILURES PRESENT"
exit 1
