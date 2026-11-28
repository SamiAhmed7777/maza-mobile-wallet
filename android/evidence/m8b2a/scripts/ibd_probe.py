#!/usr/bin/env python3
"""Read-only bench-node sync probe (runs ON samihost via `ssh samihost python3 - < ibd_probe.py`).

Prints ONLY blocks / headers / progress / initialblockdownload (+ chain + mediantime).
Credentials are read from the bench env file + its WB_RPC_CONF maza.conf in-process and are
never printed, never placed in argv, never written anywhere.
"""
import base64
import json
import os
import sys
import urllib.request


def read_kv(path):
    out = {}
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError as exc:
        print("READ-FAIL %s: %s" % (path, exc.__class__.__name__))
    return out


env_path = "/etc/maza-wallet-bench.env"
if not os.access(env_path, os.R_OK):
    print("ENV-UNREADABLE %s" % env_path)
    sys.exit(2)
env = read_kv(env_path)
conf_path = env.get("WB_RPC_CONF", "")
conf = read_kv(conf_path) if conf_path.startswith("/") else {}
if not conf:
    print("RPC-CONF-UNREADABLE")
    sys.exit(2)

host = conf.get("rpcbind", "127.0.0.1") or "127.0.0.1"
if host in ("0.0.0.0", "::", "[::]"):
    host = "127.0.0.1"
port = conf.get("rpcport") or "12832"
url = "http://%s:%s" % (host, port)
user = conf.get("rpcuser", "")
pw = conf.get("rpcpassword", "")
tok = base64.b64encode(("%s:%s" % (user, pw)).encode()).decode()
body = json.dumps({
    "jsonrpc": "1.0",
    "id": "ibdprobe",
    "method": "getblockchaininfo",
    "params": [],
}).encode()
req = urllib.request.Request(url, data=body, headers={
    "Content-Type": "application/json",
    "Authorization": "Basic %s" % tok,
})
try:
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
except Exception as exc:  # noqa: BLE001 - print class only, never the message (may carry URL)
    print("RPC-FAIL %s" % exc.__class__.__name__)
    sys.exit(3)
r = data.get("result") or (data.get("error") and {"error": data["error"]})
if not isinstance(r, dict) or "blocks" not in r:
    print("RPC-NO-RESULT error=%s" % (json.dumps(data.get("error"))[:200]))
    sys.exit(3)
for k in ("chain", "blocks", "headers", "verificationprogress", "initialblockdownload", "mediantime", "pruned"):
    print("%s=%s" % (k, r.get(k)))
