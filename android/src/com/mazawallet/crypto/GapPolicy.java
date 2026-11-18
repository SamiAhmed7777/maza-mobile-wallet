package com.mazawallet.crypto;

import java.util.Arrays;

/**
 * BIP44 gap-limit policy for the self-custody watch window (M11).
 *
 * Pure decision logic, no Android imports - the desktop SelfTest drives
 * every row (SelfTest.gapPolicyChecks) and the Android wiring in
 * SelfCustody only applies the decisions. The standard BIP44 look-ahead
 * (20) governs the watch window per chain: the window always covers the
 * highest used index + GAP more addresses, and never drops below the
 * floor the caller already imported.
 *
 * Usage comes from the wallet's own refresh surfaces (watch utxos +
 * watch history rows carry the receiving address); detection is
 * therefore bounded by what the backend reports - the persisted window
 * never shrinks, so an address that fell out of the reporting surface
 * stays watched (no blindness), it may only be re-DISPLAYED in the
 * aged-out edge case (documented in DECISIONS.md D15).
 *
 * Inherited convention, not coin policy: 20-look-ahead is the BIP44
 * standard every Bitcoin-family wallet ships; no fee/confirmation/URI
 * parameter is touched here.
 */
public final class GapPolicy {

    /** BIP44 standard look-ahead per chain (bitcoin/bips bip-0044). */
    public static final int GAP = 20;

    /** Returned when no qualifying index exists in the scanned range. */
    public static final int NO_INDEX = -1;

    private GapPolicy() {
    }

    /** Watch window for one chain: at least {@code floor}; at least
     *  highestUsed + 1 + GAP so the frontier always has GAP fresh
     *  addresses ahead of it. highestUsed is -1 when nothing is used. */
    public static int windowFor(int highestUsed, int floor) {
        if (highestUsed < -1) {
            throw new IllegalArgumentException("highestUsed < -1");
        }
        if (floor < 1) {
            throw new IllegalArgumentException("floor < 1");
        }
        return Math.max(floor, highestUsed + 1 + GAP);
    }

    /** Smallest index in [0, limit) whose used flag is false.
     *  NO_INDEX when every scanned index is used. */
    public static int firstUnused(boolean[] used, int limit) {
        requireRange(used, limit);
        for (int i = 0; i < limit; i++) {
            if (!used[i]) return i;
        }
        return NO_INDEX;
    }

    /** Next receive-display index after {@code from}: first unused
     *  scanning (from+1 .. limit-1), then wrapping (0 .. from). Never
     *  lands on a used address - the old modulo wrap reused address 0
     *  after 20 receives (the M11 reuse hazard). NO_INDEX when all
     *  scanned indices are used; the caller then grows the window. */
    public static int nextAfter(boolean[] used, int from, int limit) {
        requireRange(used, limit);
        if (from < 0 || from >= limit) {
            throw new IllegalArgumentException("from out of range");
        }
        for (int i = from + 1; i < limit; i++) {
            if (!used[i]) return i;
        }
        for (int i = 0; i <= from; i++) {
            if (!used[i]) return i;
        }
        return NO_INDEX;
    }

    /** Highest index whose used flag is true, or -1 when none. */
    public static int highestUsed(boolean[] used) {
        if (used == null) {
            throw new IllegalArgumentException("used null");
        }
        for (int i = used.length - 1; i >= 0; i--) {
            if (used[i]) return i;
        }
        return -1;
    }

    /** Shared validation: used array present, limit within its bounds. */
    private static void requireRange(boolean[] used, int limit) {
        if (used == null) {
            throw new IllegalArgumentException("used null");
        }
        if (limit < 0 || limit > used.length) {
            throw new IllegalArgumentException("limit out of range");
        }
    }

    /** Test helper: boolean array from an index list (SelfTest rows). */
    public static boolean[] usedAt(int limit, int... usedIndices) {
        boolean[] out = new boolean[limit];
        for (int i : usedIndices) {
            if (i < 0 || i >= limit) {
                throw new IllegalArgumentException("index out of range");
            }
            out[i] = true;
        }
        return out;
    }

    /** Test helper: readable view of a used array. */
    public static String describe(boolean[] used) {
        return Arrays.toString(used);
    }
}
