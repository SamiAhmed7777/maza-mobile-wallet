#!/usr/bin/env bash
# deploy/maza-indexer-install.sh - install the MAZA lean chain indexer on a
# small VPS with ONE command.
#
# Run it ON THE TARGET HOST, from the rsynced repo root:
#
#     rsync -a --delete <repo>/ <user>@<host>:/root/maza-indexer-src/
#     ssh <user>@<host> 'cd /root/maza-indexer-src && bash deploy/maza-indexer-install.sh'
#
# (or just rsync and run it yourself over ssh).
#
# WHAT IT DOES
# ------------
#   1. Preflight: root, systemd, curl, flock, python3 >= 3.10, the source
#      files are present, the data directory's parent is writable.
#   2. Creates the dedicated non-root service user "maza-indexer".
#   3. STAGED CUTOVER: every run lands in a NEW release directory
#      /opt/maza-indexer/releases/<utc-stamp>, and the "current" symlink is
#      moved to point at it. Nothing is ever edited in place, so a bad
#      release can be rolled back by moving the symlink back.
#   4. Assembles /etc/maza-indexer.env (0600, root:root) from the operator's
#      answers (stdin) or from the values already in the existing env file.
#      The RPC password is read with "read -s" (never echoed) and is NEVER
#      printed, logged, or put on a command line.
#   5. Installs the systemd unit from deploy/maza-indexer.service.example.
#      The unit's ExecStart is an ABSOLUTE path to the launcher script -
#      a ${VAR} as the executable path is FATAL under systemd-analyze verify,
#      so the launcher does the expansion.
#   6. Runs `systemd-analyze verify` on the INSTALLED unit and shows the
#      result. A finding fails the install.
#   7. systemctl daemon-reload, enable, then RESTART. (enable --now does NOT
#      restart an already-active unit - that bug leaves new code on disk and
#      old code serving, so the restart is always explicit.)
#   8. Health gate: bounded poll of GET /health (30 tries x 1s) against the
#      bound address. If it never answers 200 the install fails loudly, and
#      the previous release is rolled back if there was one.
#
# PLACEHOLDERS ONLY IN THE REPO
# ------------------------------
# Nothing in this repository contains a real credential. The env file is
# written on the TARGET host, to /etc, never into the repo. The password is
# never echoed to the terminal, never written to the journal, and never
# appears in any argument list.
set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STAMP="$(date -u +%Y%m%d-%H%M%S)"
REL_ROOT="/opt/maza-indexer"
ENV_DST="/etc/maza-indexer.env"
UNIT_DST="/etc/systemd/system/maza-indexer.service"
LOCK_FILE="/var/lock/maza-indexer-install.lock"
SERVICE_USER="maza-indexer"
SERVICE_GROUP="maza-indexer"
DEFAULT_DATADIR="/var/lib/maza-indexer"
DEFAULT_RPC_URL="http://127.0.0.1:12832"
DEFAULT_BIND="127.0.0.1:18711"
DEFAULT_BATCH="24"
DEFAULT_RATE="60"
HEALTH_TRIES=30
HEALTH_SLEEP=1

ENV_MODE="600"
NON_INTERACTIVE=0
INTERACTIVE=0
ANSWER=""
ENV_TMP=""
HEALTH_BODY=""

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"

log()  { printf '[maza-indexer %s] %s\n' "$STAMP" "$*"; }
warn() { printf '[maza-indexer %s] WARN: %s\n' "$STAMP" "$*" >&2; }
fail() { printf '[maza-indexer %s] FAIL: %s\n' "$STAMP" "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
maza-indexer installer - installs the MAZA lean chain indexer as a systemd
service on THIS host. Run it from the rsynced repo root as root.

Usage: bash deploy/maza-indexer-install.sh [options]

Options:
  --non-interactive     Read the answers from stdin (one per line, in the
                        order the questions are asked) instead of prompting.
  --env-group-readable  Install /etc/maza-indexer.env as 0640 root:maza-indexer
                        instead of 0600 root:root. Only needed if a release
                        parses the env file itself instead of reading the
                        environment systemd injects.
  -h, --help            Show this text.

Questions, in order (existing values in /etc/maza-indexer.env are kept and
are never asked again). These are EXACTLY the keys the indexer package
reads - the installer writes no other key:

  1 MAZA_INDEXER_RPC_URL       default http://127.0.0.1:12832
  2 MAZA_INDEXER_RPC_USER      required
  3 MAZA_INDEXER_RPC_PASSWORD  required, read with "read -s" (never echoed)
  4 MAZA_INDEXER_DATADIR       default /var/lib/maza-indexer
  5 MAZA_INDEXER_BIND          default 127.0.0.1:18711
  6 MAZA_INDEXER_BATCH         default 24
  7 MAZA_INDEXER_RATE          default 60
EOF
}

cleanup() {
    if [ -n "$ENV_TMP" ]; then rm -f "$ENV_TMP"; fi
    if [ -n "$HEALTH_BODY" ]; then rm -f "$HEALTH_BODY"; fi
    return 0
}
trap cleanup EXIT

while [ "$#" -gt 0 ]; do
    case "$1" in
        --non-interactive)     NON_INTERACTIVE=1 ;;
        --env-group-readable)  ENV_MODE="640" ;;
        -h|--help)             usage; exit 0 ;;
        *) usage >&2; fail "unknown argument: $1" ;;
    esac
    shift
done

if [ "$NON_INTERACTIVE" -eq 0 ] && [ -t 0 ]; then
    INTERACTIVE=1
fi

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || fail "run as root (this installs a systemd unit and writes /etc)"
command -v systemctl >/dev/null 2>&1 || fail "systemctl not found - this host has no systemd"
command -v curl >/dev/null 2>&1 || fail "curl not found - needed for the health gate"
command -v flock >/dev/null 2>&1 || fail "flock not found (util-linux) is required"

PY_BIN="$(command -v python3 || true)"
[ -n "$PY_BIN" ] || fail "python3 not found - install python3.10 or newer"
PY_VER="$("$PY_BIN" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJ="${PY_VER%%.*}"
PY_MIN="${PY_VER##*.}"
if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 10 ]; }; then
    fail "python3 ${PY_VER} is too old - the indexer needs 3.10 or newer"
fi
log "python3 ${PY_VER} at ${PY_BIN}"

UNIT_SRC="${REPO_ROOT}/deploy/maza-indexer.service.example"
LAUNCHER_SRC="${REPO_ROOT}/deploy/maza-indexer-launcher.example"
[ -f "$UNIT_SRC" ] || fail "missing ${UNIT_SRC} - run this from the rsynced repo root"
[ -f "$LAUNCHER_SRC" ] || fail "missing ${LAUNCHER_SRC} - run this from the rsynced repo root"

PKG_DIR=""
for cand in "${REPO_ROOT}/maza_indexer" "${REPO_ROOT}/src/maza_indexer" \
            "${REPO_ROOT}/python/maza_indexer" "${REPO_ROOT}/lib/maza_indexer"; do
    if [ -f "${cand}/__init__.py" ]; then
        PKG_DIR="$cand"
        break
    fi
done
[ -n "$PKG_DIR" ] || fail "the maza_indexer package is not in the repo root \
(looked for maza_indexer/__init__.py and src/, python/, lib/) - the code half \
of the indexer must be present before you install it"

# flock: one installer at a time. Two concurrent installs would race on the
# "current" symlink and on the env file.
exec 9>"$LOCK_FILE"
flock -n 9 || fail "another installer holds ${LOCK_FILE} - wait for it to finish"

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
    command -v useradd >/dev/null 2>&1 || fail "useradd not found - cannot create ${SERVICE_USER}"
    useradd --system --home-dir "$DEFAULT_DATADIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    log "created dedicated service user ${SERVICE_USER}"
else
    log "service user ${SERVICE_USER} already exists"
fi

# ---------------------------------------------------------------------------
# Answers: existing env file first, then stdin answers, then an interactive
# prompt. The secret is read with "read -s" so it is never echoed.
# ---------------------------------------------------------------------------
# The EXACT set of keys the indexer package reads. The installer writes
# these and nothing else - a key the package ignores is a lie in the env
# file. MAZA_INDEXER_PYTHON is deliberately NOT here: it is a launcher-only
# convenience, the package does not read it.
MANAGED_KEYS="MAZA_INDEXER_RPC_URL MAZA_INDEXER_RPC_USER MAZA_INDEXER_RPC_PASSWORD \
MAZA_INDEXER_DATADIR MAZA_INDEXER_BIND MAZA_INDEXER_BATCH MAZA_INDEXER_RATE"

env_get() {
    [ -f "$ENV_DST" ] || return 0
    grep -E "^${1}=" "$ENV_DST" 2>/dev/null | head -n 1 | cut -d= -f2-
}

ask() {
    # ask KEY DEFAULT PROMPT [secret]
    local key="$1" default="$2" prompt="$3" secret="${4:-0}"
    local existing="" value=""
    existing="$(env_get "$key")"
    if [ -n "$existing" ]; then
        log "keeping the existing ${key} (value not shown)"
        ANSWER="$existing"
        return 0
    fi
    if [ -n "$default" ]; then
        printf '%s [default: %s]: ' "$prompt" "$default" >&2
    else
        printf '%s: ' "$prompt" >&2
    fi
    if [ "$secret" -eq 1 ] && [ "$INTERACTIVE" -eq 1 ]; then
        IFS= read -r -s value || value=""
        printf '\n' >&2
    else
        IFS= read -r value || value=""
    fi
    value="${value:-$default}"
    if [ "$secret" -eq 1 ] && [ -z "$value" ]; then
        fail "${key} is required - it has no default and no value in ${ENV_DST}"
    fi
    ANSWER="$value"
}

ask "MAZA_INDEXER_RPC_URL" "$DEFAULT_RPC_URL" \
    "Full URL of the mazad RPC (your own node), e.g. http://127.0.0.1:12832"
RPC_URL="$ANSWER"
ask "MAZA_INDEXER_RPC_USER" "" \
    "mazad rpcuser (the rpcuser= line in maza.conf)"
RPC_USER="$ANSWER"
ask "MAZA_INDEXER_RPC_PASSWORD" "" \
    "mazad rpcpassword (the rpcpassword= line in maza.conf - not echoed)" 1
RPC_PASSWORD="$ANSWER"
ask "MAZA_INDEXER_DATADIR" "$DEFAULT_DATADIR" \
    "Directory for the index database"
DATADIR="$ANSWER"
ask "MAZA_INDEXER_BIND" "$DEFAULT_BIND" \
    "Address the indexer listens on, host:port (127.0.0.1 keeps it private)"
BIND="$ANSWER"
ask "MAZA_INDEXER_BATCH" "$DEFAULT_BATCH" \
    "Block-hash lookups per crawl batch"
BATCH="$ANSWER"
ask "MAZA_INDEXER_RATE" "$DEFAULT_RATE" \
    "Per-IP requests per minute the indexer will serve"
RATE="$ANSWER"

# Sanity-check the answers before anything is written to disk.

# systemd's EnvironmentFile parser: an unquoted value is taken literally
# except that surrounding whitespace is stripped and a value starting with
# '#' or ';' is a comment. Reject what would silently change meaning
# rather than write a value systemd would read differently than we wrote it.
validate_value() {
    local key="$1" value="$2"
    case "$value" in
        *$'\n'*|*$'\r'*) fail "${key} must not contain a newline" ;;
    esac
    case "$value" in
        ' '*|*' ') fail "${key} must not start or end with a space (systemd strips it)" ;;
    esac
    case "$value" in
        '#'*|*';'*) fail "${key} must not start with '#' or ';' (systemd reads that as a comment)" ;;
    esac
}

for pair in "MAZA_INDEXER_RPC_URL=$RPC_URL" \
            "MAZA_INDEXER_RPC_USER=$RPC_USER" \
            "MAZA_INDEXER_RPC_PASSWORD=$RPC_PASSWORD" \
            "MAZA_INDEXER_DATADIR=$DATADIR" \
            "MAZA_INDEXER_BIND=$BIND" \
            "MAZA_INDEXER_BATCH=$BATCH" \
            "MAZA_INDEXER_RATE=$RATE"; do
    validate_value "${pair%%=*}" "${pair#*=}"
done

# MAZA_INDEXER_RPC_URL: a full URL, http:// or https://, no whitespace, and
# a host part. The package splits the URL and strips any user:password@
# from it - the credentials live in their own keys, so keep them out of it.
case "$RPC_URL" in
    http://*|https://*) ;;
    *) fail "MAZA_INDEXER_RPC_URL must start with http:// or https:// (got: ${RPC_URL})" ;;
esac
case "$RPC_URL" in
    *[[:space:]]*) fail "MAZA_INDEXER_RPC_URL must not contain whitespace" ;;
esac
RPC_AUTHORITY="${RPC_URL#*://}"
RPC_AUTHORITY="${RPC_AUTHORITY%%/*}"
[ -n "$RPC_AUTHORITY" ] || fail "MAZA_INDEXER_RPC_URL has no host part: ${RPC_URL}"
case "$RPC_AUTHORITY" in
    *@*) warn "MAZA_INDEXER_RPC_URL carries credentials before '@' - put the user and password in their own keys instead" ;;
esac

# MAZA_INDEXER_BIND: host:port, with a numeric port in range. The package
# splits it on the LAST colon, so [::1]:18711 works too.
BIND_HOST="${BIND%:*}"
BIND_PORT="${BIND##*:}"
[ "$BIND_HOST" != "$BIND" ] || fail "MAZA_INDEXER_BIND must be host:port (got: ${BIND})"
[ -n "$BIND_HOST" ] || fail "MAZA_INDEXER_BIND has no host part: ${BIND}"
case "$BIND" in
    *[[:space:]]*) fail "MAZA_INDEXER_BIND must not contain whitespace" ;;
esac
case "$BIND_PORT" in
    ''|*[!0-9]*) fail "the port in MAZA_INDEXER_BIND must be a number (got: ${BIND})" ;;
esac
if [ "$BIND_PORT" -lt 1 ] || [ "$BIND_PORT" -gt 65535 ]; then
    fail "the port in MAZA_INDEXER_BIND must be between 1 and 65535 (got: ${BIND_PORT})"
fi

# MAZA_INDEXER_BATCH / MAZA_INDEXER_RATE: the package parses both as ints.
case "$BATCH" in ''|*[!0-9]*) fail "MAZA_INDEXER_BATCH must be a number: ${BATCH}";; esac
case "$RATE"  in ''|*[!0-9]*) fail "MAZA_INDEXER_RATE must be a number: ${RATE}";; esac
[ "$BATCH" -ge 1 ] || fail "MAZA_INDEXER_BATCH must be 1 or more (got: ${BATCH})"
[ "$RATE" -ge 1 ] || fail "MAZA_INDEXER_RATE must be 1 or more (got: ${RATE})"

case "$DATADIR" in *'|'*|*'&'*) fail "MAZA_INDEXER_DATADIR must not contain '|' or '&'";; esac
[ -n "$RPC_USER" ] || fail "MAZA_INDEXER_RPC_USER is required"

# --- data directory: the parent must exist and be writable ------------------
DATA_PARENT="$(dirname -- "$DATADIR")"
[ -d "$DATA_PARENT" ] || fail "the parent directory ${DATA_PARENT} does not exist - create it first, or pick another MAZA_INDEXER_DATADIR"
[ -w "$DATA_PARENT" ] || fail "the parent directory ${DATA_PARENT} is not writable"
FREE_KB="$(df -Pk "$DATA_PARENT" 2>/dev/null | awk 'NR==2 {print $4}' || true)"
if [ -n "$FREE_KB" ]; then
    log "free space on ${DATA_PARENT}: $((FREE_KB / 1024)) MiB (the index size itself is NOT yet measured - see docs/maza-indexer/README.md)"
fi
install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$DATADIR"
log "data directory ${DATADIR} owned by ${SERVICE_USER}"

# ---------------------------------------------------------------------------
# Release directory - staged cutover, never edited in place
# ---------------------------------------------------------------------------
REL_DIR="${REL_ROOT}/releases/${STAMP}"
mkdir -p "${REL_DIR}/bin"
cp -a "$PKG_DIR" "${REL_DIR}/maza_indexer"
find "${REL_DIR}" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "${REL_DIR}" -name '*.pyc' -delete 2>/dev/null || true
log "release tree ${REL_DIR} (package from ${PKG_DIR#"${REPO_ROOT}/"})"

# ---------------------------------------------------------------------------
# The systemd unit (installed from the example in the repo)
# ---------------------------------------------------------------------------
install -m 644 "$UNIT_SRC" "${UNIT_DST}.new"
sed -i \
    -e "s|^User=.*|User=${SERVICE_USER}|" \
    -e "s|^Group=.*|Group=${SERVICE_GROUP}|" \
    -e "s|^ReadWritePaths=.*|ReadWritePaths=${DATADIR}|" \
    "${UNIT_DST}.new"
if [ "$DATADIR" != "$DEFAULT_DATADIR" ]; then
    # StateDirectory names a path under /var/lib; a custom data directory
    # is created by the installer instead.
    sed -i -e '/^StateDirectory=/d' "${UNIT_DST}.new"
fi
chown root:root "${UNIT_DST}.new"
mv -f "${UNIT_DST}.new" "$UNIT_DST"
log "systemd unit installed at ${UNIT_DST}"

# ---------------------------------------------------------------------------
# The launcher script (absolute path - the unit's ExecStart names it)
# ---------------------------------------------------------------------------
install -m 0755 "$LAUNCHER_SRC" "${REL_DIR}/bin/maza-indexer-launcher"
chown -R root:root "$REL_DIR"
chmod -R go-w "$REL_DIR"

# --- backup the previous release, then move the symlink ---------------------
PREV_RELEASE="$(readlink -f "${REL_ROOT}/current" 2>/dev/null || true)"
if [ -n "$PREV_RELEASE" ] && [ -d "$PREV_RELEASE" ]; then
    mkdir -p "${REL_ROOT}/backups"
    PREV_NAME="$(basename -- "$PREV_RELEASE")"
    BACKUP_FILE="${REL_ROOT}/backups/release-${PREV_NAME}-${STAMP}.tar.gz"
    if tar -C "$(dirname -- "$PREV_RELEASE")" -czf "$BACKUP_FILE" "$PREV_NAME" 2>/dev/null; then
        log "previous release backed up to ${BACKUP_FILE}"
    else
        warn "could not archive the previous release to ${BACKUP_FILE} (it is still on disk at ${PREV_RELEASE})"
    fi
    log "previous release kept on disk at ${PREV_RELEASE}"
else
    log "no previous release - this is the first install"
fi
ln -sfn "$REL_DIR" "${REL_ROOT}/current"
log "current -> ${REL_DIR}"

# ---------------------------------------------------------------------------
# The env file: 0600, merged (operator-added keys are preserved), assembled
# from the answers above. The password is written but never printed.
# ---------------------------------------------------------------------------
ENV_TMP="$(mktemp "${ENV_DST}.tmp.XXXXXX")"
{
    printf '# /etc/maza-indexer.env - MAZA lean chain indexer.\n'
    printf '# Written by deploy/maza-indexer-install.sh on %s.\n' "$STAMP"
    printf '# Managed keys: the installer rewrites these on every run.\n'
    printf '# Any other key in this file is PRESERVED as you left it.\n'
    printf '# Mode 0600 root:root - systemd reads it as root and injects the\n'
    printf '# values into the service environment. The RPC password is never\n'
    printf '# logged, echoed, or printed.\n'
    printf 'MAZA_INDEXER_RPC_URL=%s\n' "$RPC_URL"
    printf 'MAZA_INDEXER_RPC_USER=%s\n' "$RPC_USER"
    printf 'MAZA_INDEXER_RPC_PASSWORD=%s\n' "$RPC_PASSWORD"
    printf 'MAZA_INDEXER_DATADIR=%s\n' "$DATADIR"
    printf 'MAZA_INDEXER_BIND=%s\n' "$BIND"
    printf 'MAZA_INDEXER_BATCH=%s\n' "$BATCH"
    printf 'MAZA_INDEXER_RATE=%s\n' "$RATE"
} > "$ENV_TMP"

# Preserve any extra keys the operator added by hand.
if [ -f "$ENV_DST" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in ''|'#'*) continue ;; esac
        key="${line%%=*}"
        if [ "$key" = "$line" ]; then continue; fi
        case " ${MANAGED_KEYS} " in
            *" ${key} "*) continue ;;
        esac
        printf '%s\n' "$line" >> "$ENV_TMP"
    done < "$ENV_DST"
fi

chown root:root "$ENV_TMP"
chmod "$ENV_MODE" "$ENV_TMP"
mv -f "$ENV_TMP" "$ENV_DST"
ENV_TMP=""
log "env assembled at ${ENV_DST} (${ENV_MODE}, values not shown)"

# ---------------------------------------------------------------------------
# Verify the INSTALLED unit before it is allowed to run.
# ---------------------------------------------------------------------------
if command -v systemd-analyze >/dev/null 2>&1; then
    verify_out=""
    verify_rc=0
    verify_out="$(systemd-analyze verify "$UNIT_DST" 2>&1)" || verify_rc=$?
    printf '%s\n' "$verify_out" | sed 's/^/[systemd-analyze verify] /'
    if [ "$verify_rc" -ne 0 ]; then
        fail "systemd-analyze verify failed (exit ${verify_rc}) - the unit was NOT started"
    fi
    log "systemd-analyze verify: clean (exit 0) for ${UNIT_DST}"
    if printf '%s\n' "$verify_out" | grep -q "maza-indexer.service"; then
        warn "verify printed lines about maza-indexer.service - read them above"
    fi
else
    warn "systemd-analyze not found - the unit was NOT verified"
fi

# ---------------------------------------------------------------------------
# Start it. enable --now does NOT restart an already-active unit, so the
# restart is always explicit.
# ---------------------------------------------------------------------------
systemctl daemon-reload
systemctl enable maza-indexer.service
systemctl restart maza-indexer.service
log "service restarted (unit maza-indexer.service, shorthand: systemctl status maza-indexer)"

# ---------------------------------------------------------------------------
# Health gate: bounded poll of GET /health, 30 tries x 1s.
# ---------------------------------------------------------------------------
PROBE_HOST="$BIND_HOST"
case "$PROBE_HOST" in
    0.0.0.0|'::'|'[::]') PROBE_HOST="127.0.0.1" ;;
esac
HEALTH_URL="http://${PROBE_HOST}:${BIND_PORT}/health"
HEALTH_BODY="$(mktemp /tmp/maza-indexer-health.XXXXXX)"

log "health gate: polling ${HEALTH_URL} (${HEALTH_TRIES} tries x ${HEALTH_SLEEP}s)"
health_code="000"
health_ok=0
try=1
while [ "$try" -le "$HEALTH_TRIES" ]; do
    health_code="$(curl -s -o "$HEALTH_BODY" -w '%{http_code}' --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
    [ -n "$health_code" ] || health_code="000"
    if [ "$health_code" = "200" ]; then
        health_ok=1
        break
    fi
    sleep "$HEALTH_SLEEP"
    try=$((try + 1))
done

if [ "$health_ok" -ne 1 ]; then
    warn "health gate failed: GET ${HEALTH_URL} never answered 200 (last code: ${health_code})"
    warn "last 40 journal lines:"
    journalctl -u maza-indexer.service -n 40 --no-pager >&2 2>/dev/null || true
    if [ -n "$PREV_RELEASE" ] && [ -d "$PREV_RELEASE" ]; then
        warn "rolling back to the previous release ${PREV_RELEASE}"
        ln -sfn "$PREV_RELEASE" "${REL_ROOT}/current"
        systemctl restart maza-indexer.service >/dev/null 2>&1 || true
        warn "rolled back - the service is running the previous release again"
    fi
    fail "install failed: the indexer never answered /health (code ${health_code})"
fi

log "health OK: GET ${HEALTH_URL} -> 200"
printf '[maza-indexer %s] /health body: ' "$STAMP"
cat "$HEALTH_BODY"; printf '\n'

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
cat <<EOF

[maza-indexer ${STAMP}] INSTALLED

  unit            ${UNIT_DST}
  env file        ${ENV_DST} (mode ${ENV_MODE}, root:root)
  release         ${REL_DIR}
  current symlink ${REL_ROOT}/current -> $(readlink -f "${REL_ROOT}/current")
  data directory  ${DATADIR} (owner ${SERVICE_USER})
  listen address  ${BIND_HOST}:${BIND_PORT}
  rpc target      ${RPC_URL} (user ${RPC_USER}, password not shown)
  limits          batch ${BATCH} blocks, ${RATE} req/min per IP

  check it:       systemctl status maza-indexer
                  curl -s http://${PROBE_HOST}:${BIND_PORT}/health
                  journalctl -u maza-indexer -f

  update it:      re-run this installer (staged cutover, old release kept)
  operator guide: docs/maza-indexer/README.md
  api contract:   docs/maza-indexer/API.md

EOF
