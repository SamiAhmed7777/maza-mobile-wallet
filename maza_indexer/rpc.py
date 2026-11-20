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
        for attempt in range(self.attempts):
            if attempt:
                delay = self.backoff[min(attempt - 1, len(self.backoff) - 1)]
                if delay:
                    time.sleep(delay)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                break
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
        else:
            raise RpcError(
                f"rpc {method} transport error after {self.attempts} "
                f"attempts: {last}")
        if body.get("error"):
            err = body["error"]
            code = err.get("code") if isinstance(err, dict) else None
            raise RpcError(f"rpc {method} error: {err}",
                           daemon_code=code if isinstance(code, int)
                           else None)
        return body.get("result")


class MockRpc:
    """Offline RPC stand-in for tests: method -> value or callable(params).

    Missing methods raise KeyError loudly, so a test never silently crawls
    the wrong fixture.
    """

    def __init__(self, handlers):
        self.handlers = dict(handlers)
        self.calls = []

    def call(self, method, params=None):
        self.calls.append((method, list(params or [])))
        handler = self.handlers[method]
        if callable(handler):
            return handler(list(params or []))
        return handler
