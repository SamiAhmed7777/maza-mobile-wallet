"""M28-a: the typed SEND amount in BOTH doSend sites is gated behind the
strict MazaUri decimal contract before any float use.

Source-contract pins in the house style (test_settings_resume_gate.py /
test_applog_wiring.py): wiring substrings asserted against the live files,
plus the retirement of the bare ``Double.parseDouble(amtStr)`` path the
M28 review measured as an acceptance superset (0x1p3 -> 8.0, 5f/5d -> 5.0,
1e2 -> 100.0, +5 -> 5.0). The rejection shapes themselves are pinned on the
desktop JVM by SelfTest (M28-a rows in mazaUriChecks); these pins make sure
the SEND wiring cannot silently drop the gate.
"""

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAIN_ACTIVITY = REPO / "android" / "src" / "com" / "mazawallet" / "MainActivity.java"
SELF_CUSTODY = REPO / "android" / "src" / "com" / "mazawallet" / "SelfCustody.java"

GATE_TOKENS = (
    "MazaUri.parseAmountText(amtStr)",
    "strictSats == null",
    "strictSats <= 0",
)


class SendAmountGateWiring(unittest.TestCase):

    def _read(self, path):
        self.assertTrue(path.is_file(), f"missing source file: {path}")
        return path.read_text(encoding="utf-8")

    def test_bench_send_doSend_gates_through_mazauri(self):
        text = self._read(MAIN_ACTIVITY)
        for token in GATE_TOKENS:
            self.assertIn(token, text, f"MainActivity.doSend lost gate token: {token}")
        self.assertIn('sendResult("Invalid amount.", RESULT_ERROR)', text)
        self.assertIn('sendResult("Amount must be positive.", RESULT_ERROR)', text)
        # The bench JSON body double derives from the exact parsed sats
        # (bit-identical to the old parseDouble for every accepted decimal).
        self.assertIn("strictSats / (double) MazaUri.SATS_PER_MAZA", text)

    def test_selfcustody_send_doSend_gates_through_mazauri(self):
        text = self._read(SELF_CUSTODY)
        for token in GATE_TOKENS:
            self.assertIn(token, text, f"SelfCustody.doSend lost gate token: {token}")
        self.assertIn('sendErr("Invalid amount.")', text)
        self.assertIn('sendErr("Amount must be positive.")', text)
        # The signed amount is the exact sats, not Math.round(parseDouble*COIN).
        self.assertIn("sendFlow(toHash, strictSats)", text)
        self.assertNotIn("Math.round(amt * COIN)", text)

    def test_bare_parse_double_send_path_is_retired(self):
        for path in (MAIN_ACTIVITY, SELF_CUSTODY):
            text = self._read(path)
            self.assertNotIn(
                "Double.parseDouble(amtStr)",
                text,
                f"{path.name} still parses the send amount with bare parseDouble",
            )

    def test_gate_precedes_every_amount_use_in_each_doSend(self):
        for path, use_token in (
            (MAIN_ACTIVITY, 'put("amount", amt)'),
            (SELF_CUSTODY, "sendFlow(toHash, strictSats)"),
        ):
            text = self._read(path)
            gate_at = text.find("MazaUri.parseAmountText(amtStr)")
            use_at = text.find(use_token)
            self.assertGreaterEqual(gate_at, 0, f"{path.name}: gate token not found")
            self.assertGreaterEqual(use_at, 0, f"{path.name}: use token not found")
            self.assertLess(
                gate_at,
                use_at,
                f"{path.name}: amount use precedes the strict gate",
            )


if __name__ == "__main__":
    unittest.main()
