package com.mazawallet.crypto;

import java.util.Locale;

/**
 * Origin discipline for scanned QR content (M8 code half one, M8a).
 * Pure decision table: the ONLY thing a scan may ever yield is a MAZA
 * P2PKH address. The M8b scanner shell hands scanned text to parse()
 * and acts ONLY on an ok Result; rejection reasons are user-safe and
 * never echo the rejected content.
 *
 * Hard rules baked in:
 *  - Scanned content is NEVER fetched, opened, or treated as a URL.
 *    http/https/www content and ANY other "scheme:"-shaped text is
 *    rejected outright (base58 never contains ':', so any colon-carrying
 *    payload is URI-shaped and can never be a spendable address).
 *  - The address must decode as base58check with exactly 21 payload
 *    bytes and the version byte of the ACTIVE network (S-6: parse() pins
 *    MAINNET - version 50 via Bip44Maza.ADDRESS_VERSION / NetworkParams
 *    .MAINNET; parseForNetwork validates against the chosen
 *    NetworkParams instead, so a testnet scan rejects mainnet addresses
 *    and vice versa) - the SAME contract the SelfCustody send path
 *    enforces on typed addresses, so a scan can never insert anything
 *    the typed path would reject.
 *  - maza:/maza:// payloads go through MazaUri.parse (M9: the official
 *    payment-URI contract ported from MazaCoin guiutil.cpp) and the
 *    parsed address still re-validates through the SAME base58check
 *    contract as the typed send path; a URI that carries an amount
 *    fills only the SEND amount field, never anything auto-sent.
 *  - Length is capped before any decode work, so hostile oversized
 *    payloads cannot burn decode time.
 *
 * Pure Java (no android imports, no zxing imports): the desktop selftest
 * drives every row (SelfTest.scanOriginChecks). Nested Result follows the
 * Bip32.Node / TxBuilder.Output house shape - plain nested POJOs extending
 * Object dex clean in this build (they ship today); the d8 nested-class
 * rule only bites nested classes with a PLATFORM supertype (the S-2b-ii
 * bisect). The zxing DECODER itself stays out of this class entirely: the
 * policy accepts only the decoded PAYLOAD TEXT, never a decode object.
 */
public final class ScanOrigin {

    /** Max accepted scanned-text length (chars) before any decoding. */
    public static final int MAX_LENGTH = 200;

    /** Parsed outcome: ok=true carries exactly the address substring that
     *  validated (amountSats = a maza: URI's parsed amount, 0 when the
     *  payload carried none); ok=false carries a user-safe reason and NO
     *  address. */
    public static final class Result {
        public final boolean ok;
        public final String address;   // non-null only when ok
        public final String reason;    // non-null only when !ok
        public final long amountSats;  // meaningful only when ok (0 = none)
        private Result(boolean ok, String address, String reason,
                       long amountSats) {
            this.ok = ok;
            this.address = address;
            this.reason = reason;
            this.amountSats = amountSats;
        }
    }

    private ScanOrigin() { }

    /**
     * Classify scanned QR payload text. Never throws; never performs any
     * network or filesystem action; returns ok only for a well-formed
     * MAZA MAINNET P2PKH address (bare or after a maza: scheme prefix).
     */
    public static Result parse(String scanned) {
        return parseForNetwork(scanned, NetworkParams.MAINNET);
    }

    /**
     * Network-aware variant (S-6): same origin discipline, but the
     * address contract validates against params.pubkeyVersion instead of
     * the mainnet pin. A TESTNET scan rejects every mainnet address and
     * vice versa — a cross-network address can never enter the SEND
     * field, which is the guard behind the spec's "never broadcast an
     * unintended mainnet transaction" rule.
     */
    public static Result parseForNetwork(String scanned, NetworkParams params) {
        if (scanned == null) {
            return reject("Nothing scanned");
        }
        String s = scanned.trim();
        if (s.isEmpty()) {
            return reject("Nothing scanned");
        }
        if (s.length() > MAX_LENGTH) {
            return reject("Scanned content too long");
        }
        if (s.indexOf('\n') >= 0 || s.indexOf('\r') >= 0) {
            return reject("Multi-line content rejected");
        }
        String lower = s.toLowerCase(Locale.US);
        if (lower.startsWith("maza:")) {
            // M9: the official payment-URI parse (MazaUri mirrors the
            // MazaCoin desktop guiutil.cpp contract, divergences
            // documented in DECISIONS.md D14). The parsed address is
            // still validated HERE through the same base58check contract
            // as the typed path - MazaUri never blesses an address.
            MazaUri.Parsed p = MazaUri.parse(s);
            if (!p.ok) {
                return reject(p.reason);
            }
            return addressResult(p.address, p.amountSats, params);
        }
        if (lower.startsWith("http:") || lower.startsWith("https:")
                || lower.startsWith("www.")) {
            // belt-and-braces: "www." would also fail the address decode
            // ('.' is outside base58), but the explicit check yields the
            // precise never-fetched reason instead of a generic one.
            return reject("URLs are never opened or fetched");
        }
        if (s.indexOf(':') >= 0) {
            return reject("Unsupported URI scheme - content is never opened");
        }
        return addressResult(s, 0L, params);
    }

    private static Result addressResult(String s, long amountSats,
                                        NetworkParams params) {
        byte[] payload;
        try {
            payload = Base58Check.decode(s);
        } catch (RuntimeException e) {
            // parse()'s contract is NEVER-throws on any scanned text: any
            // unchecked decode-layer failure (not just the documented
            // IllegalArgumentException) is a rejection, never a crash.
            return reject("Not a valid MAZA address");
        }
        if (payload.length != 21
                || (payload[0] & 0xFF) != params.pubkeyVersion) {
            return reject("Not a MAZA address");
        }
        return new Result(true, s, null, amountSats);
    }

    private static Result reject(String reason) {
        return new Result(false, null, reason, 0L);
    }
}
