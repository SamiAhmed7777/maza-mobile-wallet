"""JSON-RPC client for the MAZA daemon (mazad 0.16.3) + an offline mock.

Shape follows walletbench/chain.py WalletRPC (stdlib urllib, Basic auth,
bitcoin-family JSON-RPC 1.0).  Password handling: credentials go ONLY into
the Authorization header; error messages carry the RPC method and the
DAEMON's own error text, never the password.  Transport errors are retried
3 times with backoff.
"""

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 30
DEFAULT_ATTEMPTS = 3


class RpcError(Exception):
    """A JSON-RPC level error reported by the daemon (not retried).

    daemon_code carries the daemon's JSON-RPC error code as an int when
    one was parsed out of the error body, so callers can classify
    structurally instead of string-matching; it stays None for
    transport/parse failures and for string-built stand-ins (tests)."""

    def __init__(self, message, daemon_code=None):
        super().__init__(message)
        self.daemon_code = daemon_code


class JsonRpcClient:
    def __init__(self, url, user, password, timeout=DEFAULT_TIMEOUT,
                 attempts=DEFAULT_ATTEMPTS, backoff=(0.5, 1.0)):
        self.url = url
        self.user = user
        self.password = password
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self.backoff = tuple(backoff)

    def call(self, method, params=None):
        payload = json.dumps(
            {"jsonrpc": "1.0", "id": "maza-indexer",
             "method": method, "params": list(params or [])}
        ).encode("utf-8")
        body = self._post(payload, method, timeout=self.timeout)
        if body.get("error"):
            err = body["error"]
            code = err.get("code") if isinstance(err, dict) else None
            raise RpcError(f"rpc {method} error: {err}",
                           daemon_code=code if isinstance(code, int)
                           else None)
        return body.get("result")

    def call_batch(self, items):
        """Batched JSON-RPC 1.0: one HTTP POST carrying len(items) requests.

        items: sequence of (method, params) pairs.  Returns the list of
        results in item order.  Any per-item daemon error raises RpcError
        naming that item's method and the daemon's own error text (fail
        loud, IDX-7 class); a malformed batch reply (wrong type, wrong
        length, missing/duplicate ids) raises RpcError too.

        LIVE-DAEMON WITNESS 2026-11-20 (samihost mazad 0.16.3): a 3-item
        array request answered with a 3-element array in 0.157s and
        getblockheader [hash, False] inside a batch returned the 160-char
        header hex string -- the indexer crawl uses this to collapse
        3 round trips per block into 3 round trips per WINDOW.
        """
        count = len(items)
        if count == 0:
            return []
        entries = [{"jsonrpc": "1.0", "id": i, "method": method,
                    "params": list(params or [])}
                   for i, (method, params) in enumerate(items)]
        payload = json.dumps(entries).encode("utf-8")
        label = f"batch[{count}]"
        # A batch does len(items) daemon calls server-side before answering;
        # give it a timeout proportional to the window, not the single-call one.
        timeout = max(self.timeout, 10 * count)
        body = self._post(payload, label, timeout=timeout)
        if not isinstance(body, list):
            raise RpcError(f"rpc {label}: expected an array response, "
                           f"got {type(body).__name__}")
        if len(body) != count:
            raise RpcError(f"rpc {label}: expected {count} responses, "
                           f"got {len(body)}")
        results = []
        for resp in body:
            if not isinstance(resp, dict) or "id" not in resp:
                raise RpcError(f"rpc {label}: response entry without id: "
                               f"{resp!r:.200}")
            idx = resp["id"]
            if not isinstance(idx, int) or idx < 0 or idx >= count:
                raise RpcError(f"rpc {label}: response id {idx!r} out of "
                               f"range for a {count}-item batch")
            if len(results) != idx:
                raise RpcError(f"rpc {label}: responses out of order "
                               f"(expected id {len(results)}, got {idx})")
            method = items[idx][0]
            if resp.get("error"):
                err = resp["error"]
                code = err.get("code") if isinstance(err, dict) else None
                raise RpcError(f"rpc batch item {idx} {method} error: {err}",
                               daemon_code=code if isinstance(code, int)
                               else None)
            results.append(resp.get("result"))
        return results

    def _post(self, payload: bytes, method: str, timeout: float) -> dict:
        """Shared transport: attempts with backoff, HTTP 500 body mapping."""
        parts = urllib.parse.urlsplit(self.url)
        user = self.user or urllib.parse.unquote(parts.username or "")
        password = self.password or urllib.parse.unquote(parts.password or "")
        host_port = parts.netloc.rsplit("@", 1)[-1]
        raw = f"{user}:{password}".encode("utf-8")
        req = urllib.request.Request(
            urllib.parse.urlunsplit(
                ("http", host_port, parts.path or "/", "", "")),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic "
                                 + base64.b64encode(raw).decode("ascii"),
            },
        )
        last = None
        body = None
        for attempt in range(self.attempts):
            if attempt:
                delay = self.backoff[min(attempt - 1, len(self.backoff) - 1)]
                if delay:
                    time.sleep(delay)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                return body
            except urllib.error.HTTPError as exc:
                # Bitcoin-family daemons answer JSON-RPC errors with HTTP 500;
                # the useful text is in the BODY (walletbench/chain.py:67-76).
                try:
                    err_body = json.loads(exc.read().decode("utf-8"))
                    node_err = err_body.get("error") or err_body
                except Exception:
                    node_err = f"http {exc.code}"
                # Daemon-level error: deterministic, no retry.
                code = node_err.get("code") if isinstance(node_err, dict) \
                    else None
                raise RpcError(f"rpc {method} error: {node_err}",
                               daemon_code=code if isinstance(code, int)
                               else None) from exc
            except OSError as exc:
                last = exc
                continue
            except json.JSONDecodeError as exc:
                raise RpcError(f"rpc {method} bad JSON response") from exc
        raise RpcError(
            f"rpc {method} transport error after {self.attempts} "
            f"attempts: {last}")


class MockRpc:
    """Offline RPC stand-in for tests: method -> value or callable(params).

    Missing methods raise KeyError loudly, so a test never silently crawls
    the wrong fixture.
    """

    def __init__(self, handlers):
        self.handlers = dict(handlers)
        self.calls = []
        self.batch_calls = []

    def call(self, method, params=None):
        self.calls.append((method, list(params or [])))
        handler = self.handlers[method]
        if callable(handler):
            return handler(list(params or []))
        return handler

    def call_batch(self, items):
        """Batched counterpart: dispatches each item through the same
        handlers, records the batch as one entry in batch_calls, and keeps
        per-item (method, params) tuples in calls so existing assertions on
        call ordering keep working."""
        self.batch_calls.append(list(items))
        out = []
        for method, params in items:
            self.calls.append((method, list(params or [])))
            handler = self.handlers[method]
            if callable(handler):
                out.append(handler(list(params or [])))
            else:
                out.append(handler)
        return out
