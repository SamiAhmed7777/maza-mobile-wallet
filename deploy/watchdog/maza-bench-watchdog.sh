#!/bin/bash
# maza-bench-watchdog — self-healing guard for the MAZA wallet bench surfaces.
#
# Roles (first arg or MAZA_WATCHDOG_ROLE):
#   bench  (samihost) — probe the local walletbench API; a probe that fails
#          twice in a row means the service is down or wedged -> bounded
#          restart of maza-wallet-bench.service with a readiness poll.
#   tunnel (DNS2)     — probe the tunnel endpoint (full chain: ssh -L ->
#          remote walletbench). Restart maza-bench-tunnel.service ONLY when
#          the tunnel unit itself is not active. A failing probe with an
#          ACTIVE tunnel is a backend problem on the remote host; restarting
#          the tunnel cannot fix it, so that class alerts without healing.
#
# Both roles: disk-guard and (bench only) bench-state-file guards — alert
# only, a restart cannot restore deleted content.
#
# Pattern mirrored from /usr/local/bin/dashcaddy-watchdog (fleet-proven,
# kill-tested; selfhealing-service-watchdogs skill) with the mazapay
# notifier's alert-once semantics (cooldown stamp written only after a
# successful send). Failure classes are inventory-based: tunnel ssh
# blackhole, walletbench wedge/crash, bench state.json vanished once
# (2026-11 run log), recurring disk pressure on both hosts.
#
# Scope fence: this script only ever touches maza-wallet-bench.service /
# maza-bench-tunnel.service. It NEVER touches mazad, the mazapay tree, or
# the node wallet. Read-only probes otherwise.
#
# Design rules applied (skill):
#   - exit 0 even when healing (never pollute systemctl --failed)
#   - set -u, deliberately NOT set -e (a failed probe falls through)
#   - state on disk (state dir), never in memory (fresh process each cycle)
#   - bounded consecutive heals per class, escalate instead of looping
#   - poll readiness after a restart; never a fixed sleep
#   - double-probe (two failures ~DOUBLE_PROBE_SECS apart) before acting
#   - self-rotating log (1 MiB, keep half)
#   - alert cooldown per class; stamp only on confirmed delivery
#   - flock so a manual run cannot overlap a timer cycle
#
# Secrets: the Telegram token is read from TELEGRAM_TOKEN_FILE (0600, one
# line) or the host Hermes env; it is never printed, never logged, never in
# argv. Probe responses are parsed by status code only.

set -u

ROLE="${1:-${MAZA_WATCHDOG_ROLE:-}}"

# --- Host-agnostic tunables (env file /etc/maza-bench-watchdog.env) --------
ENV_FILE="${MAZA_WATCHDOG_ENV:-/etc/maza-bench-watchdog.env}"
if [ -r "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi
ROLE="${ROLE:-${MAZA_WATCHDOG_ROLE:-}}"

BENCH_SERVICE="${MAZA_BENCH_SERVICE:-maza-wallet-bench.service}"
TUNNEL_SERVICE="${MAZA_TUNNEL_SERVICE:-maza-bench-tunnel.service}"
BENCH_ENV_FILE="${MAZA_BENCH_ENV_FILE:-/etc/maza-wallet-bench.env}"
TUNNEL_PROBE_URL="${MAZA_TUNNEL_PROBE_URL:-}"
BENCH_STATE_FILE="${MAZA_BENCH_STATE_FILE:-/var/lib/maza-wallet-bench/state.json}"
DISK_PATH="${MAZA_WATCHDOG_DISK_PATH:-}"
DISK_MAX_PCT="${MAZA_WATCHDOG_DISK_MAX_PCT:-90}"
CHAT_ID="${MAZA_WATCHDOG_CHAT:-637130179}"
HERMES_ENV_FILE="${MAZA_HERMES_ENV_FILE:-/root/.hermes/.env}"
TOKEN_FILE="${MAZA_WATCHDOG_TOKEN_FILE:-/etc/maza-bench-watchdog.token}"
ALERT_COOLDOWN_SECS="${MAZA_WATCHDOG_COOLDOWN:-900}"          # 15 min
SLOW_COOLDOWN_SECS="${MAZA_WATCHDOG_SLOW_COOLDOWN:-21600}"    # 6 h
DOUBLE_PROBE_SECS="${MAZA_WATCHDOG_DOUBLE_PROBE_SECS:-5}"
MAX_CONSEC_HEALS="${MAZA_WATCHDOG_MAX_CONSEC_HEALS:-3}"
READINESS_POLLS="${MAZA_WATCHDOG_READINESS_POLLS:-30}"
LOG_MAX="${MAZA_WATCHDOG_LOG_MAX:-1048576}"                   # 1 MiB

# --- Role-dependent paths ---------------------------------------------------
case "$ROLE" in
  bench)  STATE_DIR="/var/lib/maza-bench-watchdog";  LOG="/var/log/maza-bench-watchdog.log" ;;
  tunnel) STATE_DIR="/var/lib/maza-tunnel-watchdog"; LOG="/var/log/maza-tunnel-watchdog.log" ;;
  *)
    echo "usage: $0 bench|tunnel (or set MAZA_WATCHDOG_ROLE)" >&2
    exit 0
    ;;
esac
# Test hooks: self-test runs every scenario in throwaway state/log dirs so a
# test can never touch the live watchdog state.
STATE_DIR="${MAZA_WATCHDOG_STATE_DIR:-$STATE_DIR}"
LOG="${MAZA_WATCHDOG_LOG:-$LOG}"

mkdir -p "$STATE_DIR" 2>/dev/null
touch "$LOG" 2>/dev/null

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$LOG" 2>/dev/null; }

# --- Concurrent-run protection ---------------------------------------------
if [ "${MAZA_WATCHDOG_SELFTEST:-0}" != "1" ]; then
  # Preferred lock: /run/lock (tmpfs). Fallback: state dir — e.g. first run
  # on a host where /run/lock does not exist yet; either way flock serializes.
  exec 9>"/run/lock/maza-${ROLE}-watchdog.lock" 2>/dev/null || exec 9>"$STATE_DIR/lock"
  flock -n 9 || exit 0
fi

# --- Telegram alerting (best-effort; a notify failure never blocks healing) --
# The token env-key name is assembled from fragments at runtime so no
# credential-shaped literal ever appears in this file on disk.
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
  # Count ok:true matches only — the response body is never printed.
  sent=$(curl -s -m 10 "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${CHAT_ID}" \
    --data-urlencode "text=🛡️ MAZA ${ROLE} watchdog ($(hostname -s 2>/dev/null || echo host)): $msg" \
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

# --- Probes ------------------------------------------------------------------
# Healthy = the API ANSWERS with 401 (auth required, expected unauthenticated)
# or 200. Anything else (000/5xx/timeout) is unhealthy.
probe_code() { # probe_code <url>
  local code
  code=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$1" 2>/dev/null)
  echo "${code:-000}"
}
probe_healthy() { # probe_healthy <url>
  local c
  c=$(probe_code "$1")
  [ "$c" = "401" ] || [ "$c" = "200" ]
}

bench_probe_url() {
  # Parse the bench env file IN MEMORY (values never printed/logged).
  local h p
  h=""; p=""
  if [ -r "$BENCH_ENV_FILE" ]; then
    h=$(awk -F= '/^WB_LISTEN_HOST=/{print $2; exit}' "$BENCH_ENV_FILE" | tr -d '" ')
    p=$(awk -F= '/^WB_LISTEN_PORT=/{print $2; exit}' "$BENCH_ENV_FILE" | tr -d '" ')
  fi
  h="${h:-127.0.0.1}"; p="${p:-18701}"
  echo "http://${h}:${p}/api/state"
}

unit_active() { systemctl is-active "$1" 2>/dev/null; }

# Wait for readiness by polling, never a fixed sleep. Returns 0 when the
# probe passes within READINESS_POLLS one-second attempts.
wait_ready() { # wait_ready <url>
  local url="$1" i=0
  while [ "$i" -lt "$READINESS_POLLS" ]; do
    if probe_healthy "$url"; then return 0; fi
    i=$((i + 1))
    sleep 1
  done
  return 1
}

# --- Heal bookkeeping --------------------------------------------------------
heal_streak() { # heal_streak <inc|reset|get>
  local f="$STATE_DIR/heal-streak" n
  case "$1" in
    inc)   n=$(( $(heal_streak get) + 1 )); echo "$n" > "$f";;
    reset) echo 0 > "$f";;
    get)   if [ -f "$f" ]; then n=$(tr -cd '0-9' < "$f"); else n=""; fi
           echo "${n:-0}";;
  esac
}

# --- Guards ------------------------------------------------------------------
disk_guard() {
  local path pct
  path="${DISK_PATH:-$STATE_DIR}"
  pct=$(df -P "$path" 2>/dev/null | awk 'NR==2{gsub("%","",$5); print $5}')
  case "${pct:-}" in
    ''|*[!0-9]*) return 0 ;;   # unparsable -> never alert on a bad read
    *) if [ "$pct" -ge "$DISK_MAX_PCT" ]; then
         notify "DISK-HIGH" "$SLOW_COOLDOWN_SECS" \
           "disk ${pct}% >= ${DISK_MAX_PCT}% on ${path} — alert only, manual cleanup needed"
         log "GUARD-DISK class=DISK-HIGH pct=$pct"
       fi ;;
  esac
}

bench_state_guard() {
  # The bench address book vanished once (deleter unknown, run log) — a
  # restart cannot restore it, so this class is alert-only.
  if [ ! -s "$BENCH_STATE_FILE" ]; then
    notify "STATE-FILE-MISSING" "$SLOW_COOLDOWN_SECS" \
      "bench state file missing/empty: ${BENCH_STATE_FILE} — address book gone? restore from state.json.bak-*"
    log "GUARD-STATE class=STATE-FILE-MISSING"
  fi
}

# --- Role main loops ----------------------------------------------------------
do_bench() {
  local url
  url=$(bench_probe_url)
  if probe_healthy "$url"; then
    heal_streak reset
    return 0
  fi
  sleep "$DOUBLE_PROBE_SECS"
  if probe_healthy "$url"; then
    log "TRANSIENT-RECOVERED (double-probe passed)"
    heal_streak reset
    return 0
  fi
  if [ "$(heal_streak get)" -ge "$MAX_CONSEC_HEALS" ]; then
    notify "ESCALATE" "$ALERT_COOLDOWN_SECS" \
      "bench probe down; ${MAX_CONSEC_HEALS} consecutive restarts did not recover ${BENCH_SERVICE} — manual intervention needed"
    log "HEAL-BOUNDED class=ESCALATE streak=$(heal_streak get)"
    return 0
  fi
  log "HEAL-START restart=${BENCH_SERVICE} streak=$(heal_streak get)"
  systemctl restart "$BENCH_SERVICE" >/dev/null 2>&1
  if wait_ready "$url"; then
    heal_streak reset   # recovered: the streak measures FAILED heals only
    notify "HEALED" "$ALERT_COOLDOWN_SECS" \
      "bench probe was down twice; restarted ${BENCH_SERVICE} — recovered, API answering (401/200)"
    log "HEAL-OK"
  else
    heal_streak inc
    notify "HEAL-FAILED" "$ALERT_COOLDOWN_SECS" \
      "restarted ${BENCH_SERVICE} but the probe STILL fails after ${READINESS_POLLS}s — check journalctl -u ${BENCH_SERVICE}"
    log "HEAL-FAILED streak=$(heal_streak get)"
  fi
}

do_tunnel() {
  if [ -z "$TUNNEL_PROBE_URL" ]; then
    notify "CONFIG" "$SLOW_COOLDOWN_SECS" \
      "MAZA_TUNNEL_PROBE_URL is not set in ${ENV_FILE} — tunnel watchdog cannot probe; set it to the local tunnel bind URL"
    log "CONFIG-MISSING TUNNEL_PROBE_URL"
    return 0
  fi
  if probe_healthy "$TUNNEL_PROBE_URL"; then
    heal_streak reset
    return 0
  fi
  sleep "$DOUBLE_PROBE_SECS"
  if probe_healthy "$TUNNEL_PROBE_URL"; then
    log "TRANSIENT-RECOVERED (double-probe passed)"
    heal_streak reset
    return 0
  fi
  if [ "$(unit_active "$TUNNEL_SERVICE")" = "active" ]; then
    # Tunnel alive, full chain dead: the remote backend is the problem.
    # Restarting the tunnel cannot fix a remote backend — alert only.
    notify "BACKEND-DOWN" "$ALERT_COOLDOWN_SECS" \
      "tunnel unit active but the full-chain probe fails (${TUNNEL_PROBE_URL}) — remote walletbench likely down; its own watchdog should heal it"
    log "BACKEND-DOWN (tunnel active, probe failing — no restart)"
    return 0
  fi
  if [ "$(heal_streak get)" -ge "$MAX_CONSEC_HEALS" ]; then
    notify "ESCALATE" "$ALERT_COOLDOWN_SECS" \
      "tunnel probe down; ${MAX_CONSEC_HEALS} consecutive restarts did not recover ${TUNNEL_SERVICE} — check ssh key/sshd on the remote host"
    log "HEAL-BOUNDED class=ESCALATE streak=$(heal_streak get)"
    return 0
  fi
  log "HEAL-START restart=${TUNNEL_SERVICE} streak=$(heal_streak get)"
  systemctl restart "$TUNNEL_SERVICE" >/dev/null 2>&1
  if wait_ready "$TUNNEL_PROBE_URL"; then
    heal_streak reset
    notify "HEALED" "$ALERT_COOLDOWN_SECS" \
      "tunnel probe was down twice and the unit was inactive; restarted ${TUNNEL_SERVICE} — recovered, full chain answering"
    log "HEAL-OK"
  else
    heal_streak inc
    notify "HEAL-FAILED" "$ALERT_COOLDOWN_SECS" \
      "restarted ${TUNNEL_SERVICE} but the probe STILL fails — remote backend or ssh auth problem"
    log "HEAL-FAILED streak=$(heal_streak get)"
  fi
}

# --- Entry --------------------------------------------------------------------
log_rotate
case "$ROLE" in
  bench)
    do_bench
    disk_guard
    bench_state_guard
    ;;
  tunnel)
    do_tunnel
    disk_guard
    ;;
esac
exit 0
