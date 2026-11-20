#!/bin/bash
# maza-indexer-watchdog-selftest — offline classification tests for
# maza-indexer-watchdog.sh.  Stubs curl/systemctl via PATH; every scenario
# runs in throwaway state/log dirs; no network is touched (no token is
# provided, so notify() logs ALERT-NO-TOKEN / suppression happens before any
# curl).  Hermeticity: MAZA_WATCHDOG_ENV points at an ABSENT file so a live
# env file can never leak into a scenario (M16-b lesson).
#
# Exit 0 = every assertion passed; 1 = at least one FAIL line above.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG="$HERE/maza-indexer-watchdog.sh"
WORK="$(mktemp -d /tmp/maza-idx-wd-selftest.XXXXXX)" || { echo "FATAL: mktemp failed — read-only /tmp? The selftest needs a writable temp dir."; exit 1; }
[ -n "$WORK" ] && [ -d "$WORK" ] || { echo "FATAL: empty work dir — aborting instead of cascading misleading failures."; exit 1; }
trap 'rm -rf "$WORK"' EXIT

PASS=0; FAIL=0
ok()   { PASS=$((PASS + 1)); echo "PASS $1"; }
bad()  { FAIL=$((FAIL + 1)); echo "FAIL $1"; }
assert_log_contains()    { grep -qF "$2" "$1" && ok "$3" || bad "$3 (missing: $2)"; }
assert_log_not_contains(){ grep -qF "$2" "$1" && bad "$3 (unexpected: $2)" || ok "$3"; }

# --- Stub environment ----------------------------------------------------------
STUB="$WORK/stub"; mkdir -p "$STUB"
CTRL="$WORK/ctrl"; mkdir -p "$CTRL"
RESP="$WORK/resp"; mkdir -p "$RESP"

HEALTHY='{"ok": true, "height": 100, "chain": "main", "txs_indexed": 5, "crawler_progress_age_s": 12.5}
0.050 200'
STALLED='{"ok": true, "height": 100, "chain": "main", "txs_indexed": 5, "crawler_progress_age_s": 999.0}
0.050 200'
STARTUP='{"ok": true, "height": 100, "chain": "main", "txs_indexed": 5, "crawler_progress_age_s": null}
0.050 200'
GARBAGE='this is not json at all
0.050 200'
DOWN='curl: (7) Failed to connect to 127.0.0.1 port 18711
0.000 000'

printf '%s\n' "$HEALTHY" > "$RESP/healthy"
printf '%s\n' "$STALLED" > "$RESP/stalled"
printf '%s\n' "$STARTUP" > "$RESP/startup"
printf '%s\n' "$GARBAGE" > "$RESP/garbage"
printf '%s\n' "$DOWN"    > "$RESP/down"

cat > "$STUB/curl" <<'EOF'
#!/bin/bash
# Response-file sequence stub for the WATCHDOG PROBE calls only: the Nth
# probe call cats $MAZA_SELFTEST_RESP/resp-N (falling back to resp-last,
# else resp-1).  Telegram notify() calls are NOT probes — they must never
# consume a sequence slot (a notify curl mid-heal would otherwise shift
# the readiness polls onto the wrong responses); they answer from
# $CTRL/tg-response (default {"ok":false} = send failed, no stamp).
case "$*" in
  *api.telegram.org*)
    cat "$CTRL/tg-response" 2>/dev/null || printf '{"ok":false}'
    exit 0 ;;
esac
d="$MAZA_SELFTEST_RESP"
n="$d/curln"
i=$(cat "$n" 2>/dev/null || echo 0); i=$((i + 1)); echo "$i" > "$n"
f="$d/resp-$i"
[ -r "$f" ] || f="$d/resp-last"
[ -r "$f" ] || f="$d/resp-1"
cat "$f"
EOF

cat > "$STUB/systemctl" <<'EOF'
#!/bin/bash
echo "$*" >> "$CTRL/calls.log"
case "$1" in
  is-active) cat "$CTRL/unit-state" 2>/dev/null || echo inactive ;;
  restart)
    # $CTRL/sysctl-restart-fail present -> the restart COMMAND itself fails
    # (distinct RESTART-FAILED class, judge round-2 polish fold).
    if [ -e "$CTRL/sysctl-restart-fail" ]; then exit 1; fi
    exit 0 ;;
esac
exit 0
EOF
chmod +x "$STUB/curl" "$STUB/systemctl"

export CTRL
export MAZA_SELFTEST_RESP="$RESP"

run_wd() { # run_wd <tag> — scenario dirs + env, then run the watchdog once
  local tag="$1"
  local sd="$WORK/$tag/state" lg="$WORK/$tag/log"
  mkdir -p "$sd" "$WORK/$tag"
  : > "$lg"; : > "$CTRL/calls.log"
  echo 0 > "$RESP/curln"
  MAZA_WATCHDOG_SELFTEST=1 \
  MAZA_WATCHDOG_ENV="$WORK/absent.env" \
  MAZA_WATCHDOG_STATE_DIR="$sd" \
  MAZA_WATCHDOG_LOG="$lg" \
  MAZA_WATCHDOG_READINESS_POLLS="${RP:-2}" \
  MAZA_WATCHDOG_DOUBLE_PROBE_SECS="${DP:-0}" \
  MAZA_INDEXER_LAT_SAMPLES="${LS:-50}" \
  PATH="$STUB:$PATH" \
    bash "$WATCHDOG" >> "$lg.out" 2>&1
  echo "$?"
}

seq_wd() { # seq_wd <tag> <r1> [r2...] — clean prior responses, stage resp-N files
  local tag="$1"; shift
  rm -f "$RESP"/resp-[0-9]* "$RESP/resp-last"   # no stale responses bleed across scenarios
  echo 0 > "$RESP/curln"
  local i=1
  for r in "$@"; do
    cp "$RESP/$r" "$RESP/resp-$i"
    i=$((i + 1))
  done
  cp "$RESP/resp-$((i - 1))" "$RESP/resp-last"
}

# --- S1 healthy -----------------------------------------------------------------
seq_wd s1 healthy
rc=$(run_wd s1)
[ "$rc" = "0" ] && ok "S1 exit 0" || bad "S1 exit code $rc"
assert_log_contains "$WORK/s1/log" "OK code=200 lat=50ms p95=50ms h=100 age=12.5s samples=1" "S1 healthy OK line (lat+p95+height+age)"
assert_log_not_contains "$WORK/s1/log" "HEAL-START" "S1 no heal on healthy"
[ "$(cat "$WORK/s1/state/lat-samples" 2>/dev/null)" = "50" ] && ok "S1 latency sample recorded" || bad "S1 sample missing: $(cat "$WORK/s1/state/lat-samples" 2>/dev/null)"

# --- S2 probe-down -> heal OK -----------------------------------------------------
seq_wd s2 down down healthy
rc=$(run_wd s2)
[ "$rc" = "0" ] && ok "S2 exit 0" || bad "S2 exit code $rc"
assert_log_contains "$WORK/s2/log" "HEAL-START restart=maza-indexer.service reason=probe-down" "S2 heal started on 2x probe-down"
assert_log_contains "$WORK/s2/log" "HEAL-OK" "S2 heal OK after readiness"
grep -qF "restart maza-indexer.service" "$CTRL/calls.log" && ok "S2 systemctl restart invoked" || bad "S2 no restart in calls.log"
[ "$(cat "$WORK/s2/state/heal-streak" 2>/dev/null)" = "0" ] && ok "S2 streak reset on recovery" || bad "S2 streak=$(cat "$WORK/s2/state/heal-streak" 2>/dev/null)"

# --- S3 probe-down -> heal FAILED --------------------------------------------------
seq_wd s3 down down down
rc=$(run_wd s3)
[ "$rc" = "0" ] && ok "S3 exit 0" || bad "S3 exit code $rc"
assert_log_contains "$WORK/s3/log" "HEAL-FAILED" "S3 heal failed when readiness never passes"
[ "$(cat "$WORK/s3/state/heal-streak" 2>/dev/null)" = "1" ] && ok "S3 streak incremented" || bad "S3 streak=$(cat "$WORK/s3/state/heal-streak" 2>/dev/null)"

# --- S4 escalate at MAX_CONSEC_HEALS (no restart attempted) ------------------------
seq_wd s4 down down down
mkdir -p "$WORK/s4/state"
echo 3 > "$WORK/s4/state/heal-streak"
rc=$(run_wd s4)
[ "$rc" = "0" ] && ok "S4 exit 0" || bad "S4 exit code $rc"
assert_log_contains "$WORK/s4/log" "HEAL-BOUNDED class=ESCALATE streak=3" "S4 escalates at max consecutive heals"
grep -qF "restart" "$CTRL/calls.log" && bad "S4 restart attempted past bound" || ok "S4 no restart past the bound"

# --- S5 crawler stalled -> heal OK ---------------------------------------------------
seq_wd s5 stalled stalled healthy
rc=$(run_wd s5)
[ "$rc" = "0" ] && ok "S5 exit 0" || bad "S5 exit code $rc"
assert_log_contains "$WORK/s5/log" "WARN crawler age 999.0s > 300s" "S5 stall detected (age over threshold)"
assert_log_contains "$WORK/s5/log" "HEAL-START restart=maza-indexer.service reason=crawler-stalled" "S5 stall heal started"
assert_log_contains "$WORK/s5/log" "HEAL-OK" "S5 stall heal OK"
grep -qF "restart maza-indexer.service" "$CTRL/calls.log" && ok "S5 restart invoked for stall" || bad "S5 no restart"

# --- S6 stall double-probe passes -> no heal ----------------------------------------
seq_wd s6 stalled healthy
rc=$(run_wd s6)
[ "$rc" = "0" ] && ok "S6 exit 0" || bad "S6 exit code $rc"
assert_log_contains "$WORK/s6/log" "TRANSIENT-RECOVERED (stall double-probe passed" "S6 stall recovered on double-probe"
assert_log_not_contains "$WORK/s6/log" "HEAL-START" "S6 no heal when double-probe passes"
grep -qF "restart" "$CTRL/calls.log" && bad "S6 restart on a recovered stall" || ok "S6 no restart"

# --- S7 startup null age -> no stall eval -------------------------------------------
seq_wd s7 startup
rc=$(run_wd s7)
[ "$rc" = "0" ] && ok "S7 exit 0" || bad "S7 exit code $rc"
assert_log_contains "$WORK/s7/log" "age=startup" "S7 null age logged as startup"
assert_log_not_contains "$WORK/s7/log" "WARN" "S7 no stall eval on null age"

# --- S8 garbage body -> answered-200, no heal (fail-safe) ----------------------------
seq_wd s8 garbage
rc=$(run_wd s8)
[ "$rc" = "0" ] && ok "S8 exit 0" || bad "S8 exit code $rc"
assert_log_contains "$WORK/s8/log" "OK code=200" "S8 200-with-garbage is not a down"
assert_log_not_contains "$WORK/s8/log" "HEAL-START" "S8 no heal on unparsable age (unavailable signal never aggresses)"

# --- S9 alert cooldown suppression (stamp pre-seeded, no token needed) ---------------
seq_wd s9 down down healthy
mkdir -p "$WORK/s9/state"
date +%s > "$WORK/s9/state/alert-HEALED"
rc=$(run_wd s9)
[ "$rc" = "0" ] && ok "S9 exit 0" || bad "S9 exit code $rc"
assert_log_contains "$WORK/s9/log" "ALERT-SUPPRESSED class=HEALED" "S9 suppressed repeat within cooldown"

# --- S10 p95 window caps at LAT_SAMPLES ----------------------------------------------
seq_wd s10 healthy
# run_wd seeds 1 sample (default LS); then 5 more cycles with LS=5 ->
# 6 samples recorded into a 5-slot window -> trimmed to exactly 5.
rc=$(run_wd s10)
i=2
while [ "$i" -le 6 ]; do
  cp "$RESP/healthy" "$RESP/resp-$i"
  i=$((i + 1))
done
cp "$RESP/healthy" "$RESP/resp-last"
# run exactly 5 extra cycles (each appends 1 sample; from cycle 6 on the
# trim keeps the file at exactly LAT_SAMPLES lines — never size-conditional,
# the cap makes a size-based while condition unsatisfiable).
c=0
while [ "$c" -lt 5 ]; do
  MAZA_WATCHDOG_SELFTEST=1 \
  MAZA_WATCHDOG_ENV="$WORK/absent.env" \
  MAZA_WATCHDOG_STATE_DIR="$WORK/s10/state" \
  MAZA_WATCHDOG_LOG="$WORK/s10/log" \
  MAZA_WATCHDOG_READINESS_POLLS=2 MAZA_WATCHDOG_DOUBLE_PROBE_SECS=0 \
  MAZA_INDEXER_LAT_SAMPLES=5 PATH="$STUB:$PATH" \
    bash "$WATCHDOG" >/dev/null 2>&1
  c=$((c + 1))
done
[ "$(wc -l < "$WORK/s10/state/lat-samples")" = "5" ] && ok "S10 sample window capped at 5" || bad "S10 window size $(wc -l < "$WORK/s10/state/lat-samples")"
assert_log_contains "$WORK/s10/log" "p95=50ms" "S10 p95 computed over the window"

# --- S11 script parse patterns present (python cross-pin counterpart) -----------------
grep -qE "^AGE_SED='.*'$" "$WATCHDOG" && ok "S11 AGE_SED pattern line present" || bad "S11 AGE_SED line missing"
grep -qE "^HEIGHT_SED='.*'$" "$WATCHDOG" && ok "S11 HEIGHT_SED pattern line present" || bad "S11 HEIGHT_SED line missing"

# --- S12 restart COMMAND fails -> distinct RESTART-FAILED class -----------------------
seq_wd s12 down down down
touch "$CTRL/sysctl-restart-fail"
rc=$(run_wd s12)
rm -f "$CTRL/sysctl-restart-fail"
[ "$rc" = "0" ] && ok "S12 exit 0" || bad "S12 exit code $rc"
assert_log_contains "$WORK/s12/log" "RESTART-FAILED systemctl exit=1" "S12 restart-command failure reported distinctly"
assert_log_contains "$WORK/s12/log" "HEAL-FAILED" "S12 heal still fails honestly when the restart command failed"
[ "$(cat "$WORK/s12/state/heal-streak" 2>/dev/null)" = "1" ] && ok "S12 streak incremented past a failed restart command" || bad "S12 streak=$(cat "$WORK/s12/state/heal-streak" 2>/dev/null)"

# --- S13 (judge r2 blocker): stalled + restart FAILS + probe STAYS 200-stalled -------
# The false-success shape: the API keeps answering 200 through a crawler
# stall, so a readiness-only recovery check would log HEAL-OK and reset the
# streak.  A failed restart command must be a FAILED heal: no HEAL-OK, no
# HEALED class, streak incremented.
seq_wd s13 stalled stalled stalled
touch "$CTRL/sysctl-restart-fail"
rc=$(run_wd s13)
rm -f "$CTRL/sysctl-restart-fail"
[ "$rc" = "0" ] && ok "S13 exit 0" || bad "S13 exit code $rc"
assert_log_contains "$WORK/s13/log" "RESTART-FAILED systemctl exit=1" "S13 restart-command failure reported"
assert_log_contains "$WORK/s13/log" "HEAL-FAILED streak=1 (restart command failed)" "S13 failed restart recorded as a FAILED heal"
assert_log_not_contains "$WORK/s13/log" "HEAL-OK" "S13 no false HEAL-OK on 200-but-stalled"
assert_log_not_contains "$WORK/s13/log" "class=HEALED" "S13 no HEALED alert class"
[ "$(cat "$WORK/s13/state/heal-streak" 2>/dev/null)" = "1" ] && ok "S13 streak NOT reset by the healthy-looking probe" || bad "S13 streak=$(cat "$WORK/s13/state/heal-streak" 2>/dev/null)"

# --- S14 restart OK but readiness probe STILL stalled -> HEAL-FAILED ------------------
# The other false-success half: the restart executes, the API answers 200,
# but the age is still over the threshold -> recovery must NOT be declared.
seq_wd s14 stalled stalled stalled
rc=$(run_wd s14)
[ "$rc" = "0" ] && ok "S14 exit 0" || bad "S14 exit code $rc"
assert_log_contains "$WORK/s14/log" "HEAL-FAILED streak=1" "S14 stall heal fails when the age never clears"
assert_log_not_contains "$WORK/s14/log" "HEAL-OK" "S14 no HEAL-OK while the age stays over threshold"
[ "$(cat "$WORK/s14/state/heal-streak" 2>/dev/null)" = "1" ] && ok "S14 streak incremented" || bad "S14 streak=$(cat "$WORK/s14/state/heal-streak" 2>/dev/null)"

# --- S15 fully healthy cycle resets a prior failed-heal streak ------------------------
seq_wd s15 healthy
mkdir -p "$WORK/s15/state"
echo 2 > "$WORK/s15/state/heal-streak"
rc=$(run_wd s15)
[ "$rc" = "0" ] && ok "S15 exit 0" || bad "S15 exit code $rc"
assert_log_contains "$WORK/s15/log" "OK code=200" "S15 healthy cycle logged"
[ "$(cat "$WORK/s15/state/heal-streak" 2>/dev/null)" = "0" ] && ok "S15 healthy cycle cleared the failed-heal streak" || bad "S15 streak=$(cat "$WORK/s15/state/heal-streak" 2>/dev/null)"

# --- S16 (judge r3 blocker): stalled -> restart OK -> 200 GARBAGE body -> HEAL-FAILED -
# The exact demanded pin: a successful restart followed by HTTP 200 with a
# malformed/unparseable body is NO evidence the stall cleared.  Readiness
# must fail closed: HEAL-FAILED, streak preserved, NO HEAL-OK.
seq_wd s16 stalled stalled garbage garbage garbage
rc=$(run_wd s16)
[ "$rc" = "0" ] && ok "S16 exit 0" || bad "S16 exit code $rc"
assert_log_contains "$WORK/s16/log" "HEAL-START restart=maza-indexer.service reason=crawler-stalled" "S16 stall heal started"
assert_log_contains "$WORK/s16/log" "HEAL-FAILED streak=1" "S16 garbage-200 readiness fails closed"
assert_log_not_contains "$WORK/s16/log" "HEAL-OK" "S16 no HEAL-OK on unparseable readiness probes"
[ "$(cat "$WORK/s16/state/heal-streak" 2>/dev/null)" = "1" ] && ok "S16 streak preserved" || bad "S16 streak=$(cat "$WORK/s16/state/heal-streak" 2>/dev/null)"

# --- S17 contrast: explicit JSON null after restart IS recovery -----------------------
# Same shape as S16 but the post-restart body carries the EXPLICIT null
# (fresh crawler, never ran): that is a real "age cleared" signal -> HEAL-OK.
seq_wd s17 stalled stalled startup startup
rc=$(run_wd s17)
[ "$rc" = "0" ] && ok "S17 exit 0" || bad "S17 exit code $rc"
assert_log_contains "$WORK/s17/log" "HEAL-OK" "S17 explicit-null readiness declares recovery"
[ "$(cat "$WORK/s17/state/heal-streak" 2>/dev/null)" = "0" ] && ok "S17 streak reset on real recovery" || bad "S17 streak=$(cat "$WORK/s17/state/heal-streak" 2>/dev/null)"

echo "-----"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = "0" ]
