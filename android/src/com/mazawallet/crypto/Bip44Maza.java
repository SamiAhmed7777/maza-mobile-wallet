package com.mazawallet.crypto;

/**
 * BIP44 for MAZA (SLIP-44 coin type 13): m/44'/13'/0'/<chain>/<index>,
 * address version byte 50 (0x32) -> "M..." base58check of hash160(pub),
 * WIF version byte 224 (0xE0) with 0x01 compressed suffix. P2PKH only.
 * No android deps.
 */
public final class Bip44Maza {

    public static final int COIN_TYPE = 13;
    public static final int ADDRESS_VERSION = 50;   // 0x32 -> "M..."
    public static final int WIF_VERSION = 224;      // 0xE0
    public static final int RECEIVE_CHAIN = 0;
    public static final int CHANGE_CHAIN = 1;
    public static final int GAP_LIMIT = 20;

    private Bip44Maza() {}

    /** m/44'/13'/0' account node from a BIP39 seed. */
    public static Bip32.Node accountNode(byte[] seed) {
        return Bip32.derive(Bip32.masterKey(seed),
                "m/44'/" + COIN_TYPE + "'/0'");
    }

    /** Key at m/44'/13'/0'/<chain>/<index>. */
    public static Bip32.Node keyAt(Bip32.Node account, int chain, int index) {
        return Bip32.derive(account, chain + "/" + index);
    }

    /** base58check(version || hash160(compressed pubkey)). */
    public static String address(Bip32.Node key) {
        byte[] h160 = Base58Check.hash160(key.pub());
        byte[] payload = new byte[21];
        payload[0] = (byte) ADDRESS_VERSION;
        System.arraycopy(h160, 0, payload, 1, 20);
        return Base58Check.encode(payload);
    }

    /** base58check(0xE0 || priv32 || 0x01). */
    public static String wif(Bip32.Node key) {
        byte[] payload = new byte[34];
        payload[0] = (byte) WIF_VERSION;
        System.arraycopy(Secp256k1.toFixed(key.priv, 32), 0, payload, 1, 32);
        payload[33] = 0x01; // compressed
        return Base58Check.encode(payload);
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
