"""PURE verification helpers -- liftable to a phone later.

No imports beyond stdlib + hashutil.  All hex in/out is DISPLAY order (the
daemon's spelling); the byte-order convention is documented in hashutil.

CLI (F10): python3 -m maza_indexer.verify <txid_hex> <merkleroot_hex>
<branch_json|@file> <pos>  -- prints "true"/"false" (the verify_merkle_proof
result); exit 0 on true, 1 on false, 2 on usage/parse error.  No network.
"""

import json
import sys

from .hashutil import double_sha256


def header_hash(header_hex: str) -> str:
    """Display-order block identity hash of an 80-byte header hex.

    MAZA block identity = double-SHA256 of the serialized header for every
    block in every PoW era (MazaCore primitives/block.cpp:18-21); the
    returned hex is the DISPLAY form, i.e. double_sha256(bytes)[::-1].hex().
    """
    raw = bytes.fromhex(header_hex)
    return double_sha256(raw)[::-1].hex()


def verify_merkle_proof(txid_hex: str, merkleroot_hex: str,
                        branch: list, pos: int) -> bool:
    """True iff txid climbs the branch to merkleroot at leaf position pos.

    branch: sibling hashes, display hex, leaf level upward (exactly what
    /api/v0/proof returns as "merkle"); pos: the tx's index in the block's
    tx list.  Pure arithmetic -- no storage, no network.
    """
    if not isinstance(pos, int) or pos < 0:
        return False
    try:
        current = bytes.fromhex(txid_hex)[::-1]
        root = merkleroot_hex.lower()
    except ValueError:
        return False
    for sibling_hex in branch:
        try:
            sibling = bytes.fromhex(sibling_hex)[::-1]
        except (ValueError, AttributeError, TypeError):
            return False
        if pos & 1:
            current = double_sha256(sibling + current)
        else:
            current = double_sha256(current + sibling)
        pos >>= 1
    return current[::-1].hex() == root


_USAGE = ("usage: python3 -m maza_indexer.verify <txid_hex> <merkleroot_hex> "
          "<branch_json|@file> <pos>")


def _load_branch(arg: str):
    """branch JSON (inline list of hex strings, or @file)."""
    if arg.startswith("@"):
        with open(arg[1:], "r", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(arg)


def _check_hex64(name: str, value: str) -> bool:
    """Exactly 64 hex chars (the display form of a 32-byte hash)."""
    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _main(argv) -> int:
    if len(argv) != 4:
        sys.stderr.write(_USAGE + "\n")
        return 2
    txid_hex, merkleroot_hex, branch_arg, pos_s = argv
    # Input validation is a usage-error class (exit 2): a malformed proof
    # can never be answered "false" -- false means well-formed-but-wrong.
    if not _check_hex64("txid", txid_hex):
        sys.stderr.write(
            f"txid must be exactly 64 hex chars, got {txid_hex!r}\n")
        return 2
    if not _check_hex64("merkleroot", merkleroot_hex):
        sys.stderr.write(
            f"merkleroot must be exactly 64 hex chars, "
            f"got {merkleroot_hex!r}\n")
        return 2
    try:
        branch = _load_branch(branch_arg)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"branch is not readable JSON: {exc}\n")
        return 2
    # Every branch element is one 32-byte sibling hash in display hex:
    # anything shorter/longer/non-hex is malformed, not "false".
    if not isinstance(branch, list) or not all(
            isinstance(x, str) and _check_hex64("branch", x) for x in branch):
        sys.stderr.write(
            "branch must be a JSON list of exactly-64-char hex strings\n")
        return 2
    try:
        pos = int(pos_s)
    except ValueError:
        sys.stderr.write(f"pos must be an integer, got {pos_s!r}\n")
        return 2
    if pos < 0:
        sys.stderr.write(f"pos must be an integer >= 0, got {pos_s!r}\n")
        return 2
    # A branch of L levels represents a tree of width 2**L; a position at
    # or beyond that width has nonzero residual bits past L levels and is
    # unprovable -- usage error, never "false".
    if pos >= 2 ** len(branch):
        sys.stderr.write(
            f"pos must be < 2**len(branch) ({2 ** len(branch)}), "
            f"got {pos_s!r}\n")
        return 2
    ok = verify_merkle_proof(txid_hex, merkleroot_hex, branch, pos)
    print("true" if ok else "false")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
