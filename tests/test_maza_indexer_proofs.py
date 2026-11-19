"""Proofs tests: merkle_branch vs the test's OWN independent merkle loop
(written twice on purpose -- any disagreement fails), verified through BOTH
maza_indexer.verify and the test's independent verifier, across odd/even
leaf counts that exercise the self-duplication rule.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from maza_indexer.hashutil import double_sha256
from maza_indexer.proofs import merkle_branch, merkle_branch_hex
from maza_indexer.verify import verify_merkle_proof

from test_maza_indexer_core import indep_merkle_root, make_tx


def _indep_verify(txid_hex, merkleroot_hex, branch, pos):
    """Independent verifier (a THIRD implementation, not proofs.py, not
    verify.py): climb display-order hashes with explicit byte order."""
    current = bytes.fromhex(txid_hex)[::-1]
    p = pos
    for sib in branch:
        s = bytes.fromhex(sib)[::-1]
        if p & 1:
            current = double_sha256(s + current)
        else:
            current = double_sha256(current + s)
        p >>= 1
    return current[::-1].hex() == merkleroot_hex.lower()


class TestMerkle(unittest.TestCase):
    def test_root_agreement_with_independent_loop(self):
        # proofs.py and the test's own loop must agree on every root; a
        # disagreement fails here first, before any API surface.
        for n in range(1, 10):
            txs = [make_tx([(b"\x00" * 32, 0xFFFFFFFF, b"\x01")],
                           [(0, b"")]) for _ in range(n)]
            internals = [t["internal"] for t in txs]
            # Root via proofs.py: climb every leaf and the root falls out.
            for idx in range(n):
                branch, pos = merkle_branch(internals, idx)
                current = internals[idx]
                p = pos
                for sib in branch:
                    if p & 1:
                        current = double_sha256(sib + current)
                    else:
                        current = double_sha256(current + sib)
                    p >>= 1
                self.assertEqual(current, indep_merkle_root(internals),
                                 f"n={n} idx={idx}")
            self.assertEqual(indep_merkle_root(internals),
                             indep_merkle_root(internals))

    def test_odd_levels_duplicate_last_node(self):
        # With 3 leaves the first level is odd: leaf 2's sibling is ITSELF
        # (duplicated), and the branch must still verify.
        txs = [make_tx([(b"\x00" * 32, 0xFFFFFFFF, bytes([1, i]))],
                       [(0, b"")]) for i in range(3)]
        internals = [t["internal"] for t in txs]
        branch, pos = merkle_branch(internals, 2)
        self.assertEqual(pos, 2)
        self.assertEqual(branch[0], internals[2])  # duplicate of itself
        root = indep_merkle_root(internals)
        self.assertTrue(verify_merkle_proof(txs[2]["txid"],
                                            root[::-1].hex(),
                                            [b[::-1].hex() for b in branch],
                                            pos))
        self.assertTrue(_indep_verify(txs[2]["txid"], root[::-1].hex(),
                                      [b[::-1].hex() for b in branch], pos))

    def test_every_leaf_of_several_block_shapes(self):
        # n in {1, 2, 3, 5, 6, 7}: single-tx (empty branch, txid == root),
        # even, odd, and odd-with-duplication shapes.
        for n in (1, 2, 3, 5, 6, 7):
            txs = [make_tx([(b"\x00" * 32, 0xFFFFFFFF, bytes([2, i]))],
                           [(0, b"")]) for i in range(n)]
            internals = [t["internal"] for t in txs]
            display = [t["txid"] for t in txs]
            root_display = indep_merkle_root(internals)[::-1].hex()
            for idx in range(n):
                branch, pos = merkle_branch(internals, idx)
                self.assertEqual(pos, idx)
                branch_hex = [b[::-1].hex() for b in branch]
                self.assertTrue(
                    verify_merkle_proof(display[idx], root_display,
                                        branch_hex, pos),
                    f"verify.py n={n} idx={idx}")
                self.assertTrue(
                    _indep_verify(display[idx], root_display,
                                  branch_hex, pos),
                    f"independent n={n} idx={idx}")
            # Single-tx block: empty branch IS the proof (txid == root).
            if n == 1:
                self.assertEqual(merkle_branch(internals, 0), ([], 0))
                self.assertTrue(verify_merkle_proof(display[0],
                                                    root_display, [], 0))

    def test_merkle_branch_hex_wrapper(self):
        txs = [make_tx([(b"\x00" * 32, 0xFFFFFFFF, bytes([3, i]))],
                       [(0, b"")]) for i in range(4)]
        display = [t["txid"] for t in txs]
        root_display = indep_merkle_root([t["internal"] for t in txs])[
            ::-1].hex()
        branch_hex, pos = merkle_branch_hex(display, 3)
        self.assertEqual(pos, 3)
        self.assertTrue(verify_merkle_proof(display[3], root_display,
                                            branch_hex, pos))
        self.assertTrue(_indep_verify(display[3], root_display,
                                      branch_hex, pos))

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError):
            merkle_branch([], 0)
        with self.assertRaises(ValueError):
            merkle_branch([b"\x00" * 32], 1)

    def test_verify_rejects_tampering(self):
        txs = [make_tx([(b"\x00" * 32, 0xFFFFFFFF, bytes([4, i]))],
                       [(0, b"")]) for i in range(4)]
        internals = [t["internal"] for t in txs]
        root_display = indep_merkle_root(internals)[::-1].hex()
        branch, pos = merkle_branch(internals, 1)
        branch_hex = [b[::-1].hex() for b in branch]
        # Wrong txid / wrong root / wrong pos / tampered branch.
        self.assertFalse(verify_merkle_proof(txs[0]["txid"], root_display,
                                             branch_hex, pos))
        self.assertTrue(verify_merkle_proof(txs[1]["txid"], root_display,
                                            branch_hex, pos))
        self.assertFalse(verify_merkle_proof(txs[1]["txid"], "00" * 32,
                                             branch_hex, pos))
        self.assertFalse(verify_merkle_proof(txs[1]["txid"], root_display,
                                             branch_hex, pos + 1))
        bad = list(branch_hex)
        bad[0] = "11" * 32
        self.assertFalse(verify_merkle_proof(txs[1]["txid"], root_display,
                                             bad, pos))


if __name__ == "__main__":
    unittest.main()
