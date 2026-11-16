package com.mazawallet.crypto;

import java.math.BigInteger;
import java.security.GeneralSecurityException;
import java.util.ArrayList;
import java.util.List;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/**
 * BIP32 private derivation: master key from seed, CKDpriv (hardened and
 * soft), path parser ("m/44'/13'/0'/0/0"), xprv serialization per
 * bip-0032.mediawiki. No android deps.
 */
public final class Bip32 {

    public static final long HARDENED = 0x80000000L;

    /** A BIP32 node: private key + chain code (both 32 bytes worth). */
    public static final class Node {
        public final BigInteger priv;   // 1..n-1
        public final byte[] chainCode;  // 32 bytes

        private Node(BigInteger priv, byte[] chainCode) {
            this.priv = priv;
            this.chainCode = chainCode;
        }

        /** Compressed 33-byte pubkey of this node. */
        public byte[] pub() {
            return Secp256k1.pubFromPriv(priv);
        }

        /** First 4 bytes of hash160(pub): the key fingerprint. */
        public byte[] fingerprint() {
            byte[] h160 = Base58Check.hash160(pub());
            return new byte[]{h160[0], h160[1], h160[2], h160[3]};
        }
    }

    private Bip32() {}

    /** master key: I = HMAC-SHA512("Bitcoin seed", seed). */
    public static Node masterKey(byte[] seed) {
        byte[] i = hmacSha512("Bitcoin seed".getBytes(java.nio.charset.StandardCharsets.US_ASCII), seed);
        return nodeFromI(i);
    }

    private static Node nodeFromI(byte[] i) {
        byte[] il = new byte[32];
        byte[] ir = new byte[32];
        System.arraycopy(i, 0, il, 0, 32);
        System.arraycopy(i, 32, ir, 0, 32);
        BigInteger priv = new BigInteger(1, il);
        if (priv.signum() == 0 || priv.compareTo(Secp256k1.N) >= 0) {
            throw new IllegalStateException("invalid BIP32 key material");
        }
        return new Node(priv, ir);
    }

    /** CKDpriv: derive child at index (>= HARDENED means hardened). */
    public static Node ckdPriv(Node parent, long index) {
        byte[] data = new byte[37];
        if (index >= HARDENED) {
            data[0] = 0x00;
            System.arraycopy(Secp256k1.toFixed(parent.priv, 32), 0, data, 1, 32);
        } else {
            System.arraycopy(parent.pub(), 0, data, 0, 33);
        }
        data[33] = (byte) (index >>> 24);
        data[34] = (byte) (index >>> 16);
        data[35] = (byte) (index >>> 8);
        data[36] = (byte) index;
        byte[] i = hmacSha512(parent.chainCode, data);
        BigInteger il = new BigInteger(1, slice(i, 0, 32));
        if (il.compareTo(Secp256k1.N) >= 0) {
            throw new IllegalStateException("CKDpriv IL out of range");
        }
        BigInteger child = il.add(parent.priv).mod(Secp256k1.N);
        if (child.signum() == 0) {
            throw new IllegalStateException("CKDpriv produced zero key");
        }
        return new Node(child, slice(i, 32, 32));
    }

    /**
     * Parse "m/44'/13'/0'/0/0" (or "44'/13'/0'/0/0") into child indices.
     * ' and h and H mark hardened.
     */
    public static long[] parsePath(String path) {
        String p = path.trim();
        if (p.equals("m") || p.equals("M") || p.isEmpty()) return new long[0];
        if (p.startsWith("m/") || p.startsWith("M/")) p = p.substring(2);
        String[] parts = p.split("/");
        List<Long> indices = new ArrayList<>();
        for (String part : parts) {
            boolean hardened = false;
            String num = part;
            if (num.endsWith("'") || num.endsWith("h") || num.endsWith("H")) {
                hardened = true;
                num = num.substring(0, num.length() - 1);
            }
            long idx = Long.parseLong(num); // throws NumberFormatException
            if (idx < 0 || idx > 0x7FFFFFFFL) {
                throw new IllegalArgumentException("path index out of range: " + part);
            }
            indices.add(hardened ? idx + HARDENED : idx);
        }
        long[] out = new long[indices.size()];
        for (int i = 0; i < out.length; i++) out[i] = indices.get(i);
        return out;
    }

    /** Derive a path from the master node. */
    public static Node derive(Node master, String path) {
        Node node = master;
        for (long idx : parsePath(path)) {
            node = ckdPriv(node, idx);
        }
        return node;
    }

    /**
     * xprv serialization:
     * 0x0488ADE4 || depth(1) || parent_fp(4) || child_num(4 BE) ||
     * chaincode(32) || 0x00 || key(32), base58check.
     */
    public static String xprv(Node node, int depth, byte[] parentFingerprint,
            long childNumber) {
        byte[] payload = new byte[78];
        payload[0] = (byte) 0x04;
        payload[1] = (byte) 0x88;
        payload[2] = (byte) 0xAD;
        payload[3] = (byte) 0xE4;
        payload[4] = (byte) depth;
        System.arraycopy(parentFingerprint, 0, payload, 5, 4);
        payload[9] = (byte) (childNumber >>> 24);
        payload[10] = (byte) (childNumber >>> 16);
        payload[11] = (byte) (childNumber >>> 8);
        payload[12] = (byte) childNumber;
        System.arraycopy(node.chainCode, 0, payload, 13, 32);
        payload[45] = 0x00;
        System.arraycopy(Secp256k1.toFixed(node.priv, 32), 0, payload, 46, 32);
        return Base58Check.encode(payload);
    }

    private static byte[] slice(byte[] data, int off, int len) {
        byte[] out = new byte[len];
        System.arraycopy(data, off, out, 0, len);
        return out;
    }

    private static byte[] hmacSha512(byte[] key, byte[] data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA512");
            mac.init(new SecretKeySpec(key, "HmacSHA512"));
            return mac.doFinal(data);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e); // HmacSHA512 always present
        }
    }
}
