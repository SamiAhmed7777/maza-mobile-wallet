"""IDX-9d transient-RPC tolerance tests (live-defect round 2026-11-20).

LIVE DEFECT being pinned: mazad's IBD run restarts ~every 30-45 min; in the
seconds-to-minutes window after each restart the daemon answers JSON-RPC
-28 ("Loading wallet...") or refuses connections.  ingest.run() treated any
RpcError as fatal and the process exited into a systemd 5s restart burst
(samihost 2026-11-20 02:2x-02:46 PST: NRestarts 17->33, four deaths in 24s,
public /indexer/health 2x 000), taking the read API down with it.

The fix: the crawl's rpc.call sites route through Ingestor.rpc_paused(),
which pauses (capped exponential backoff, loud per-retry log) through
TRANSIENT shapes -- daemon warm-up -28 and transport exhaustion -- and
re-raises everything else unchanged (fail loud: the IDX-7 wrong-verbosity
defect class must never be masked as a stall).

Also pinned here: the api._send BrokenPipe/ConnectionReset guard -- the
same incident's journal was full of socketserver tracebacks from health
probes that timed out client-side, which polluted every error grep used
for triage.

MockRpc/ScriptedRpc only -- no network in unit tests.
"""

import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from maza_indexer import api as api_module
from maza_indexer.ingest import (Ingestor, RPC_PAUSE_BASE_S, RPC_PAUSE_CAP_S,
                                 rpc_error_is_transient)
from maza_indexer.rpc import MockRpc, RpcError
from maza_indexer.store import Store
from test_maza_indexer_core import build_chain, make_config, make_mock_rpc

# The EXACT wire shapes from the live incident (samihost journal,
# 2026-11-20 11:46:31 CET): rpc.py wraps the daemon's error dict verbatim.
WARMUP_WALLET = ("rpc getblockchaininfo error: "
                 "{'code': -28, 'message': 'Loading wallet...'}")
WARMUP_BLOCKIDX = ('rpc getblockchaininfo error: '
                   '{"code": -28, "message": "Loading block index..."}')
TRANSPORT_DEAD = ("rpc getblock transport error after 3 attempts: "
                  "[Errno 111] Connection refused")
PERMANENT_VERBOSITY = ("rpc getblockheader error: "
                       "{'code': -1, 'message': 'JSON value is not a "
                       "boolean as expected'}")
PERMANENT_RANGE = ("rpc getblockhash error: "
                   "{'code': -8, 'message': 'Block height out of range'}")
PERMANENT_BADJSON = "rpc getblock bad JSON response"


class ScriptedRpc(MockRpc):
    """MockRpc with a one-shot fault script.  Each entry is (method, exc)
    -- fires on that method's 1st call -- or (method, exc, nth) -- fires
    on exactly that 1-based CALL NUMBER.  Call numbers count every call,
    retries included, so a retry inside one rpc_paused loop advances the
    counter: nth=1 + nth=3 means "fault the first call, then the third"
    (i.e. the next height's getblock).  Records every fault it fired."""

    def __init__(self, handlers, faults):
        super().__init__(handlers)
        self.faults = [(f[0], f[1], f[2] if len(f) > 2 else 1)
                       for f in faults]
        self.fired = []
        self._counts = {}

    def call(self, method, params=None):
        self._counts[method] = self._counts.get(method, 0) + 1
        for i, (m, exc, nth) in enumerate(self.faults):
            if m == method and nth == self._counts[method]:
                del self.faults[i]
                self.fired.append((method, exc))
                raise exc
        return super().call(method, params)

    def call_batch(self, items):
        """Batched window: the SAME fault script, applied per item.  Each
        item counts against its method's call counter exactly like a
        single call did, so a fault keyed to (getblock, nth=3) still
        lands on the 3rd block of the crawl -- it now surfaces as the
        whole batch raising (the window is all-or-nothing)."""
        for method, _params in items:
            self._counts[method] = self._counts.get(method, 0) + 1
            for i, (m, exc, nth) in enumerate(self.faults):
                if m == method and nth == self._counts[method]:
                    del self.faults[i]
                    self.fired.append((method, exc))
                    raise exc
        return super().call_batch(items)


class _PauseRecorder:
    """Stands in for time.sleep: records every pause and never blocks."""

    def __init__(self):
        self.delays = []

    def __call__(self, seconds):
        self.delays.append(seconds)


def _ingestor_with_faults(faults, method="getblockchaininfo", tip=11):
    """Store + ScriptedRpc over the standard 12-block fixture + an
    ingestor whose sleeps are recorded.  Faults target the whole-call
    level (any method); the fixture stays the core suite's own."""
    tmp = tempfile.mkdtemp(prefix="idx9d-")
    cfg = make_config(tmp)
    store = Store(cfg.db_path)
    base = make_mock_rpc(build_chain(), tip=tip)
    rpc = ScriptedRpc(base.handlers, faults)
    rec = _PauseRecorder()
    ing = Ingestor(store, rpc, cfg, poll_seconds=0.001, sleep_fn=rec)
    return tmp, store, rpc, rec, ing


class TestRpcErrorClassification(unittest.TestCase):
    """The classifier must separate the two node-restart-window shapes
    from every permanent daemon error -- including the exact IDX-7
    verbosity shape, which MUST stay permanent."""

    def test_warmup_single_quote_dict_is_transient(self):
        self.assertTrue(rpc_error_is_transient(RpcError(WARMUP_WALLET)))

    def test_warmup_double_quote_dict_is_transient(self):
        self.assertTrue(rpc_error_is_transient(RpcError(WARMUP_BLOCKIDX)))

    def test_transport_exhaustion_is_transient(self):
        self.assertTrue(rpc_error_is_transient(RpcError(TRANSPORT_DEAD)))

    def test_verbosity_minus1_is_permanent(self):
        # The IDX-7 live defect's exact shape: a wrong call signature
        # crash-looped from block 0 in minutes BECAUSE it exited loud.
        self.assertFalse(
            rpc_error_is_transient(RpcError(PERMANENT_VERBOSITY)))

    def test_range_minus8_is_permanent(self):
        self.assertFalse(rpc_error_is_transient(RpcError(PERMANENT_RANGE)))

    def test_bad_json_is_permanent(self):
        self.assertFalse(
            rpc_error_is_transient(RpcError(PERMANENT_BADJSON)))

    def test_code_without_warmup_value_is_permanent(self):
        self.assertFalse(rpc_error_is_transient(
            RpcError("rpc x error: {'code': 500, 'message': 'boom'}")))

    def test_plain_message_is_permanent(self):
        self.assertFalse(rpc_error_is_transient(RpcError("mystery failure")))

    def test_structural_daemon_code_wins_over_text(self):
        # A structured -28 classifies transient even in an odd message
        # shape; a structured permanent code classifies permanent EVEN
        # when its message text contains the transport marker.
        self.assertTrue(rpc_error_is_transient(
            RpcError("weird shape", daemon_code=-28)))
        self.assertFalse(rpc_error_is_transient(
            RpcError("rpc x error: {'code': -1, 'message': "
                     "'transport error after 3 attempts'}",
                     daemon_code=-1)))

    def test_structural_warmup_code_without_marker_text(self):
        self.assertTrue(rpc_error_is_transient(
            RpcError("rpc getblockchaininfo error: "
                     "{'code': -28, 'message': 'Loading block index...'}",
                     daemon_code=-28)))


class TestCrawlPausesThroughTransients(unittest.TestCase):

    def test_warmup_pauses_then_crawl_completes(self):
        # The live incident replay: two -28 warm-up answers, then the
        # daemon recovers and the crawl finishes normally.
        faults = [("getblockchaininfo", RpcError(WARMUP_WALLET), 1),
                  ("getblockchaininfo", RpcError(WARMUP_WALLET), 2)]
        tmp, store, rpc, rec, ing = _ingestor_with_faults(faults)
        try:
            summary = ing.run(max_blocks=3)
            self.assertEqual(int(summary["synced_to"]), 2)
            self.assertEqual(summary["crawled"], 3)
            self.assertEqual(len(rpc.fired), 2)
            # Capped exponential backoff: 5s then 10s (base, base*2).
            self.assertEqual(rec.delays, [RPC_PAUSE_BASE_S,
                                          RPC_PAUSE_BASE_S * 2])
            cur = ing.load_cursor()
            self.assertEqual(int(cur["height"]), 2)
        finally:
            store.close()

    def test_transport_death_midcrawl_pauses_then_completes(self):
        # Node vanishes BETWEEN blocks: the getblock for the second block
        # dies with transport exhaustion, the crawl pauses, the daemon
        # returns, and the batch finishes.
        faults = [("getblock", RpcError(TRANSPORT_DEAD))]
        tmp, store, rpc, rec, ing = _ingestor_with_faults(faults)
        try:
            summary = ing.run(max_blocks=3)
            self.assertEqual(int(summary["synced_to"]), 2)
            self.assertEqual(summary["crawled"], 3)
            self.assertEqual(len(rpc.fired), 1)
            self.assertEqual(rec.delays, [RPC_PAUSE_BASE_S])
        finally:
            store.close()

    def test_backoff_caps_at_cap(self):
        faults = [("getblockchaininfo", RpcError(WARMUP_WALLET), n)
                  for n in range(1, 6)]
        tmp, store, rpc, rec, ing = _ingestor_with_faults(faults)
        try:
            ing.run(max_blocks=1)
            self.assertEqual(len(rpc.fired), 5)
            self.assertEqual(rec.delays, [5.0, 10.0, 20.0, 40.0, 60.0])
            self.assertEqual(rec.delays[-1], RPC_PAUSE_CAP_S)
        finally:
            store.close()

    def test_reads_serve_while_crawl_is_paused(self):
        # The availability point of the fix: while the crawl sits INSIDE a
        # pause (inside the injected sleep callback -- the production
        # process stays up and its API thread reads the store), a SEPARATE
        # reader connection can open the same db and serve queries.
        # IDX-10 batching: a window's blocks are all fetched before any is
        # stored (all-or-nothing window), so "blocks visible during a
        # pause" needs pauses in TWO DIFFERENT windows.  With batch=2:
        # pause 1 = h0's item of window [h0,h1] (nothing stored yet);
        # pause 2 = h2's item (count 5) of window [h2,h3] -- window
        # [h0,h1] is already stored and cursor-saved, so the independent
        # reader must see tip 1 / 2 blocks.  Each pause opens a fresh
        # rpc_paused_batch loop, so both delays restart at base.
        faults = [("getblock", RpcError(WARMUP_WALLET), 1),
                  ("getblock", RpcError(WARMUP_WALLET), 5)]
        tmp, store, rpc, rec, ing = _ingestor_with_faults(faults)
        ing.cfg.batch = 2  # two-block windows so the chain has 6 windows
        seen_during_pause = []

        def sleep_and_read(seconds):
            rec.delays.append(seconds)
            reader = Store(store.path)  # second handle, like the API
            try:
                seen_during_pause.append(
                    (reader.tip_height(), reader.counts()["blocks"]))
            finally:
                reader.close()

        ing.sleep_fn = sleep_and_read
        try:
            # max_blocks=4 so the crawl continues past window [h0,h1] into
            # window [h2,h3] -- the second pause must land in a NEW window
            # (a bounded stop inside window 1 would never open window 2).
            summary = ing.run(max_blocks=4)
            self.assertEqual(int(summary["synced_to"]), 3)
            self.assertEqual(summary["crawled"], 4)
            self.assertEqual(len(rpc.fired), 2)
            self.assertEqual(rec.delays, [RPC_PAUSE_BASE_S,
                                          RPC_PAUSE_BASE_S])
            # Pause 1 (window [h0,h1] fetch): nothing stored yet.
            # Pause 2 (window [h2,h3] fetch): window [h0,h1] is stored
            # and cursor-saved -- the reader sees tip 1 / 2 blocks.
            self.assertEqual(seen_during_pause, [(None, 0), (1, 2)])
        finally:
            store.close()


class TestPermanentErrorsStillFailLoud(unittest.TestCase):
    """Non-transient shapes must RAISE out of run() exactly as before --
    an indefinite pause must never mask a real defect (IDX-7 class)."""

    def _assert_raises_permanent(self, method, exc, fault_method=None):
        faults = [(fault_method or method, exc)]
        tmp, store, rpc, rec, ing = _ingestor_with_faults(faults)
        try:
            with self.assertRaises(RpcError):
                ing.run(max_blocks=3)
            # No pause was taken for a permanent error.
            self.assertEqual(rec.delays, [])
            self.assertEqual(len(rpc.fired), 1)
        finally:
            store.close()

    def test_verbosity_error_fails_loud(self):
        self._assert_raises_permanent("getblockchaininfo",
                                      RpcError(PERMANENT_VERBOSITY),
                                      fault_method="getblockchaininfo")

    def test_range_error_fails_loud(self):
        self._assert_raises_permanent("getblockhash", RpcError(PERMANENT_RANGE))

    def test_bad_json_fails_loud(self):
        self._assert_raises_permanent("getblock", RpcError(PERMANENT_BADJSON))


class TestSendSwallowsClientDisconnects(unittest.TestCase):
    """api._send must not let a mid-response client disconnect escape as
    a socketserver traceback -- the incident journal filled with exactly
    that noise (health probes timing out client-side under ingest
    churn), which polluted every error grep used for triage."""

    @staticmethod
    def _handler(wfile):
        h = api_module._Handler.__new__(api_module._Handler)
        h.wfile = wfile
        h.sent = []

        def _rec(name):
            def _m(*args, **kwargs):
                h.sent.append(name)
            return _m

        h.send_response = _rec("response")
        h.send_header = _rec("header")
        h.end_headers = _rec("end")
        return h

    def test_broken_pipe_is_swallowed(self):
        class _Dead:
            def write(self, b):
                raise BrokenPipeError("[Errno 32] Broken pipe")

        h = self._handler(_Dead())
        # Must not raise; connection is marked for close.
        h._send(200, {"ok": True})
        self.assertTrue(h.close_connection)
        self.assertEqual(h.sent, ["response", "header", "header", "end"])

    def test_connection_reset_is_swallowed(self):
        class _Dead:
            def write(self, b):
                raise ConnectionResetError("[Errno 104] Connection reset")

        h = self._handler(_Dead())
        h._send(200, {"ok": True})
        self.assertTrue(h.close_connection)

    def test_healthy_write_unchanged_and_still_serves(self):
        buf = io.BytesIO()
        h = self._handler(buf)
        h._send(200, {"ok": True}, body=False)  # HEAD shape: no body write
        self.assertFalse(getattr(h, "close_connection", False))
        h2 = self._handler(buf)
        h2._send(200, {"ok": True})
        self.assertFalse(getattr(h2, "close_connection", False))
        self.assertIn(b'"ok"', buf.getvalue())


if __name__ == "__main__":
    unittest.main()
