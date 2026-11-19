#!/usr/bin/env python3
"""Source contracts for the read-only Android chain explorer."""
import os
import re
import unittest
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "android", "src", "com", "mazawallet")


def read(*parts):
    with open(os.path.join(REPO, *parts), "r", encoding="utf-8") as handle:
        return handle.read()


class ExplorerWiring(unittest.TestCase):
    def test_settings_entry_and_intent(self):
        settings = read("android", "src", "com", "mazawallet", "SettingsActivity.java")
        self.assertIn("R.string.settings_explorer", settings)
        self.assertIn("new Intent(this, ExplorerActivity.class)", settings)

    def test_manifest_private_activity_with_uimode(self):
        root = ET.parse(os.path.join(REPO, "android", "AndroidManifest.xml")).getroot()
        ns = "{http://schemas.android.com/apk/res/android}"
        rows = [node for node in root.findall("./application/activity")
                if node.get(ns + "name") == ".ExplorerActivity"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get(ns + "exported"), "false")
        self.assertIn("uiMode", rows[0].get(ns + "configChanges", "").split("|"))
        self.assertEqual(rows[0].get(ns + "theme"),
                         "@android:style/Theme.Material.NoActionBar")

    def test_retry_rows_and_broadcast_pin(self):
        net = read("android", "src", "com", "mazawallet", "Net.java")
        for path in ("/api/v0/address", "/api/v0/tx", "/api/v0/block"):
            self.assertIn('new Route("GET", "%s", 3, false)' % path, net)
        self.assertIn('new Route("POST", "/api/broadcast", 1, true)', net)

    def test_parser_is_android_free(self):
        parser = read("android", "src", "com", "mazawallet", "ExplorerParse.java")
        self.assertNotRegex(parser, r"(?m)^import\s+android\.")
        self.assertIn("movePointLeft(8).toPlainString()", parser)
        self.assertIn('SimpleDateFormat("yyyy-MM-dd HH:mm"', parser)
        self.assertIn('"Proof: not available"', parser)

    def test_strings_present_and_ascii(self):
        with open(os.path.join(REPO, "android", "res", "values", "strings.xml"),
                  "rb") as handle:
            raw = handle.read()
        raw.decode("ascii")
        strings = raw.decode("ascii")
        for key in ("settings_explorer", "settings_explorer_open", "explorer_title",
                    "explorer_search", "explorer_no_indexer", "explorer_unknown"):
            self.assertIn('name="%s"' % key, strings)

    def test_client_derives_origin_and_honors_override(self):
        client = read("android", "src", "com", "mazawallet", "IndexerClient.java")
        self.assertIn('KEY_INDEXER_URL = "indexer_url"', client)
        self.assertIn('prefs.getString(KEY_INDEXER_URL, "")', client)
        self.assertIn('origin.toASCIIString() + "/indexer"', client)
        self.assertIn("uri.getHost()", client)
        self.assertIn("prefs.contains(MainActivity.KEY_URL)", client)

    def test_wiring_stays_out_of_main_activity(self):
        main = read("android", "src", "com", "mazawallet", "MainActivity.java")
        self.assertNotIn("ExplorerActivity", main)
        self.assertNotIn("settings_explorer", main)
        activity = read("android", "src", "com", "mazawallet", "ExplorerActivity.java")
        self.assertIn("IndexerClient.configuredBase", activity)
        self.assertIn("Base58Check.decode", activity)
        self.assertIn('matches("[0-9a-fA-F]{64}")', activity)
        self.assertIn('matches("[0-9]+")', activity)


if __name__ == "__main__":
    unittest.main()
