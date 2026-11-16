package com.mazawallet.crypto;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

/**
 * Base58Check encode/decode (Bitcoin alphabet, 4-byte double-SHA256
 * checksum). No android deps.
 */
public final class Base58Check {

    private static final String ALPHABET =
            "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    private static final int[] INDEXES = new int[128];

    static {
        Arrays.fill(INDEXES, -1);
        for (int i = 0; i < ALPHABET.length(); i++) {
            INDEXES[ALPHABET.charAt(i)] = i;
        }
    }

    private Base58Check() {}

    /** base58check(data) = base58(data || first4(doubleSHA256(data))). */
    public static String encode(byte[] data) {
        byte[] withChecksum = new byte[data.length + 4];
        System.arraycopy(data, 0, withChecksum, 0, data.length);
        byte[] checksum = checksum(data);
        System.arraycopy(checksum, 0, withChecksum, data.length, 4);
        return rawEncode(withChecksum);
    }

    /** Decode a base58check string; verifies and strips the checksum. */
    public static byte[] decode(String s) {
        byte[] withChecksum = rawDecode(s);
        if (withChecksum.length < 4) {
            throw new IllegalArgumentException("base58check too short");
        }
        byte[] data = new byte[withChecksum.length - 4];
        System.arraycopy(withChecksum, 0, data, 0, data.length);
        byte[] expected = checksum(data);
        for (int i = 0; i < 4; i++) {
            if (withChecksum[data.length + i] != expected[i]) {
                throw new IllegalArgumentException("base58check checksum mismatch");
            }
        }
        return data;
    }

    static byte[] checksum(byte[] data) {
        byte[] hash = sha256(sha256(data));
        return new byte[]{hash[0], hash[1], hash[2], hash[3]};
    }

    static byte[] sha256(byte[] data) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(data);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e); // SHA-256 is always present
        }
    }

    /** hash160 = RIPEMD-160(SHA-256(x)), using the pure-Java RIPEMD-160. */
    public static byte[] hash160(byte[] data) {
        return Ripemd160.digest(sha256(data));
    }

    /** doubleSHA256 = SHA-256(SHA-256(x)). */
    public static byte[] doubleSha256(byte[] data) {
        return sha256(sha256(data));
    }

    private static String rawEncode(byte[] data) {
        int zeros = 0;
        while (zeros < data.length && data[zeros] == 0) zeros++;
        // Big-endian bignum division by 58 (payloads are <= ~80 bytes, so
        // BigInteger simplicity wins over micro-optimization here).
        java.math.BigInteger num =
                new java.math.BigInteger(1, Arrays.copyOfRange(data, zeros, data.length));
        StringBuilder sb = new StringBuilder();
        java.math.BigInteger fiftyEight = java.math.BigInteger.valueOf(58);
        while (num.signum() > 0) {
            java.math.BigInteger[] divRem = num.divideAndRemainder(fiftyEight);
            sb.append(ALPHABET.charAt(divRem[1].intValue()));
            num = divRem[0];
        }
        for (int i = 0; i < zeros; i++) sb.append('1');
        return sb.reverse().toString();
    }

    private static byte[] rawDecode(String s) {
        int zeros = 0;
        while (zeros < s.length() && s.charAt(zeros) == '1') zeros++;
        // decoded holds the number little-endian-ish: least significant byte
        // at the highest index, grown leftward via outputStart.
        byte[] decoded = new byte[(s.length() - zeros) * 733 / 1000 + 1];
        int outputStart = decoded.length;
        for (int i = zeros; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c >= 128 || INDEXES[c] < 0) {
                throw new IllegalArgumentException("invalid base58 char: " + c);
            }
            int carry = INDEXES[c];
            for (int j = decoded.length - 1; j >= outputStart; j--) {
                int num = (decoded[j] & 0xFF) * 58 + carry;
                decoded[j] = (byte) num;
                carry = (num >>> 8) & 0xFF;
            }
            if (carry != 0) {
                if (outputStart == 0) {
                    throw new IllegalArgumentException("base58 overflow");
                }
                decoded[--outputStart] = (byte) carry;
            }
        }
        // Skip padding zero bytes produced during the multiply passes.
        while (outputStart < decoded.length && decoded[outputStart] == 0) outputStart++;
        byte[] out = new byte[zeros + (decoded.length - outputStart)];
        System.arraycopy(decoded, outputStart, out, zeros, decoded.length - outputStart);
        return out;
    }
}
