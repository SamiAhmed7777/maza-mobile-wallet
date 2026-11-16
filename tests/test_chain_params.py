#!/usr/bin/env python3
"""Offline verification of the MAZA coin profile against real mainnet headers.

Fixtures were harvested from the live samihost mazad (MazaCore 0.16.3,
2026-11-16 UTC): sha256d-era headers (genesis, height 2000000, height
2105603, height 4480773) and genuine MinotaurX type-1 headers (heights
4480797, 4480789). The pinned finding under test: the block IDENTITY hash is
double-SHA256 for every block regardless of PoW algo
(primitives/block.cpp:18-21) — MinotaurX/Hive are mining-validity functions
only. Daemon-reported hashes are display order; header_hash returns internal
byte order per the ElectrumX Coin API, so every comparison goes through
hash_to_display_hex().

Chain constants are additionally anchored to the vendored MazaCore excerpts
(vendor/maza-core-326935b-excerpts.txt, sha256-pinned below).

Run:  python3 -m unittest discover -s tests -v
"""

import hashlib
import os
import sys
import tempfile
import unittest

# Make the repo root importable without installing anything.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indexer.maza_coin import (  # noqa: E402
    ALL_FIXTURES,
    BECH32_HRP,
    ELECTRUMX_PIN,
    FIXTURES,
    FIXTURES_MINOTAURX,
    GENESIS_HASH,
    LEGACY_SHA256D_VERSION_FLOOR,
    P2PKH_VERSION_BYTE,
    P2SH_VERSION_BYTE,
    WIF_VERSION_BYTE,
    build_coin_class,
    double_sha256,
    get_pow_type,
    get_pow_type_name,
    hash_to_display_hex,
    header_hash,
)

VENDOR_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "vendor", "maza-core-326935b-excerpts.txt",
)
VENDOR_SHA256 = "f874f8b18a6c37bdd7b11689ccfb19ae733fcd56c7c3b9e891939fce5e11e245"


def _hx(hexstr: str) -> bytes:
    return bytes.fromhex(hexstr)


class TestPowTypeDispatch(unittest.TestCase):
    """Two distinct rules, exactly as block.h has them: GetPoWType is the raw
    bits-16..23 byte; GetPoWTypeName applies the legacy-floor rule FIRST."""

    def test_raw_type_byte_has_no_floor_exception(self):
        self.assertEqual(get_pow_type(0), 0)
        self.assertEqual(get_pow_type(3), 0)
        self.assertEqual(get_pow_type(0x00010000), 1)
        self.assertEqual(get_pow_type(0x00010001), 1)

    def test_display_name_applies_floor_first(self):
        self.assertEqual(get_pow_type_name(0x20000000), "sha256d")
        self.assertEqual(get_pow_type_name(0x20000001), "sha256d")
        self.assertEqual(get_pow_type_name(0x21000000), "sha256d")

    def test_floor_and_type_byte_diverge_exactly_as_cited_code(self):
        # 0x20010000: type byte = 1 (minotaurx) but the legacy floor wins the
        # DISPLAY name — the quirk block.h:106-117 genuinely has.
        self.assertEqual(get_pow_type(0x20010000), 1)
        self.assertEqual(get_pow_type_name(0x20010000), "sha256d")

    def test_unknown_type_bytes_do_not_crash(self):
        self.assertEqual(get_pow_type_name(0x00020000), "unknown(2)")
        self.assertEqual(get_pow_type_name(0x00050000), "unknown(5)")

    def test_fixture_versions_dispatch_correctly(self):
        for name, raw_hex, _want in FIXTURES:
            version = int.from_bytes(_hx(raw_hex)[0:4], "little")
            self.assertEqual(
                get_pow_type(version), 0, f"{name}: expected sha256d-era header"
            )
            self.assertEqual(get_pow_type_name(version), "sha256d")
        for name, raw_hex, _want in FIXTURES_MINOTAURX:
            version = int.from_bytes(_hx(raw_hex)[0:4], "little")
            self.assertEqual(
                get_pow_type(version), 1, f"{name}: expected minotaurx header"
            )
            self.assertEqual(get_pow_type_name(version), "minotaurx")


class TestHeaderHashAgainstLiveChain(unittest.TestCase):
    """Identity hash = double-SHA256 for ALL blocks; internal byte order."""

    def test_sha256d_fixtures_match_daemon_hashes(self):
        for name, raw_hex, want_display in FIXTURES:
            got = hash_to_display_hex(header_hash(_hx(raw_hex)))
            self.assertEqual(
                got, want_display,
                f"{name}: header hash disagrees with daemon-reported hash",
            )

    def test_minotaurx_identity_hash_is_still_sha256d(self):
        # The pinned finding: type-1 (minotaurx-mined) blocks identify by
        # double-SHA256 too — same rule as primitives/block.cpp:18-21.
        for name, raw_hex, want_display in FIXTURES_MINOTAURX:
            got = hash_to_display_hex(header_hash(_hx(raw_hex)))
            self.assertEqual(
                got, want_display,
                f"{name}: minotaurx block identity hash disagrees with daemon",
            )

    def test_header_length_is_enforced(self):
        with self.assertRaises(ValueError):
            header_hash(b"\x00" * 79)
        with self.assertRaises(ValueError):
            header_hash(b"\x00" * 81)

    def test_display_conversion_roundtrip(self):
        raw = double_sha256(b"x")
        back = bytes(reversed(_hx(hash_to_display_hex(raw))))
        self.assertEqual(raw, back)


class TestChainConstants(unittest.TestCase):
    """Constants anchored to vendored MazaCore excerpts + live node checks."""

    def test_genesis(self):
        _name, genesis_hex, genesis_hash = FIXTURES[0]
        self.assertEqual(hash_to_display_hex(header_hash(_hx(genesis_hex))), genesis_hash)
        self.assertEqual(GENESIS_HASH, genesis_hash)

    def test_address_and_key_versions(self):
        self.assertEqual(P2PKH_VERSION_BYTE, 50)   # "M..." mainnet addresses
        self.assertEqual(P2SH_VERSION_BYTE, 9)
        self.assertEqual(WIF_VERSION_BYTE, 224)    # chain code, NOT Komodo's 244
        self.assertEqual(BECH32_HRP, "maza")

    def test_legacy_floor_constant(self):
        self.assertEqual(LEGACY_SHA256D_VERSION_FLOOR, 0x20000000)


class TestVendoredProvenance(unittest.TestCase):
    """The vendored MazaCore excerpts are the test-time anchor for constants."""

    def test_vendor_file_is_pinned(self):
        with open(VENDOR_FILE, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(
            digest, VENDOR_SHA256,
            "vendor/maza-core-326935b-excerpts.txt changed — re-pin VENDOR_SHA256 "
            "and re-verify against upstream 326935b before touching constants",
        )
        with open(VENDOR_FILE, "r", encoding="utf-8") as f:
            text = f.read()
        for needle in (
            "PUBKEY_ADDRESS] = std::vector<unsigned char>(1,50)",
            "SCRIPT_ADDRESS] = std::vector<unsigned char>(1,9)",
            "SECRET_KEY] = std::vector<unsigned char>(1,224)",
            'bech32_hrp = "maza"',
            "nPowTargetSpacing = 2 * 60",
            "RecommendedNumConfirmations = 6",
            "DEFAULT_MIN_RELAY_TX_FEE = 1000",
            "m/0'/0'/k",
            "CBlockHeader::GetHash() const { return SerializeHash(*this); }",
        ):
            self.assertIn(needle, text, f"vendored excerpt lost: {needle}")


class TestElectrumxIntegration(unittest.TestCase):
    """Exercises the REAL electrumx API when the pinned tree is installed.

    Install (matches requirements-dev.txt):
        pip install -e <electrumx clone at pin ee28cd8...>   # dist name: e-x
    Without electrumx these tests skip cleanly; the deployment venv runs them
    for real. PyPI electrumx 1.20.2 (stale, altcoin-stripped) is rejected by
    name so a wrong install cannot silently pass.
    """

    def _coin_cls_or_skip(self):
        try:
            import electrumx.lib.coins as coins  # noqa: F401
            from importlib.metadata import version
            dist = version("e-x")  # raises PackageNotFoundError on PyPI build
        except Exception:
            self.skipTest(
                "pinned electrumx (dist 'e-x', git ee28cd8...) not installed"
            )
        coin_cls = build_coin_class()
        self.assertIsNotNone(coin_cls)
        return coins, coin_cls

    def test_coin_class_registers_via_env_programmatic_path(self):
        coins, coin_cls = self._coin_cls_or_skip()
        self.assertTrue(issubclass(coin_cls, coins.Coin))
        self.assertEqual(coin_cls.NAME, "MazaCoin")
        self.assertEqual(coin_cls.NET, "mainnet")
        self.assertEqual(coin_cls.GENESIS_HASH, GENESIS_HASH)
        self.assertEqual(coin_cls.P2PKH_VERBYTE, bytes([50]))
        self.assertEqual(coin_cls.RPC_PORT, 12832)

    def test_env_accepts_coin_and_server_entry_point_passes_fixtures(self):
        coins, coin_cls = self._coin_cls_or_skip()
        # COIN-env NAME lookup cannot find out-of-module classes (upstream
        # util.subclasses scans only electrumx.lib.coins); the OFFICIAL path
        # for custom coins is Env(coin=...) — the Env docstring says so.
        # Exercise that exact wiring, env vars patched and restored.
        saved = {k: os.environ.get(k) for k in
                 ("DB_DIRECTORY", "DAEMON_URL", "DB_ENGINE")}
        os.environ["DB_DIRECTORY"] = tempfile.mkdtemp(prefix="maza-exdb-")
        os.environ["DAEMON_URL"] = "http://user:pw@127.0.0.1:12832"
        os.environ["DB_ENGINE"] = "leveldb"
        try:
            from electrumx.server.env import Env
            env = Env(coin_cls)
            self.assertIs(env.coin, coin_cls)
            # header_hash_rev is the method block_processor.py actually
            # calls; every fixture (both PoW eras) must survive it.
            for _name, raw_hex, want_hash in ALL_FIXTURES:
                got = hash_to_display_hex(env.coin.header_hash_rev(_hx(raw_hex)))
                self.assertEqual(got, want_hash)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_pinned_tree_fingerprints(self):
        coins, coin_cls = self._coin_cls_or_skip()
        from importlib.metadata import version
        import electrumx.lib.tx as lib_tx
        import electrumx.lib.util as util
        # Fingerprints that separate the pinned git tree from PyPI 1.20.2:
        self.assertEqual(version("e-x"), "2.0.1")
        self.assertTrue(hasattr(lib_tx, "DeserializerSegWit"))
        self.assertGreater(
            len(util.subclasses(coins.Coin)), 100,  # PyPI build has 5
            "coin registry too small — stale/PyPI electrumx?",
        )
        # If this is an editable install from a git clone, enforce the commit
        # pin outright (best-effort for non-checkout installs).
        import pathlib
        import subprocess
        import electrumx as _ex
        probe = pathlib.Path(_ex.__file__).resolve().parent
        git_root = None
        for _ in range(4):
            if (probe / ".git").exists():
                git_root = probe
                break
            probe = probe.parent
        if git_root is not None:
            head = subprocess.run(
                ["git", "-C", str(git_root), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(
                head, ELECTRUMX_PIN,
                f"electrumx tree at {git_root} is NOT the pinned commit",
            )

    def test_runner_check_only_validates_wiring(self):
        coins, coin_cls = self._coin_cls_or_skip()
        from indexer import run_indexer
        saved = {k: os.environ.get(k) for k in run_indexer.REQUIRED_ENV_VARS}
        os.environ["DB_DIRECTORY"] = tempfile.mkdtemp(prefix="maza-exdb-")
        os.environ["DAEMON_URL"] = "http://user:pw@127.0.0.1:12832"
        os.environ["DB_ENGINE"] = "leveldb"
        try:
            self.assertEqual(run_indexer.check_only(), 0)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
