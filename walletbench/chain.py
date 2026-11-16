"""Chain adapter for the wallet bench: mazad JSON-RPC + an offline MockChain.

Adapted from mazapay/mazad.py (same product family, stdlib-only).

ISOLATION MODEL (judge-verified 2026-11-16): Bitcoin-style accounts are
BOOKKEEPING LABELS, not UTXO isolation — wallet coin selection can consume
UTXOs associated with any account, so `sendfrom`/`sendtoaddress` are NEVER
used here. Every send is built as a raw transaction whose inputs are
explicitly selected from the bench addresses' own unspent outputs
(`listunspent` filtered by address), with change returned to a bench-owned
address. Only the bench UTXOs can ever be consumed; the mazapay-bridge
deposit is mathematically out of reach.
"""

import hashlib
import json
import secrets
from typing import Any, Dict, List, Optional, Tuple
import base64
import urllib.error
import urllib.parse
import urllib.request

from . import config

# Flat fee per send, MAZA. Generous vs the code floor (1000 sat/kB relay,
# typical tx < 0.5 kB => ~0.000005); bench play funds, simplicity wins.
FLAT_FEE = 0.0001


class ChainError(Exception):
    pass


class WalletRPC:
    """JSON-RPC client for mazad (0.16.3), raw-tx send path."""

    def __init__(self, url: str, user: str, password: str,
                 timeout: Optional[int] = None, account: Optional[str] = None):
        self.url = url
        self.user = user
        self.password = password
        self.timeout = timeout or config.RPC_TIMEOUT
        self.account = account if account is not None else config.ACCOUNT

    def rpc(self, method: str, *params: Any) -> Any:
        payload = json.dumps(
            {"jsonrpc": "1.0", "id": "maza-wallet-bench",
             "method": method, "params": list(params)}
        ).encode("utf-8")
        parts = urllib.parse.urlsplit(self.url)
        user = self.user or (urllib.parse.unquote(parts.username or ""))
        password = self.password or (urllib.parse.unquote(parts.password or ""))
        host_port = parts.netloc.rsplit("@", 1)[-1]
        raw = f"{user}:{password}".encode("utf-8")
        req = urllib.request.Request(
            urllib.parse.urlunsplit(("http", host_port, parts.path or "/", "", "")),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic " + base64.b64encode(raw).decode("ascii"),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Bitcoin-family RPC answers JSON-RPC errors with HTTP 500 —
            # the real error message lives in the BODY, not the status line
            # (masking it turned "Invalid Maza address" into a mystery 502).
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                node_err = err_body.get("error") or err_body
            except Exception:
                node_err = str(exc)
            raise ChainError(f"rpc {method} error: {node_err}") from exc
        except OSError as exc:
            raise ChainError(f"rpc {method} transport error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ChainError(f"rpc {method} bad JSON: {exc}") from exc
        if body.get("error"):
            raise ChainError(f"rpc {method} error: {body['error']}")
        return body.get("result")

    # --- wallet surface ------------------------------------------------------
    def getnewaddress(self) -> str:
        return str(self.rpc("getnewaddress", self.account))

    def import_watch_addresses(self, addresses: List[str]) -> int:
        """Watch-only import of client-held addresses (self-custody mode).

        The SERVER never receives the keys for these addresses — the phone
        signs everything locally; importaddress here only lets the wallet
        surface balances/history/broadcast for them. rescan=false: fresh
        addresses only receive NEW transactions, and a 4.48M-block rescan
        per address would pin the node for hours.
        """
        count = 0
        for address in addresses:
            self.rpc("importaddress", address, "", False)
            count += 1
        return count

    def sendraw_only(self, raw_hex: str) -> str:
        """Broadcast a client-signed raw transaction (self-custody path).

        No signing happens here — the bytes arrive already signed by the
        phone's key. This endpoint can never move funds by itself.
        """
        return str(self.rpc("sendrawtransaction", raw_hex))

    def listunspent_for(self, addresses: List[str],
                        minconf: int = 1) -> List[Dict[str, Any]]:
        return list(self.rpc("listunspent", int(minconf), 9999999,
                             list(addresses)) or [])

    def validateaddress(self, address: str) -> Dict[str, Any]:
        return dict(self.rpc("validateaddress", address) or {})

    def getrawtransaction_verbose(self, txid: str) -> Dict[str, Any]:
        """Decoded tx by txid (M20 funding-change reconciliation)."""
        return dict(self.rpc("getrawtransaction", txid, 1) or {})

    def listtransactions_all(self, count: int = 100) -> List[Dict[str, Any]]:
        return list(self.rpc("listtransactions", "*", int(count), 0) or [])

    def send_precise(self, from_addresses: List[str], to: str,
                     amount: float, change_address: str) -> str:
        """Spend ONLY unspent outputs belonging to from_addresses.

        Builds, signs and broadcasts a raw transaction: output = `to` +
        optional change back to change_address; fee = FLAT_FEE. Raises
        ChainError on insufficient funds. This is the isolation mechanism —
        see module docstring.
        """
        utxos = self.listunspent_for(from_addresses)
        need = amount + FLAT_FEE
        picked: List[Dict[str, Any]] = []
        total = 0.0
        for utxo in sorted(utxos, key=lambda u: -float(u.get("amount", 0))):
            total += float(utxo.get("amount", 0))
            picked.append({"txid": utxo["txid"], "vout": int(utxo["vout"])})
            if total >= need:
                break
        if total < need:
            raise ChainError(
                f"insufficient bench funds: have {total}, need {need}")
        outputs: Dict[str, float] = {to: round(amount, 8)}
        change = round(total - amount - FLAT_FEE, 8)
        if change > 0:
            outputs[change_address] = change
        raw = self.rpc("createrawtransaction", picked, outputs)
        signed = self.rpc("signrawtransaction", raw)
        if not (isinstance(signed, dict) and signed.get("complete")):
            raise ChainError("signing failed: transaction incomplete")
        return str(self.rpc("sendrawtransaction", signed["hex"]))


class MockChain:
    """In-memory stand-in with the identical surface — offline tests only.

    Tracks UTXOs per address so tests can PROVE the isolation property:
    a send from the bench address never consumes foreign UTXOs.
    """

    def __init__(self, account: str = None):
        self.account = account if account is not None else config.ACCOUNT
        self.utxos: List[Dict[str, Any]] = []  # {txid,vout,address,amount}
        self.txs: List[Dict[str, Any]] = []
        self._addr_seq = 0
        self._utxo_seq = 0
        self.last_send: Dict[str, Any] = {}
        self.watched: List[str] = []
        self.last_broadcast: str = ""
        # Addresses the NODE wallet holds keys for but the bench book does
        # not know (default-account change sinks — the M20 swept-change
        # hazard). getnewaddress() intentionally does NOT mark itself here:
        # existing tests use it as a stand-in external recipient.
        self.wallet_owned: set = set()
        # txid -> decoded tx dict, for getrawtransaction_verbose (M20 tests).
        self.decoded_txs: Dict[str, Dict[str, Any]] = {}

    def import_watch_addresses(self, addresses: List[str]) -> int:
        for address in addresses:
            if address not in self.watched:
                self.watched.append(address)
        return len(addresses)

    def sendraw_only(self, raw_hex: str) -> str:
        self.last_broadcast = raw_hex
        return hashlib.sha256(raw_hex.encode("ascii")).hexdigest()

    def fund_address(self, address: str, amount: float, label: str = "") -> None:
        """Test helper: mint an unspent output at `address`."""
        self._utxo_seq += 1
        self.utxos.append({"txid": f"mint{self._utxo_seq:04d}", "vout": 0,
                           "address": address, "amount": float(amount),
                           "label": label})

    def getnewaddress(self) -> str:
        self._addr_seq += 1
        return "M" + f"{self._addr_seq:011d}" + "x" * 22  # 1+11+22 = 34

    def listunspent_for(self, addresses: List[str],
                        minconf: int = 1) -> List[Dict[str, Any]]:
        return [u for u in self.utxos if u["address"] in set(addresses)]

    def validateaddress(self, address: str) -> Dict[str, Any]:
        valid = isinstance(address, str) and address.startswith("M") \
            and len(address) == 34
        return {"isvalid": valid, "ismine": address in self.wallet_owned,
                "iswatchonly": False, "address": address}

    def mint_wallet_address(self) -> str:
        """Mint a node-side default-account address: wallet-owned, NOT in
        the bench book — models the swept-change sink M20 reconciles."""
        self._addr_seq += 1
        addr = "M" + f"{self._addr_seq:011d}" + "y" * 22
        self.wallet_owned.add(addr)
        return addr

    def record_decoded_tx(self, txid: str, vout: List[Dict[str, Any]]) -> None:
        """Test helper: register a decoded tx for getrawtransaction_verbose."""
        self.decoded_txs[txid] = {"txid": txid, "vout": list(vout)}

    def getrawtransaction_verbose(self, txid: str) -> Dict[str, Any]:
        tx = self.decoded_txs.get(txid)
        if tx is None:
            raise ChainError("rpc getrawtransaction error: "
                             "No such transaction or Info about "
                             "transaction <{}> is not available".format(txid))
        return dict(tx)

    def listtransactions_all(self, count: int = 100) -> List[Dict[str, Any]]:
        return list(self.txs[:count])

    def send_precise(self, from_addresses: List[str], to: str,
                     amount: float, change_address: str) -> str:
        ours = set(from_addresses)
        utxos = [u for u in self.utxos if u["address"] in ours]
        need = amount + FLAT_FEE
        picked: List[Dict[str, Any]] = []
        total = 0.0
        for utxo in sorted(utxos, key=lambda u: -float(u.get("amount", 0))):
            total += float(utxo["amount"])
            picked.append({"txid": utxo["txid"], "vout": int(utxo["vout"])})
            if total >= need:
                break
        if total < need:
            raise ChainError(f"insufficient bench funds: have {total}, need {need}")
        # Consume exactly the picked UTXOs.
        picked_ids = {(p["txid"], p["vout"]) for p in picked}
        self.utxos = [u for u in self.utxos
                      if (u["txid"], u["vout"]) not in picked_ids]
        change = round(total - amount - FLAT_FEE, 8)
        if change > 0:
            self.fund_address(change_address, change)
        self.last_send = {"from_addresses": sorted(ours), "to": to,
                          "amount": float(amount), "consumed": sorted(picked_ids)}
        txid = secrets.token_hex(32)
        self.txs.insert(0, {"category": "send", "amount": -amount,
                            "confirmations": 0, "time": 0, "address": to,
                            "txid": txid})
        return txid


def get_chain() -> WalletRPC:
    url, user, password = config.rpc_endpoint()
    if not url:
        raise ChainError("no RPC endpoint configured (WB_RPC_URL or WB_RPC_CONF)")
    return WalletRPC(url, user, password)
