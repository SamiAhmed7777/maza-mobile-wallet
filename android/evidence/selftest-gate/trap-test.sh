#!/usr/bin/env bash
# Trap-verification harness for probe.sh — proves the EXIT/INT/TERM restore
# trap really restores SelfTest.java when the probe is interrupted mid-run
# (during the corrupted-source phase, before the verified-restore step).
#
# Method: launch probe.sh as an async job, poll the live tree until the
# one-character corruption is OBSERVED, then send SIGTERM to the probe's
# own pid ($! of this harness — no pgrep guessing) and verify the probe
# exited 90 (the trap restore path) with the tree byte-identical to the
# committed content. SIGINT cannot be used here: POSIX sets SIGINT to
# SIG_IGN for async jobs and a signal ignored at entry cannot be trapped;
# TERM and INT share the same trap handler in probe.sh. Writes its
# findings to stdout; the caller captures them as trap-test-transcript.log.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
TARGET="$REPO/android/src/com/mazawallet/crypto/SelfTest.java"
PROBE_LOG="$(mktemp)"
trap 'rm -f "$PROBE_LOG"' EXIT
GOOD='8eb208f7e05d987a9b044a8e98c6b087f15a0bfc'
BAD='8eb208f7e05d987a9b044a8e98c6b087f15a0bfd'
FAILS=0
assert() {
  if [ "$2" = "$3" ]; then
    echo "ASSERT PASS: $1 (expected=$2 actual=$3)"
  else
    echo "ASSERT FAIL: $1 (expected=$2 actual=$3)"
    FAILS=$((FAILS+1))
  fi
}

echo "## trap test start $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "note: the probe is launched as an async job, and POSIX sets SIGINT to"
echo "SIG_IGN for async jobs (a signal ignored at entry cannot be trapped),"
echo "so the trap path is exercised with SIGTERM — same handler, real delivery."

ST="$(git -C "$REPO" status --porcelain -- android/src/com/mazawallet/crypto/SelfTest.java)"
if [ -n "$ST" ]; then
  echo "FATAL: SelfTest.java dirty — test refuses to start" >&2
  exit 1
fi
echo "ASSERT PASS: SelfTest.java clean before test"

echo
echo "### CMD: bash probe.sh (async) -> poll for observed corruption -> kill -TERM \$!  (the probe pid itself)"
bash "$HERE/probe.sh" > "$PROBE_LOG" 2>&1 &
PID=$!
OBSERVED=0
for i in $(seq 1 120); do
  if grep -q "$BAD" "$TARGET" 2>/dev/null; then OBSERVED=1; break; fi
  kill -0 "$PID" 2>/dev/null || break
  sleep 1
done
if [ "$OBSERVED" -eq 1 ]; then
  echo "corruption OBSERVED in live tree at poll ${i}s — sending SIGTERM to probe pid $PID (\$! of this harness, no pgrep guess)"
  echo "### CMD: kill -TERM $PID"
  kill -TERM "$PID"
  wait "$PID"
  RC=$?
  echo "probe exit code after SIGTERM: $RC  (90 = trap restore path)"
  assert "probe exit code is exactly 90 (trap restore path)" "90" "$RC"
else
  echo "corruption NOT observed within 120s (probe alive: $(kill -0 "$PID" 2>/dev/null && echo yes || echo no)) — test cannot exercise the trap, reporting FAIL"
  kill -TERM "$PID" 2>/dev/null
  wait "$PID" 2>/dev/null
  FAILS=$((FAILS+1))
fi

echo
echo "### CMD: grep -c corrupted-constant SelfTest.java   (must be 0)"
if grep -q "$BAD" "$TARGET"; then
  echo "CORRUPTION STILL PRESENT — TRAP FAILED"
  FAILS=$((FAILS+1))
else
  echo "0 — corrupted constant gone"
fi
echo
echo "### CMD: git status --porcelain -- SelfTest.java   (must be empty)"
ST="$(git -C "$REPO" status --porcelain -- android/src/com/mazawallet/crypto/SelfTest.java)"
echo "${ST:-<empty>}  (empty = restored byte-identical to committed content)"
assert "tree clean after interruption" "" "$ST"
echo
echo "### CMD: tail of the interrupted probe log"
tail -3 "$PROBE_LOG"

echo
echo "## trap test summary: FAILS=$FAILS"
if [ "$FAILS" -eq 0 ]; then
  echo "TRAP TEST RESULT: PASS"
  echo "TRAP TEST EXIT CODE: 0"
  exit 0
fi
echo "TRAP TEST RESULT: FAIL"
echo "TRAP TEST EXIT CODE: 1"
exit 1
