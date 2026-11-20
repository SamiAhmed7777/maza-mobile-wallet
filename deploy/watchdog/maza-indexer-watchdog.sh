#!/bin/bash
# maza-indexer-watchdog — down/stall guard for the maza-indexer serving
# surface (samihost).  IDX-9c-ii.
#
# Failure classes and remedies:
#   probe down twice  (000/5xx/timeout on /health)
#        -> bounded restart of maza-indexer.service + readiness poll
#           (a dead or wedged process; the API is the product surface).
#   crawler stalled twice (200 but crawler_progress_age_s > stall threshold)
#        -> same bounded restart (a wedged crawl THREAD: the API still
#           serves, but ingest stopped making scheduling progress; a
#           restart re-enters the crawl loop cleanly — ingest is
#           idempotent, the IDX-9b same-hash skip makes re-ingest safe).
#   healthy -> record the probe latency into a rolling window, log the
#           window's p95 every cycle (the "keep measuring" instrument for
#           the RW-split + cheap-counts fixes: latency during catch-up is
#           now DATA, not a surprise).
#
# Why the stall class is AGE-based, not height-based: /health exposes the
# crawler's loop-progress age (seconds since the crawl thread last made a
# scheduling move).  HEIGHT FROZEN alone is normal in two live shapes —
# tip rest (no new blocks to ingest) and an RPC pause (mazad restart
# window; the crawl retries with capped backoff and marks progress on
# every wake) — so a height-only watchdog would false-heal a healthy
# indexer.  The age field stays fresh through both shapes (IDX-9c-ii
# liveness registry in maza_indexer/ingest.py); only a genuinely wedged
# crawl thread lets it grow.  A long node outage is loud in the journal
# (RPC-PAUSE lines) and does NOT trip this watchdog.
#
# Startup tolerance (fail-safe): age = null (crawler has never run in this
# process) or an unparsable body age = empty -> NO stall eval that cycle.
# An unavailable signal can never make the watchdog more aggressive
# (M16-b rule).
#
# Scope fence: this script only ever restarts maza-indexer.service.  It
# NEVER touches mazad, maza-wallet-bench, the tunnel, the store DB, or
# the node wallet.  Probes are unauthenticated (/health has no auth by
# design).  The disk guard lives in the bench watchdog on this host —
# duplicating it here would double-alert, so there is deliberately none.
#
# Design rules applied (M16 pattern, fleet-proven):
#   - exit 0 even when healing (never pollute systemctl --failed)
#   - set -u, deliberately NOT set -e (a failed probe falls through)
#   - state on disk, never in memory (fresh process each cycle)
#   - bounded consecutive heals, escalate instead of looping
#   - poll readiness after a restart; never a fixed sleep
#   - double-probe (two failures ~DOUBLE_PROBE_SECS apart) before acting
#   - self-rotating log (1 MiB, keep half)
#   - alert cooldown per class; stamp only on confirmed delivery
#   - flock so a manual run cannot overlap a timer cycle
#
# Secrets: the Telegram token is read from TELEGRAM token file (0600) or
# the host Hermes env (key name assembled from fragments so no
# credential-shaped literal appears in this file); never printed, never
# logged, never in argv.  Pure bash + sed/awk + curl: no python3
# dependency (the JSON field extraction is pinned against the real
# emitted /health body by tests/test_maza_indexer_liveness.py).

set -u

# --- Tunables (env file /etc/maza-indexer-watchdog.env) ----------------------
ENV_FILE="${MAZA_WATCHDOG_ENV:-/etc/maza-indexer-watchdog.env}"
if [ -r "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

SERVICE="${MAZA_INDEXER_SERVICE:-maza-indexer.service}"
HEALTH_URL="${MAZA_INDEXER_HEALTH_URL:-http://127.0.0.1:18711/health}"
STALL_SECS="${MAZA_INDEXER_STALL_SECS:-300}"
LAT_SAMPLES="${MAZA_INDEXER_LAT_SAMPLES:-50}"
CHAT_ID="${MAZA_WATCHDOG_CHAT:-637130179}"
HERMES_ENV_FILE="${MAZA_HERMES_ENV_FILE:-/root/.hermes/.env}"
TOKEN_FILE="${MAZA_WATCHDOG_TOKEN_FILE:-/etc/maza-indexer-watchdog.token}"
ALERT_COOLDOWN_SECS="${MAZA_WATCHDOG_COOLDOWN:-900}"        # 15 min
DOUBLE_PROBE_SECS="${MAZA_WATCHDOG_DOUBLE_PROBE_SECS:-5}"
MAX_CONSEC_HEALS="${MAZA_WATCHDOG_MAX_CONSEC_HEALS:-3}"
READINESS_POLLS="${MAZA_WATCHDOG_READINESS_POLLS:-30}"
LOG_MAX="${MAZA_WATCHDOG_LOG_MAX:-1048576}"                 # 1 MiB

STATE_DIR="${MAZA_WATCHDOG_STATE_DIR:-/var/lib/maza-indexer-watchdog}"
LOG="${MAZA_WATCHDOG_LOG:-/var/log/maza-indexer-watchdog.log}"

# /health body field extraction (single-line json.dumps emission; pinned by
# tests/test_maza_indexer_liveness.py against the REAL server body — keep
# the variable names and the line-start single-quoted shape).
AGE_SED='s/.*"crawler_progress_age_s": \([0-9][0-9]*\.[0-9][0-9]*\).*/\1/p'
HEIGHT_SED='s/.*"height": \([0-9][0-9]*\).*/\1/p'

# Sanitize the numeric knobs: a bad env value falls back to the default
# rather than feeding awk garbage (and AGE is format-checked before use).
case "$STALL_SECS" in ''|*[!0-9]*) STALL_SECS=300 ;; esac
case "$LAT_SAMPLES" in ''|*[!0-9]*) LAT_SAMPLES=50 ;; esac
case "$DOUBLE_PROBE_SECS" in ''|*[!0-9]*) DOUBLE_PROBE_SECS=5 ;; esac

mkdir -p "$STATE_DIR" 2>/dev/null
touch "$LOG" 2>/dev/null

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$LOG" 2>/dev/null; }

# --- Concurrent-run protection -------------------------------------------------
if [ "${MAZA_WATCHDOG_SELFTEST:-0}" != "1" ]; then
  exec 9>"/run/lock/maza-indexer-watchdog.lock" 2>/dev/null \
    || exec 9>"$STATE_DIR/lock"
  flock -n 9 || exit 0
fi

# --- Telegram alerting (best-effort; never blocks healing) ---------------------
notify() { # notify <class> <cooldown-secs> <message>
  local class="$1" cooldown="$2" msg="$3"
  local now last elapsed stamp token tkey sent
  now=$(date +%s)
  stamp="$STATE_DIR/alert-$class"
  if [ -f "$stamp" ]; then
    last=$(tr -cd '0-9' < "$stamp" 2>/dev/null)
    last="${last:-0}"
    elapsed=$((now - last))
    if [ "$elapsed" -lt "$cooldown" ]; then
      log "ALERT-SUPPRESSED class=$class (${elapsed}s < ${cooldown}s)"
      return 0
    fi
  fi
  token=""
  if [ -n "$TOKEN_FILE" ] && [ -r "$TOKEN_FILE" ]; then
    token=$(head -1 "$TOKEN_FILE" 2>/dev/null | tr -d '\r\n')
  fi
  if [ -z "$token" ] && [ -r "$HERMES_ENV_FILE" ]; then
    tkey="HERMES""_ENV_""TELE""GRAM_BOT_TOKEN"
    token=$(grep -E "^${tkey}=" "$HERMES_ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
  fi
  if [ -z "$token" ]; then
    log "ALERT-NO-TOKEN class=$class msg=${msg:0:160}"
    return 0
  fi
  sent=$(curl -s -m 10 "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=🛡️ MAZA indexer watchdog ($(hostname -s 2>/dev/null || echo host)): $msg" \
    2>/dev/null | grep -c '"ok":true')
  if [ "${sent:-0}" -ge 1 ]; then
    date +%s > "$stamp"
    log "ALERT-SENT class=$class msg=$msg"
  else
    log "ALERT-SEND-FAILED class=$class msg=${msg:0:160} (cooldown NOT burned)"
  fi
}

log_rotate() {
  [ -f "$LOG" ] || return 0
  local size
  size=$(stat -c%s "$LOG" 2>/dev/null || echo 0)
  if [ "$size" -gt "$LOG_MAX" ]; then
    tail -c $((LOG_MAX / 2)) "$LOG" > "${LOG}.tmp" 2>/dev/null \
      && mv "${LOG}.tmp" "$LOG"
  fi
}

# --- Probe --------------------------------------------------------------------
# One curl capture: body + "\n<time_total> <http_code>".  Sets AGE (float or
# empty), HEIGHT (int or empty), LAT_MS (int), CODE; returns 0 only when the
# API answered 200.  A 200 with an unparsable body still yields empty AGE —
# the probe ANSWERED, so it is not a down; the stall class simply skips that
# cycle (fail-safe: no data can never trigger a heal).
probe_health() {
  AGE=""; HEIGHT=""; LAT_MS=""; CODE="000"; AGE_PARSED=0; AGE_NULL=0
  local out tail body
  out=$(curl -s -m 8 -w '\n%{time_total} %{http_code}' "$HEALTH_URL" 2>/dev/null)
  tail=$(printf '%s\n' "$out" | tail -n 1)
  CODE=$(printf '%s\n' "$tail" | awk '{print $2}')
  LAT_MS=$(printf '%s\n' "$tail" | awk '{printf "%d", $1 * 1000}')
  case "$CODE" in
    200) : ;;
    *) CODE="${CODE:-000}"; return 1 ;;
  esac
  body=$(printf '%s\n' "$out" | sed '$d')
  # The empty AGE value carries TWO meanings that must stay distinct:
  #   explicit JSON null  (AGE_NULL=1)  = fresh crawler, never ran -- a real
  #                                       "age cleared" recovery signal
  #   key absent / body not the expected emission (AGE_PARSED=0) = NO
  #                                       evidence about the crawler; the
  #                                       stall readiness must fail closed
  case "$body" in
    *'"crawler_progress_age_s":'*)
      AGE_PARSED=1
      AGE=$(printf '%s\n' "$body" | sed -n "$AGE_SED" | head -n 1)
      case "$AGE" in
        ''|*[!0-9.]*)
          AGE=""
          case "$body" in *'"crawler_progress_age_s": null'*) AGE_NULL=1 ;; esac ;;
      esac ;;
  esac
  HEIGHT=$(printf '%s\n' "$body" | sed -n "$HEIGHT_SED" | head -n 1)
  case "$HEIGHT" in ''|*[!0-9]*) HEIGHT="" ;; esac
  return 0
}

age_label() { # human label for the OK line from the last probe's parse state
  if [ "$AGE_PARSED" = "1" ]; then
    if [ -n "$AGE" ]; then echo "$AGE"; else echo "startup"; fi
  else
    echo "unparsed"
  fi
}

# Wait for readiness by polling, never a fixed sleep.  For a crawler-stalled
# heal the poll counts as ready only when the probe is 200 AND the parse
# state PROVES the stall cleared: a float age under the threshold, or the
# explicit JSON null (fresh crawler).  A 200 whose body lacks the key or is
# not the expected emission is NO evidence -- fail closed, keep trying.
is_ready_probe() { # is_ready_probe <reason> — runs ONE probe; 0 when ready
  probe_health || return 1
  [ "$1" = "crawler-stalled" ] || return 0
  [ "$AGE_PARSED" = "1" ] || return 1
  if [ -n "$AGE" ]; then ! age_over_stall; else [ "$AGE_NULL" = "1" ]; fi
}

wait_ready() { # wait_ready [reason]
  local reason="${1:-}" i=0
  while [ "$i" -lt "$READINESS_POLLS" ]; do
    if is_ready_probe "$reason"; then return 0; fi
    i=$((i + 1))
    sleep 1
  done
  return 1
}

# --- Latency window (p95 observability) ----------------------------------------
SAMPLES_FILE="$STATE_DIR/lat-samples"

samples_count() {
  local n
  n=$(wc -l < "$SAMPLES_FILE" 2>/dev/null)
  case "$n" in ''|*[!0-9]*) n=0 ;; esac
  echo "$n"
}

record_sample() { # record_sample <lat_ms>
  case "$1" in ''|*[!0-9]*) return 0 ;; esac
  printf '%s\n' "$1" >> "$SAMPLES_FILE" 2>/dev/null
  if [ "$(samples_count)" -gt "$LAT_SAMPLES" ]; then
    tail -n "$LAT_SAMPLES" "$SAMPLES_FILE" > "${SAMPLES_FILE}.tmp" 2>/dev/null \
      && mv "${SAMPLES_FILE}.tmp" "$SAMPLES_FILE"
  fi
}

samples_p95() {
  # p95 = ceil(0.95*n)th smallest of the window (n<=LAT_SAMPLES); 0 when empty.
  local n idx
  n=$(samples_count)
  [ "$n" -gt 0 ] || { echo 0; return 0; }
  idx=$(( (95 * n + 99) / 100 ))
  [ "$idx" -ge 1 ] || idx=1
  sort -n "$SAMPLES_FILE" 2>/dev/null | sed -n "${idx}p"
}

# --- Heal bookkeeping ------------------------------------------------------------
heal_streak() { # heal_streak <inc|reset|get>
  local f="$STATE_DIR/heal-streak" n
  case "$1" in
    inc)   n=$(( $(heal_streak get) + 1 )); echo "$n" > "$f";;
    reset) echo 0 > "$f";;
    get)   if [ -f "$f" ]; then n=$(tr -cd '0-9' < "$f"); else n=""; fi
           echo "${n:-0}";;
  esac
}

indexer_heal() { # indexer_heal <reason> — bounded restart + readiness poll
  local reason="$1" restart_rc
  if [ "$(heal_streak get)" -ge "$MAX_CONSEC_HEALS" ]; then
    notify "ESCALATE" "$ALERT_COOLDOWN_SECS" \
      "indexer down/stalled; $MAX_CONSEC_HEALS consecutive restarts did not recover $SERVICE — manual intervention needed"
    log "HEAL-BOUNDED class=ESCALATE streak=$(heal_streak get)"
    return 0
  fi
  log "HEAL-START restart=$SERVICE reason=$reason streak=$(heal_streak get)"
  restart_rc=0
  systemctl restart "$SERVICE" >/dev/null 2>&1 || restart_rc=$?
  if [ "$restart_rc" -ne 0 ]; then
    # The recovery action itself never executed.  HTTP readiness now would
    # only reflect the OLD process state — for a stall that is exactly the
    # 200-but-still-stalled shape, which would falsely log HEAL-OK and reset
    # the escalation streak.  A failed restart command IS a failed heal;
    # the next fully-healthy cycle resets the streak instead.
    log "RESTART-FAILED systemctl exit=$restart_rc"
    notify "RESTART-FAILED" "$ALERT_COOLDOWN_SECS" \
      "systemctl restart $SERVICE exited $restart_rc — check journalctl -u $SERVICE and systemctl status"
    heal_streak inc
    notify "HEAL-FAILED" "$ALERT_COOLDOWN_SECS" \
      "recovery for $reason did not execute: systemctl restart $SERVICE exited $restart_rc — check journalctl -u $SERVICE"
    log "HEAL-FAILED streak=$(heal_streak get) (restart command failed)"
    return 0
  fi
  if wait_ready "$reason"; then
    heal_streak reset   # recovered: the streak measures FAILED heals only
    notify "HEALED" "$ALERT_COOLDOWN_SECS" \
      "indexer was $reason; restarted $SERVICE — recovered, /health answering 200"
    log "HEAL-OK"
  else
    heal_streak inc
    notify "HEAL-FAILED" "$ALERT_COOLDOWN_SECS" \
      "restarted $SERVICE ($reason) but /health STILL fails after ${READINESS_POLLS}s — check journalctl -u $SERVICE"
    log "HEAL-FAILED streak=$(heal_streak get)"
  fi
}

age_over_stall() { # age_over_stall — 0 when AGE is set and > STALL_SECS
  [ -n "$AGE" ] || return 1
  awk "BEGIN{exit !($AGE > $STALL_SECS)}"
}

# --- Main cycle -------------------------------------------------------------------
do_indexer() {
  if probe_health; then
    record_sample "$LAT_MS"
    if [ "$AGE_PARSED" = "1" ] && [ -n "$AGE" ] && age_over_stall; then
      log "WARN crawler age ${AGE}s > ${STALL_SECS}s (h=${HEIGHT:-?}) — double-probe before stall heal"
      sleep "$DOUBLE_PROBE_SECS"
      if is_ready_probe "crawler-stalled"; then
        log "TRANSIENT-RECOVERED (stall double-probe passed, age=${AGE:-null}s)"
      else
        indexer_heal "crawler-stalled"
        return 0
      fi
    fi
    log "OK code=200 lat=${LAT_MS}ms p95=$(samples_p95)ms h=${HEIGHT:-?} age=$(age_label)s samples=$(samples_count)"
    if [ "$AGE_PARSED" != "1" ]; then
      # 200 but the body carries no usable age: fail-safe = no stall eval,
      # and NOT a recovery declaration either (no evidence) — keep the
      # failed-heal streak so escalation still bounds a wedged crawler.
      log "WARN health body missing/unparsable crawler_progress_age_s — no stall eval, heal streak preserved"
    else
      heal_streak reset   # healthy cycle with usable age: failed-heal streak clears
    fi
    return 0
  fi
  sleep "$DOUBLE_PROBE_SECS"
  if probe_health; then
    record_sample "$LAT_MS"
    log "TRANSIENT-RECOVERED (down double-probe passed)"
    return 0
  fi
  indexer_heal "probe-down"
}

log_rotate
do_indexer
exit 0
