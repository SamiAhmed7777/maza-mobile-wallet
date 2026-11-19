"""CLI: run (default), --reorg-delete <height>, --status.

--reorg-delete is the documented MANUAL recovery for a reorg: deletes every
block >= height (one store transaction, addresses recomputed), rewinds the
cursor to height-1, and exits -- the next `run` re-crawls from there.
--status prints the cursor and row counts, never credentials.
"""

import argparse
import json
import sys

from .api import IndexerApp, serve
from .config import IndexerConfig
from .ingest import Ingestor, ReorgAbort
from .rpc import JsonRpcClient
from .store import Store


def _status(cfg: IndexerConfig) -> int:
    store = Store(cfg.db_path)
    try:
        cursor = {"height": -1, "hash": ""}
        try:
            with open(cfg.cursor_path, "r", encoding="utf-8") as fh:
                cursor = json.loads(fh.read())
        except (OSError, ValueError):
            pass
        counts = store.counts()
        print(json.dumps({
            "cursor": {"height": cursor.get("height"),
                       "hash": cursor.get("hash")},
            "counts": counts,
            "tip": store.tip_height(),
            "datadir": cfg.datadir,
            "bind": f"{cfg.host}:{cfg.port}",
        }))
    finally:
        store.close()
    return 0


def _reorg_delete(cfg: IndexerConfig, height: int) -> int:
    store = Store(cfg.db_path)
    try:
        summary = store.reorg_delete(height)
        print(f"reorg-delete >= {height}: {json.dumps(summary)}")
        # Rewind the cursor so the next run re-crawls exactly the deleted
        # span.  hash of the new frontier (or empty when deleting from 0).
        new_hash = ""
        if height > 0:
            b = store.block_by_height(height - 1)
            new_hash = b["hash"] if b else ""
        ingestor = Ingestor(store, None, cfg)
        ingestor.save_cursor(height - 1, new_hash)
    finally:
        store.close()
    return 0


def _run(cfg: IndexerConfig) -> int:
    import threading

    store = Store(cfg.db_path)
    rpc = JsonRpcClient(cfg.rpc_url, cfg.rpc_user, cfg.rpc_password)
    ingestor = Ingestor(store, rpc, cfg)
    app = IndexerApp(store, cfg)
    server = serve(app, cfg.host, cfg.port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"maza-indexer serving on {cfg.host}:{cfg.port}, "
          f"crawling {cfg.rpc_url}", file=sys.stderr)
    try:
        ingestor.run()
    except ReorgAbort as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1
    finally:
        server.shutdown()
        store.close()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m maza_indexer",
        description="MAZA lean chain indexer (stdlib-only; trusts the "
                    "daemon's chain, identity-checks headers only).")
    parser.add_argument("--reorg-delete", type=int, metavar="HEIGHT",
                        help="delete blocks >= HEIGHT then exit (manual "
                             "reorg recovery)")
    parser.add_argument("--status", action="store_true",
                        help="print cursor + counts, no secrets")
    args = parser.parse_args(argv)
    cfg = IndexerConfig.from_env()
    if args.status:
        return _status(cfg)
    if args.reorg_delete is not None:
        return _reorg_delete(cfg, args.reorg_delete)
    return _run(cfg)


if __name__ == "__main__":
    sys.exit(main())
