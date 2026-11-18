package com.mazawallet.crypto;

/**
 * Per-transaction fee policy for the self-custody send flow (M10).
 *
 * Mirrors MazaCoin/MazaCore 0.16.3 GetMinimumFee as the wallet's own
 * cold start executes it (a phone has no fee-estimate data), with every
 * constant and control-flow step FETCHED from the upstream tree -
 * never recalled from memory:
 *
 *   wallet.h:47            DEFAULT_TRANSACTION_FEE = 0          (paytxfee default)
 *   wallet/fees.cpp:42-54  estimates unavailable -> fallbackFee
 *                          (FeeReason::FALLBACK branch)
 *   wallet.cpp:63          fallbackFee = CFeeRate(DEFAULT_FALLBACK_FEE)
 *   wallet.h:49            DEFAULT_FALLBACK_FEE = 10000         (sat/kB)
 *   wallet/fees.cpp:68-72  required-fee floor = minRelayTxFee
 *   validation.h:53        DEFAULT_MIN_RELAY_TX_FEE = 1000      (sat/kB)
 *   wallet/fees.cpp:71-74  cap at maxTxFee
 *   validation.h:56        DEFAULT_TRANSACTION_MAXFEE = 0.1*COIN (sat)
 *   wallet.cpp:3091 +      dust change folds into the fee at the discard
 *   wallet/fees.cpp:80-89  rate (no estimates -> m_discard_rate, floored
 *                          at dustRelayFee = 3000)
 *   policy.h:46            DUST_RELAY_TX_FEE = 3000             (sat/kB)
 *   policy.cpp:20-30       dust threshold = 182 * dustRate / 1000
 *                          = 546 sats for a spendable P2PKH output
 *   policy/feerate.h:37    CFeeRate::GetFee = size*ratePerK/1000 (truncating)
 *   policy.h               MAX_STANDARD_TX_SIZE = 100000        (size guard)
 *
 * What changed vs the bench era: the flat 10000-sat constant is gone.
 * MazaCore pays 10 sat/byte (10000 sat/kB) PER TRANSACTION when it has
 * no estimate data - a 226-byte payment is 2260 sat (0.00002260 MAZA),
 * not a flat 10000. The bench edition fee (DECISIONS.md D7) is a
 * server-side bench policy and is untouched by this class.
 */
public final class FeePolicy {

    /** wallet.h:49 DEFAULT_FALLBACK_FEE (sat/kB) - the rate GetMinimumFee
     *  falls back to when fee estimation has no data (fees.cpp:52-54). */
    public static final long FALLBACK_RATE_PER_K = 10000;

    /** validation.h:53 DEFAULT_MIN_RELAY_TX_FEE (sat/kB) - the
     *  required-fee floor (wallet/fees.cpp GetRequiredFee). */
    public static final long MIN_RELAY_RATE_PER_K = 1000;

    /** policy.h:46 DUST_RELAY_TX_FEE (sat/kB) - the dust-change discard
     *  rate; GetDiscardRate (fees.cpp:87) floors the discard rate at
     *  dustRelayFee when no estimates exist. */
    public static final long DUST_RATE_PER_K = 3000;

    /** policy.h MAX_STANDARD_TX_SIZE - sizes beyond this are refused
     *  loud (a MAZA tx this large is not standard; never build one). */
    public static final long MAX_TX_SIZE_BYTES = 100000;

    /** validation.h:56 DEFAULT_TRANSACTION_MAXFEE = 0.1 * COIN (sat). */
    public static final long MAX_FEE_SATS = 10000000L;

    /** policy.cpp:27-30: 34-byte serialized P2PKH out + 148-byte
     *  redeeming input = 182 ("546 satoshis at the default rate"). */
    public static final long P2PKH_DUST_SIZE_BYTES = 182;

    private FeePolicy() {
    }

    /** CFeeRate::GetFee (policy/feerate.h): size * ratePerK / 1000,
     *  integer division (truncating). 0 bytes -> 0 fee; negative or
     *  over-standard sizes are refused loud. */
    public static long getFee(long sizeBytes, long ratePerK) {
        if (sizeBytes < 0) {
            throw new IllegalArgumentException("negative tx size");
        }
        if (sizeBytes > MAX_TX_SIZE_BYTES) {
            throw new IllegalArgumentException(
                    "tx size over MAX_STANDARD_TX_SIZE");
        }
        return sizeBytes * ratePerK / 1000;
    }

    /** GetMinimumFee at the wallet's cold start (fees.cpp): the
     *  fallback rate (estimates unavailable), floored by the required
     *  fee (minRelay rate), capped at maxTxFee - the exact order the
     *  upstream function applies. */
    public static long feeForSize(long signedTxBytes) {
        long fee = getFee(signedTxBytes, FALLBACK_RATE_PER_K);
        long floor = getFee(signedTxBytes, MIN_RELAY_RATE_PER_K);
        if (fee < floor) {
            fee = floor;
        }
        if (fee > MAX_FEE_SATS) {
            fee = MAX_FEE_SATS;
        }
        return fee;
    }

    /** Dust threshold for a spendable P2PKH output at the dust relay
     *  rate (policy.cpp:20-30): 182 * 3000 / 1000 = 546 sats. A change
     *  output below this folds into the fee instead of being created. */
    public static long dustThresholdSats() {
        return getFee(P2PKH_DUST_SIZE_BYTES, DUST_RATE_PER_K);
    }
}
