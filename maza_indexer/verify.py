"""PURE verification helpers -- liftable to a phone later.

No imports beyond stdlib + hashutil.  All hex in/out is DISPLAY order (the
daemon's spelling); the byte-order convention is documented in hashutil.
"""

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
