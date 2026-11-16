package com.mazawallet.crypto;

/** Hex encode/decode helpers. Package-private; no android deps. */
final class Hex {

    private static final char[] DIGITS =
            "0123456789abcdef".toCharArray();

    private Hex() {}

    static String toHex(byte[] data) {
        StringBuilder sb = new StringBuilder(data.length * 2);
        for (byte b : data) {
            sb.append(DIGITS[(b >> 4) & 0x0F]);
            sb.append(DIGITS[b & 0x0F]);
        }
        return sb.toString();
    }

    static byte[] fromHex(String hex) {
        if (hex.length() % 2 != 0) {
            throw new IllegalArgumentException("odd hex length");
        }
        byte[] out = new byte[hex.length() / 2];
        for (int i = 0; i < out.length; i++) {
            int hi = Character.digit(hex.charAt(i * 2), 16);
            int lo = Character.digit(hex.charAt(i * 2 + 1), 16);
            if (hi < 0 || lo < 0) {
                throw new IllegalArgumentException("bad hex digit");
            }
            out[i] = (byte) ((hi << 4) | lo);
        }
        return out;
    }
}
