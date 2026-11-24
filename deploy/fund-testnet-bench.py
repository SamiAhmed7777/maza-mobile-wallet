#!/usr/bin/env python3
"""S-6-ii-prep-c: bench-book bring-up + funding for the TESTNET walletbench.

Run ON samihost from the rsynced repo root:

    python3 deploy/fund-testnet-bench.py            # DRY-RUN (default)
    python3 deploy/fund-testnet-bench.py --execute  # bring-up + (if gates pass) fund
    python3 deploy/fund-testnet-bench.py --selftest # offline, temp-dir only

DRY-RUN is strictly read-only: it proves the service is up (unauthenticated
401), reads getblockchaininfo + listunspent over the node RPC parsed from the
env's WB_RPC_CONF, and prints the gate panel plus the plan. It NEVER sends
the authenticated /api/state call — on a cold book that call itself is the
mutation (it triggers _ensure_addresses -> getnewaddress -> persist), so it
is reserved for --execute.

--execute performs, in order:
  1. BOOK BRING-UP (explicit, first — finding B: no endpoint cold-starts
     the bench book; /api/watch/utxos reads the watch book only):
       a. unauthenticated GET /api/state -> expect 401 (service up, locked)
       b. authenticated GET /api/state   -> triggers _ensure_addresses ->
          getnewaddress -> durable persist of state.json
       c. verify the persisted file: valid JSON, checksum-valid MAZA
          addresses (base58check, v50/v88 — walletbench.addrcheck)
       d. RESTART-PROOF: systemctl restart the unit, wait for it to answer,
          authenticated /api/state again -> the SAME primary address
          (proves the chain-tolerant loader keeps a testnet book alive
          across restarts — finding A)
  2. GATES (funding proceeds only when ALL hard gates pass):
       chain=test · blocks==headers · tip>=101 ·
       tip fresh (median age <2h) ·
       matured node-wallet UTXOs (minconf=101) >= --amount
     The ibd/chainwork FLAGs are printed report-only: on this self-mined
     fork initialblockdownload is structurally stuck True (MAZA testnet
     minimumchainwork, chainparams.cpp:277) and cannot express sync truth.
  3. FUND: node-wallet sendtoaddress(primary, amount) -> txid ->
       POST /api/book/reconcile {txid} (M20: books any swept change).

Credentials (WB_TOKEN, RPC user/password) are parsed in-process and are
never printed, never placed in argv, never logged. Addresses ARE printed
(blockchain-public data). Exit codes: 0 success/dry-run, 1 gate or probe
failure (node-RPC transport failures — stalled/refused/non-JSON — land
here as named GateFail FATAL lines, never raw tracebacks), 2 selftest
failure.
"""

import argparse
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from walletbench.addrcheck import is_maza_address  # noqa: E402
from walletbench.config import parse_maza_conf  # noqa: E402

BENCH_ENV_PATH = os.environ.get(
    "FUND_BENCH_ENV", "/etc/maza-wallet-bench-testnet.env")
UNIT_NAME = os.environ.get("FUND_UNIT", "maza-wallet-bench-testnet.service")
# Sync gate — WHY NOT the ibd flag: MAZA testnet carries a REAL-chain
# minimumchainwork (chainparams.cpp:277, nMinimumChainWork=0x5f2e22e5a21778
# "Block 627011"). A 0.16.3 daemon keeps initialblockdownload=True until
# nChainWork reaches that minimum; the self-mined controlled fork sits
# ORDERS of magnitude below (measured 2026-11-24: tip=142 chainwork
# 0x55b66b6db vs the minimum), so the flag is structurally stuck True and
# proves nothing here. The sync truth this gate exists for (never trust
# balances on a mid-sync node) is expressed by blocks==headers + a FRESH
# tip instead.
TIP_FRESH_MAX_AGE_S = 7200  # tip block must be <2h old (campaign mines continuously)
TIP_GATE = 101          # block-1 coinbase matures (100-block coinbase delay)
FUND_MINCONF = 101      # only spend fully-matured coinbases
RESTART_TIMEOUT_S = 45


class GateFail(Exception):
    pass


def parse_env_file(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def http_json(url: str, token: Optional[str] = None,
              method: str = "GET", body: Optional[dict] = None,
              timeout: int = 10) -> Tuple[int, Any]:
    """Return (status, parsed-json-or-None). Never raises on HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                return resp.status, json.loads(resp.read())
            except (json.JSONDecodeError, ValueError):
                return resp.status, None
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except (json.JSONDecodeError, ValueError):
            return exc.code, None
    except (urllib.error.URLError, OSError):
        return 0, None


def rpc_call(conf: Dict[str, str], method: str,
             params: list) -> Any:
    """One JSON-RPC call over the conf-parsed endpoint; creds in-process."""
    host = conf.get("rpcconnect") or conf.get("rpcbind") or "127.0.0.1"
    if ":" in host:
        host, _, port = host.rpartition(":")
        host = host or "127.0.0.1"
    else:
        port = conf.get("rpcport", "18446")
    if host in ("0.0.0.0", "", "::"):
        host = "127.0.0.1"
    import base64
    url = f"http://{host}:{port}/"
    req = urllib.request.Request(url, data=json.dumps({
        "jsonrpc": "1.0", "id": "fund", "method": method,
        "params": params}).encode())
    req.add_header("Content-Type", "application/json")
    raw = (conf.get("rpcuser", "") + ":" + conf.get("rpcpassword", ""))
    req.add_header("Authorization", "Basic "
                   + base64.b64encode(raw.encode()).decode())
    # Transport failures must exit as a named gate failure (FATAL line,
    # exit 1), never a raw traceback: a stalled node RPC raised raw
    # TimeoutError/URLError out of run() (residual (b), 47th tick 2026-11-24).
    # socket.timeout/TimeoutError/ConnectionRefusedError/DNS failures are
    # OSError subclasses; urllib wraps some as URLError; HTTPError (4xx/5xx
    # from the daemon) is a URLError subclass too; torn reads raise
    # http.client.HTTPException. The message carries the method and the
    # failure reason only — never creds, never a response payload.
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, http.client.HTTPException,
            OSError) as exc:
        raise GateFail(f"rpc {method} transport failure: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GateFail(f"rpc {method}: non-JSON response") from exc
    if not isinstance(payload, dict):
        raise GateFail(f"rpc {method}: non-object JSON response")
    if payload.get("error"):
        raise GateFail(f"rpc {method} error: {payload['error']}")
    return payload.get("result")


def rpc_conf_from_env(env: Dict[str, str]) -> Dict[str, str]:
    conf_path = env.get("WB_RPC_CONF")
    if not conf_path:
        raise GateFail("env has no WB_RPC_CONF")
    return parse_maza_conf(conf_path)


def gate_report(info: Dict[str, Any], matured_total: float,
                amount: float, now_ts: Optional[int] = None
                ) -> List[Tuple[str, bool, str, bool]]:
    """Pure gate evaluation. Rows are (name, passed, observed, hard).

    `hard` rows gate funding; the ibd/chainwork rows are report-only —
    the ibd FLAG is structurally stuck True on this self-mined fork
    (testnet minimumchainwork, see TIP_FRESH_MAX_AGE_S comment) and
    must never fail the run.
    """
    tip = int(info.get("blocks", 0))
    headers = int(info.get("headers", -1))
    ibd = bool(info.get("initialblockdownload"))
    chain = str(info.get("chain", ""))
    mediantime = int(info.get("mediantime", 0))
    now_ts = int(now_ts if now_ts is not None else time.time())
    tip_age = now_ts - mediantime
    chainwork = str(info.get("chainwork", ""))
    return [
        ("chain=test", chain == "test", f"chain={chain}", True),
        ("blocks==headers", tip == headers,
         f"blocks={tip} headers={headers}", True),
        (f"tip>={TIP_GATE}", tip >= TIP_GATE, f"tip={tip}", True),
        (f"tip fresh (median age <{TIP_FRESH_MAX_AGE_S}s)",
         0 <= tip_age < TIP_FRESH_MAX_AGE_S, f"mediantime age={tip_age}s",
         True),
        (f"matured(minconf={FUND_MINCONF}) >= {amount}",
         matured_total >= amount, f"matured_total={matured_total:.8f}", True),
        # report-only: structurally stuck on the self-mined fork
        ("ibd flag (report-only)", True,
         f"initialblockdownload={ibd} (stuck by testnet "
         "minimumchainwork on this fork; sync truth = rows above)",
         False),
        ("chainwork (report-only)", True, f"chainwork={chainwork}", False),
    ]


def bench_base_url(env: Dict[str, str]) -> str:
    host = env.get("WB_LISTEN_HOST", "127.0.0.1")
    port = env.get("WB_LISTEN_PORT", "18702")
    return f"http://{host}:{port}"


def verify_state_file(path: str) -> Tuple[List[str], List[str]]:
    """Structural validation of the persisted book; returns (book, watch)."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.loads(fh.read())
    if not isinstance(data, dict):
        raise GateFail("state.json is not a JSON object")
    book = data.get("addresses")
    watch = data.get("watch_addresses")
    if not isinstance(book, list) or not book:
        raise GateFail("state.json has no addresses list")
    for label, lst in (("addresses", book), ("watch_addresses", watch)):
        if not isinstance(lst, list):
            raise GateFail(f"state.json {label} is not a list")
        for addr in lst:
            if not is_maza_address(addr):
                raise GateFail(
                    f"state.json {label} holds a non-MAZA entry "
                    f"(len={len(addr) if isinstance(addr, str) else '?'})")
    return [a for a in book if isinstance(a, str)], \
        [a for a in (watch or []) if isinstance(a, str)]


def wait_for_service(base: str, timeout_s: int = RESTART_TIMEOUT_S) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        status, _ = http_json(base + "/api/state", timeout=5)
        if status == 401:
            return
        time.sleep(2)
    raise GateFail(f"service did not come back within {timeout_s}s")


def bring_up_book(env: Dict[str, str]) -> str:
    """Explicit book cold-start + restart-proof; returns primary address."""
    token = env.get("WB_TOKEN")
    if not token:
        raise GateFail("env has no WB_TOKEN")
    base = bench_base_url(env)
    state_path = env.get("WB_STATE_FILE")
    if not state_path:
        raise GateFail("env has no WB_STATE_FILE")

    status, _ = http_json(base + "/api/state", timeout=10)
    if status != 401:
        raise GateFail(f"pre-probe: expected 401 locked, got {status}")
    print(f"  [bring-up] service up + locked: 401 ok")

    status, payload = http_json(base + "/api/state", token=token, timeout=30)
    if status != 200 or not isinstance(payload, dict):
        raise GateFail(f"authenticated /api/state -> {status} (book trigger "
                       "failed)")
    primary = payload.get("address")
    if not isinstance(primary, str) or not is_maza_address(primary):
        raise GateFail("served primary address failed MAZA validation")
    if not os.path.exists(state_path):
        raise GateFail("authenticated /api/state did not persist state.json")
    book, watch = verify_state_file(state_path)
    if not book or book[0] != primary:
        raise GateFail("persisted book's primary != served primary")
    print(f"  [bring-up] book persisted: addresses={len(book)} "
          f"watch={len(watch)} primary checksum-valid (v50/v88)")

    # Restart-proof (finding A): the chain-tolerant loader must keep a
    # testnet book alive across Restart=always — the old letter-shape
    # gate crash-looped here.
    print(f"  [bring-up] restart-proof: restarting {UNIT_NAME}")
    subprocess.run(["systemctl", "restart", UNIT_NAME], check=True)
    wait_for_service(base)
    status, payload2 = http_json(base + "/api/state", token=token, timeout=30)
    if status != 200 or not isinstance(payload2, dict):
        raise GateFail(f"post-restart /api/state -> {status} "
                       "(state load failed — crash-loop suspect)")
    if payload2.get("address") != primary:
        raise GateFail("post-restart primary address DIFFERS from "
                       "pre-restart (book not durable)")
    print("  [bring-up] restart-proof PASS: same primary address "
          "across a real service restart")
    return primary


def run(env_path: str, execute: bool, amount: float) -> int:
    env = parse_env_file(env_path)
    conf = rpc_conf_from_env(env)
    base = bench_base_url(env)
    print(f"fund-testnet-bench: mode={'EXECUTE' if execute else 'DRY-RUN'} "
          f"amount={amount}")
    print(f"  bench={base} env={env_path} (token present: "
          f"{'yes' if env.get('WB_TOKEN') else 'NO'})")

    status, _ = http_json(base + "/api/state", timeout=10)
    if status != 401:
        raise GateFail(f"bench service probe: expected 401, got {status} "
                       "(service down or unexpectedly open)")
    print("  service probe: 401 locked ok")

    info = rpc_call(conf, "getblockchaininfo", [])
    # listunspent(minconf, maxconf) — node wallet's UTXOs at >=minconf;
    # remaining positionals default (no address filter, safe-only).
    unspent = rpc_call(conf, "listunspent",
                       [FUND_MINCONF, 9999999]) or []
    matured_total = float(sum(u.get("amount", 0) for u in unspent))
    rows = gate_report(info, matured_total, amount)
    print("  gates:")
    for name, ok, observed, hard in rows:
        tag = "PASS" if ok else "FAIL"
        if not hard:
            tag = "note"
        print(f"    [{tag}] {name}  ({observed})")

    if not execute:
        state_path = env.get("WB_STATE_FILE", "")
        exists = os.path.exists(state_path) if state_path else False
        print(f"  state.json exists: {exists}"
              + (f" (book cold-start = --execute step 1)" if not exists else ""))
        print("DRY-RUN COMPLETE — nothing mutated. --execute performs: "
              "book bring-up (+restart-proof), then funding only if every "
              "gate passes.")
        return 0

    print("EXECUTE: step 1 — book bring-up")
    primary = bring_up_book(env)

    failed = [name for name, ok, _observed, hard in rows
              if hard and not ok]
    if failed:
        print(f"EXECUTE STOPPED before funding: gates failed: {failed}; "
              "book bring-up is done and durable. Re-run --execute when "
              "the maturity/sync gates pass.")
        return 1

    print(f"EXECUTE: step 2 — funding {amount} MAZA -> bench primary")
    txid = rpc_call(conf, "sendtoaddress", [primary, amount])
    if not isinstance(txid, str) or len(txid) != 64:
        raise GateFail(f"sendtoaddress returned no txid: {type(txid)}")
    print(f"  funding txid: {txid}")
    token = env["WB_TOKEN"]
    status, payload = http_json(base + "/api/book/reconcile", token=token,
                                method="POST", body={"txid": txid},
                                timeout=30)
    if status != 200:
        # Non-fatal for the FUNDING itself (coins are on-chain at the
        # primary address); reconcile only books swept change (M20).
        print(f"  WARNING: /api/book/reconcile -> {status}; the funding "
              "output is booked (it is the primary), any swept change "
              "must be reconciled manually.")
    else:
        print(f"  reconcile: {json.dumps(payload)}")
    print("EXECUTE COMPLETE")
    return 0


def selftest() -> int:
    """Offline: temp-dir env/conf trees + pure logic only. No network."""
    import tempfile
    ok = True
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))
        if not cond:
            nonlocal ok
            ok = False

    # --- env + conf parsing -------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        conf_path = os.path.join(tmp, "rpc.conf")
        with open(conf_path, "w") as fh:
            fh.write("rpcuser=funduser\nrpcpassword=fundpw\n"
                     "rpcbind=127.0.0.1:18446\nrpcport=18446\n")
        env_path = os.path.join(tmp, "bench.env")
        with open(env_path, "w") as fh:
            fh.write("# comment line\nWB_TOKEN=tok123\n"
                     f"WB_RPC_CONF={conf_path}\nWB_LISTEN_HOST=127.0.0.1\n"
                     "WB_LISTEN_PORT=18702\n")
        env = parse_env_file(env_path)
        check("env-parse token", env.get("WB_TOKEN") == "tok123")
        check("env-parse port", env.get("WB_LISTEN_PORT") == "18702")
        conf = rpc_conf_from_env(env)
        check("conf-parse bind", conf.get("rpcbind") == "127.0.0.1:18446")
        check("conf-parse user", conf.get("rpcuser") == "funduser")
        check("base-url", bench_base_url(env) == "http://127.0.0.1:18702")

        # --- gates (pure) -------------------------------------------------
        now = 1_800_000_000  # fixed clock for deterministic rows
        rows = gate_report(
            {"chain": "test", "blocks": 140, "headers": 140,
             "initialblockdownload": False, "mediantime": now - 60,
             "chainwork": "0xaa"}, 3.0, 2.0, now_ts=now)
        hard = [(n, ok) for n, ok, _o, h in rows if h]
        check("gates all-pass at tip140 (7 rows)",
              all(ok for _n, ok in hard) and len(rows) == 7
              and all(ok for _n, _o, _obs, h in rows if not h))
        rows = gate_report(
            {"chain": "test", "blocks": 96, "headers": 96,
             "initialblockdownload": True, "mediantime": now - 3 * 3600,
             "chainwork": "0x01"}, 3.0, 2.0, now_ts=now)
        failed = [n for n, ok, _o, h in rows if h and not ok]
        check("gates fail on short+stale tip (ibd report-only)",
              len(failed) == 2 and failed[0].startswith("tip>=")
              and failed[1].startswith("tip fresh"))
        rows = gate_report(
            {"chain": "main", "blocks": 200, "headers": 190,
             "initialblockdownload": False, "mediantime": now - 60,
             "chainwork": "0x02"}, 1.0, 2.0, now_ts=now)
        failed = [n for n, ok, _o, h in rows if h and not ok]
        check("gates fail on chain/sync/amount",
              failed == ["chain=test", "blocks==headers",
                         f"matured(minconf={FUND_MINCONF}) >= 2.0"])
        rows = gate_report(
            {"chain": "test", "blocks": 140, "headers": 140,
             "initialblockdownload": True, "mediantime": now - 30,
             "chainwork": "0x03"}, 3.0, 2.0, now_ts=now)
        failed = [n for n, ok, _o, h in rows if h and not ok]
        check("stuck ibd flag never fails the run", failed == [])

        # --- state verification (addrcheck-driven) ------------------------
        from walletbench.addrcheck import encode_address
        good = os.path.join(tmp, "state.json")
        with open(good, "w") as fh:
            json.dump({"addresses": [encode_address(88, b"\xb9" * 20)],
                       "txids": [],
                       "watch_addresses": [encode_address(88, b"\xb8" * 20)]},
                      fh)
        book, watch = verify_state_file(good)
        check("state-verify testnet book", len(book) == 1 and len(watch) == 1)
        bad = os.path.join(tmp, "state-bad.json")
        with open(bad, "w") as fh:
            json.dump({"addresses": ["M" + "1" * 33], "txids": [],
                       "watch_addresses": []}, fh)
        try:
            verify_state_file(bad)
            check("state-verify rejects junk", False)
        except GateFail:
            check("state-verify rejects junk", True)

    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print(f"SELFTEST: {sum(1 for _, p in checks if p)}/{len(checks)} PASS")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser(
        description="testnet bench-book bring-up + funding (S-6-ii-prep-c)")
    ap.add_argument("--execute", action="store_true",
                    help="perform bring-up + funding (default: dry-run)")
    ap.add_argument("--amount", type=float, default=2.0,
                    help="MAZA to fund the bench book with (default 2.0)")
    ap.add_argument("--selftest", action="store_true",
                    help="offline self-test in a temp dir; exit 0/2")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if args.amount <= 0 or args.amount > 50:
        print("FATAL: --amount must be within (0, 50]", file=sys.stderr)
        return 1
    try:
        return run(BENCH_ENV_PATH, args.execute, args.amount)
    except GateFail as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
