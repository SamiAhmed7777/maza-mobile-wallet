#!/usr/bin/env bash
# Install the MAZA wallet bench TESTNET service on samihost (sibling of
# install-walletbench.sh — S-6-ii controlled-env backend).
#
# Run ON samihost, from the rsynced repo root:
#   bash deploy/install-walletbench-testnet.sh
#
# What it does:
#   1. Preflight: port 18702 free or already held by our own testnet unit
#      (upgrade path); a tailscale IPv4 exists; the mainnet bench release
#      tree exists (this service REUSES /opt/maza-wallet-bench/current —
#      one release tree, two units); a running mazad with
#      datadir=/var/lib/mazad-testnet is found and answers chain=test.
#   2. Assemble /etc/maza-wallet-bench-testnet.env (0600) — WB_TOKEN
#      preserved byte-identically across reruns; RPC endpoint+creds are
#      parsed IN-PROCESS from the testnet mazad /proc cmdline (exact
#      datadir match required) and written to a dedicated 0600
#      mazad-owned conf file (maza.conf format, no systemd quoting
#      layer); the env carries WB_RPC_CONF pointing at it. Values are
#      never echoed, never in argv, never logged.
#   3. systemd unit maza-wallet-bench-testnet.service (User=mazad, same
#      release tree, port 18702, tailnet-IP bind ONLY).
#   4. Health gates:
#      a. /api/state on the bound IP must answer 401 (serving + locked);
#      b. authenticated /api/watch/utxos with the env token must answer
#         200 JSON — proves the REAL path: token -> service -> testnet
#         mazad RPC (the service cold-starts its book off the testnet
#         wallet here, so this also proves node wallet access);
#      c. identity gate: the release's own walletbench.config must resolve
#         the RPC endpoint to 127.0.0.1:18446 with the env applied.
#   5. RESTARTS the unit on every run (enable --now does not restart an
#      already-active service — upgrade-path bug found live 2026-11-16).
#
# Reversibility: this installs a NEW sibling unit; the mainnet bench is
# never touched. Rollback = `systemctl disable --now
# maza-wallet-bench-testnet.service` — that STOPS serving; the installed
# env/unit/state files remain on disk and are removed manually if wanted.
set -euo pipefail

STAMP="$(date -u +%Y%m%d-%H%M%S)"
PORT="18702"
REL_ROOT="/opt/maza-wallet-bench"
ENV_DST="/etc/maza-wallet-bench-testnet.env"
UNIT_DST="/etc/systemd/system/maza-wallet-bench-testnet.service"
STATE_DIR="/var/lib/maza-wallet-bench-testnet"
RPC_CONF_DST="${STATE_DIR}/rpc.conf"
TS_IP="$(tailscale ip -4 2>/dev/null | head -1)"

log() { echo "[walletbench-testnet ${STAMP}] $*"; }
fail() { log "FAIL: $*"; exit 1; }

# Failure cleanup: the unit has Restart=always — if we die AFTER starting it
# (health gate failure), a stop-less exit leaves it crash-looping forever.
# The EXIT trap stops + disables the NEW unit on any failed exit past start.
UNIT_STARTED=0
INSTALL_OK=0
on_exit() {
  local rc=$?
  if [ "$INSTALL_OK" = "1" ]; then return; fi
  if [ "$UNIT_STARTED" = "1" ]; then
    systemctl disable --now maza-wallet-bench-testnet.service >/dev/null 2>&1 || true
    log "failure cleanup: testnet unit stopped + disabled (exit rc=${rc})"
  fi
}
trap on_exit EXIT

# --- main body (run) --------------------------------------------------------
run() {

# --- preflight --------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || fail "run as root"
for bin in python3 curl systemctl ss tailscale; do
  command -v "$bin" >/dev/null 2>&1 || fail "missing required tool: $bin"
done
[ -n "$TS_IP" ] || fail "no tailscale IPv4 — the testnet bench binds the tailnet IP"
[ -d walletbench ] || fail "run from the repo root (walletbench/ missing)"
[ -d "${REL_ROOT}/current" ] || fail "no release tree at ${REL_ROOT}/current — run deploy/install-walletbench.sh first (this service reuses that release tree)"

port_line="$(ss -tln 2>/dev/null | awk -v p=":${PORT}\$" '$4 ~ p {print}' || true)"
if [ -n "$port_line" ]; then
  # The listener must belong to OUR unit, not merely have a unit file on
  # disk: resolve the listener PID and require its cgroup to name the
  # testnet unit (an unrelated process squatting :18702 fails loud).
  lpid="$(ss -tlnp 2>/dev/null | awk -v p=":${PORT}\$" '$4 ~ p {print $NF}' | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2 || true)"
  [ -n "$lpid" ] || fail "port ${PORT} held but listener PID not resolvable: ${port_line}"
  lcg="$(cat "/proc/${lpid}/cgroup" 2>/dev/null | grep -oE 'maza-wallet-bench-testnet\.service' | head -1 || true)"
  if [ -z "$lcg" ]; then
    systemctl cat maza-wallet-bench-testnet.service >/dev/null 2>&1 \
      || fail "port ${PORT} held by a FOREIGN process (pid ${lpid}, not our unit): ${port_line}"
    fail "port ${PORT} held by pid ${lpid} outside our unit (stale unit file present): ${port_line}"
  fi
  log "port ${PORT} held by our unit (upgrade path, listener pid ${lpid})"
fi

# --- env + rpc conf (creds parsed in-process; token preserved exactly) ------
umask 077
ENV_SUMMARY="$(python3 - "$ENV_DST" "$TS_IP" "$RPC_CONF_DST" <<'PY'
import base64, glob, http.client, json, os, pwd, secrets, sys

env_dst, ts_ip, rpc_dst = sys.argv[1], sys.argv[2], sys.argv[3]
WANT_DATADIR = "/var/lib/mazad-testnet"

def datadir_of(parts):
    d = None
    for i, a in enumerate(parts):
        if a == "-datadir" and i + 1 < len(parts):
            d = parts[i + 1]
        elif a.startswith("-datadir="):
            d = a.split("=", 1)[1]
    return d

pid = None
for p in sorted(glob.glob("/proc/[0-9]*/cmdline")):
    try:
        parts = open(p, "rb").read().decode("utf-8", "replace").split("\x00")
    except Exception:
        continue
    if not parts or not parts[0].endswith("/mazad"):
        continue
    if datadir_of([a for a in parts[1:] if a]) == WANT_DATADIR:
        pid = p
        break
if not pid:
    print("FATAL: no running mazad with -datadir=" + WANT_DATADIR,
          file=sys.stderr)
    sys.exit(1)
args = [a for a in open(pid, "rb").read().decode("utf-8", "replace").split("\x00") if a]
kv = {}
# Credentials are read from key=value args only (-rpcuser=X shape). The
# split form (-rpcuser X) is not produced by this node's launcher; if it
# ever is, the missing-key FATAL below fails the install loudly rather
# than guessing.
rest = args[1:]
for i, a in enumerate(rest):
    if a.startswith("-") and "=" in a:
        k, v = a[1:].split("=", 1)
        kv[k] = v
if "rpcuser" not in kv or "rpcpassword" not in kv:
    print("FATAL: testnet mazad cmdline lacks rpcuser/rpcpassword",
          file=sys.stderr)
    sys.exit(1)
host, port = "127.0.0.1", kv.get("rpcport", "18446")

def call(method):
    c = http.client.HTTPConnection(host, int(port), timeout=10)
    c.request("POST", "/",
              json.dumps({"jsonrpc": "1.0", "id": "install",
                          "method": method, "params": []}),
              {"Content-Type": "application/json",
               "Authorization": "Basic " + base64.b64encode(
                   (kv["rpcuser"] + ":" + kv["rpcpassword"]).encode()
               ).decode()})
    r = c.getresponse()
    raw = r.read()
    c.close()
    if r.status != 200:
        print("FATAL: RPC %s answered HTTP %d" % (method, r.status),
              file=sys.stderr)
        sys.exit(1)
    d = json.loads(raw)
    if d.get("error"):
        print("FATAL: RPC %s returned error: %s"
              % (method, str(d["error"])[:200]), file=sys.stderr)
        sys.exit(1)
    return d.get("result") or {}

# ALL node probes precede ANY file write: a dead/misconfigured node fails
# the install before rpc.conf, the env file, the state dir, or the unit
# ever change.
info = call("getblockchaininfo")
if info.get("chain") != "test":
    print("FATAL: node answered chain=%r, expected 'test'"
          % info.get("chain"), file=sys.stderr)
    sys.exit(1)
wallet_count = len(call("listwallets"))

os.makedirs(os.path.dirname(rpc_dst), exist_ok=True)
ent = pwd.getpwnam("mazad")
conf_lines = [
    "rpcbind=" + host,
    "rpcport=" + port,
    "rpcuser=" + kv["rpcuser"],
    "rpcpassword=" + kv["rpcpassword"],
]
fd = os.open(rpc_dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(conf_lines) + "\n")
os.chmod(rpc_dst, 0o600)
os.chown(rpc_dst, ent.pw_uid, ent.pw_gid)

token = ""
had_token = False
if os.path.isfile(env_dst):
    for line in open(env_dst, encoding="utf-8", errors="replace"):
        if line.startswith("WB_TOKEN="):
            token = line.rstrip("\n").split("=", 1)[1]
            had_token = bool(token)
if not token:
    token = secrets.token_urlsafe(24)
lines = [
    "WB_TOKEN=" + token,
    "WB_LISTEN_HOST=" + ts_ip,
    "WB_LISTEN_PORT=18702",
    "WB_ACCOUNT=mobile-play-testnet",
    "WB_MAX_SEND=50",
    "WB_RPC_CONF=" + rpc_dst,
    "WB_STATE_FILE=/var/lib/maza-wallet-bench-testnet/state.json",
]
fd = os.open(env_dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(lines) + "\n")
os.chmod(env_dst, 0o600)
print("OK chain=test rpcport=%s wallet=%s token=%s creds=%s"
      % (port, wallet_count,
         "preserved" if had_token else "generated",
         "rpc.conf-0600-mazad"))
PY
)" || fail "env assembly failed (testnet node probe)
$ENV_SUMMARY"
log "env assembled at ${ENV_DST} (0600) + creds at a 0600 mazad-owned rpc conf — ${ENV_SUMMARY%%$'\n'*}"

mkdir -p "$STATE_DIR"
chown mazad:mazad "$STATE_DIR"
chmod 750 "$STATE_DIR"
# Backup the testnet address book before ANY restart (same rule as the
# mainnet bench: the book is the pointer to generated addresses). Keep 5.
if [ -f "${STATE_DIR}/state.json" ]; then
  cp "${STATE_DIR}/state.json" "${STATE_DIR}/state.json.bak-${STAMP}"
  ls -1t "${STATE_DIR}"/state.json.bak-* 2>/dev/null | tail -n +6 | xargs -r rm -f
  chown mazad:mazad "${STATE_DIR}/state.json.bak-${STAMP}"
  log "testnet state.json backed up"
fi

# --- systemd unit -----------------------------------------------------------
cat > "$UNIT_DST" <<EOF
[Unit]
Description=MAZA wallet bench TESTNET (maza-mobile-wallet S-6-ii controlled-env backend)
After=network-online.target mazad.service

[Service]
User=mazad
Group=mazad
WorkingDirectory=${REL_ROOT}/current
EnvironmentFile=${ENV_DST}
ExecStart=/usr/bin/python3 -m walletbench.api
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$UNIT_DST"
systemctl daemon-reload
# Cleanup coverage starts HERE: from this moment any failed exit (restart
# failure, enable failure, any gate failure) stops + disables the unit via
# the EXIT trap — Restart=always would otherwise crash-loop it forever.
UNIT_STARTED=1
systemctl restart maza-wallet-bench-testnet.service
systemctl enable maza-wallet-bench-testnet.service

# --- health gate a: serving + locked (bounded poll) -------------------------
gate_ok=""
for _ in 1 2 3 4 5; do
  sleep 2
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://${TS_IP}:${PORT}/api/state" || true)"
  if [ "$code" = "401" ]; then gate_ok=1; break; fi
done
[ -n "$gate_ok" ] || fail "health gate failed: /api/state on ${TS_IP}:${PORT} never answered 401 (last code: ${code:-none})"
log "health OK: /api/state -> 401 (locked) on ${TS_IP}:${PORT}"

# --- health gate b: authenticated read through the REAL path ----------------
# Proves token -> service -> state -> testnet mazad RPC end to end (the
# cold-start book generation runs against the testnet wallet). Token is read
# from the env file in-process; never echoed.
UTXO_CHECK="$(python3 - "$ENV_DST" "$TS_IP" "$PORT" <<'PY'
import json, sys, urllib.request
env_dst, ts_ip, port = sys.argv[1], sys.argv[2], sys.argv[3]
token = ""
for line in open(env_dst, encoding="utf-8", errors="replace"):
    if line.startswith("WB_TOKEN="):
        token = line.split("=", 1)[1].strip()
if not token:
    print("FATAL: no WB_TOKEN in env", file=sys.stderr)
    sys.exit(1)
req = urllib.request.Request(
    "http://%s:%s/api/watch/utxos" % (ts_ip, port),
    headers={"Authorization": "Bearer " + token})
try:
    with urllib.request.urlopen(req, timeout=25) as r:
        if r.status != 200:
            print("FATAL: /api/watch/utxos answered HTTP %d, expected 200"
                  % r.status, file=sys.stderr)
            sys.exit(1)
        body = json.loads(r.read())
        print("OK status=%d keys=%s" % (r.status, sorted(body)[:6]))
except Exception as e:
    print("FATAL: %s: %s" % (type(e).__name__, e), file=sys.stderr)
    sys.exit(1)
PY
)" || fail "authenticated read gate failed
$UTXO_CHECK"
log "authenticated read OK: ${UTXO_CHECK%%$'\n'*}"

# --- health gate c: identity (release config resolves the testnet RPC) ------
IDENT="$(python3 - "$ENV_DST" "${REL_ROOT}/current" <<'PY'
import os, sys
from urllib.parse import urlparse
env_dst, rel = sys.argv[1], sys.argv[2]
for line in open(env_dst, encoding="utf-8", errors="replace"):
    line = line.rstrip("\n")
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k] = v
sys.path.insert(0, rel)
import walletbench.config as cfg
url, _user, _pw = cfg.rpc_endpoint()
u = urlparse(url)
print("%s:%s" % (u.hostname, u.port))
PY
)" || fail "identity gate failed to run"
[ "$IDENT" = "127.0.0.1:18446" ] || fail "identity gate failed: resolved RPC endpoint ${IDENT}, expected 127.0.0.1:18446"
log "identity OK: release config resolves RPC to ${IDENT} (testnet node)"

log "serving on http://${TS_IP}:${PORT}/ (tailnet only, testnet node)"
log "DONE"
INSTALL_OK=1
}

run "$@"
