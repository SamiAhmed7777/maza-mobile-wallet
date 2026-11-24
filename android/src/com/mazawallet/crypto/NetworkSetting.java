package com.mazawallet.crypto;

/**
 * Network SELECTION contract for S-6-ii (testnet switch, core half).
 *
 * S-6-i shipped the parameter threading (NetworkParams/Bip44Maza overloads,
 * fail-loud forId, no global mutable mode in crypto). This class is the UI
 * layer's single source of truth for the SHARED-PREFERENCES contract that
 * carries the selection:
 *
 *   KEY_NETWORK      stored network id ("main" | "test"), read through
 *                    resolve() - null/absent resolves to MAINNET (fail-safe
 *                    default for every existing install), anything else
 *                    resolves via NetworkParams.forId which THROWS on an
 *                    unknown id (no silent fallback for a value nobody
 *                    wrote - same contract as NetworkParams.forId).
 *   KEY_URL_MAINNET  endpoint for the mainnet bench backend (the public
 *                    test front door; value owned by the UI layer).
 *   KEY_URL_TESTNET  endpoint for a testnet walletbench backend. There is
 *                    NO public testnet endpoint (that exposure decision is
 *                    Payu-gated and NOT taken), so the UI layer defaults
 *                    this to EMPTY - a testnet connection must be
 *                    configured explicitly (controlled-env posture).
 *
 * SETTINGS-SIDE WRITER (S-6-ii-b): the Settings NETWORK card is the ONLY
 * code in the app that WRITES KEY_NETWORK (commit-persisted; pinned by
 * tests/test_network_switch_core.py's settings-only-write walk). Every
 * other surface reads the selection through resolve() and follows it:
 * per-network endpoint keys, the resume reconnect guard, and the scan
 * consumer all resolve the ACTIVE network.
 *
 * Pure Java, no android imports: desktop SelfTest drives every row.
 */
public final class NetworkSetting {

    public static final String KEY_NETWORK = "network";
    public static final String KEY_URL_MAINNET = "url";
    public static final String KEY_URL_TESTNET = "url_testnet";

    private NetworkSetting() {}

    /** Resolve a persisted network id. null/empty -> MAINNET (fail-safe
     *  default; every pre-switch install has no network key at all).
     *  Unknown ids THROW (NetworkParams.forId) - a corrupted prefs store
     *  must surface, not silently mainnet. */
    public static NetworkParams resolve(String storedId) {
        if (storedId == null || storedId.length() == 0) {
            return NetworkParams.MAINNET;
        }
        return NetworkParams.forId(storedId);
    }

    /** Which shared-prefs key carries the endpoint for this network.
     *  The VALUES are the UI layer's (defaults live where DEFAULT_URL
     *  lives); only the key contract is pinned here. */
    public static String urlPrefKey(NetworkParams params) {
        return params.isMainnet() ? KEY_URL_MAINNET : KEY_URL_TESTNET;
    }
}
