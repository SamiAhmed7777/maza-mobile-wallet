package com.mazawallet.crypto;

/**
 * MAZA network parameters (S-6 testnet mode, code half).
 *
 * Every value here is FETCHED from MazaCore v0.16.3 source
 * (github.com/MazaCoin/maza tag v0.16.3, src/chainparams.cpp) — never
 * memorized, never adjusted to make code pass:
 *   MAINNET  CMainParams   : pubkey 50, script 9, wif 224, hrp "maza"
 *                            (chainparams.cpp:171-173, bech32 :177)
 *   TESTNET  CTestNetParams: pubkey 88, script 188, wif 239, hrp "tmaza"
 *                            (chainparams.cpp:297-299, bech32 :303,
 *                             strNetworkID "test" at :211)
 * The testnet address vector set pinned in SelfTest.mazaTestnetChecks is
 * node-validated: the samihost testnet mazad (chain=test) validateaddress
 * returns isvalid=true for every pinned testnet address and isvalid=false
 * for the pinned mainnet ones (cross-network negative control).
 *
 * MAINNET is the fail-safe default for every existing call path: the
 * un-parameterized Bip44Maza.address/wif and ScanOrigin.parse methods keep
 * pinning MAINNET until a caller EXPLICITLY passes TESTNET. There is no
 * global mutable mode anywhere in the crypto layer — network selection is
 * a parameter the UI layer must thread deliberately (S-6: the Settings
 * NETWORK card selects it; every consumer resolves it through
 * NetworkSetting.resolve).
 *
 * Pure Java, no android imports: desktop SelfTest drives every row.
 */
public final class NetworkParams {

    /** MazaCore CMainParams (chainparams.cpp:171-177). */
    public static final NetworkParams MAINNET =
            new NetworkParams(50, 9, 224, "maza", "main");

    /** MazaCore CTestNetParams (chainparams.cpp:211, 297-303). */
    public static final NetworkParams TESTNET =
            new NetworkParams(88, 188, 239, "tmaza", "test");

    public final int pubkeyVersion;   // base58Prefixes[PUBKEY_ADDRESS]
    public final int scriptVersion;   // base58Prefixes[SCRIPT_ADDRESS]
    public final int wifVersion;      // base58Prefixes[SECRET_KEY] (WIF)
    public final String bech32Hrp;    // bech32_hrp
    public final String id;           // strNetworkID

    private NetworkParams(int pubkeyVersion, int scriptVersion,
                          int wifVersion, String bech32Hrp, String id) {
        this.pubkeyVersion = pubkeyVersion;
        this.scriptVersion = scriptVersion;
        this.wifVersion = wifVersion;
        this.bech32Hrp = bech32Hrp;
        this.id = id;
    }

    /** True only for the MAINNET singleton. */
    public boolean isMainnet() {
        return this == MAINNET;
    }

    /** Resolve a persisted network id; UNKNOWN ids FAIL LOUD — there is
     *  no silent mainnet fallback for a stored value nobody wrote. */
    public static NetworkParams forId(String id) {
        if (MAINNET.id.equals(id)) return MAINNET;
        if (TESTNET.id.equals(id)) return TESTNET;
        throw new IllegalArgumentException("unknown network id: " + id);
    }
}
