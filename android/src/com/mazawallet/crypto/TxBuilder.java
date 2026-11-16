package com.mazawallet.crypto;

import java.math.BigInteger;
import java.util.List;

/**
 * Legacy P2PKH transaction builder: version 1, SIGHASH_ALL signing with
 * RFC6979 nonces, DER + low-S signatures, scriptSig = <push sig> <push pub>.
 * Consensus serialization only; no android deps.
 */
public final class TxBuilder {

    public static final long SIGHASH_ALL = 1;
    public static final long SEQUENCE_FINAL = 0xFFFFFFFFL;

    public static final class Input {
        public final byte[] txid;          // 32 bytes, display (big-endian) order
        public final int vout;
        public final byte[] scriptPubKey;  // of the UTXO being spent
        public final long value;           // UTXO value, satoshis (fee checks)

        public Input(byte[] txid, int vout, byte[] scriptPubKey, long value) {
            if (txid.length != 32) throw new IllegalArgumentException("txid must be 32 bytes");
            this.txid = txid;
            this.vout = vout;
            this.scriptPubKey = scriptPubKey;
            this.value = value;
        }
    }

    public static final class Output {
        public final long value;           // satoshis
        public final byte[] scriptPubKey;

        public Output(long value, byte[] scriptPubKey) {
            this.value = value;
            this.scriptPubKey = scriptPubKey;
        }
    }

    private TxBuilder() {}

    /**
     * Build the fully-signed raw transaction.
     * Refuses: empty inputs, any output value < 0, negative fee.
     * privKeys[i] signs inputs.get(i).
     */
    public static byte[] buildAndSign(List<Input> inputs, List<Output> outputs,
            BigInteger[] privKeys) {
        if (inputs == null || inputs.isEmpty()) {
            throw new IllegalArgumentException("no inputs");
        }
        if (privKeys.length != inputs.size()) {
            throw new IllegalArgumentException("one key per input required");
        }
        long inTotal = 0;
        for (Input in : inputs) {
            inTotal = Math.addExact(inTotal, in.value);
        }
        long outTotal = 0;
        for (Output out : outputs) {
            if (out.value < 0) {
                throw new IllegalArgumentException("negative output value");
            }
            outTotal = Math.addExact(outTotal, out.value);
        }
        if (outTotal > inTotal) {
            throw new IllegalArgumentException("negative fee");
        }

        byte[][] scriptSigs = new byte[inputs.size()][];
        for (int i = 0; i < inputs.size(); i++) {
            byte[] digest = sighash(inputs, outputs, i);
            Secp256k1.Signature sig = Secp256k1.sign(digest, privKeys[i]);
            byte[] der = Secp256k1.derEncode(sig.r, sig.s);
            byte[] withType = new byte[der.length + 1];
            System.arraycopy(der, 0, withType, 0, der.length);
            withType[der.length] = (byte) SIGHASH_ALL;
            byte[] pub = Secp256k1.pubFromPriv(privKeys[i]);
            scriptSigs[i] = concat(pushData(withType), pushData(pub));
        }

        ByteWriter w = new ByteWriter();
        w.u32(1); // version
        w.varInt(inputs.size());
        for (int i = 0; i < inputs.size(); i++) {
            Input in = inputs.get(i);
            w.bytes(reverse(in.txid));
            w.u32(in.vout);
            w.varBytes(scriptSigs[i]);
            w.u32(SEQUENCE_FINAL);
        }
        w.varInt(outputs.size());
        for (Output out : outputs) {
            w.u64(out.value);
            w.varBytes(out.scriptPubKey);
        }
        w.u32(0); // locktime
        return w.toByteArray();
    }

    /** Legacy SIGHASH_ALL digest: copy of tx with only inputIndex's scriptSig set. */
    public static byte[] sighash(List<Input> inputs, List<Output> outputs,
            int inputIndex) {
        ByteWriter w = new ByteWriter();
        w.u32(1);
        w.varInt(inputs.size());
        for (int i = 0; i < inputs.size(); i++) {
            Input in = inputs.get(i);
            w.bytes(reverse(in.txid));
            w.u32(in.vout);
            if (i == inputIndex) {
                w.varBytes(in.scriptPubKey);
            } else {
                w.varInt(0);
            }
            w.u32(SEQUENCE_FINAL);
        }
        w.varInt(outputs.size());
        for (Output out : outputs) {
            w.u64(out.value);
            w.varBytes(out.scriptPubKey);
        }
        w.u32(0);
        w.u32(SIGHASH_ALL);
        return Base58Check.doubleSha256(w.toByteArray());
    }

    /** Transaction id (display order) of a signed raw transaction. */
    public static byte[] txidOf(byte[] rawTx) {
        return reverse(Base58Check.doubleSha256(rawTx));
    }

    /** scriptSig/data push prefix. */
    public static byte[] pushData(byte[] data) {
        if (data.length <= 75) {
            byte[] out = new byte[data.length + 1];
            out[0] = (byte) data.length;
            System.arraycopy(data, 0, out, 1, data.length);
            return out;
        }
        if (data.length <= 0xFF) {
            byte[] out = new byte[data.length + 2];
            out[0] = 0x4C;
            out[1] = (byte) data.length;
            System.arraycopy(data, 0, out, 2, data.length);
            return out;
        }
        throw new IllegalArgumentException("pushData too large");
    }

    static byte[] reverse(byte[] b) {
        byte[] out = new byte[b.length];
        for (int i = 0; i < b.length; i++) out[i] = b[b.length - 1 - i];
        return out;
    }

    static byte[] concat(byte[] a, byte[] b) {
        byte[] out = new byte[a.length + b.length];
        System.arraycopy(a, 0, out, 0, a.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }

    /** Little-endian byte writer for consensus serialization. */
    static final class ByteWriter {
        private final java.io.ByteArrayOutputStream buf =
                new java.io.ByteArrayOutputStream();

        void u32(long v) {
            for (int i = 0; i < 4; i++) buf.write((int) (v >>> (8 * i)) & 0xFF);
        }

        void u64(long v) {
            for (int i = 0; i < 8; i++) buf.write((int) (v >>> (8 * i)) & 0xFF);
        }

        void varInt(long v) {
            if (v < 0xFD) {
                buf.write((int) v);
            } else if (v <= 0xFFFF) {
                buf.write(0xFD);
                buf.write((int) v & 0xFF);
                buf.write((int) (v >>> 8) & 0xFF);
            } else if (v <= 0xFFFFFFFFL) {
                buf.write(0xFE);
                u32(v);
            } else {
                buf.write(0xFF);
                u64(v);
            }
        }

        void varBytes(byte[] data) {
            varInt(data.length);
            bytes(data);
        }

        void bytes(byte[] data) {
            buf.write(data, 0, data.length);
        }

        byte[] toByteArray() {
            return buf.toByteArray();
        }
    }
}
