package com.mazawallet.crypto;

import java.nio.charset.StandardCharsets;
import java.util.Locale;

/**
 * M9: the official maza: payment-URI contract, ported from the MazaCoin
 * desktop wallet sources (fetched from github.com/MazaCoin/maza master,
 * 2026-11-17 - never from memory):
 *   - src/qt/guiutil.cpp:146-206   parseBitcoinURI (scheme, path/params)
 *   - src/qt/guiutil.cpp:221-243   formatBitcoinURI (build side)
 *   - src/qt/bitcoinunits.cpp:144-181  BitcoinUnits::parse(BTC) amount rules
 *   - src/qt/bitcoinunits.h:112-120    removeSpaces (' ', U+2009, U+202F)
 * Pure decision table (no android/zxing imports) driven by the desktop
 * selftest (SelfTest.mazaUriChecks). ScanOrigin is the ONLY scan-side
 * consumer: it routes maza:/maza:// payloads here and then validates the
 * parsed address through the SAME base58check contract as the typed send
 * path. Nothing parsed from a URI is ever fetched or opened.
 *
 * Inherited contract (guiutil.cpp):
 *  - scheme is "maza", case-insensitive (QUrl lower-cases schemes); the
 *    address part is NEVER case-folded.
 *  - "maza://" normalizes to "maza:" before parsing (a host-shaped
 *    prefix risks downstream case-folding of the address).
 *    DIVERGENCE (DECISIONS.md D14): upstream's normalizer replaces 11
 *    characters against a 7-character prefix (guiutil.cpp:213-215,
 *    uri.replace(0, 11, "maza:")), slicing the first four characters off
 *    the address; we strip exactly the 7-character prefix.
 *  - address = everything before the first '?', with ONE trailing '/'
 *    trimmed (guiutil.cpp:154-157).
 *  - query params are percent-decoded (UTF-8, '+' stays literal - not
 *    form encoding), processed in order, later duplicates overwriting:
 *      label / message  accepted, carried verbatim
 *      amount           parsed by the BitcoinUnits::parse(BTC) rules;
 *                       an EMPTY value means absent (amount stays 0)
 *      "<unknown>"      silently ignored (guiutil.cpp falls through)
 *      "req-<unknown>"  REJECTS the whole URI (a required feature this
 *                       wallet cannot satisfy); req-label / req-message /
 *                       req-amount are accepted via the known rows
 *  - amount rules (bitcoinunits.cpp:144-181): spaces and thin spaces
 *    ignored; at most one '.'; at most 8 fractional digits; the combined
 *    digit string capped at 18 chars (the 63-bit guard); the fraction is
 *    left-justified to 8 digits ("0.5" and ".5" both = 50000000 sats).
 *    DIVERGENCES (D14): (a) upstream hands the digits to
 *    QString::toLongLong which accepts a leading '+'/'-' - a scanned
 *    payment request can never carry a signed amount into this wallet,
 *    so digits-only is enforced; (b) upstream Qt silently keeps
 *    malformed percent-escapes literal - we fail closed instead.
 *
 * format()/formatAmount() mirror formatBitcoinURI (guiutil.cpp:221-243):
 * "maza:<addr>", then "?amount=<8dp, no separators>" when amount != 0,
 * then "&label=..." / "&message=..." in that order, percent-encoded
 * UTF-8 with everything outside the RFC 3986 unreserved set escaped -
 * a strict superset of upstream's table, so it always decodes to the
 * same value. format() is pure string assembly: the receive screen
 * (M9-ii) validates its address before calling.
 */
public final class MazaUri {

    /** Fraction digits the desktop parses/formats in BTC units. */
    public static final int AMOUNT_DECIMALS = 8;
    /** Digit-string cap from bitcoinunits.cpp:171 ("will exceed 63 bits"). */
    public static final int MAX_AMOUNT_DIGITS = 18;
    /** Satoshis per MAZA (BitcoinUnits::BTC base unit). */
    public static final long SATS_PER_MAZA = 100_000_000L;

    /** Parsed outcome: ok=true carries exactly the parsed fields;
     *  ok=false carries a user-safe reason and NOTHING parsed. */
    public static final class Parsed {
        public final boolean ok;
        public final String address;   // non-null only when ok
        public final long amountSats;  // 0 = no amount requested
        public final String label;     // "" when absent
        public final String message;   // "" when absent
        public final String reason;    // non-null only when !ok
        private Parsed(boolean ok, String address, long amountSats,
                       String label, String message, String reason) {
            this.ok = ok;
            this.address = address;
            this.amountSats = amountSats;
            this.label = label;
            this.message = message;
            this.reason = reason;
        }

        static Parsed ok(String address, long amountSats, String label,
                         String message) {
            return new Parsed(true, address, amountSats, label, message, null);
        }

        static Parsed fail(String reason) {
            return new Parsed(false, null, 0L, "", "", reason);
        }
    }

    private static final char[] HEX = "0123456789ABCDEF".toCharArray();

    private MazaUri() { }

    /**
     * Parse a maza:/maza:// payment URI. Never throws; performs no
     * network or filesystem action; returns fail for anything that is
     * not a maza: URI (ScanOrigin owns the scheme dispatch for scanned
     * text and validates the returned address itself).
     */
    public static Parsed parse(String uri) {
        if (uri == null) {
            return Parsed.fail("Nothing scanned");
        }
        String s = uri.trim();
        String lower = s.toLowerCase(Locale.US);
        String rest;
        if (lower.startsWith("maza://")) {
            // 7-char prefix strip - see the class javadoc divergence note
            // (upstream replace(0, 11, ...) would eat 4 address chars).
            rest = s.substring(7);
        } else if (lower.startsWith("maza:")) {
            rest = s.substring(5);
        } else {
            return Parsed.fail("Not a maza: URI");
        }
        int q = rest.indexOf('?');
        String path = q < 0 ? rest : rest.substring(0, q);
        String query = q < 0 ? null : rest.substring(q + 1);
        // one trailing '/' may be added by the OS (guiutil.cpp:154-157)
        if (path.endsWith("/")) {
            path = path.substring(0, path.length() - 1);
        }
        if (path.isEmpty()) {
            return Parsed.fail("URI carries no address");
        }
        long amount = 0L;
        String label = "";
        String message = "";
        if (query != null) {
            for (String item : query.split("&")) {
                if (item.isEmpty()) {
                    continue; // QUrlQuery yields no item for empty runs
                }
                int eq = item.indexOf('=');
                String rawKey = eq < 0 ? item : item.substring(0, eq);
                String rawValue = eq < 0 ? "" : item.substring(eq + 1);
                String key = pctDecode(rawKey);
                String value = pctDecode(rawValue);
                if (key == null || value == null) {
                    return Parsed.fail("URI is malformed");
                }
                boolean required = key.startsWith("req-");
                if (required) {
                    key = key.substring(4);
                }
                boolean known = true;
                if (key.equals("label")) {
                    label = value;
                } else if (key.equals("message")) {
                    message = value;
                } else if (key.equals("amount")) {
                    if (!value.isEmpty()) {
                        Long parsed = parseAmount(value);
                        if (parsed == null) {
                            return Parsed.fail("Amount is not valid");
                        }
                        amount = parsed;
                    }
                } else {
                    known = false;
                }
                if (required && !known) {
                    return Parsed.fail("Required URI parameter not supported");
                }
            }
        }
        return Parsed.ok(path, amount, label, message);
    }

    /**
     * BitcoinUnits::parse(BitcoinUnits::BTC, value) ported for scanned
     * amounts (bitcoinunits.cpp:144-181). Returns null on any invalid
     * shape; empty input is handled by the caller (absent amount).
     */
    private static Long parseAmount(String value) {
        String cleaned = removeSpaces(value);
        int dot = cleaned.indexOf('.');
        String whole;
        String frac;
        if (dot < 0) {
            whole = cleaned;
            frac = "";
        } else {
            if (cleaned.indexOf('.', dot + 1) >= 0) {
                return null; // more than one dot
            }
            whole = cleaned.substring(0, dot);
            frac = cleaned.substring(dot + 1);
        }
        if (frac.length() > AMOUNT_DECIMALS) {
            return null; // exceeds max precision
        }
        StringBuilder digits = new StringBuilder(whole.length()
                + AMOUNT_DECIMALS);
        digits.append(whole);
        digits.append(frac);
        // str = whole + frac.leftJustified(8, '0') - bitcoinunits.cpp:169.
        // (The fraction is padded to 8 AFTER the whole: "1.5" -> "150000000".)
        for (int i = frac.length(); i < AMOUNT_DECIMALS; i++) {
            digits.append('0');
        }
        String s = digits.toString();
        if (s.isEmpty() || s.length() > MAX_AMOUNT_DIGITS) {
            return null; // empty or longer numbers exceed 63 bits
        }
        long acc = 0L;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c < '0' || c > '9') {
                return null; // signed/foreign characters rejected (D14)
            }
            acc = acc * 10L + (c - '0');
        }
        return acc;
    }

    /** bitcoinunits.h:112-120 - ' ', U+2009, U+202F are ignored. */
    private static String removeSpaces(String s) {
        StringBuilder b = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c != ' ' && c != 0x2009 && c != 0x202F) {
                b.append(c);
            }
        }
        return b.toString();
    }

    /**
     * QUrlQuery-style percent-decoding of one key or value. Returns null
     * on a malformed escape (fail-closed; upstream Qt keeps malformed
     * escapes literal - D14 divergence). '+' stays literal.
     */
    private static String pctDecode(String raw) {
        if (raw.indexOf('%') < 0) {
            return raw;
        }
        byte[] in = raw.getBytes(StandardCharsets.UTF_8);
        byte[] out = new byte[in.length];
        int m = 0;
        for (int i = 0; i < in.length; ) {
            if (in[i] == '%') {
                if (i + 2 > in.length - 1) {
                    return null; // truncated escape
                }
                int hi = hexVal((char) (in[i + 1] & 0xFF));
                int lo = hexVal((char) (in[i + 2] & 0xFF));
                if (hi < 0 || lo < 0) {
                    return null; // malformed escape
                }
                out[m++] = (byte) ((hi << 4) | lo);
                i += 3;
            } else {
                out[m++] = in[i++];
            }
        }
        return new String(out, 0, m, StandardCharsets.UTF_8);
    }

    private static int hexVal(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    }

    /**
     * BitcoinUnits::format(BTC, amount, false, separatorNever) for the
     * scan-fill prefill: always exactly 8 fractional digits, never
     * separators. Caller-error on a negative amount (an IllegalArgumentException,
     * never a user-facing path).
     */
    public static String formatAmount(long amountSats) {
        if (amountSats < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        return String.format(Locale.US, "%d.%08d",
                amountSats / SATS_PER_MAZA, amountSats % SATS_PER_MAZA);
    }

    /**
     * formatBitcoinURI (guiutil.cpp:221-243): maza:<addr>, then amount
     * (when non-zero), then label, then message, '?' before the first
     * parameter and '&' between the rest. Pure string assembly - the
     * caller validates the address before calling.
     */
    public static String format(String address, long amountSats,
                                String label, String message) {
        StringBuilder b = new StringBuilder("maza:").append(address);
        int params = 0;
        if (amountSats != 0L) {
            b.append(params == 0 ? '?' : '&')
                    .append("amount=").append(formatAmount(amountSats));
            params++;
        }
        if (label != null && !label.isEmpty()) {
            b.append(params == 0 ? '?' : '&')
                    .append("label=").append(pctEncode(label));
            params++;
        }
        if (message != null && !message.isEmpty()) {
            b.append(params == 0 ? '?' : '&')
                    .append("message=").append(pctEncode(message));
            params++;
        }
        return b.toString();
    }

    /** UTF-8 percent-encoding, everything outside the RFC 3986 unreserved
     *  set escaped, uppercase hex (Qt-style output). */
    private static String pctEncode(String s) {
        byte[] bytes = s.getBytes(StandardCharsets.UTF_8);
        StringBuilder b = new StringBuilder(bytes.length);
        for (byte v : bytes) {
            int u = v & 0xFF;
            if ((u >= 'A' && u <= 'Z') || (u >= 'a' && u <= 'z')
                    || (u >= '0' && u <= '9')
                    || u == '-' || u == '.' || u == '_' || u == '~') {
                b.append((char) u);
            } else {
                b.append('%').append(HEX[(u >> 4) & 0xF]).append(HEX[u & 0xF]);
            }
        }
        return b.toString();
    }
}
