#!/usr/bin/env python3
"""Wiring contract for S-6-ii (testnet switch): core + Settings UI halves.

S-6-i shipped the crypto parameter threading; S-6-ii-a threaded the ACTIVE
network through the UI layer (crypto/NetworkSetting.java prefs contract,
MainActivity activeNetwork()/endpointUrlFor(), SelfCustody encodes/validates
every address for host.network()); S-6-ii-b (this change) ships the
user-visible surface: the Settings NETWORK card (the ONLY writer of the
network key, commit()-persisted), per-network endpoint prefill/persistence on
the Connect card and the SERVER card, the reconnect guard (a network switch
made in Settings drops the session to the OLD backend on resume), and the
scan consumer threading (ScanOrigin validates against the ACTIVE version
byte). The decision MATH stays behaviorally covered in SelfTest's S-6-ii
switch-core section (desktop JVM, riding the node-validated testnet anchors
from S-6-i).

This file pins what SelfTest cannot: the source shape - the key contract is
single-sourced in NetworkSetting, the send guard uses the ACTIVE version
byte (never the mainnet constant), SelfCustody has NO un-parameterized
address-encoding call site left, ONLY SettingsActivity writes the network
key, and NetworkSetting stays android-free.
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(REPO, "android", "src", "com", "mazawallet")
CRYPTO = os.path.join(APP, "crypto")
NS = os.path.join(CRYPTO, "NetworkSetting.java")
MACT = os.path.join(APP, "MainActivity.java")
SC = os.path.join(APP, "SelfCustody.java")
SA = os.path.join(APP, "SettingsActivity.java")
STRINGS = os.path.join(REPO, "android", "res", "values", "strings.xml")
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

    def test_network_key_written_by_settings_only(self):
        # S-6-ii-b contract: the Settings switch UI is the ONLY writer of
        # the network key in the whole app package (crypto included -
        # crypto owns no prefs writes either). Every OTHER file carrying a
        # write shape is an offender; Settings MUST carry it.
        offenders = []
        settings_has_write = False
        for dirpath, _dirnames, filenames in os.walk(APP):
            for name in filenames:
                if not name.endswith(".java"):
                    continue
                body = read(os.path.join(dirpath, name))
                if "putString(NetworkSetting.KEY_NETWORK" not in body:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), APP)
                if rel == "SettingsActivity.java":
                    settings_has_write = True
                else:
                    offenders.append(rel)
        self.assertEqual(
            [], offenders,
            "only SettingsActivity may WRITE the network key: %s" % offenders)
        self.assertTrue(
            settings_has_write,
            "SettingsActivity must own the network-key write (the switch)")

    def test_connect_card_serves_active_network(self):
        src = read(MACT)
        # Connect prefill: per-network saved endpoint (never the mainnet key)
        self.assertIn("final NetworkParams connectNet = activeNetwork();", src)
        self.assertIn("urlEt = input(endpointUrlFor(connectNet),", src)
        self.assertNotIn("input(prefs.getString(KEY_URL, DEFAULT_URL),", src)
        # the card NAMES the network (separate services, separate books)
        self.assertIn('"Network: MAZA mainnet"', src)
        self.assertIn('"Network: MAZA testnet (controlled environment)"', src)

    def test_unlock_binds_session_and_persists_per_network(self):
        src = read(MACT)
        # session identity captured at unlock success (NetworkParams.id is a
        # public final FIELD - the compiled shape, not a getter)
        self.assertIn("sessionNetId = activeNetwork().id;", src)
        # the typed URL persists under THAT network's endpoint key
        self.assertIn("NetworkSetting.urlPrefKey(activeNetwork()),\n"
                      "                            url).apply();", src)
        # the legacy unconditional mainnet-key write is gone
        self.assertNotIn("prefs.edit().putString(KEY_URL, url).apply();", src)
        # the session drop point clears the identity too
        self.assertIn("sessionNetId = null;", src)

    def test_resume_guard_drops_switched_session(self):
        src = read(MACT)
        self.assertIn("private boolean sessionNetworkChanged() {", src)
        self.assertIn("|| !activeNetwork().id.equals(sessionNetId);", src)
        # the guard runs in onResume BEFORE the lock decisions and drops the
        # session through showConnect (mirrors the session-expired path)
        guard_at = src.find("if (token != null && sessionNetworkChanged()) {")
        self.assertGreater(guard_at, 0, "resume guard call site missing")
        relock_at = src.find("pinGuard.onResumeLocked()")
        self.assertGreater(relock_at, guard_at,
                           "guard must run BEFORE the lock overlay decisions")
        self.assertIn("showConnect(getString(R.string.net_network_switched));",
                      src)
        # fail-safe: a session with no recorded id counts as changed
        self.assertIn("return sessionNetId == null", src)

    def test_scan_consumer_threaded_to_active_network(self):
        src = read(MACT)
        self.assertIn(
            "ScanOrigin.parseForNetwork(payloadText, activeNetwork());", src)
        # the mainnet-pinned consumer call is gone
        self.assertNotIn("ScanOrigin.parse(payloadText);", src)


class TestSettingsActivitySwitch(unittest.TestCase):
    def test_switch_persists_with_commit_discipline(self):
        src = read(SA)
        # the ONLY network-key write in the app, commit()-persisted (the
        # durable write lands before the UI reflects it)
        self.assertIn("putString(NetworkSetting.KEY_NETWORK, netId).commit();",
                      src)
        # a failed commit aborts the UI update (toast, no re-render)
        self.assertIn("if (!persisted) {", src)
        self.assertIn("getString(R.string.network_save_failed)", src)

    def test_switch_uses_networksetting_contract(self):
        src = read(SA)
        self.assertIn("private NetworkParams activeNetwork() {", src)
        self.assertIn("NetworkSetting.resolve(\n"
                      "                prefs.getString(NetworkSetting"
                      ".KEY_NETWORK, null))", src)
        # ids come from NetworkParams (never literals)
        self.assertIn("NetworkParams.MAINNET.id", src)
        self.assertIn("NetworkParams.TESTNET.id", src)
        self.assertNotIn('"main"', src)
        self.assertNotIn('"test"', src)

    def test_endpoint_card_is_per_network(self):
        src = read(SA)
        # prefill + save both go through the ACTIVE network's endpoint key
        self.assertIn("urlEt = input(savedEndpointForActiveNetwork(),", src)
        self.assertIn("NetworkSetting.urlPrefKey(activeNetwork()), "
                      "url).apply();", src)
        self.assertNotIn("putString(MainActivity.KEY_URL,", src)
        # the endpoint card re-points when the network switches
        self.assertIn("private void refreshEndpointCard() {", src)
        self.assertIn("renderNetwork();\n        refreshEndpointCard();", src)
        # testnet default EMPTY (no public testnet endpoint exists)
        self.assertIn('net.isMainnet() ? MainActivity.DEFAULT_URL : ""', src)

    def test_network_card_present_with_strings(self):
        src = read(SA)
        self.assertIn("R.string.settings_network", src)
        self.assertIn("R.string.network_mainnet", src)
        self.assertIn("R.string.network_testnet", src)
        self.assertIn("R.string.settings_network_note", src)
        st = read(STRINGS)
        for name in ("settings_network", "network_mainnet",
                     "network_testnet", "settings_network_note",
                     "network_save_failed", "net_network_switched"):
            self.assertIn('name="%s"' % name, st)


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
