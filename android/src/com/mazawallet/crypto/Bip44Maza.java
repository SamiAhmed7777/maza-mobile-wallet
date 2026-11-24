package com.mazawallet.crypto;

/**
 * BIP44 for MAZA (SLIP-44 coin type 13): m/44'/13'/0'/<chain>/<index>,
 * address version byte 50 (0x32) -> "M..." base58check of hash160(pub),
 * WIF version byte 224 (0xE0) with 0x01 compressed suffix. P2PKH only.
 * No android deps.
 */
public final class Bip44Maza {

    public static final int COIN_TYPE = 13;
    // Mainnet version bytes, kept as named constants for the existing call
    // sites; single source of truth is NetworkParams.MAINNET (S-6: the
    // testnet twins live there — pubkey 88 / wif 239, chainparams.cpp
    // CTestNetParams:297-299, node-validated via SelfTest.mazaTestnetChecks).
    public static final int ADDRESS_VERSION = NetworkParams.MAINNET.pubkeyVersion;
    public static final int WIF_VERSION = NetworkParams.MAINNET.wifVersion;
    public static final int RECEIVE_CHAIN = 0;
    public static final int CHANGE_CHAIN = 1;
    public static final int GAP_LIMIT = 20;

    private Bip44Maza() {}

    /** m/44'/13'/0' account node from a BIP39 seed. The derivation PATH is
     *  network-independent (SLIP-44 coin 13 on both MazaCore networks) —
     *  only the ENCODING version bytes differ per network. */
    public static Bip32.Node accountNode(byte[] seed) {
        return Bip32.derive(Bip32.masterKey(seed),
                "m/44'/" + COIN_TYPE + "'/0'");
    }

    /** Key at m/44'/13'/0'/<chain>/<index>. */
    public static Bip32.Node keyAt(Bip32.Node account, int chain, int index) {
        return Bip32.derive(account, chain + "/" + index);
    }

    /** base58check(version || hash160(compressed pub)) — MAINNET pin. */
    public static String address(Bip32.Node key) {
        return address(key, NetworkParams.MAINNET);
    }

    /** base58check(params.pubkeyVersion || hash160(compressed pub)). */
    public static String address(Bip32.Node key, NetworkParams params) {
        byte[] h160 = Base58Check.hash160(key.pub());
        byte[] payload = new byte[21];
        payload[0] = (byte) params.pubkeyVersion;
        System.arraycopy(h160, 0, payload, 1, 20);
        return Base58Check.encode(payload);
    }

    /** base58check(0xE0 || priv32 || 0x01) — MAINNET pin. */
    public static String wif(Bip32.Node key) {
        return wif(key, NetworkParams.MAINNET);
    }

    /** base58check(params.wifVersion || priv32 || 0x01). */
    public static String wif(Bip32.Node key, NetworkParams params) {
        byte[] payload = new byte[34];
        payload[0] = (byte) params.wifVersion;
        System.arraycopy(Secp256k1.toFixed(key.priv, 32), 0, payload, 1, 32);
        payload[33] = 0x01; // compressed
        return Base58Check.encode(payload);
    }

    /** True when addr decodes as a 21-byte base58check P2PKH payload whose
     *  version byte matches params. Never throws on malformed input. */
    public static boolean isNetworkAddress(String addr, NetworkParams params) {
        byte[] payload;
        try {
            payload = Base58Check.decode(addr);
        } catch (RuntimeException e) {
            return false;
        }
        return payload.length == 21
                && (payload[0] & 0xFF) == params.pubkeyVersion;
    }

    /** Legacy P2PKH scriptPubKey: 76 a9 14 <hash160(pub)> 88 ac. */
    public static byte[] p2pkhScript(Bip32.Node key) {
        return p2pkhScriptForHash(Base58Check.hash160(key.pub()));
    }

    public static byte[] p2pkhScriptForHash(byte[] h160) {
        byte[] out = new byte[25];
        out[0] = (byte) 0x76;
        out[1] = (byte) 0xA9;
        out[2] = (byte) 0x14;
        System.arraycopy(h160, 0, out, 3, 20);
        out[23] = (byte) 0x88;
        out[24] = (byte) 0xAC;
        return out;
    }
}
