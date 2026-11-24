"""fund-testnet-bench.py rpc_call transport-failure mapping (residual (b)).

Contract pinned here: EVERY node-RPC transport failure shape — stalled
(socket.timeout/TimeoutError), refused (ConnectionRefusedError), wrapped
URLError, torn/non-JSON body, non-object JSON, daemon error payload —
surfaces as GateFail (the script's FATAL/exit-1 path), never a raw
traceback out of run(). Messages name the METHOD and the failure only:
never the rpcpassword, never a response payload.
"""

import importlib.util
import json
import os
import socket
import unittest
import urllib.error
import urllib.request
from unittest import mock

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_REPO, "deploy", "fund-testnet-bench.py")

_spec = importlib.util.spec_from_file_location("fund_testnet_bench", _SCRIPT)
fund = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fund)

CONF = {"rpcuser": "funduser", "rpcpassword": "s3cretpw",
        "rpcbind": "127.0.0.1:18446"}
METHOD = "getblockchaininfo"


class _FakeResp(object):
    """Minimal urlopen() return value: context manager + read()."""

    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TransportFailureMappingTest(unittest.TestCase):
    def _raises_gatefail(self, side_effect=None, return_value=None,
                         needle=None, absent=("s3cretpw",)):
        original = urllib.request.urlopen
        kwargs = {}
        if side_effect is not None:
            kwargs["side_effect"] = side_effect
        if return_value is not None:
            kwargs["return_value"] = return_value
        try:
            with mock.patch("urllib.request.urlopen", **kwargs):
                with self.assertRaises(fund.GateFail) as ctx:
                    fund.rpc_call(CONF, METHOD, [])
        finally:
            self.assertEqual(urllib.request.urlopen, original,
                             "urlopen not restored")
        message = str(ctx.exception)
        self.assertIn(METHOD, message, "method not named in GateFail")
        for secret in absent:
            self.assertNotIn(secret, message, "secret leaked in GateFail")
        if needle is not None:
            self.assertIn(needle, message)
        return message

    def test_timeout_maps_to_gatefail(self):
        msg = self._raises_gatefail(side_effect=socket.timeout("timed out"),
                                    needle="transport failure")
        self.assertIn("timed out", msg)

    def test_conn_refused_maps_to_gatefail(self):
        self._raises_gatefail(side_effect=ConnectionRefusedError(111, "x"),
                              needle="transport failure")

    def test_urlerror_maps_to_gatefail(self):
        self._raises_gatefail(
            side_effect=urllib.error.URLError("no route to host"),
            needle="transport failure")

    def test_httperror_maps_to_gatefail(self):
        # HTTPError is the 4xx/5xx shape (wrong rpc creds -> 401 from the
        # daemon); it must land in the same named GateFail path.
        self._raises_gatefail(
            side_effect=urllib.error.HTTPError(
                "http://127.0.0.1:18446/", 401, "Unauthorized", {}, None),
            needle="transport failure")

    def test_non_json_body_maps_to_gatefail(self):
        self._raises_gatefail(
            return_value=_FakeResp(b"<html>502 Bad Gateway</html>"),
            needle="non-JSON response")

    def test_non_object_json_maps_to_gatefail(self):
        self._raises_gatefail(
            return_value=_FakeResp(json.dumps([1, 2]).encode()),
            needle="non-object JSON response")

    def test_daemon_error_payload_maps_to_gatefail(self):
        msg = self._raises_gatefail(
            return_value=_FakeResp(json.dumps(
                {"result": None, "error":
                 {"code": -4, "message": "wallet already contains key"}}
            ).encode()),
            needle="wallet already contains key")

    def test_happy_path_returns_result(self):
        result = {"chain": "test", "blocks": 142}
        with mock.patch(
                "urllib.request.urlopen",
                return_value=_FakeResp(json.dumps(
                    {"result": result, "error": None}).encode())):
            self.assertEqual(fund.rpc_call(CONF, METHOD, []), result)


if __name__ == "__main__":
    unittest.main()
