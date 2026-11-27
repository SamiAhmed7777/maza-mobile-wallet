package com.mazawallet;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

/**
 * M29: the typed receive amount as an approximate dollar figure.
 *
 * <pre>
 *   ~ $9.01 . FreiXLite . 42s old
 *   ~ $0.001802 . FreiXLite . 42s old
 *   ~ $1.80 . CoinMarketCap . 2m old
 * </pre>
 *
 * <p>The examples above are ASCII stand-ins for what is printed: "~" stands
 * for U+2248 (almost equal) and each "." separator for U+00B7 (middle
 * dot). The separators are written as escapes below so this source stays
 * pure ASCII. The venue is the source name alone, never the pair.
 *
 * Payu's ask (2026-11-26): the receive amount should also read in USD.
 * The figure is the typed MAZA amount times the dollar leg of the latest
 * quote (D19), multiplied as exact decimals - never a float.
 *
 * <p>DISPLAY ONLY, and never part of the request. The payment URI is
 * composed by MazaUri alone; MazaCore's formatBitcoinURI carries amount,
 * label and message and no dollar value (D14, D20).
 *
 * <p>NOTHING STALE. The balance line prints an old rate with the word
 * STALE in front of it. This figure is different: it is a number a payer
 * may be told. So a quote the bench marks stale, a quote with no usable
 * dollar leg, an unusable age, or an amount that is not a positive number
 * of sats shows NO line at all.
 *
 * <p>PLATFORM ONLY (java.* alone): tests/test_usd_approx.py compiles this
 * on the desktop JVM and drives the real formatter.
 */
public final class UsdApprox {

    private UsdApprox() {
    }

    /** The smallest figure this line prints. Below it the line says
     *  "less than" instead of rounding a number down to nothing. */
    private static final BigDecimal FLOOR = new BigDecimal("0.00000001");

    /** The display line, or null when there is nothing honest to show. */
    public static String format(Long amountSats, PriceLine.Quote quote) {
        if (amountSats == null || amountSats <= 0L) return null;
        if (quote == null || quote.stale || quote.ageS < 0L) return null;
        if (!PriceLine.isAmount(quote.usd)) return null;
        BigDecimal value = BigDecimal.valueOf(amountSats).movePointLeft(8)
                .multiply(new BigDecimal(quote.usd));
        BigDecimal four = value.round(new MathContext(4, RoundingMode.HALF_UP));
        String shown;
        if (value.compareTo(FLOOR) < 0) {
            shown = "< $0.00000001";
        } else if (four.compareTo(BigDecimal.ONE) >= 0) {
            // A dollar and up: cents.
            shown = "$" + value.setScale(2, RoundingMode.HALF_UP).toPlainString();
        } else {
            // Under a dollar, cents would erase most small amounts (one
            // MAZA is a fraction of a cent): four significant digits.
            // Eight decimal places is the finest this line prints (FLOOR is
            // 1e-8); smaller values take the "less than" branch above.
            shown = "$" + four.setScale(8, RoundingMode.HALF_UP)
                    .stripTrailingZeros().toPlainString();
        }
        StringBuilder line = new StringBuilder("\u2248 ").append(shown);
        String venue = PriceLine.sourceName(quote.source);
        if (venue != null) line.append(" \u00B7 ").append(venue);
        line.append(" \u00B7 ").append(PriceLine.age(quote.ageS));
        return line.toString();
    }
}
