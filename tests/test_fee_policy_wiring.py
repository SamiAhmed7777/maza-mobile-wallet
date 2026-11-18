#!/usr/bin/env python3
"""Wiring contract for M10: size-based self-custody send fees.

The MATH lives where it is executed:
  - crypto/FeePolicy.java is driven on the desktop JVM by
    crypto/SelfTest.java feePolicyChecks() (22 rows: the fetched
    upstream constants, CFeeRate truncating-division semantics, the
    fee-for-size chain, the 546-sat dust threshold).

This file pins the WIRING the SelfTest cannot see: FeePolicy purity,
the upstream citation trail (every constant names its fetched file/line),
the flat FEE_SATS constant being GONE from SelfCustody, the fee<->size
fixpoint loop, the dust-change fold (MazaCore never creates a dust
change output), the fee display being per-tx (no flat-fee claim), the
bench edition fee staying untouched (walletbench FLAT_FEE + MainActivity
server-side fee rows), the spend POSTs staying pinned at exactly one
attempt, and the docs honesty (DECISIONS D4 + user-guide send row).
"""
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEE_POLICY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                          "crypto", "FeePolicy.java")
SELFTEST = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "SelfTest.java")
CUSTODY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                       "SelfCustody.java")
MAIN = os.path.join(REPO, "android", "src", "com", "mazawallet",
                    "MainActivity.java")
NET = os.path.join(REPO, "android", "src", "com", "mazawallet", "Net.java")
BENCH_API = os.path.join(REPO, "walletbench", "api.py")
DECISIONS = os.path.join(REPO, "DECISIONS.md")
USER_GUIDE = os.path.join(REPO, "docs", "user-guide.md")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class FeePolicyPurity(unittest.TestCase):
    """FeePolicy: pure math class, no Android imports."""

    def setUp(self):
        self.src = read(FEE_POLICY)

    def test_no_android_imports(self):
        self.assertNotIn("import android", self.src)

    def test_no_network_or_io(self):
        for banned in ("java.net", "java.io", "java.nio", "JSONObject",
                       "HttpURLConnection", "java.util.ArrayList"):
            self.assertNotIn(banned, self.src)

    def test_top_level_final_no_platform_supertype(self):
        # d8 nested-class rule: platform-supertype nested classes are
        # unbuildable; FeePolicy is a plain final utility class.
        self.assertIn("public final class FeePolicy", self.src)
        self.assertNotIn("extends", self.src.split("public final class")[1])


class UpstreamCitations(unittest.TestCase):
    """Every constant names the fetched upstream file:line (never memory)."""

    def setUp(self):
        self.src = read(FEE_POLICY)

    def test_fallback_rate_cited(self):
        self.assertIn("wallet.h:49", self.src)
        self.assertIn("FALLBACK_RATE_PER_K = 10000", self.src)

    def test_min_relay_cited(self):
        self.assertIn("validation.h:53", self.src)
        self.assertIn("MIN_RELAY_RATE_PER_K = 1000", self.src)

    def test_dust_rate_cited(self):
        self.assertIn("policy.h:46", self.src)
        self.assertIn("DUST_RATE_PER_K = 3000", self.src)

    def test_maxfee_cited(self):
        self.assertIn("MAX_FEE_SATS", self.src)
        self.assertIn("0.1", self.src)

    def test_dust_threshold_cited(self):
        self.assertIn("policy.cpp:20-30", self.src)
        self.assertIn("182", self.src)

    def test_getfee_semantics_cited(self):
        self.assertIn("feerate.h", self.src)
        self.assertIn("1000", self.src)  # the /1000 truncating division


class SelfCustodyWiring(unittest.TestCase):
    """The flat fee is gone; the send flow uses the fixpoint loop."""

    def setUp(self):
        self.src = read(CUSTODY)

    def test_flat_fee_constant_gone(self):
        self.assertNotIn("FEE_SATS = 10000", self.src)
        self.assertNotIn("0.0001 MAZA fixed", self.src)

    def test_flat_fee_display_gone(self):
        # The send card must not claim a flat fee any more.
        self.assertNotIn('label("fee " + fmt(FEE_SATS', self.src)
        self.assertIn("fee 10 sat/byte per-tx (MazaCore rate; exact fee at send)",
                      self.src)

    def test_uses_fee_policy_for_size(self):
        self.assertIn("FeePolicy.feeForSize(raw.length)", self.src)

    def test_fixpoint_loop_present(self):
        self.assertIn("FeePolicy.feeForSize(300)", self.src)
        self.assertIn("if (actual == fee)", self.src)
        self.assertIn("raw = null;", self.src)

    def test_fee_stabilization_gate_before_broadcast(self):
        self.assertIn("Fee did not stabilize; send aborted before broadcast.",
                      self.src)
        # The broadcast happens only after the loop: raw must be non-null.
        order = self.src.index("Fee did not stabilize")
        self.assertLess(order, self.src.index('"/api/broadcast"'))

    def test_dust_change_folds_into_fee(self):
        self.assertIn("FeePolicy.dustThresholdSats()", self.src)
        self.assertIn("IsDust", self.src)  # citation comment for the fold
        self.assertIn("fee = Math.addExact(fee, change);", self.src)

    def test_dust_boundary_matches_upstream_isdust(self):
        # Upstream IsDust: nValue < GetDustThreshold. A change output at
        # EXACTLY the threshold is not dust: it must be kept (>=), folded
        # strictly below it.
        self.assertIn("change >= FeePolicy.dustThresholdSats()", self.src)

    def test_change_output_still_imported_before_broadcast(self):
        # The judge recovery invariant: a change output is watched before
        # the signed bytes are broadcast (unchanged by M10).
        self.assertIn("Change-address import failed; not broadcasting.",
                      self.src)

    def test_no_second_fee_model(self):
        # No re-introduced hardcoded per-tx fee anywhere in the send flow.
        self.assertNotIn("long fee = 10000", self.src)


class BenchEditionUntouched(unittest.TestCase):
    """D7: the bench (custodial) send fee is a server-side bench policy."""

    def test_walletbench_flat_fee_intact(self):
        api = read(BENCH_API)
        self.assertIn("FLAT_FEE", api)
        self.assertIn('"fee": FLAT_FEE', api)

    def test_mainactivity_server_fee_rows_intact(self):
        src = read(MAIN)
        self.assertIn("fmtAmount(ws.fee)", src)
        self.assertIn('o.optDouble("fee", 0.0001)', src)

    def test_spend_post_still_never_retried(self):
        net = read(NET)
        self.assertIn('new Route("POST", "/api/broadcast", 1, true)', net)


class SelfTestWiring(unittest.TestCase):
    """The desktop selftest drives the policy's behavior."""

    def setUp(self):
        self.src = read(SELFTEST)

    def test_section_registered(self):
        self.assertIn("FeePolicy per-tx fees (M10, MazaCore GetMinimumFee mirror)",
                      self.src)
        self.assertIn("feePolicyChecks();", self.src)

    def test_rows_drive_the_real_class(self):
        self.assertIn("FeePolicy.dustThresholdSats() == 546", self.src)
        self.assertIn("FeePolicy.feeForSize(226) == 2260", self.src)
        self.assertIn("FeePolicy.getFee(1999, 1500) == 2998", self.src)


class DocsHonesty(unittest.TestCase):
    """DECISIONS D4 carries the decision; the user-guide stops claiming flat."""

    def setUp(self):
        self.decisions = read(DECISIONS)
        self.guide = read(USER_GUIDE)

    def test_decisions_d4_documents_per_tx_fee(self):
        self.assertIn("GetMinimumFee", self.decisions)
        self.assertIn("wallet/fees.cpp", self.decisions)
        self.assertIn("fallbackFee", self.decisions)
        self.assertIn("10000", self.decisions)
        self.assertIn("546", self.decisions)

    def test_decisions_records_flat_fee_removal_and_payu_note(self):
        self.assertIn("flat 10000", self.decisions)

    def test_user_guide_self_custody_row_updated(self):
        # The self-custody send row must describe the per-tx MazaCore rate.
        self.assertIn("10 sat/byte", self.guide)

    def test_user_guide_bench_row_stays_flat(self):
        # The bench edition fee (D7) is unchanged.
        self.assertIn("fee 0.0001 MAZA", self.guide)


if __name__ == "__main__":
    unittest.main()
