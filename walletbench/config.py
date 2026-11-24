"""Configuration for the MAZA wallet bench service (env-driven).

Bench edition: the keys live in the mazad node's wallet under a dedicated
account (see DECISIONS.md D7) — this service is the v0 test surface, not the
self-custody v1 wallet.
"""

import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(PACKAGE_DIR)
TEMPLATES_DIR = os.path.join(PACKAGE_DIR, "templates")
STATIC_DIR = os.path.join(PACKAGE_DIR, "static")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


LISTEN_HOST = _env("WB_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(_env("WB_LISTEN_PORT", "18701"))
# Unlock token; required for the API to serve anything but 401s.
TOKEN = _env("WB_TOKEN")
# Dedicated mazad wallet account backing the bench wallet.
ACCOUNT = _env("WB_ACCOUNT", "mobile-play")
# Hard per-send cap (bench guard — play funds only).
MAX_SEND = float(_env("WB_MAX_SEND", "50"))
# mazad RPC: either explicit URL/user/password or a maza.conf path to parse.
RPC_URL = _env("WB_RPC_URL")
RPC_USER = _env("WB_RPC_USER")
RPC_PASSWORD = _env("WB_RPC_PASSWORD")
RPC_CONF = _env("WB_RPC_CONF", "/var/lib/mazad/maza.conf")
RPC_TIMEOUT = int(_env("WB_RPC_TIMEOUT", "15"))
# Durable address-book persistence. Empty (dev/tests) = memory-only; the
# The installer sets WB_STATE_FILE to the instance's own state.json path
# (e.g. /var/lib/maza-wallet-bench/state.json for the mainnet bench or
# /var/lib/maza-wallet-bench-testnet/state.json for the testnet sibling)
# so a Restart=always cycle cannot orphan funded addresses. Read LIVE via
# state_file() — tests repoint it per-case.


def state_file() -> str:
    return _env("WB_STATE_FILE")
# Static assets served from STATIC_DIR — exact-filename whitelist.
STATIC_WHITELIST = {
    "wallet.js": "application/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
    "icon.png": "image/png",
}


def parse_maza_conf(path: str) -> dict:
    """Parse rpcuser/rpcpassword/rpcport/rpcconnect|rpcbind from maza.conf."""
    out = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def rpc_endpoint() -> tuple:
    """Resolve (url, user, password) for the mazad RPC, conf path fallback.

    Reads env live (not import-time constants) so tests can repoint
    WB_RPC_CONF/WB_RPC_URL per-case.
    """
    url = _env("WB_RPC_URL")
    if url:
        return url, _env("WB_RPC_USER"), _env("WB_RPC_PASSWORD")
    conf_path = _env("WB_RPC_CONF", "/var/lib/mazad/maza.conf")
    conf = parse_maza_conf(conf_path)
    host = conf.get("rpcconnect") or conf.get("rpcbind") or "127.0.0.1"
    # rpcbind values may carry a port ("127.0.0.1:12832").
    if ":" in host:
        host, _, port = host.rpartition(":")
        host = host or "127.0.0.1"
    else:
        port = conf.get("rpcport", "12832")
    url = f"http://{host}:{port}/"
    return url, conf.get("rpcuser", ""), conf.get("rpcpassword", "")
