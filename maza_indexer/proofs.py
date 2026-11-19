"""Merkle branch construction, Bitcoin Core pairing semantics.

Pairing: concat left+right, double-SHA256.  An odd node duplicates itself
(the Bitcoin Core merkle rule, MerkleCompanion).  All hex crossing this
module's API is DISPLAY order (the daemon's spelling); the raw climbing is
done in INTERNAL order (see hashutil's byte-order convention docstring).
"""

from typing import List, Sequence, Tuple

from .hashutil import double_sha256


def merkle_branch(txids_bytes: Sequence[bytes],
                  target_idx: int) -> Tuple[List[bytes], int]:
    """Branch of sibling digests (INTERNAL order, leaf level upward) for
    leaf `target_idx`, plus the leaf position used for verification.

    txids_bytes: the block's tx digests in INTERNAL byte order, block order.
    """
    if not txids_bytes:
        raise ValueError("empty tx list has no merkle branch")
    if not 0 <= target_idx < len(txids_bytes):
        raise ValueError(f"target_idx {target_idx} out of range")
    level = list(txids_bytes)
    pos = target_idx
    branch: List[bytes] = []
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])  # odd node duplicates itself
        sibling = level[pos ^ 1]
        branch.append(sibling)
        pos //= 2
        level = [double_sha256(level[i] + level[i + 1])
                 for i in range(0, len(level), 2)]
    # The RETURNED position is the leaf index the verifier climbs FROM
    # (pos ^= 1 for the sibling, then pos >>= 1 per branch step) -- the
    # loop-local `pos` above is only the prover's cursor into the tree.
    return branch, target_idx


def merkle_branch_hex(txids_display_hex: Sequence[str],
                      target_idx: int) -> Tuple[List[str], int]:
    """Display-order wrapper: txid hex in as the RPC provides them,
    (branch hex list, pos) out -- what the /api/v0/proof route returns."""
    internals = [bytes.fromhex(t)[::-1] for t in txids_display_hex]
    branch, pos = merkle_branch(internals, target_idx)
    return [b[::-1].hex() for b in branch], target_idx
