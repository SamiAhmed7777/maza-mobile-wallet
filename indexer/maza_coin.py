#!/usr/bin/env python3
"""MazaCoin (MAZA) coin profile for ElectrumX — constants and header-hash
behavior inherited from MazaCore 0.16.3 (HEAD 326935b = tag v0.16.3).

Rule (Sami 2026-11-15): every decision mirrors the existing wallet code, not
invented policy. Sources: DECISIONS.md at the repo root; vendored code
excerpts in vendor/ (sha256-pinned in the tests).

ElectrumX integration contract (verified against spesmilo/electrumx git
master, commit ee28cd8ddcc61019d78880ad59582b9b4ce3cc99, dist name `e-x`):
- The server hashes headers via Coin.header_hash_rev() (block_processor.py),
  whose base implementation is electrumx.lib.hash.double_sha256 — the RAW
  digest in internal byte order. We override header_hash_rev explicitly so
  the fixtures prove the exact entry point the server calls.
- Display conversion is electrumx.lib.hash.hash_to_hex_str (rev-to-hum); the
  local hash_to_display_hex mirrors it for offline tests.
- lib_tx is imported upstream-style (`import electrumx.lib.tx as lib_tx`);
  DESERIALIZER uses lib_tx.DeserializerSegWit (present in the pinned tree).
- Registration: the OFFICIAL custom-coin path is Env(coin=MazaCoin) — the
  Env docstring says it "accepts a Coin class as first argument to have
  ElectrumX serve custom coins". COIN-env NAME lookup cannot see
  out-of-module classes (upstream util.subclasses scans only the
  electrumx.lib.coins module), so the indexer launches through a small
  runner that passes the class programmatically; DB_ENGINE is required
  (leveldb or rocksdb).
- Version pin: PyPI electrumx 1.20.2 is a stale, altcoin-stripped build —
  the deployment venv MUST install the git tree at the pinned commit (see
  requirements-dev.txt).

Block identity hash: CBlockHeader::GetHash() is SerializeHash(*this)
(primitives/block.cpp:18-21) — double-SHA256 of the serialized header, for
EVERY block regardless of PoW algorithm. MinotaurX and Hive are the
GetPoWHash() mining-validity functions only; they affect whether a block is
valid, not what it is called. Verified live on mainnet: sha256d(header)
reproduces the daemon-reported hash for sha256d-era fixtures AND for genuine
type-1 (minotaurx) blocks at heights 4480797/4480789. PoW validation itself
is the daemon's job, as it is for every ElectrumX-backed fork.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Type

# --- Chain constants (MazaCore src/chainparams.cpp, mainnet; see vendor/) ---
GENESIS_HASH = "00000c7c73d8ce604178dae13f0fc6ec0be3275614366d44b1b4b5c6e238c60c"
P2PKH_VERSION_BYTE = 50   # base58Prefixes[PUBKEY_ADDRESS]  -> "M..." addresses
P2SH_VERSION_BYTE = 9     # base58Prefixes[SCRIPT_ADDRESS]
WIF_VERSION_BYTE = 224    # base58Prefixes[SECRET_KEY]  (Komodo config says
                          # 244 — chain code wins per DECISIONS.md D3)
BECH32_HRP = "maza"       # chainparams.cpp:177
BLOCK_SPACING_SECS = 120  # nPowTargetSpacing = 2 * 60 (per algo)
DAEMON_RPC_PORT = 12832

# --- PoW dispatch (src/primitives/block.h) — informational: the identity
# hash does NOT depend on it; it describes which GetPoWHash() validated the
# block's work. TWO distinct rules, kept separate exactly as the code has
# them: GetPoWType() is the raw bits-16..23 byte; GetPoWTypeName() applies
# the >=0x20000000 legacy-floor display rule FIRST, then maps the byte.
POW_TYPE_SHA256D = 0
POW_TYPE_MINOTAURX = 1
POW_TYPE_NAMES = ("sha256d", "minotaurx")
LEGACY_SHA256D_VERSION_FLOOR = 0x20000000

# Real mainnet fixtures harvested from the samihost mazad (2026-11-16 UTC).
# (raw 80-byte header hex, daemon block hash in display order)
FIXTURES = (
    ("genesis_h0_v1",
     "0100000000000000000000000000000000000000000000000000000000000000000000004f9f"
     "58d1d1c7dd6c2818dabb394af876bb8d16fc4c59d99d9834588e3796d4621b20e552f0ff0f"
     "1e2915a87c",
     "00000c7c73d8ce604178dae13f0fc6ec0be3275614366d44b1b4b5c6e238c60c"),
    ("h2000000_v3",
     "030000008666822d9af6725b1e63c0f83df2aafe9472ea40238ef553a741000000000000b4fe"
     "32d64b139e017d8bb57f44194abdadfb180cd3b7dac66491260c4d8bcefc33513261bdcf62"
     "1a8ec9bb95",
     "000000000000043f808a17ba7d2d19966df8b105ffab6d2df489047a9e6f8275"),
    ("h2105603_v0x20000000",
     "000000206095d77a65f04b8aef30fe7e3cb893545171aa1be81fc3de9600000000000000a7d3"
     "d1582ddb0b744ec77e73dd97d4562b69c7b1b559256928108008e856ad579ba3fb61360802"
     "1a21921751",
     "00000000000001c7adf6339094f040f880de829994ce5a9a888fe95e34669e61"),
    ("h4480773_v0",
     "000000004df171da875a34421d9f8eb8e12a22133618ae5befe91b749aff0c891394307bf83"
     "c933801e74a74a84476f5604f5a3720fdf70d17d7e268be266593688f24eadb47fa6ab1150"
     "11ec0000000",
     "00047ac31dafad2ae869454643fb2aaef6fb42c5e9d11a3eb098a755edeee91d"),
)

# Genuine MinotaurX (type-1) mainnet headers, same harvest. Their identity
# hash is STILL sha256d (block.cpp:18-21) — these fixtures pin that finding,
# which is what makes the whole chain indexable without a MinotaurX oracle.
FIXTURES_MINOTAURX = (
    ("h4480797_v0x00010000",
     "00000100679c5ff61afdaa398e91bf757f8b1a1beeeced92f766877c1a000000000000005d81"
     "7b6dddbe050b945692498d6d94f272c19da3858e81cff7b25ab6ed6de47b314dfa6af8ae0"
     "21db0f36e29",
     "d018ea96ccf304dec8f066a5f69c6950a9e12c428e40c8927190d4238d2a1404"),
    ("h4480789_v0x00010000",
     "000001001c5bfe2a2da4ca5c629b6733b81b38ee18a6e741109f94d03a22e9a545824f4476f3"
     "10d2ed896def903b7ccddd63bf8b683f5f429622aeeebb8a34f400a6dc601f4cfa6acfa40"
     "21dbe9eb022",
     "d9307af1e2dbc2989bde6c02dffaab02f5e059a19fe466807bafe81f8a0f678e"),
)

ALL_FIXTURES = FIXTURES + FIXTURES_MINOTAURX

ELECTRUMX_PIN = "ee28cd8ddcc61019d78880ad59582b9b4ce3cc99"


def double_sha256(data: bytes) -> bytes:
    """Raw double SHA-256 digest, INTERNAL byte order (electrumx convention).

    Do NOT compare this against explorer-style hex directly; convert with
    hash_to_display_hex() first.
    """
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hash_to_display_hex(raw_hash: bytes) -> str:
    """Internal-order hash -> displayed hex string (rev-to-hum, electrumx's
    hash_to_hex_str)."""
    return bytes(reversed(raw_hash)).hex()


# Back-compat alias for electrumx naming parity.
sha256d = double_sha256


def get_pow_type(version: int) -> int:
    """CBlockHeader::GetPoWType() — the RAW type byte at bits 16..23.

    Faithful to block.h:106-108: no legacy-floor exception here; that rule
    lives only in the display-name function below. (The two genuinely
    diverge for versions like 0x20010000 — type byte 1, displayed sha256d.)
    """
    return (version >> 16) & 0xFF


def get_pow_type_name(version: int) -> str:
    """CBlockHeader::GetPoWTypeName() — legacy-floor display rule FIRST
    (block.h:112-113): nVersion >= 0x20000000 displays as 'sha256d' whatever
    the type byte says; below the floor the type byte selects the name.
    Unknown type bytes never raise (unlike upstream, which would
    out-of-range-index) — they render 'unknown(<n>)'.
    """
    if version >= LEGACY_SHA256D_VERSION_FLOOR:
        return POW_TYPE_NAMES[POW_TYPE_SHA256D]
    ptype = get_pow_type(version)
    if ptype < len(POW_TYPE_NAMES):
        return POW_TYPE_NAMES[ptype]
    return f"unknown({ptype})"


def header_hash(raw_header: bytes) -> bytes:
    """Block identity hash of an 80-byte MazaCore header, INTERNAL byte order.

    Always double-SHA256: CBlockHeader::GetHash() is SerializeHash(*this)
    (primitives/block.cpp:18-21), unchanged from Bitcoin, so the identity
    hash is algorithm-independent. Verified against live mainnet fixtures of
    both PoW eras — see ALL_FIXTURES.
    """
    if len(raw_header) != 80:
        raise ValueError(f"header must be exactly 80 bytes, got {len(raw_header)}")
    return double_sha256(raw_header)


def build_coin_class() -> Optional[Type]:
    """Return the ElectrumX coin class when electrumx is importable.

    Requires the pinned git tree (ELECTRUMX_PIN, dist `e-x`); PyPI's 1.20.2
    is a stale altcoin-stripped build and is rejected by name in the test
    suite. Returns None when electrumx is not installed (offline test runs).
    """
    try:
        from electrumx.lib.coins import Coin  # type: ignore
        import electrumx.lib.tx as lib_tx     # type: ignore
    except ImportError:
        return None

    class MazaCoin(Coin):
        NAME = "MazaCoin"
        SHORTNAME = "MAZA"
        NET = "mainnet"
        P2PKH_VERBYTE = bytes([P2PKH_VERSION_BYTE])
        P2SH_VERBYTES = (bytes([P2SH_VERSION_BYTE]),)
        WIF_BYTE = bytes([WIF_VERSION_BYTE])
        GENESIS_HASH = GENESIS_HASH
        DESERIALIZER = lib_tx.DeserializerSegWit
        RPC_PORT = DAEMON_RPC_PORT
        # MazaCore 0.16.3 is the daemon; electrumx's Bitcoin-class default
        # (core 31) does not apply to this chain.
        MIN_REQUIRED_DAEMON_VERSION = "0.16.3"
        # 0.16.3 supports -txindex; the indexer requires it for history serving.
        REQUIRED_DAEMON_INDEXES = ("txindex",)
        TX_COUNT = 14_000_000
        TX_COUNT_HEIGHT = 4_400_000
        TX_PER_BLOCK = 2

        @classmethod
        def header_hash_rev(cls, header: bytes) -> bytes:
            """The server's actual entry point (block_processor.py).

            Base Coin.header_hash_rev is already double_sha256(header); we
            route through the module function so the fixture suite exercises
            exactly what the server calls, with MazaCore provenance inline.
            """
            return header_hash(header)

    return MazaCoin
