"""IDX-9c-i cheap counts read path: /health and /api/v0/stats must never pay
full COUNT(*) table scans.

Before this change counts() ran four full table scans per call (blocks, txs,
outputs, addresses); outputs is the monster table and every public /health
probe paid all four. Measured live shape: /health 000 under catch-up ingest
(DNS2 probe, 2026-11-20 tick) with the local retry returning 200 only after
33s. Now counters live in a `counters` table maintained transactionally by
add_block (+) and reorg_delete (-), backfilled once at open for legacy DBs,
and counts() is 4 point lookups.

Offline tests only: the synthesized chain fixture from test_maza_indexer_core,
a real ephemeral HTTP server for the /health + /api/v0/stats contract rows,
and EXPLAIN QUERY PLAN as the scan-shape pin (the counters read may not touch
any backing table).
"""

import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from maza_indexer.api import IndexerApp, serve
from maza_indexer import config as config_mod
from maza_indexer.store import Store, StoreIntegrityError

from test_maza_indexer_core import (build_chain, ingest_chain,
                                    make_config, make_mock_rpc)
from maza_indexer.ingest import Ingestor

_BIG_TABLES = ("blocks", "txs", "outputs", "addresses")


def _real_counts(store):
    """Ground truth straight from the backing tables (write connection)."""
    out = {}
    for name in _BIG_TABLES:
        row = store.conn.execute(
            "SELECT COUNT(*) FROM %s" % name).fetchone()
        out[name] = int(row[0])
    return out


class TestCountsCheapPath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="idx-counts")
        self.cfg, self.store, _ing = ingest_chain(self._tmp.name)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_counts_match_backing_tables_after_ingest(self):
        self.assertEqual(self.store.counts(), _real_counts(self.store))

    def test_counts_match_backing_tables_after_reorg_delete(self):
        deleted = self.store.reorg_delete(5)
        self.assertGreater(deleted["blocks"], 0)
        self.assertEqual(self.store.counts(), _real_counts(self.store))

    def test_counts_keys_contract_unchanged(self):
        got = self.store.counts()
        self.assertEqual(sorted(got), sorted(_BIG_TABLES))
        for v in got.values():
            self.assertIsInstance(v, int)

    def test_counts_read_plan_never_scans_backing_tables(self):
        """The scan-shape pin, on the SQL counts() ITSELF executes: a trace
        callback on the read connection collects every statement counts()
        runs; each must mention the counters table and none may scan a
        backing table. If anyone reintroduces a COUNT(*) here, the traced
        SQL names the backing table and this fails."""
        collected = []
        self.store._ro.set_trace_callback(collected.append)
        try:
            self.store.counts()
        finally:
            self.store._ro.set_trace_callback(None)
        self.assertTrue(collected, "counts() executed no SQL")
        for sql in collected:
            self.assertIn("counters", sql)
            for big in _BIG_TABLES:
                self.assertNotIn(big, sql)

    def test_idempotent_reingest_does_not_bump_counters(self):
        """The crash-window skip path (same hash at same height) must return
        before any counter move - replaying the whole chain leaves counts
        byte-identical."""
        before = self.store.counts()
        cfg = self.cfg
        rpc = make_mock_rpc(build_chain(), tip=11)
        ing = Ingestor(self.store, rpc, cfg, poll_seconds=0.001,
                       sleep_fn=lambda s: (_ for _ in ()).throw(
                           AssertionError("poll must not run in tests")))
        ing.run(max_blocks=12)
        self.assertEqual(self.store.counts(), before)

    def test_divergence_refusal_leaves_counters_unchanged(self):
        """The divergence ValueError fires before the write transaction, so
        a refused block must not move any counter."""
        before = self.store.counts()
        with self.assertRaises(ValueError):
            self.store.add_block(3, "00" * 32, "ff" * 80,
                                 "00" * 32, 1, 1234567890, 1.0, [])
        self.assertEqual(self.store.counts(), before)

    def test_legacy_db_without_counter_rows_backfills_at_open(self):
        """A pre-upgrade live DB carries real rows but no counters table.
        Simulated by dropping it: reopen must recreate + backfill from the
        real tables, and counts() must then agree with ground truth."""
        self.store.conn.execute("DROP TABLE counters")
        self.store.conn.commit()
        self.store.close()
        reopened = Store(self.cfg.db_path)
        try:
            self.assertEqual(reopened.counts(), _real_counts(reopened))
            names = [r[0] for r in reopened.conn.execute(
                "SELECT name FROM counters").fetchall()]
            self.assertEqual(sorted(names), sorted(_BIG_TABLES))
        finally:
            reopened.close()

    def test_missing_counter_row_fails_loud_not_silent_zero(self):
        """A counter row deleted out-of-band on an OPEN store must raise
        StoreIntegrityError from counts() - never serve a silent 0 - and a
        reopen must heal it via the backfill."""
        self.store.conn.execute(
            "DELETE FROM counters WHERE name='txs'")
        self.store.conn.commit()
        with self.assertRaises(StoreIntegrityError):
            self.store.counts()
        self.store.close()
        reopened = Store(self.cfg.db_path)
        try:
            self.assertEqual(reopened.counts()["txs"],
                             _real_counts(reopened)["txs"])
        finally:
            reopened.close()

    def test_backfill_is_noop_on_second_open(self):
        """Every open after the first must find all counter rows present
        (the backfill's SELECT-then-INSERT finds nothing to do)."""
        self.store.close()
        reopened = Store(self.cfg.db_path)
        try:
            self.assertEqual(reopened.counts(), _real_counts(reopened))
        finally:
            reopened.close()


class TestCountsApiContract(unittest.TestCase):
    """/health and /api/v0/stats keep their exact response contracts, now
    served from the cheap path, through the real HTTP server."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="idx-counts-api")
        cls.cfg, cls.store, _ing = ingest_chain(cls._tmp.name)
        cls.app = IndexerApp(cls.store, cls.cfg)
        cls.server = serve(cls.app, "127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.store.close()
        cls._tmp.cleanup()

    def _get(self, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", path)
            resp = conn.getresponse()
            return resp.status, json.loads(resp.read().decode("utf-8"))
        finally:
            conn.close()

    def test_health_contract_unchanged(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["chain"], config_mod.CHAIN_NAME)
        self.assertIn("height", body)
        self.assertIn("txs_indexed", body)
        self.assertEqual(body["txs_indexed"], self.store.counts()["txs"])
        self.assertEqual(body["height"], self.store.tip_height())

    def test_stats_contract_unchanged(self):
        status, body = self._get("/api/v0/stats")
        self.assertEqual(status, 200)
        counts = self.store.counts()
        self.assertEqual(body["height"], self.store.tip_height() or 0)
        self.assertEqual(body["total_txs"], counts["txs"])
        self.assertEqual(body["address_count"], counts["addresses"])


if __name__ == "__main__":
    unittest.main()
