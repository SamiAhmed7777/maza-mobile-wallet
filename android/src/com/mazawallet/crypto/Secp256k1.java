package com.mazawallet.crypto;

import java.math.BigInteger;
import java.security.GeneralSecurityException;
import java.util.Arrays;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * secp256k1: affine point arithmetic over F(p), compressed pubkeys,
 * ECDSA sign (RFC6979 deterministic nonce, low-S) and verify.
 * Pure java.math.BigInteger + javax.crypto HMAC-SHA256; no android deps.
 */
public final class Secp256k1 {

    public static final BigInteger P = new BigInteger(1, Hex.fromHex(
            "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F"));
    public static final BigInteger N = new BigInteger(1, Hex.fromHex(
            "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141"));
    private static final BigInteger HALF_N = N.shiftRight(1);
    private static final BigInteger GX = new BigInteger(1, Hex.fromHex(
            "79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798"));
    private static final BigInteger GY = new BigInteger(1, Hex.fromHex(
            "483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8"));
    public static final Point G = new Point(GX, GY);
    public static final Point INFINITY = new Point(null, null);

    /** Affine point; null coordinates = point at infinity. Immutable. */
    public static final class Point {
        public final BigInteger x;
        public final BigInteger y;

        private Point(BigInteger x, BigInteger y) {
            this.x = x;
            this.y = y;
        }

        public boolean isInfinity() {
            return x == null;
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof Point)) return false;
            Point p = (Point) o;
            if (isInfinity() || p.isInfinity()) return isInfinity() && p.isInfinity();
            return x.equals(p.x) && y.equals(p.y);
        }

        @Override
        public int hashCode() {
            return isInfinity() ? 0 : x.hashCode() * 31 + y.hashCode();
        }
    }

    private Secp256k1() {}

    private static BigInteger mod(BigInteger a) {
        BigInteger r = a.mod(P);
        return r;
    }

    private static BigInteger modInv(BigInteger a) {
        return a.modPow(P.subtract(new BigInteger("2")), P); // BigInteger.TWO is Java 9+; Android's runtime lacks it
    }

    /** Point addition (handles infinity, doubling, and a == -b). */
    public static Point add(Point a, Point b) {
        if (a.isInfinity()) return b;
        if (b.isInfinity()) return a;
        if (a.x.equals(b.x)) {
            if (a.y.equals(b.y)) return dbl(a);
            return INFINITY; // a == -b
        }
        BigInteger slope = mod(b.y.subtract(a.y).multiply(modInv(b.x.subtract(a.x))));
        BigInteger x3 = mod(slope.multiply(slope).subtract(a.x).subtract(b.x));
        BigInteger y3 = mod(slope.multiply(a.x.subtract(x3)).subtract(a.y));
        return new Point(x3, y3);
    }

    public static Point dbl(Point a) {
        if (a.isInfinity()) return INFINITY;
        if (a.y.signum() == 0) return INFINITY;
        BigInteger slope = mod(BigInteger.valueOf(3)
                .multiply(a.x).multiply(a.x).multiply(modInv(a.y.shiftLeft(1))));
        BigInteger x3 = mod(slope.multiply(slope).subtract(a.x.shiftLeft(1)));
        BigInteger y3 = mod(slope.multiply(a.x.subtract(x3)).subtract(a.y));
        return new Point(x3, y3);
    }

    /** Scalar multiplication via double-and-add. */
    public static Point mul(BigInteger k, Point p) {
        if (k.signum() == 0 || p.isInfinity()) return INFINITY;
        k = k.mod(N);
        Point result = INFINITY;
        Point addend = p;
        while (k.signum() > 0) {
            if (k.testBit(0)) result = add(result, addend);
            addend = dbl(addend);
            k = k.shiftRight(1);
        }
        return result;
    }

    /** Compressed SEC1 encoding: 0x02/0x03 || x (33 bytes). */
    public static byte[] compress(Point p) {
        byte[] out = new byte[33];
        out[0] = (byte) (p.y.testBit(0) ? 0x03 : 0x02);
        byte[] x = p.x.toByteArray();
        // toByteArray may add a leading zero sign byte; copy right-aligned.
        System.arraycopy(x, Math.max(0, x.length - 32), out, 33 - Math.min(32, x.length),
                Math.min(32, x.length));
        return out;
    }

    /** Decompress a 33-byte SEC1 point (p mod 4 == 3, so y = a^((p+1)/4)). */
    public static Point decompress(byte[] compressed) {
        if (compressed.length != 33
                || (compressed[0] != 0x02 && compressed[0] != 0x03)) {
            throw new IllegalArgumentException("bad compressed pubkey");
        }
        BigInteger x = new BigInteger(1, Arrays.copyOfRange(compressed, 1, 33));
        BigInteger y = modPow(x.modPow(BigInteger.valueOf(3), P).add(BigInteger.valueOf(7)),
                P.add(BigInteger.ONE).shiftRight(2));
        if (y.testBit(0) != (compressed[0] == 0x03)) {
            y = P.subtract(y);
        }
        return new Point(x, y);
    }

    private static BigInteger modPow(BigInteger base, BigInteger exp) {
        return base.modPow(exp, P);
    }

    /** Compressed pubkey (33 bytes) for a private key. */
    public static byte[] pubFromPriv(BigInteger priv) {
        return compress(mul(priv, G));
    }

    /** RFC6979 deterministic nonce (HMAC-SHA256) for secp256k1 + SHA-256 digest. */
    public static BigInteger rfc6979Nonce(BigInteger priv, byte[] digest) {
        byte[] x = toFixed(priv, 32);
        byte[] h1 = bits2Octets(digest);
        byte[] v = new byte[32];
        byte[] k = new byte[32];
        Arrays.fill(v, (byte) 0x01);
        Arrays.fill(k, (byte) 0x00);
        k = hmacSha256(k, concat(v, new byte[]{0}, x, h1));
        v = hmacSha256(k, v);
        k = hmacSha256(k, concat(v, new byte[]{1}, x, h1));
        v = hmacSha256(k, v);
        while (true) {
            v = hmacSha256(k, v);
            BigInteger candidate = new BigInteger(1, v);
            if (candidate.signum() > 0 && candidate.compareTo(N) < 0) {
                return candidate;
            }
            k = hmacSha256(k, concat(v, new byte[]{0}));
            v = hmacSha256(k, v);
        }
    }

    /** bits2octets for qlen == holen == 256: int(h1) mod n, 32-byte BE. */
    private static byte[] bits2Octets(byte[] digest) {
        BigInteger z = new BigInteger(1, digest).mod(N);
        return toFixed(z, 32);
    }

    public static final class Signature {
        public final BigInteger r;
        public final BigInteger s;

        public Signature(BigInteger r, BigInteger s) {
            this.r = r;
            this.s = s;
        }
    }

    /** ECDSA sign with RFC6979 nonce; low-S enforced. */
    public static Signature sign(byte[] digest, BigInteger priv) {
        BigInteger z = new BigInteger(1, digest);
        BigInteger k = rfc6979Nonce(priv, digest);
        Point p = mul(k, G);
        BigInteger r = p.x.mod(N);
        BigInteger s = k.modInverse(N).multiply(z.add(r.multiply(priv))).mod(N);
        if (s.compareTo(HALF_N) > 0) {
            s = N.subtract(s);
        }
        return new Signature(r, s);
    }

    /** ECDSA verify against a compressed pubkey. */
    public static boolean verify(byte[] digest, Signature sig, byte[] compressedPub) {
        return verify(digest, sig, decompress(compressedPub));
    }

    public static boolean verify(byte[] digest, Signature sig, Point pub) {
        if (sig.r.signum() <= 0 || sig.r.compareTo(N) >= 0
                || sig.s.signum() <= 0 || sig.s.compareTo(N) >= 0) {
            return false;
        }
        BigInteger z = new BigInteger(1, digest);
        BigInteger w = sig.s.modInverse(N);
        BigInteger u1 = z.multiply(w).mod(N);
        BigInteger u2 = sig.r.multiply(w).mod(N);
        Point p = add(mul(u1, G), mul(u2, pub));
        if (p.isInfinity()) return false;
        return p.x.mod(N).equals(sig.r);
    }

    /** DER-encode an (r, s) pair (strict minimal form). */
    public static byte[] derEncode(BigInteger r, BigInteger s) {
        byte[] rb = toFixedUnsigned(r);
        byte[] sb = toFixedUnsigned(s);
        if (rb[0] < 0) { /* never happens via toFixedUnsigned */ }
        byte[] rEnc = withSignPad(rb);
        byte[] sEnc = withSignPad(sb);
        int len = 2 + rEnc.length + 2 + sEnc.length;
        byte[] out = new byte[2 + len];
        out[0] = 0x30;
        out[1] = (byte) len;
        out[2] = 0x02;
        out[3] = (byte) rEnc.length;
        System.arraycopy(rEnc, 0, out, 4, rEnc.length);
        int off = 4 + rEnc.length;
        out[off] = 0x02;
        out[off + 1] = (byte) sEnc.length;
        System.arraycopy(sEnc, 0, out, off + 2, sEnc.length);
        return out;
    }

    private static byte[] withSignPad(byte[] b) {
        if ((b[0] & 0x80) != 0) {
            byte[] out = new byte[b.length + 1];
            System.arraycopy(b, 0, out, 1, b.length);
            return out;
        }
        return b;
    }

    /** Minimal unsigned big-endian encoding (zero -> single 0x00 byte). */
    private static byte[] toFixedUnsigned(BigInteger v) {
        byte[] b = v.toByteArray();
        int start = 0;
        while (start < b.length - 1 && b[start] == 0) start++;
        return Arrays.copyOfRange(b, start, b.length);
    }

    /** Fixed-width 32-byte big-endian encoding of v (v < 2^256). */
    static byte[] toFixed(BigInteger v, int width) {
        byte[] b = v.toByteArray();
        byte[] out = new byte[width];
        int srcPos = Math.max(0, b.length - width);
        int len = Math.min(b.length, width);
        System.arraycopy(b, srcPos, out, width - len, len);
        return out;
    }

    private static byte[] concat(byte[]... parts) {
        int len = 0;
        for (byte[] p : parts) len += p.length;
        byte[] out = new byte[len];
        int off = 0;
        for (byte[] p : parts) {
            System.arraycopy(p, 0, out, off, p.length);
            off += p.length;
        }
        return out;
    }

    private static byte[] hmacSha256(byte[] key, byte[] data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e); // HmacSHA256 is always present
        }
    }
}
