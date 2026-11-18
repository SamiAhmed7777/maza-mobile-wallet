#!/usr/bin/env python3
"""Wiring contract for M9: the maza: payment-URI contract (MazaUri).

The decision MATH (every accepted/rejected URI shape, both documented
divergences, format + round-trip) is covered BEHAVIORALLY in
crypto/SelfTest.java mazaUriChecks() — 41 checks on the desktop JVM.

This file pins what SelfTest cannot: the official-source provenance
class cites (MazaCoin guiutil.cpp / bitcoinunits.cpp — the contract was
ported from fetched sources, never from memory), the scan-side routing
(ScanOrigin delegates to MazaUri and still re-validates the address
through the send-path base58check contract), the SEND-field amount
wiring in MainActivity, the documented upstream divergences, and the
docs honesty (no stale "fail-closed until M9" claims anywhere).
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAZA_URI = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "MazaUri.java")
SCAN_ORIGIN = os.path.join(REPO, "android", "src", "com", "mazawallet",
                           "crypto", "ScanOrigin.java")
SELFTEST = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "SelfTest.java")
MAIN = os.path.join(REPO, "android", "src", "com", "mazawallet",
                    "MainActivity.java")
DECISIONS = os.path.join(REPO, "DECISIONS.md")
SECURITY = os.path.join(REPO, "docs", "SECURITY.md")
DEP_LIC = os.path.join(REPO, "docs", "DEPENDENCY-LICENSES.md")
SPEC_AUDIT = os.path.join(REPO, "docs", "SPEC-AUDIT.md")
USER_GUIDE = os.path.join(REPO, "docs", "user-guide.md")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class MazaUriPurity(unittest.TestCase):
    def test_pure_java_no_android_no_zxing_no_network(self):
        src = read(MAZA_URI)
        imports = [ln.strip() for ln in src.splitlines()
                   if ln.strip().startswith("import ")]
        self.assertTrue(imports, "standard imports present")
        for imp in imports:
            self.assertFalse(imp.startswith("import android"),
                             "no android imports: %s" % imp)
            self.assertFalse("zxing" in imp, "no zxing imports: %s" % imp)
            self.assertFalse("java.net" in imp,
                             "no networking imports: %s" % imp)
            self.assertFalse("java.io" in imp,
                             "no filesystem imports: %s" % imp)
        self.assertNotIn("URL", src.replace("URLs", "").replace("URI", ""),
                         "no URL/fetch machinery in the parser")
        self.assertNotIn("Http", src)

    def test_official_source_provenance_cited(self):
        """The contract must cite the fetched MazaCoin sources with file
        and line anchors - never a from-memory shape."""
        src = read(MAZA_URI)
        self.assertIn("src/qt/guiutil.cpp", src)
        self.assertIn("src/qt/bitcoinunits.cpp:144-181", src)
        self.assertIn("parseBitcoinURI", src)
        self.assertIn("formatBitcoinURI", src)
        self.assertIn("removeSpaces", src)

    def test_official_contract_constants(self):
        src = read(MAZA_URI)
        self.assertIn("AMOUNT_DECIMALS = 8", src)
        self.assertIn("MAX_AMOUNT_DIGITS = 18", src)
        self.assertIn("SATS_PER_MAZA = 100_000_000L", src)

    def test_both_documented_divergences_present(self):
        """D14 divergences: the upstream maza:// replace(0, 11, ...)
        slicing bug (we strip the exact 7-char prefix) and digits-only
        amounts (upstream toLongLong accepts a sign)."""
        src = read(MAZA_URI)
        self.assertIn("replace(0, 11", src,
                      "upstream slicing bug documented")
        self.assertIn("substring(7)", src, "exact 7-char prefix strip")
        self.assertIn("toLongLong", src, "signed-amount divergence cited")
        self.assertIn("digits-only", src.lower())
        # signed amounts are structurally impossible: the digit loop
        # rejects everything outside '0'..'9'
        self.assertIn("c < '0' || c > '9'", src)


class ScanSideRouting(unittest.TestCase):
    def test_scan_origin_delegates_to_maza_uri(self):
        src = read(SCAN_ORIGIN)
        self.assertIn("MazaUri.Parsed p = MazaUri.parse(s);", src,
                      "maza: payloads go through the M9 parser")
        self.assertIn("addressResult(p.address, p.amountSats)", src,
                      "the parsed address re-validates through the "
                      "send-path base58check contract")
        self.assertNotIn("URI parameters are not supported yet", src,
                         "the M8a fail-closed placeholder is gone")
        self.assertNotIn("REJECTED until M9", src)

    def test_scan_result_carries_amount(self):
        src = read(SCAN_ORIGIN)
        self.assertIn("public final long amountSats;", src)

    def test_main_activity_fills_the_amount_field(self):
        src = read(MAIN)
        self.assertIn("import com.mazawallet.crypto.MazaUri;", src)
        self.assertIn("MazaUri.formatAmount(r.amountSats)", src)
        self.assertIn("amountEt.setText", src,
                      "a scanned amount prefills the SEND amount field")
        self.assertIn("nothing is ever auto-sent from a scan", src,
                      "prefill-only guard documented at the fill site")

    def test_selftest_drives_the_contract(self):
        src = read(SELFTEST)
        self.assertIn("private static void mazaUriChecks()", src)
        self.assertIn("mazaUriChecks();", src,
                      "runner invokes the MazaUri checks")
        self.assertNotIn("rejected until M9", src,
                         "stale M8a-era row flipped")


class DocsHonesty(unittest.TestCase):
    def test_decisions_d14_documents_the_contract(self):
        src = read(DECISIONS)
        self.assertIn("## D14", src)
        self.assertIn("guiutil.cpp", src)
        self.assertIn("replace(0, 11", src)
        self.assertIn("toLongLong", src)

    def test_no_stale_fail_closed_until_m9_claims_anywhere(self):
        for path in (SECURITY, DEP_LIC):
            src = read(path)
            self.assertNotIn("fail-closed until M9", src,
                             "%s still claims the M8a placeholder" % path)

    def test_security_documents_the_parsed_params_policy(self):
        src = read(SECURITY)
        self.assertIn("req-", src, "req-* rejection documented")
        self.assertIn("never fetched", src)

    def test_spec_audit_names_the_m9_code_half(self):
        src = read(SPEC_AUDIT)
        self.assertIn("M9", src)
        self.assertIn("MazaUri", src)

    def test_user_guide_honest_about_scope(self):
        src = read(USER_GUIDE)
        self.assertIn("maza:", src, "payment-URI scan documented")
        # M9-ii shipped: the guide must DOCUMENT the request screen (not
        # list it as pending any more) and keep the display-only scope.
        self.assertIn("Show payment QR", src,
                      "receive request screen documented as shipped")
        self.assertNotIn("Request-amount\n  receive screen", src,
                         "no stale 'pending' wording left")


if __name__ == "__main__":
    unittest.main()
