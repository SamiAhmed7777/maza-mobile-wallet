"""MAZA address validation, chain-tolerant (stdlib-only).

The bench service is deployed twice: mainnet (walletbench, accounts on the
mainnet mazad) and testnet (walletbench-testnet sibling, accounts on the
testnet mazad, S-6-ii). Address-shaped gates that hardcode the MAINNET
letter shape (`startswith("M")` + `len == 34`) silently reject valid
testnet addresses — and worse, when applied to the persisted state file,
they crash-loop the service on every restart once a testnet book exists
(S-6-ii-prep-c finding A: 0/4000 synthetic testnet addresses pass the
M-prefix check, 4000/4000 mainnet controls pass).

The correct predicate is base58check DECODE + version-byte membership,
not a letter-shape check:

  decode -> payload must be exactly 25 bytes (version 1 + hash160 20 +
  checksum 4) -> version in MAZA_ADDRESS_VERSIONS.

Version bytes are FETCHED from source, never memorized —
MazaCoin/maza tag v0.16.3, src/chainparams.cpp
(sha256 50ed60dc647095a60447824a6b124c4fef06c42fdc564f058bc0cf241875b910):

    line 171 (mainnet):  base58Prefixes[PUBKEY_ADDRESS] = (1, 50)
    line 297 (testnet):  base58Prefixes[PUBKEY_ADDRESS] = (1, 88)

(regtest, line 401, carries 140 and is intentionally not accepted — the
bench has no regtest deployment.) The same constants are mirrored by the
Android app's crypto/NetworkParams.java (commit 988ad31, S-6-i); any
change here must be mirrored there.
"""

import hashlib
from typing import Optional, Tuple

# (mainnet, testnet) — fetched; see module docstring for provenance.
MAZA_ADDRESS_VERSIONS: Tuple[int, ...] = (50, 88)

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {ch: i for i, ch in enumerate(_B58_ALPHABET)}

# P2PKH paylod: version byte + 20-byte hash160 + 4-byte checksum.
_P2PKH_LEN = 25


def base58check_version(address: object) -> Optional[int]:
    """Decode a base58check string; return the version byte, or None.

    Strict: the decoded payload must be exactly a P2PKH (25-byte) shape
    and the double-SHA256 checksum must verify. Bitcoin-family rule:
    the checksum is DOUBLE SHA-256 (hash then hash again), take the
    first 4 bytes. Non-string input (ints, None, dicts) returns None —
    callers rely on that for fail-loud state validation.
    """
    if not isinstance(address, str) or not address:
        return None
    # A 25-byte payload base58-encodes to 33-35 chars depending on
    # leading zero bytes; a length gate first rejects obvious junk cheaply.
    if not 25 <= len(address) <= 36:
        return None
    num = 0
    for ch in address:
        idx = _B58_INDEX.get(ch)
        if idx is None:
            return None
        num = num * 58 + idx
    body = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    # Leading '1' characters encode leading zero bytes.
    pad = len(address) - len(address.lstrip("1"))
    raw = b"\x00" * pad + body
    if len(raw) != _P2PKH_LEN:
        return None
    payload, checksum = raw[:-4], raw[-4:]
    expect = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    if checksum != expect:
        return None
    return payload[0]


def is_maza_address(address: object) -> bool:
    """True iff `address` is a checksum-valid P2PKH MAZA address on a
    deployed chain (mainnet v50 or testnet v88)."""
    return base58check_version(address) in MAZA_ADDRESS_VERSIONS


def encode_address(version: int, hash160_bytes: bytes) -> str:
    """Base58check-encode a P2PKH address (offline fixtures/tests only;
    the live benches get their addresses from the node wallet)."""
    if len(hash160_bytes) != 20:
        raise ValueError("hash160 must be 20 bytes")
    raw = bytes([version]) + hash160_bytes
    checksum = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[:4]
    num = int.from_bytes(raw + checksum, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = _B58_ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * pad + out
