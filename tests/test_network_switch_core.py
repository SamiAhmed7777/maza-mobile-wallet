#!/usr/bin/env python3
"""Wiring contract for S-6-ii switch CORE (zero behavior change).

S-6-i shipped the crypto parameter threading; S-6-ii-a (this change) threads
the ACTIVE network through the UI layer: crypto/NetworkSetting.java is the
prefs contract, MainActivity resolves it (activeNetwork/endpointUrlFor) and
SelfCustody encodes/validates every address for host.network(). NOTHING
WRITES the network key yet - the Settings switch UI lands in the S-6-ii
second half together with its own gate review, so every install today
resolves MAINNET exactly as before (the fail-safe default). The decision
MATH is behaviorally covered in SelfTest's S-6-ii switch-core section
(desktop JVM, riding the node-validated testnet anchors from S-6-i).

This file pins what SelfTest cannot: the source shape - the key contract is
single-sourced in NetworkSetting, the send guard uses the ACTIVE version
byte (never the mainnet constant), SelfCustody has NO un-parameterized
address-encoding call site left, MainActivity never persists a network id
(no user-visible switch exists yet), and NetworkSetting stays android-free.
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "android", "src", "com", "mazawallet")
CRYPTO = os.path.join(APP, "crypto")
NS = os.path.join(CRYPTO, "NetworkSetting.java")
MACT = os.path.join(APP, "MainActivity.java")
SC = os.path.join(APP, "SelfCustody.java")
SELFTEST = os.path.join(CRYPTO, "SelfTest.java")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestNetworkSettingShape(unittest.TestCase):
    def test_pure_android_free_final(self):
        src = read(NS)
        self.assertNotIn("import android", src)
        self.assertIn("public final class NetworkSetting {", src)
        self.assertIn("private NetworkSetting() {}", src)

    def test_key_contract_single_sourced(self):
        src = read(NS)
        self.assertIn('KEY_NETWORK = "network"', src)
        self.assertIn('KEY_URL_MAINNET = "url"', src)
        self.assertIn('KEY_URL_TESTNET = "url_testnet"', src)

    def test_resolve_fail_safe_default_fail_loud_unknown(self):
        src = read(NS)
        # null/absent -> MAINNET (every pre-switch install)
        self.assertIn("if (storedId == null || storedId.length() == 0) {",
                      src)
        self.assertIn("return NetworkParams.MAINNET;", src)
        # unknown ids delegate to the fail-loud forId (no silent fallback)
        self.assertIn("return NetworkParams.forId(storedId);", src)

    def test_endpoint_keys_per_network(self):
        src = read(NS)
        self.assertIn("return params.isMainnet() ? KEY_URL_MAINNET "
                      ": KEY_URL_TESTNET;", src)


class TestMainActivityPlumbing(unittest.TestCase):
    def test_no_duplicate_url_key_constant(self):
        src = read(MACT)
        # the mainnet key is ALIASED from NetworkSetting (no second source)
        self.assertIn("static final String KEY_URL = "
                      "NetworkSetting.KEY_URL_MAINNET;", src)
        self.assertNotIn('static final String KEY_URL = "url";', src)

    def test_active_network_helpers_present(self):
        src = read(MACT)
        self.assertIn("private NetworkParams activeNetwork() {", src)
        self.assertIn("prefs.getString(NetworkSetting.KEY_NETWORK, null)",
                      src)
        self.assertIn("private String endpointUrlFor(NetworkParams net) {",
                      src)
        # testnet endpoint default is EMPTY (no public testnet endpoint;
        # exposure decision Payu-gated, NOT taken)
        self.assertIn('String def = net.isMainnet() ? DEFAULT_URL : "";',
                      src)

    def test_host_network_impl(self):
        src = read(MACT)
        self.assertIn("public NetworkParams network() {", src)
        self.assertIn("return activeNetwork();", src)

    def test_network_key_never_written(self):
        # THE zero-behavior-change pin: nothing in the app package may
        # persist a network id until the Settings switch UI + its gate
        # review land (S-6-ii second half). Walk every app file, crypto
        # included (crypto owns no prefs writes either).
        offenders = []
        for dirpath, _dirnames, filenames in os.walk(APP):
            for name in filenames:
                if not name.endswith(".java"):
                    continue
                body = read(os.path.join(dirpath, name))
                if "putString(NetworkSetting.KEY_NETWORK" in body:
                    offenders.append(os.path.relpath(
                        os.path.join(dirpath, name), APP))
        self.assertEqual(
            [], offenders,
            "no code may WRITE the network key before the Settings switch "
            "lands (S-6-ii second half): %s" % offenders)


class TestSelfCustodyThreading(unittest.TestCase):
    def test_host_contract_declares_network(self):
        src = read(SC)
        self.assertIn("NetworkParams network();", src)
        self.assertIn("private NetworkParams net() {", src)
        self.assertIn("return host.network();", src)

    def test_no_unparameterized_address_encoding_left(self):
        src = read(SC)
        # every old MAINNET-pinned shape is gone from the six call sites
        for old in ("Bip44Maza.address(keyAt(chain, i)).equals",
                    "Bip44Maza.address(keyAt(Bip44Maza.RECEIVE_CHAIN, "
                    "recvIndex))",
                    "Bip44Maza.address(changeKey);",
                    "out.add(Bip44Maza.address(keyAt(chain, i)));",
                    "Bip44Maza.address(keyAt(Bip44Maza.RECEIVE_CHAIN, "
                    "idx))"):
            self.assertNotIn(old, src)
        # the send guard validates against the ACTIVE version byte
        self.assertIn("!= net().pubkeyVersion", src)
        self.assertNotIn("!= Bip44Maza.ADDRESS_VERSION", src)

    def test_selftest_pins_the_switch_core(self):
        src = read(SELFTEST)
        self.assertIn("networksetting: null/absent resolves MAINNET",
                      src)
        self.assertIn("networksetting: stored ids resolve both networks",
                      src)
        self.assertIn("networksetting: unknown id FAILS LOUD", src)
        self.assertIn("networksetting: endpoint keys per network", src)
        self.assertIn("networksetting composition", src)


if __name__ == "__main__":
    unittest.main()
