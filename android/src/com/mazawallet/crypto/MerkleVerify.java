package com.mazawallet.crypto;

/**
 * IDX-8 two-source verification: the client-side Merkle proof check.
 *
 * <p>Java port of the lean indexer's shipped math
 * ({@code maza_indexer/verify.py::verify_merkle_proof}), with the CLI's
 * usage-error contract folded INTO the verdict: a position at or beyond the
 * tree width ({@code pos >= 2**len(branch)}), a hash that is not exactly
 * 64 hex chars, or a null branch can never answer {@code true}. In the
 * Python tree the raw function lacks the width check (the CLI adds it as
 * exit-code 2); here the check is in the function itself because a wallet
 * has no separate "usage error" channel - malformed input must simply never
 * verify. This is deliberately stricter than the raw Python function on
 * pathological inputs and identical on every well-formed one.
 *
 * <p>Byte-order convention (matches hashutil/verify.py exactly): all hex
 * in and out is DISPLAY order (the daemon's spelling). Each hash is
 * reversed to INTERNAL order before climbing; pair hashing is
 * double-SHA256(left || right) with the current node on the left when the
 * position bit is 0 and the sibling on the left when it is 1; an odd node's
 * sibling is the node itself (Bitcoin Core pairing, handled by the indexer's
 * proof builder - the branch carries the duplicated value explicitly). The
 * final digest is reversed back to display order and compared with the
 * expected merkleroot (case-insensitive).
 *
 * <p>What a {@code true} answer means (DECISIONS D17): the (txid, height)
 * pair a row displays climbs this branch to the merkleroot the INDEXER
 * reports for that block. It ties the two indexer surfaces together with
 * client-side math; it does NOT independently verify block headers, proof of
 * work, or the merkleroot itself against a second chain source.
 *
 * <p>Pure Java: no Android imports (desktop-JVM SelfTest +
 * tests/test_explorer_merkle_crosscheck.py drive it).
 */
public final class MerkleVerify {

    private MerkleVerify() {}

    /**
     * True iff {@code txidHex} climbs {@code branch} (display-hex siblings,
     * leaf level upward) to {@code merklerootHex} from leaf position
     * {@code pos}. Any malformed input answers {@code false}.
     */
    public static boolean verify(String txidHex, String merklerootHex,
            String[] branch, int pos) {
        if (txidHex == null || merklerootHex == null || branch == null
                || pos < 0) return false;
        if (pos >= treeWidth(branch.length)) return false;
        byte[] current = reversed32(txidHex);
        if (current == null) return false;
        byte[] root = reversed32(merklerootHex);
        if (root == null) return false;
        for (int i = 0; i < branch.length; i++) {
            byte[] sibling = reversed32(branch[i]);
            if (sibling == null) return false;
            byte[] joined = new byte[64];
            if ((pos & 1) != 0) {
                System.arraycopy(sibling, 0, joined, 0, 32);
                System.arraycopy(current, 0, joined, 32, 32);
            } else {
                System.arraycopy(current, 0, joined, 0, 32);
                System.arraycopy(sibling, 0, joined, 32, 32);
            }
            current = Base58Check.doubleSha256(joined);
            pos >>= 1;
        }
        // Both sides are INTERNAL order now: the recomputed digest and the
        // decoded root. A malformed root never reaches this compare.
        for (int i = 0; i < 32; i++) {
            if (current[i] != root[i]) return false;
        }
        return true;
    }

    /** Tree width of an L-level branch: 2^L (long math; L capped at 62). */
    public static long treeWidth(int branchLen) {
        if (branchLen <= 0) return 1L;
        if (branchLen > 62) branchLen = 62;
        return 1L << branchLen;
    }

    /**
     * Decode exactly-64-hex-chars to 32 bytes and reverse to INTERNAL
     * order; null when the input is not exactly 64 hex chars (odd length,
     * wrong length, non-hex digit) - the caller answers false.
     */
    private static byte[] reversed32(String displayHex) {
        if (displayHex == null || displayHex.length() != 64) return null;
        byte[] raw;
        try {
            raw = Hex.fromHex(displayHex);
        } catch (IllegalArgumentException e) {
            return null;
        }
        for (int i = 0, j = raw.length - 1; i < j; i++, j--) {
            byte t = raw[i];
            raw[i] = raw[j];
            raw[j] = t;
        }
        return raw;
    }
}
