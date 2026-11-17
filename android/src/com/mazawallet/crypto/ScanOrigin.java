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
 *    bytes and version 50 (Bip44Maza.ADDRESS_VERSION) - the SAME
 *    contract the SelfCustody send path enforces on typed addresses,
 *    so a scan can never insert anything the typed path would reject.
 *  - maza: URI parameters (?amount=...) are REJECTED until M9 ships
 *    the payment-URI contract; fail-closed beats half-parsed.
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
     *  validated; ok=false carries a user-safe reason and NO address. */
    public static final class Result {
        public final boolean ok;
        public final String address; // non-null only when ok
        public final String reason;  // non-null only when !ok
        private Result(boolean ok, String address, String reason) {
            this.ok = ok;
            this.address = address;
            this.reason = reason;
        }
    }

    private ScanOrigin() { }

    /**
     * Classify scanned QR payload text. Never throws; never performs any
     * network or filesystem action; returns ok only for a well-formed
     * MAZA mainnet P2PKH address (bare or after a maza: scheme prefix).
     */
    public static Result parse(String scanned) {
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
            String rest = s.substring(5);
            if (rest.indexOf('?') >= 0) {
                return reject("URI parameters are not supported yet");
            }
            if (rest.isEmpty()) {
                return reject("URI carries no address");
            }
            return addressResult(rest);
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
        return addressResult(s);
    }

    private static Result addressResult(String s) {
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
                || (payload[0] & 0xFF) != Bip44Maza.ADDRESS_VERSION) {
            return reject("Not a MAZA address");
        }
        return new Result(true, s, null);
    }

    private static Result reject(String reason) {
        return new Result(false, null, reason);
    }
}
