package com.mazawallet.crypto;

/**
 * Pure-Java RIPEMD-160. Implemented from the public domain reference
 * specification (Dobbertin, Bosselaers, Preneel). Android's JCE providers
 * do not ship RIPEMD-160 on modern API levels, so this is the only
 * hash160 path. Package-private; no android deps.
 */
final class Ripemd160 {

    private Ripemd160() {}

    static byte[] digest(byte[] msg) {
        int[] h = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0};

        // Pad: 0x80, zeros to 56 mod 64, then 64-bit little-endian bit length.
        long bitLen = (long) msg.length * 8;
        int paddedLen = ((msg.length + 8) / 64 + 1) * 64;
        byte[] buf = new byte[paddedLen];
        System.arraycopy(msg, 0, buf, 0, msg.length);
        buf[msg.length] = (byte) 0x80;
        for (int i = 0; i < 8; i++) {
            buf[paddedLen - 8 + i] = (byte) (bitLen >>> (8 * i));
        }

        int[] x = new int[16];
        for (int off = 0; off < paddedLen; off += 64) {
            for (int i = 0; i < 16; i++) {
                int j = off + i * 4;
                x[i] = (buf[j] & 0xFF) | ((buf[j + 1] & 0xFF) << 8)
                        | ((buf[j + 2] & 0xFF) << 16) | ((buf[j + 3] & 0xFF) << 24);
            }
            int h0 = h[0], h1 = h[1], h2 = h[2], h3 = h[3], h4 = h[4];
            int a = h0, b = h1, c = h2, d = h3, e = h4;
            int ap = a, bp = b, cp = c, dp = d, ep = e;

            for (int i = 0; i < 80; i++) {
                int t = a + f(i, b, c, d) + x[r1(i)] + k1(i);
                t = Integer.rotateLeft(t, s1(i)) + e;
                a = e; e = d; d = Integer.rotateLeft(c, 10); c = b; b = t;

                t = ap + f(79 - i, bp, cp, dp) + x[r2(i)] + k2(i);
                t = Integer.rotateLeft(t, s2(i)) + ep;
                ap = ep; ep = dp; dp = Integer.rotateLeft(cp, 10); cp = bp; bp = t;
            }
            // Combine the two parallel lines into the state; the right
            // line's registers feed in rotated by one position.
            h[0] = h1 + c + dp;
            h[1] = h2 + d + ep;
            h[2] = h3 + e + ap;
            h[3] = h4 + a + bp;
            h[4] = h0 + b + cp;
        }

        byte[] out = new byte[20];
        for (int i = 0; i < 5; i++) {
            out[i * 4] = (byte) h[i];
            out[i * 4 + 1] = (byte) (h[i] >>> 8);
            out[i * 4 + 2] = (byte) (h[i] >>> 16);
            out[i * 4 + 3] = (byte) (h[i] >>> 24);
        }
        return out;
    }

    private static int f(int i, int x, int y, int z) {
        if (i < 16) return x ^ y ^ z;
        if (i < 32) return (x & y) | (~x & z);
        if (i < 48) return (x | ~y) ^ z;
        if (i < 64) return (x & z) | (y & ~z);
        return x ^ (y | ~z);
    }

    private static int k1(int i) {
        if (i < 16) return 0x00000000;
        if (i < 32) return 0x5A827999;
        if (i < 48) return 0x6ED9EBA1;
        if (i < 64) return 0x8F1BBCDC;
        return 0xA953FD4E;
    }

    private static int k2(int i) {
        if (i < 16) return 0x50A28BE6;
        if (i < 32) return 0x5C4DD124;
        if (i < 48) return 0x6D703EF3;
        if (i < 64) return 0x7A6D76E9;
        return 0x00000000;
    }

    private static final int[] RL = {
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
        7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
        3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12,
        1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
        4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13
    };

    private static final int[] RR = {
        5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12,
        6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
        15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13,
        8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
        12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11
    };

    private static final int[] SL = {
        11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8,
        7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
        11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5,
        11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
        9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6
    };

    private static final int[] SR = {
        8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6,
        9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
        9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5,
        15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
        8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11
    };

    private static int r1(int i) { return RL[i]; }
    private static int r2(int i) { return RR[i]; }
    private static int s1(int i) { return SL[i]; }
    private static int s2(int i) { return SR[i]; }
}
