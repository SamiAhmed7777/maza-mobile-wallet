#!/usr/bin/env python3
"""Wiring contract for S-6-i: MAZA network parameters (testnet code half).

The decision MATH (every testnet/mainnet vector) is covered BEHAVIORALLY in
crypto/SelfTest.java's "MAZA testnet profile" section — 15 checks driving
NetworkParams + Bip44Maza overloads + ScanOrigin.parseForNetwork on the
desktop JVM, with values node-validated against the samihost testnet mazad.

This file pins what SelfTest cannot: the source shape (NetworkParams
carries ONLY the fetched chainparams constants with citations; fail-loud
forId; NO global mutable network mode anywhere), the fail-safe delegation
(the UN-parameterized Bip44Maza/ScanOrigin entry points stay MAINNET-pinned
so no existing call path silently moves networks), and the doc honesty
(DECISIONS D18 + SPEC-AUDIT carry the same constants as the code).
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRYPTO = os.path.join(REPO, "android", "src", "com", "mazawallet", "crypto")
NP = os.path.join(CRYPTO, "NetworkParams.java")
B44 = os.path.join(CRYPTO, "Bip44Maza.java")
SCAN = os.path.join(CRYPTO, "ScanOrigin.java")
SELFTEST = os.path.join(CRYPTO, "SelfTest.java")
DECISIONS = os.path.join(REPO, "DECISIONS.md")
AUDIT = os.path.join(REPO, "docs", "SPEC-AUDIT.md")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestNetworkParamsSource(unittest.TestCase):
    def test_constants_are_fetched_with_citations(self):
        src = read(NP)
        # the five testnet constants exactly as fetched from
        # MazaCore v0.16.3 chainparams.cpp CTestNetParams
        self.assertIn("new NetworkParams(88, 188, 239, \"tmaza\", \"test\")",
                      src)
        # the five mainnet constants (CMainParams)
        self.assertIn("new NetworkParams(50, 9, 224, \"maza\", \"main\")",
                      src)
        # provenance citations present (never memorized values)
        self.assertIn("chainparams.cpp", src)
        self.assertIn("CTestNetParams", src)
        self.assertIn("v0.16.3", src)

    def test_for_id_fails_loud_no_silent_fallback(self):
        src = read(NP)
        self.assertIn("throw new IllegalArgumentException", src)
        self.assertIn("unknown network id", src)

    def test_no_global_mutable_mode(self):
        # the class must carry no mutable static state: every field final,
        # no setter-shaped methods, singletons only
        src = read(NP)
        for f in ("pubkeyVersion", "scriptVersion", "wifVersion",
                  "bech32Hrp", "id"):
            self.assertRegex(src, r"public final (int|String) %s;" % f)
        self.assertNotIn("public static void set", src)


class TestFailSafeDelegation(unittest.TestCase):
    def test_bip44_mainnet_pins_unchanged_signatures(self):
        src = read(B44)
        # the un-parameterized entry points still exist and pin MAINNET
        self.assertIn("public static String address(Bip32.Node key) {",
                      src)
        self.assertIn("public static String wif(Bip32.Node key) {", src)
        self.assertIn("return address(key, NetworkParams.MAINNET);", src)
        self.assertIn("return wif(key, NetworkParams.MAINNET);", src)
        # named mainnet constants now derive from the single source of truth
        self.assertIn("ADDRESS_VERSION = NetworkParams.MAINNET.pubkeyVersion",
                      src)
        self.assertIn("WIF_VERSION = NetworkParams.MAINNET.wifVersion", src)
        # derivation path is network-independent (coin 13, unchanged)
        self.assertIn('"m/44\'/" + COIN_TYPE + "\'/0\'"', src)

    def test_network_aware_overloads_exist(self):
        src = read(B44)
        self.assertIn("public static String address(Bip32.Node key, "
                      "NetworkParams params)", src)
        self.assertIn("public static String wif(Bip32.Node key, "
                      "NetworkParams params)", src)
        self.assertIn("public static boolean isNetworkAddress(String addr, "
                      "NetworkParams params)", src)
        # isNetworkAddress never throws on malformed input
        self.assertIn("catch (RuntimeException e)", src)

    def test_scanorigin_parse_stays_mainnet_pinned(self):
        src = read(SCAN)
        # public parse() delegates to the MAINNET contract
        self.assertIn("public static Result parse(String scanned) {", src)
        self.assertIn("return parseForNetwork(scanned, NetworkParams.MAINNET);",
                      src)
        # the network-aware variant validates against params, not a constant
        self.assertIn("(payload[0] & 0xFF) != params.pubkeyVersion", src)
        # the OLD constant-pin shape is gone (no double source of truth)
        self.assertNotIn("!= Bip44Maza.ADDRESS_VERSION", src)

    def test_no_caller_threads_testnet_yet(self):
        # S-6-i ships NO user-visible testnet surface: NO file in the app
        # package (com.mazawallet, outside the crypto/ primitives and the
        # vector-pinning SelfTest) may reference TESTNET or NetworkParams
        # until the Settings/endpoint half lands (S-6-ii). Repo-wide walk,
        # not a hand-list, so the pin holds as files are added.
        app_root = os.path.join(REPO, "android", "src", "com", "mazawallet")
        crypto_root = os.path.join(app_root, "crypto")
        offenders = []
        for dirpath, _dirnames, filenames in os.walk(app_root):
            if dirpath.startswith(crypto_root):
                continue  # the primitives themselves own the parameter
            for name in filenames:
                if not name.endswith(".java"):
                    continue
                with open(os.path.join(dirpath, name),
                          encoding="utf-8") as f:
                    body = f.read()
                if "TESTNET" in body or "NetworkParams" in body:
                    offenders.append(os.path.relpath(
                        os.path.join(dirpath, name), app_root))
        self.assertEqual(
            [], offenders,
            "app-package files must stay network-blind until S-6-ii: %s"
            % offenders)


class TestVectorAndDocHonesty(unittest.TestCase):
    def test_selftest_pins_the_node_validated_set(self):
        src = read(SELFTEST)
        self.assertIn("MAZA testnet profile", src)
        for addr in ("cdYDYkC2r7jqcZquHojyCbYP1sMapXBSLU",
                     "cRaRQX9vwtteR8zsdUgnDcBoFqd5PJ6WSS",
                     "cZd627rrUWfH1iUwRDhgSwAkuoAw6mi7wN"):
            self.assertIn(addr, src)
        self.assertIn("parse() rejects testnet addr on mainnet", src)
        self.assertIn("forId: round-trips both, FAILS LOUD on unknown", src)

    def test_decisions_d18_matches_code_constants(self):
        src = read(DECISIONS)
        self.assertIn("## D18", src)
        self.assertIn("| testnet | 88 | 188 | 239 | tmaza | test |", src)
        self.assertIn("| mainnet | 50 | 9 | 224 | maza | main |", src)
        self.assertIn("chainparams.cpp:171-173", src)
        self.assertIn("CTestNetParams", src)

    def test_spec_audit_row_updated(self):
        src = read(AUDIT)
        self.assertIn("CODE HALF DONE 2026-11-23 (S-6-i", src)
        self.assertIn("REMAINING (S-6-ii)", src)


if __name__ == "__main__":
    unittest.main()
