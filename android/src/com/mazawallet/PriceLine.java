package com.mazawallet;

import java.util.regex.Pattern;

/**
 * M26: MAZA price discovery - the wallet side. One line under the balance:
 *
 * <pre>
 *   1 MAZA ~ $0.00180249 . FreiXLite MAZA_LTC . 42s old
 *   1 MAZA ~ $0.00180249 . FreiXLite MAZA_LTC . STALE 16m old
 *   1 MAZA ~ $0.00122588 . CoinMarketCap . 2m old
 *   1 MAZA ~ 0.00004258 LTC . FreiXLite MAZA_LTC . 42s old
 * </pre>
 *
 * Payu's directive (2026-11-25): the price comes from FreiXLite, with
 * CoinMarketCap where needed (the dollar leg, and the fallback when the
 * venue has nothing). The deciding lives in the bench
 * (walletbench/price.py); this class only turns what the bench answered
 * into honest copy.
 *
 * <p>DISPLAY ONLY. Nothing in the wallet spends, fees, confirms or validates
 * against this number. Amounts stay decimal strings end to end: nothing
 * here parses, rounds or multiplies money.
 *
 * <p>PLATFORM ONLY (java.* alone): tests/test_price_wiring.py compiles this
 * on the desktop JVM and drives the real formatter.
 */
public final class PriceLine {

    private PriceLine() {
    }

    /** One quote from GET /api/price. Amounts are decimal strings exactly
     *  as the bench sent them; any field may be null. Built by {@link
     *  Quote#of} from what the bench sent - never with a defaulted age. */
    public static final class Quote {
        /** Dollar price per 1 MAZA; null when no dollar leg exists. */
        public final String usd;
        /** "freixlite" or "coinmarketcap". */
        public final String source;
        /** Venue market, e.g. "MAZA_LTC"; null on the fallback. */
        public final String pair;
        /** Last traded price on the venue, in {@code quote}. */
        public final String last;
        /** "LTC" or "BTC"; null on the fallback. */
        public final String quote;
        /** Age of the oldest input, in seconds. */
        public final long ageS;
        /** The bench says an input is older than its freshness window. */
        public final boolean stale;

        public Quote(String usd, String source, String pair, String last,
                String quote, long ageS, boolean stale) {
            this.usd = usd;
            this.source = source;
            this.pair = pair;
            this.last = last;
            this.quote = quote;
            this.ageS = ageS;
            this.stale = stale;
        }

        /**
         * M27 (review fold deleg_1ab54e7f F8): the bench's fields as one
         * quote, or null when an honesty field is missing or unusable.
         *
         * <p>{@code ageRaw} must be a JSON integer (Integer or Long) and
         * {@code staleRaw} a JSON boolean - nothing else. Both arrive as
         * Object so that "absent" stays distinguishable: a default of 0
         * seconds / not stale would dress a quote of unknown age up as a
         * fresh one. A negative age is unknown too (a clock that moved).
         * No age, no line: fail closed.
         */
        public static Quote of(String usd, String source, String pair, String last,
                String quote, Object ageRaw, Object staleRaw) {
            boolean intAge = ageRaw instanceof Integer || ageRaw instanceof Long;
            if (!intAge || !(staleRaw instanceof Boolean)) return null;
            long ageS = ((Number) ageRaw).longValue();
            if (ageS < 0L) return null;
            return new Quote(usd, source, pair, last, quote, ageS,
                    (Boolean) staleRaw);
        }
    }

    private static final Pattern AMOUNT = Pattern.compile("[0-9]{1,12}(\\.[0-9]{1,12})?");
    private static final Pattern SYMBOL = Pattern.compile("[A-Za-z0-9_]{1,24}");

    /** A plain positive decimal: the only thing this wallet will ever print
     *  as a price. Anything else (zero, negative, exponent, text, null, a
     *  leading-zero form like 00.5 or 007) is not an amount. */
    static boolean isAmount(String s) {
        if (s == null || !AMOUNT.matcher(s).matches() || !s.matches(".*[1-9].*")) {
            return false;
        }
        // A leading zero followed by another digit never prints (no $00.5).
        return !(s.length() > 1 && s.charAt(0) == '0' && s.charAt(1) != '.');
    }

    static boolean isSymbol(String s) {
        return s != null && SYMBOL.matcher(s).matches();
    }

    /** The display line, or null when there is nothing honest to show (no
     *  usable amount at all, or an age that is not an age). */
    public static String format(Quote q) {
        if (q == null || q.ageS < 0L) return null;
        String amount;
        if (isAmount(q.usd)) {
            amount = "$" + q.usd;
        } else if (isAmount(q.last) && isSymbol(q.quote)) {
            // The venue traded, but there is no dollar leg for its quote
            // currency: quote it in that currency rather than invent one.
            amount = q.last + " " + q.quote;
        } else {
            return null;
        }
        StringBuilder line = new StringBuilder();
        line.append("1 MAZA \u2248 ").append(amount);
        String venue = sourceName(q.source);
        if (venue != null) {
            line.append(" \u00B7 ").append(venue);
            if (isSymbol(q.pair)) line.append(' ').append(q.pair);
        }
        line.append(" \u00B7 ");
        if (q.stale) line.append("STALE ");
        line.append(age(q.ageS));
        return line.toString();
    }

    static String sourceName(String code) {
        if ("freixlite".equals(code)) return "FreiXLite";
        if ("coinmarketcap".equals(code)) return "CoinMarketCap";
        return isSymbol(code) ? code : null;
    }

    /** "42s old", "16m old", "3h old", "2d old". The clamp is belt and
     *  braces: Quote.of never lets a negative age through, and format
     *  refuses one. */
    static String age(long seconds) {
        long s = Math.max(0L, seconds);
        if (s < 60L) return s + "s old";
        if (s < 3600L) return (s / 60L) + "m old";
        if (s < 86400L) return (s / 3600L) + "h old";
        return (s / 86400L) + "d old";
    }
}
