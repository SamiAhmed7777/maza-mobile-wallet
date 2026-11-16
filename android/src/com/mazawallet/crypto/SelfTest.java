package com.mazawallet.crypto;

import java.io.FileInputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Desktop-JVM self test for the crypto package. Every check prints one
 * PASS/FAIL line; exit code is nonzero if any check fails. Runs with plain
 * java: no android.* anywhere. Usage:
 *   java com.mazawallet.crypto.SelfTest [path-to-bip39_english.txt]
 */
public final class SelfTest {

    private static int failures = 0;
    private static int total = 0;

    public static void main(String[] args) throws Exception {
        String wordlistPath = args.length > 0
                ? args[0] : "android/res/raw/bip39_english.txt";
        String[] wordlist;
        try (FileInputStream in = new FileInputStream(wordlistPath)) {
            wordlist = Bip39.loadWordlist(in);
        }

        section("BIP39 (official Trezor vectors)");
        String mnZero = "abandon abandon abandon abandon abandon abandon"
                + " abandon abandon abandon abandon abandon about";
        String mn7f = "legal winner thank year wave sausage worth useful"
                + " legal winner thank yellow";

        check("bip39 entropy 0x00.. -> mnemonic",
                Bip39.entropyToMnemonic(new byte[16], wordlist).equals(mnZero));
        check("bip39 entropy 0x7f.. -> mnemonic",
                Bip39.entropyToMnemonic(fill((byte) 0x7f, 16), wordlist).equals(mn7f));

        String seedTrezor = Hex.toHex(Bip39.mnemonicToSeed(mnZero, "TREZOR"));
        check("bip39 seed(mnemonic, TREZOR)",
                seedTrezor.equals("c55257c360c07c72029aebc1b53c05ed0362ada38ead3e"
                        + "3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf14163"
                        + "0c7a3c4ab7c81b2f001698e7463b04"),
                seedTrezor);

        String seedEmpty = Hex.toHex(Bip39.mnemonicToSeed(mnZero, ""));
        check("bip39 seed(mnemonic, \"\")",
                seedEmpty.equals("5eb00bbddcf069084889a8ab9155568165f5c453ccb85e"
                        + "70811aaed6f6da5fc19a5ac40b389cd370d086206dec8aa6c43d"
                        + "aea6690f20ad3d8d48b2d2ce9e38e4"),
                seedEmpty);

        section("RIPEMD-160 (spec test vectors)");
        check("ripemd160(\"\")",
                Hex.toHex(Ripemd160.digest(new byte[0])).equals(
                        "9c1185a5c5e9fc54612808977ee8f548b2258d31"));
        check("ripemd160(\"abc\")",
                Hex.toHex(Ripemd160.digest("abc".getBytes("US-ASCII"))).equals(
                        "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc"));
        check("ripemd160(quick brown fox)",
                Hex.toHex(Ripemd160.digest(
                        "The quick brown fox jumps over the lazy dog"
                                .getBytes("US-ASCII"))).equals(
                        "37f332f68db77bd9d7edd4969571ad671cf9dd3b"));

        section("Base58Check");
        byte[] payload = new byte[37];
        for (int i = 0; i < payload.length; i++) payload[i] = (byte) (i * 7 + 1);
        String encoded = Base58Check.encode(payload);
        check("base58check roundtrip", Arrays.equals(Base58Check.decode(encoded), payload));
        byte[] zeroPayload = new byte[5];
        check("base58check leading zeros",
                Base58Check.encode(zeroPayload).startsWith("11111")
                        && Arrays.equals(Base58Check.decode(Base58Check.encode(zeroPayload)),
                                zeroPayload));

        section("BIP32 (bip-0032 Test Vector 1)");
        byte[] seed32 = Hex.fromHex("000102030405060708090a0b0c0d0e0f");
        Bip32.Node m = Bip32.masterKey(seed32);
        Bip32.Node m0h = Bip32.ckdPriv(m, Bip32.HARDENED);
        Bip32.Node m0h1 = Bip32.ckdPriv(m0h, 1);

        String xprvM = Bip32.xprv(m, 0, new byte[4], 0);
        check("bip32 xprv m", xprvM.equals(
                "xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3j"
                        + "PPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi"),
                xprvM);

        String xprvM0h = Bip32.xprv(m0h, 1, m.fingerprint(), Bip32.HARDENED);
        check("bip32 xprv m/0'", xprvM0h.equals(
                "xprv9uHRZZhk6KAJC1avXpDAp4MDc3sQKNxDiPvvkX8Br5ngLNv1Txv"
                        + "Uxt4cV1rGL5hj6KCesnDYUhd7oWgT11eZG7XnxHrnYeSvkzY7d2bhkJ7"),
                xprvM0h);

        String xprvM0h1 = Bip32.xprv(m0h1, 2, m0h.fingerprint(), 1);
        check("bip32 xprv m/0'/1", xprvM0h1.equals(
                "xprv9wTYmMFdV23N2TdNG573QoEsfRrWKQgWeibmLntzniatZvR9BmLn"
                        + "vSxqu53Kw1UmYPxLgboyZQaXwTCg8MSY3H2EU4pWcQDnRnrVA1xe8fs"),
                xprvM0h1);

        section("MAZA profile (canonical mnemonic seed, coin 13)");
        byte[] mazaSeed = Bip39.mnemonicToSeed(mnZero, "");
        Bip32.Node account = Bip44Maza.accountNode(mazaSeed);
        Bip32.Node k0 = Bip44Maza.keyAt(account, 0, 0);
        Bip32.Node k1 = Bip44Maza.keyAt(account, 0, 1);
        Bip32.Node k2 = Bip44Maza.keyAt(account, 0, 2);

        check("maza address m/44'/13'/0'/0/0",
                Bip44Maza.address(k0).equals("MLhJ8cs5sG8YY6YcMs5rmqCV6hZjqF7LEE"),
                Bip44Maza.address(k0));
        check("maza address m/44'/13'/0'/0/1",
                Bip44Maza.address(k1).equals("M8jVzPpyy3HMLfhahY2fnqquLfqENRXaW8"),
                Bip44Maza.address(k1));
        check("maza address m/44'/13'/0'/0/2",
                Bip44Maza.address(k2).equals("MGnAbzXuVf3ywFBeVH3a2AprzdP61igYPU"),
                Bip44Maza.address(k2));

        String wif = Bip44Maza.wif(k0);
        check("maza WIF m/44'/13'/0'/0/0",
                wif.equals("aGpgV4Riom5x1wdH7TXrsc4zJhLgYajVJMUsrYBJoUbChz5xcwi6"), wif);

        String script = Hex.toHex(Bip44Maza.p2pkhScript(k0));
        check("maza p2pkh scriptPubKey",
                script.startsWith("76a914") && script.endsWith("88ac")
                        && script.length() == 50,
                script);

        section("BTC cross-check (same mnemonic, m/44'/0'/0'/0/0, version 0x00)");
        Bip32.Node btc = Bip32.derive(Bip32.masterKey(mazaSeed), "m/44'/0'/0'/0/0");
        byte[] h160 = Base58Check.hash160(btc.pub());
        byte[] btcPayload = new byte[21];
        btcPayload[0] = 0x00;
        System.arraycopy(h160, 0, btcPayload, 1, 20);
        String btcAddr = Base58Check.encode(btcPayload);
        check("btc address m/44'/0'/0'/0/0",
                btcAddr.equals("1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA"), btcAddr);

        section("TxBuilder (legacy P2PKH, SIGHASH_ALL)");
        check("txbuilder sign + verify", txBuilderCheck(k0));

        System.out.println();
        if (failures == 0) {
            System.out.println("ALL " + total + " CHECKS PASSED");
        } else {
            System.out.println("FAILURES: " + failures + " of " + total);
        }
        System.exit(failures == 0 ? 0 : 1);
    }

    /** Sign a fake 1-in/2-out tx with the fixed WIF key; verify each sig. */
    private static boolean txBuilderCheck(Bip32.Node key) throws IOException {
        // Decode the fixed WIF and require it to round-trip to the same key.
        byte[] wifPayload = Base58Check.decode(Bip44Maza.wif(key));
        if ((wifPayload[0] & 0xFF) != Bip44Maza.WIF_VERSION
                || wifPayload.length != 34 || wifPayload[33] != 0x01) {
            return false;
        }
        BigInteger priv = new BigInteger(1, Arrays.copyOfRange(wifPayload, 1, 33));
        if (!priv.equals(key.priv)) return false;

        // Fake UTXO paying 0.001 MAZA to our address; fake prev txid.
        byte[] prevTxid = Hex.fromHex(
                "c5f13de79a5a29c0a6ab0e0c3f28b7a251a30d6d8e12f4a7b9e02c6d45a1f708");
        long utxoValue = 100000; // 0.001 MAZA in satoshis
        long sendValue = 40000;  // 0.0004 MAZA
        long feeValue = 10000;   // 0.0001 MAZA
        long changeValue = utxoValue - sendValue - feeValue;

        TxBuilder.Input in = new TxBuilder.Input(prevTxid, 0,
                Bip44Maza.p2pkhScript(key), utxoValue);
        List<TxBuilder.Input> inputs = new ArrayList<>();
        inputs.add(in);

        List<TxBuilder.Output> outputs = new ArrayList<>();
        outputs.add(new TxBuilder.Output(sendValue,
                Bip44Maza.p2pkhScriptForHash(Arrays.copyOfRange(
                        Base58Check.hash160(Secp256k1.pubFromPriv(priv)), 0, 20))));
        outputs.add(new TxBuilder.Output(changeValue, Bip44Maza.p2pkhScript(key)));

        byte[] raw = TxBuilder.buildAndSign(inputs, outputs, new BigInteger[]{priv});
        if (raw.length < 200) return false; // 1-in/2-out signed tx is ~225 bytes

        // Recompute the sighash and verify the embedded DER signature.
        byte[] digest = TxBuilder.sighash(inputs, outputs, 0);
        byte[] pub = Secp256k1.pubFromPriv(priv);
        Secp256k1.Signature sig = extractSig(raw);
        if (sig == null) return false;
        if (sig.s.compareTo(Secp256k1.N.shiftRight(1)) > 0) return false; // low-S
        if (!Secp256k1.verify(digest, sig, pub)) return false;

        // Sanity: version 1 LE prefix, parseable txid, negative-fee refusal.
        if (raw[0] != 1 || raw[1] != 0 || raw[2] != 0 || raw[3] != 0) return false;
        if (TxBuilder.txidOf(raw).length != 32) return false;
        boolean refused = false;
        try {
            List<TxBuilder.Output> bad = new ArrayList<>();
            bad.add(new TxBuilder.Output(-1, Bip44Maza.p2pkhScript(key)));
            TxBuilder.buildAndSign(inputs, bad, new BigInteger[]{priv});
        } catch (IllegalArgumentException e) {
            refused = "negative output value".equals(e.getMessage());
        }
        return refused;
    }

    /** Pull the first pushed item (sig+hashtype) out of the signed raw tx. */
    private static Secp256k1.Signature extractSig(byte[] raw) {
        // version(4) + varint in-count(1) + txid(32) + vout(4) = 41; then
        // varint scriptSig length, then scriptSig.
        int off = 41;
        int len = raw[off] & 0xFF;
        if (len > 0xFC) return null; // must be a single-byte varint
        byte[] scriptSig = Arrays.copyOfRange(raw, off + 1, off + 1 + len);
        int pushLen = scriptSig[0] & 0xFF;
        if (pushLen > 75 || pushLen + 1 > scriptSig.length) return null;
        byte[] sigAndType = Arrays.copyOfRange(scriptSig, 1, 1 + pushLen);
        if (sigAndType[sigAndType.length - 1] != (byte) TxBuilder.SIGHASH_ALL) {
            return null;
        }
        return parseDer(Arrays.copyOfRange(sigAndType, 0, sigAndType.length - 1));
    }

    private static Secp256k1.Signature parseDer(byte[] der) {
        try {
            if (der[0] != 0x30 || (der[1] & 0xFF) != der.length - 2) return null;
            if (der[2] != 0x02) return null;
            int rLen = der[3] & 0xFF;
            BigInteger r = new BigInteger(1, Arrays.copyOfRange(der, 4, 4 + rLen));
            int sOff = 4 + rLen;
            if (der[sOff] != 0x02) return null;
            int sLen = der[sOff + 1] & 0xFF;
            BigInteger s = new BigInteger(1,
                    Arrays.copyOfRange(der, sOff + 2, sOff + 2 + sLen));
            return new Secp256k1.Signature(r, s);
        } catch (RuntimeException e) {
            return null;
        }
    }

    private static void section(String name) {
        System.out.println("-- " + name);
    }

    private static void check(String name, boolean ok) {
        check(name, ok, null);
    }

    private static void check(String name, boolean ok, String detail) {
        total++;
        if (ok) {
            System.out.println("PASS " + name);
        } else {
            failures++;
            System.out.println("FAIL " + name + (detail == null ? "" : "  got: " + detail));
        }
    }

    private static byte[] fill(byte v, int len) {
        byte[] out = new byte[len];
        Arrays.fill(out, v);
        return out;
    }
}
