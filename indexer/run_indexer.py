#!/usr/bin/env python3
"""Launch the MAZA ElectrumX indexer with the MazaCoin coin profile.

This is the small Env(coin=...) runner the deployment uses: COIN-env name
lookup cannot find out-of-module coin classes (upstream util.subclasses only
scans electrumx.lib.coins), and passing the class programmatically is the
official custom-coin path — the Env docstring: "accepts a Coin class as
first argument to have ElectrumX serve custom coins".

Usage:
    python3 indexer/run_indexer.py            # run the server
    python3 indexer/run_indexer.py --check-only
        # validate env + coin wiring, print chain facts, exit 0 — no
        # sockets, no DB. Used by the test suite and post-install checks.

Environment (required): DB_DIRECTORY, DAEMON_URL, DB_ENGINE (leveldb|rocksdb).
Requires electrumx at the pinned git commit — see requirements-dev.txt and
deploy/install-electrumx-dev.sh.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indexer.maza_coin import (  # noqa: E402
    BECH32_HRP,
    GENESIS_HASH,
    P2PKH_VERSION_BYTE,
    build_coin_class,
)

REQUIRED_ENV_VARS = ("DB_DIRECTORY", "DAEMON_URL", "DB_ENGINE")


def missing_env_vars() -> list[str]:
    return [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]


def check_only() -> int:
    """Validate env + coin wiring without opening sockets or the DB."""
    missing = missing_env_vars()
    if missing:
        print(f"missing required env vars: {', '.join(missing)}")
        return 2
    try:
        from electrumx import Env
    except ImportError:
        print("electrumx not importable — install the pinned tree "
              "(deploy/install-electrumx-dev.sh)")
        return 3
    try:
        coin_cls = build_coin_class()
    except Exception as exc:
        print(f"coin class failed to build: {type(exc).__name__}: {exc}")
        print("a missing-attribute diagnostic here (e.g. no attribute "
              "'DeserializerSegWit') means the installed electrumx is NOT "
              "the pinned git build — reinstall via "
              "deploy/install-electrumx-dev.sh")
        return 4
    if coin_cls is None:
        print("coin class failed to build even with electrumx importable")
        return 4
    env = Env(coin_cls)
    print(f"coin: {coin_cls.NAME} ({coin_cls.SHORTNAME}) net={coin_cls.NET}")
    print(f"genesis: {coin_cls.GENESIS_HASH}")
    print(f"genesis matches chain code: {coin_cls.GENESIS_HASH == GENESIS_HASH}")
    print(f"p2pkh version byte: {P2PKH_VERSION_BYTE} ('M' addresses), "
          f"bech32 hrp: {BECH32_HRP}")
    print(f"daemon rpc port: {env.coin.RPC_PORT}")
    print("wiring OK")
    return 0


def serve() -> int:
    """Run the server: the official electrumx CLI shape with our coin class."""
    import electrumx
    from electrumx import Controller, Env, PYTHON_MIN_VERSION
    from electrumx.lib.util import CompactFormatter, make_logger

    log_fmt = Env.default('LOG_FORMAT', '%(levelname)s:%(name)s:%(message)s')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(CompactFormatter(log_fmt))
    logger = make_logger('maza-indexer', handler=handler, level='INFO')
    logger.info(f'MazaCoin indexer starting (electrumx {electrumx.__version__})')
    try:
        if sys.version_info < PYTHON_MIN_VERSION:
            mvs = '.'.join(str(part) for part in PYTHON_MIN_VERSION)
            raise RuntimeError(f'ElectrumX requires Python {mvs} or greater')
        env = Env(build_coin_class())
        controller = Controller(env)
        asyncio.run(controller.run())
    except Exception:
        logger.exception('MAZA indexer terminated abnormally')
        return 1
    logger.info('MAZA indexer terminated normally')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check-only', action='store_true',
                        help='validate wiring and exit (no sockets, no DB)')
    args = parser.parse_args(argv)
    return check_only() if args.check_only else serve()


if __name__ == '__main__':
    sys.exit(main())
