#!/bin/bash
# verify-read-only.sh — zero-write checks for the IDX-9c-ii changeset,
# designed for a READ-ONLY review sandbox (no mktemp, no new files, no
# network): bash -n syntax, python ast.parse syntax (python3 -B, no .pyc),
# the watchdog's own sed parse patterns against an embedded body literal,
# the p95 index formula against a python math.ceil baseline, and the timer
# initial trigger.  Prints CHECK ... OK/FAIL lines; exit 0 = all passed.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILS=0
ck() { # ck <label> <rc>
  if [ "$2" = "0" ]; then echo "CHECK $1: OK"; else echo "CHECK $1: FAIL"; FAILS=$((FAILS + 1)); fi
}

# 1-2: shell syntax (bash -n writes nothing)
bash -n "$HERE/maza-indexer-watchdog.sh" 2>/dev/null; ck "bash -n maza-indexer-watchdog.sh" $?
bash -n "$HERE/maza-indexer-watchdog-selftest.sh" 2>/dev/null; ck "bash -n maza-indexer-watchdog-selftest.sh" $?

# 3-5: python syntax via ast.parse (no bytecode writes with -B)
for f in maza_indexer/ingest.py maza_indexer/api.py tests/test_maza_indexer_liveness.py; do
  python3 -B -c "import ast,sys; ast.parse(open(sys.argv[1], encoding='utf-8').read())" \
    "$HERE/../../$f" 2>/dev/null
  ck "python syntax $f" $?
done

# 6-8: the watchdog's OWN sed patterns against a real emission-shape body.
# Read the patterns from the script so this check cannot drift from it.
AGE_SED=$(grep -E "^AGE_SED=" "$HERE/maza-indexer-watchdog.sh" | head -1 | sed "s/^AGE_SED='//; s/'$//")
HEIGHT_SED=$(grep -E "^HEIGHT_SED=" "$HERE/maza-indexer-watchdog.sh" | head -1 | sed "s/^HEIGHT_SED='//; s/'$//")
BODY_OK='{"ok": true, "height": 100, "chain": "main", "txs_indexed": 5, "crawler_progress_age_s": 12.5}'
BODY_NULL='{"ok": true, "height": 100, "chain": "main", "txs_indexed": 5, "crawler_progress_age_s": null}'
AGE=$(printf '%s' "$BODY_OK" | sed -n "$AGE_SED" | head -n 1)
[ "$AGE" = "12.5" ]; ck "AGE_SED extracts float age from health body ($AGE)" $?
AGE_NULL=$(printf '%s' "$BODY_NULL" | sed -n "$AGE_SED" | head -n 1)
[ -z "$AGE_NULL" ]; ck "AGE_SED yields empty on null age" $?
H=$(printf '%s' "$BODY_OK" | sed -n "$HEIGHT_SED" | head -n 1)
[ "$H" = "100" ]; ck "HEIGHT_SED extracts height ($H)" $?

# 9: p95 index formula == ceil(0.95*n) for n=1..50, bash awk vs python.
BAD=0
for n in $(seq 1 50); do
  A=$(awk "BEGIN{printf \"%d\", (95*$n+99)/100}")
  P=$(python3 -B -c "import math; print(math.ceil(0.95*$n))")
  [ "$A" = "$P" ] || BAD=1
done
ck "p95 index formula == python math.ceil for n=1..50" $BAD

# 10: timer initial trigger (round-1 blocker 1's static half)
grep -qE "^OnBootSec=60s$" "$HERE/maza-indexer-watchdog.timer" 2>/dev/null
ck "timer OnBootSec=60s present" $?

echo
if [ "$FAILS" = "0" ]; then echo "VERIFY-READ-ONLY: ALL PASS"; exit 0
else echo "VERIFY-READ-ONLY: $FAILS FAILURES"; exit 1; fi
