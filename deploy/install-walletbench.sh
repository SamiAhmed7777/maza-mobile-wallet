#!/usr/bin/env bash
# Install the MAZA wallet bench service on samihost (staged cutover).
#
# Run ON samihost, from the rsynced repo root (same pattern as
# mazapay's deploy/service/install-bridge.sh):
#   bash deploy/install-walletbench.sh
#
# What it does:
#   1. Preflight: maza.conf readable by the mazad user; port 18701 free or
#      already held by our own unit (upgrade path); a tailscale IPv4 exists.
#   2. Release dir /opt/maza-wallet-bench/releases/<stamp> + current symlink.
#   3. Assemble /etc/maza-wallet-bench.env (0600) — WB_TOKEN preserved
#      byte-identically across reruns; WB_LISTEN_HOST = tailscale IPv4
#      (loopback + tailnet ONLY, never 0.0.0.0).
#   4. systemd unit maza-wallet-bench.service (User=mazad so the RPC conf
#      at /var/lib/mazad/maza.conf stays 0600 mazad:mazad).
#   5. Health gate: `curl http://<bound-ip>:18701/api/state` must answer 401
#      (serving + locked — both properties in one check). The installer
#      RESTARTS the unit on every run: `enable --now` does not restart an
#      already-active service (upgrade-path bug found live 2026-11-16 —
#      new code on disk, old code serving).
set -euo pipefail

STAMP="$(date -u +%Y%m%d-%H%M%S)"
PORT="18701"
REL_ROOT="/opt/maza-wallet-bench"
ENV_DST="/etc/maza-wallet-bench.env"
RPC_CONF="/var/lib/mazad/maza.conf"
TS_IP="$(tailscale ip -4 2>/dev/null | head -1)"

log() { echo "[walletbench ${STAMP}] $*"; }
fail() { log "FAIL: $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run as root"
[ -f "$RPC_CONF" ] || fail "missing $RPC_CONF"
sudo -u mazad test -r "$RPC_CONF" || fail "mazad user cannot read $RPC_CONF"
[ -n "$TS_IP" ] || fail "no tailscale IPv4 — bench binds the tailnet IP"

port_line="$(ss -tln 2>/dev/null | awk -v p=":${PORT}\$" '$4 ~ p {print}' || true)"
if [ -n "$port_line" ]; then
  systemctl cat maza-wallet-bench.service >/dev/null 2>&1 \
    || fail "port ${PORT} held by something else: ${port_line}"
  log "port ${PORT} held by installed unit (upgrade path)"
fi

[ -d walletbench ] || fail "run from the repo root (walletbench/ missing)"

# --- release dir -----------------------------------------------------------
REL_DIR="${REL_ROOT}/releases/${STAMP}"
mkdir -p "$REL_DIR"
cp -a walletbench "$REL_DIR/walletbench"
find "$REL_DIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
chown -R root:root "$REL_DIR"
chmod -R go-w "$REL_DIR"
prev="$(readlink -f "${REL_ROOT}/current" 2>/dev/null || true)"
ln -sfn "$REL_DIR" "${REL_ROOT}/current"
log "release ${REL_DIR} (previous: ${prev:-none})"

# --- env file (token preserved across reruns) ------------------------------
TOKEN_VAL=""
if [ -f "$ENV_DST" ]; then
  TOKEN_VAL="$(grep -E '^WB_TOKEN=' "$ENV_DST" | head -1 | cut -d= -f2-)"
fi
if [ -z "$TOKEN_VAL" ]; then
  TOKEN_VAL="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  log "generated new WB_TOKEN"
else
  log "preserved existing WB_TOKEN"
fi
umask 077
cat > "$ENV_DST" <<EOF
WB_TOKEN=${TOKEN_VAL}
WB_LISTEN_HOST=${TS_IP}
WB_LISTEN_PORT=${PORT}
WB_ACCOUNT=mobile-play
WB_MAX_SEND=50
WB_RPC_CONF=${RPC_CONF}
WB_STATE_FILE=/var/lib/maza-wallet-bench/state.json
EOF
chmod 600 "$ENV_DST"
mkdir -p /var/lib/maza-wallet-bench
chown mazad:mazad /var/lib/maza-wallet-bench
chmod 750 /var/lib/maza-wallet-bench
# Backup the address book before ANY restart: the book IS the pointer to
# funded addresses (lost once on 2026-11-16 while funds stayed safe in the
# node wallet — recovery was manual chain forensics). Keep the last 5.
if [ -f /var/lib/maza-wallet-bench/state.json ]; then
  cp /var/lib/maza-wallet-bench/state.json \
     "/var/lib/maza-wallet-bench/state.json.bak-${STAMP}"
  ls -1t /var/lib/maza-wallet-bench/state.json.bak-* 2>/dev/null \
    | tail -n +6 | xargs -r rm -f
  chown mazad:mazad /var/lib/maza-wallet-bench/state.json.bak-"${STAMP}"
  log "state.json backed up"
fi
log "env assembled at ${ENV_DST} (0600, host=${TS_IP})"

# --- systemd unit ----------------------------------------------------------
cat > /etc/systemd/system/maza-wallet-bench.service <<EOF
[Unit]
Description=MAZA wallet bench (maza-mobile-wallet v0, account-scoped)
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
systemctl daemon-reload
# Upgrade path: enable --now does NOT restart an already-active unit — the
# old process would keep serving the previous release (found live 2026-11-16:
# new code on disk, old code serving). Restart explicitly, every time.
systemctl restart maza-wallet-bench.service
systemctl enable maza-wallet-bench.service

# --- health gate -----------------------------------------------------------
sleep 2
# The unit binds WB_LISTEN_HOST (the tailnet IP) — health-check THAT address,
# not loopback (a bind to the tailnet IP does not listen on 127.0.0.1).
code="$(curl -s -o /dev/null -w '%{http_code}' "http://${TS_IP}:${PORT}/api/state" || true)"
[ "$code" = "401" ] || fail "health gate failed: /api/state on ${TS_IP}:${PORT} answered ${code}, expected 401 (serving + locked)"
log "health OK: /api/state -> 401 (locked) on ${TS_IP}:${PORT}"
log "serving on http://${TS_IP}:${PORT}/ (tailnet only)"
log "DONE"
