#!/usr/bin/env python3
"""WCAG 2.1 contrast audit for the MAZA wallet dark/light palettes (S-3).

WHAT THIS FILE OWNS
-------------------
The palette (android/res/values/colors.xml), the two themes
(android/res/values/styles.xml) and the mode resolver
(android/src/com/mazawallet/ThemeController.java). This test reads those
files as the source of truth -- it never hardcodes a palette value -- and
prints the full contrast table on every run.

FAIL POLICY (no contradictions allowed)
---------------------------------------
1. Pairings resolvable INSIDE this lane's territory (both colors come from
   colors.xml/styles.xml) are hard-asserted: >= 4.5:1 for normal text,
   >= 3:1 for large text (>= 24sp, or >= 19sp bold). A failure here is our
   bug and must be fixed in the palette.
2. Pairings whose ink is defined OUTSIDE this lane's territory (the colors
   MainActivity.java and SelfCustody.java hardcode per widget) are NOT
   asserted. They are registered in OUT_OF_TERRITORY_PAIRINGS with the
   measured ratio for BOTH palettes; the test only asserts that the ratio is
   recorded. Below-threshold rows warn loudly on stderr and skipTest(...) so
   the suite stays green, AND they are enforced by an expected-failure
   ledger gate: EXPECTED_BELOW_THRESHOLD (generated from the live tree) must
   equal reality exactly - the sibling gate test FAILS THE SUITE on any
   untracked violation or silent ledger drift, in either direction. Wave-2
   acceptance is an empty ledger (the reskin converts both files).

WHY THE HARDCODED ROWS MATTER
-----------------------------
Both source files used to pin their own ink constants, so every text/background
pair they drew travelled together and survived a palette change by ignoring it.
The rows measured the cross-lane contradiction that appeared the moment those
surfaces came from this palette (which is exactly what adopting light mode
means): the app's surfaces turned light while its ink stayed dark-theme white.
The PIN dialogs were the one place where that contradiction already rendered,
because an AlertDialog surface follows the activity theme (our palette) while
its body text was built by MainActivity's hardcoded labels.

WAVE-2 RESKIN (landed): both files now resolve every surface and ink from the
theme through UiTheme, so the out-of-territory table is EMPTY and the ledger is
EMPTY - that is the acceptance state. The table and the ledger stay in place as
the regression gate: reintroducing a hardcoded ink in either file repopulates a
row and fails the ledger test immediately. The dark-render baseline below is
frozen to the hexes those constants shipped with, so dark mode provably still
renders the same colors.

Run:  python3 -m unittest discover -s tests -v
      python3 tests/test_theme_contrast.py --table     (print the table only)
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANDROID = os.path.join(REPO_ROOT, "android")
RES_VALUES = os.path.join(ANDROID, "res", "values")
COLORS_XML = os.path.join(RES_VALUES, "colors.xml")
STYLES_XML = os.path.join(RES_VALUES, "styles.xml")
SRC = os.path.join(ANDROID, "src", "com", "mazawallet")
MAIN_ACTIVITY = os.path.join(SRC, "MainActivity.java")
SELF_CUSTODY = os.path.join(SRC, "SelfCustody.java")
THEME_CONTROLLER = os.path.join(SRC, "ThemeController.java")
UI_THEME = os.path.join(SRC, "UiTheme.java")

ANDROID_SDK = os.environ.get("ANDROID_SDK", "/opt/android-sdk")
ANDROID_JAR = os.path.join(ANDROID_SDK, "platforms", "android-34", "android.jar")
JAVAC = shutil.which("javac")
JAVA = shutil.which("java")

NORMAL_TEXT_MIN = 4.5      # WCAG 1.4.3, normal-size text
LARGE_TEXT_MIN = 3.0       # WCAG 1.4.3, large text and WCAG 1.4.11 components

# Palette slots every theme must define, in both modes.
PALETTE_KEYS = (
    "background", "surface", "bar", "divider",
    "text_primary", "text_secondary", "accent", "danger", "success",
)

# Dark-render baseline: the exact hexes the nine hardcoded ints in
# MainActivity.java shipped with (BG / CARD / BAR / DIVIDER / TEXT / MUTED /
# ACCENT / RED / GREEN) before the wave-2 reskin replaced them with palette
# lookups. Frozen here so "dark mode looks identical to today" is a machine
# check, not a promise: if someone edits a maza_dark_* value, dark mode has
# visibly changed and this fails.
DARK_RENDER_BASELINE = {
    "background": "#FF141414",
    "surface": "#FF1E1E1E",
    "bar": "#FF1A1A1A",
    "divider": "#FF2E2E2E",
    "text_primary": "#FFFFFFFF",
    "text_secondary": "#FFB3B3B3",
    "accent": "#FFF0A000",
    "danger": "#FFFF6B6B",
    "success": "#FF6FD66F",
}


# --------------------------------------------------------------- colour math

def hex_to_rgb(value):
    """'#AARRGGBB' or '#RRGGBB' -> (r, g, b). Alpha is validated elsewhere."""
    text = value.strip().lstrip("#")
    if len(text) == 8:
        text = text[2:]
    if len(text) != 6:
        raise ValueError("not a 6- or 8-digit hex colour: %r" % (value,))
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def relative_luminance(rgb):
    """WCAG 2.1 relative luminance."""
    channels = []
    for value in rgb:
        c = value / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(rgb_a, rgb_b):
    """WCAG 2.1 contrast ratio, 1.0 .. 21.0."""
    la = relative_luminance(rgb_a)
    lb = relative_luminance(rgb_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def is_large_text(sp, bold):
    """WCAG large text: >= 18pt, or >= 14pt when bold (1pt = 4/3 px, 1sp ~ 1px
    at mdpi, so the thresholds land on 24sp / 18.66sp -- 19sp rounds up)."""
    return sp >= 24 or (bold and sp >= 19)


def threshold_for(sp, bold):
    return LARGE_TEXT_MIN if is_large_text(sp, bold) else NORMAL_TEXT_MIN


def ratio_text(ratio):
    return "n/a" if ratio is None else "%.2f:1" % ratio


# ------------------------------------------------------------- resource load

def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def parse_color_resources(path):
    """<color name="x">#AARRGGBB</color> -> {name: '#AARRGGBB'}."""
    root = ElementTree.parse(path).getroot()
    colors = {}
    for element in root.findall("color"):
        name = element.get("name")
        value = (element.text or "").strip()
        if not name:
            raise ValueError("%s has a <color> without a name" % path)
        colors[name] = value
    return colors


def parse_styles(path=STYLES_XML):
    """{style name: {'parent': ..., 'items': {item name: value}}}."""
    root = ElementTree.parse(path).getroot()
    styles = {}
    for style in root.findall("style"):
        items = {}
        for item in style.findall("item"):
            items[item.get("name")] = (item.text or "").strip()
        styles[style.get("name")] = {"parent": style.get("parent"), "items": items}
    return styles


def load_palettes(colors_path=COLORS_XML):
    """Both palettes, read from colors.xml. Raises with a precise message."""
    colors = parse_color_resources(colors_path)
    palettes = {}
    for mode in ("dark", "light"):
        palette = {}
        for key in PALETTE_KEYS:
            name = "maza_%s_%s" % (mode, key)
            if name not in colors:
                raise ValueError("%s is missing <color name=\"%s\">" % (colors_path, name))
            palette[key] = colors[name]
        palettes[mode] = palette
    return palettes


try:
    PALETTES = load_palettes()
    PALETTE_LOAD_ERROR = None
except Exception as exc:                                    # noqa: BLE001 - reported by a test
    PALETTES = {}
    PALETTE_LOAD_ERROR = "%s: %s" % (exc.__class__.__name__, exc)


# -------------------------------------------- in-territory pairing table (A)

# (pairing, fg key, bg key, size sp, bold, where it is rendered)
IN_TERRITORY_PAIRINGS = (
    ("header title 'MAZA Wallet'", "text_primary", "background", 22, True,
     "addHeader(), 22sp bold, every tab + lock cover"),
    ("balance value", "text_primary", "background", 36, True,
     "BALANCE tab balanceTv, 36sp bold"),
    ("account / fee / last-sync line", "text_secondary", "background", 12, False,
     "accountTv + lastSyncTv, 12-13sp muted"),
    ("section heading (RECEIVE/SEND/HISTORY/SECURITY)", "accent", "background", 13, True,
     "13sp bold amber section labels"),
    ("card primary text", "text_primary", "surface", 15, False,
     "card() body text"),
    ("card secondary text", "text_secondary", "surface", 13, False,
     "card() muted lines (fee hint, notes)"),
    ("card section label", "accent", "surface", 12, True,
     "BALANCE / RECEIVE ADDRESS / SECURITY captions"),
    ("self-custody balance", "text_primary", "surface", 28, True,
     "SelfCustody balanceTv, 28sp bold on card"),
    ("error line on screen", "danger", "background", 13, False,
     "connect / QR error text outside a card"),
    ("error line in card", "danger", "surface", 13, False,
     "PIN + send error text inside a card"),
    ("outgoing amount in tx row", "danger", "surface", 15, True,
     "txRow sent amount, 15sp bold"),
    ("incoming amount in tx row", "success", "surface", 15, True,
     "txRow received amount, 15sp bold"),
    ("unconfirmed badge", "accent", "surface", 12, False,
     "txRow 'unconfirmed', 12sp amber"),
    ("lock cover heading", "text_primary", "background", 22, True,
     "lockOverlay 'Wallet locked', 22sp bold"),
    ("unselected tab label", "text_secondary", "bar", 12, False,
     "bottom tab bar, 12sp muted"),
    ("selected tab label", "accent", "bar", 12, True,
     "bottom tab bar, 12sp bold amber"),
    ("button label", "text_primary", "surface", 14, False,
     "theme text color on colorButtonNormal fill (platform draws the label "
     "from the same Material text family; the fill is ours)"),
    ("dialog body text", "text_primary", "surface", 13, False,
     "AlertDialog body (PIN prompts) via Theme.MazaWallet.*.Dialog"),
    ("dialog hint text", "text_secondary", "surface", 13, False,
     "dialog EditText hint color"),
    ("dialog accent action", "accent", "surface", 14, False,
     "dialog positive/negative button accent"),
)

# Decorative separators: WCAG 1.4.11 exempts non-informational hairlines, so
# they are printed for completeness with a DECORATIVE verdict, not asserted.
DECORATIVE_PAIRINGS = (
    ("hairline divider", "divider", "background"),
    ("hairline divider on card", "divider", "surface"),
)


# ---------------------------------------- out-of-territory pairing table (B)

_JAVA_INT_CONST = re.compile(
    r"private\s+static\s+final\s+int\s+([A-Z][A-Z0-9_]*)\s*=\s*0x([0-9A-Fa-f]{8})\s*;")

# file -> surfaces of OUR palette it prints text onto
OUT_OF_TERRITORY_SOURCES = (
    ("MainActivity.java", MAIN_ACTIVITY, ("background", "surface", "bar")),
    ("SelfCustody.java", SELF_CUSTODY, ("background", "surface")),
)

# hardcoded constant -> palette slot it duplicates, and what it inks
OUT_OF_TERRITORY_INKS = (
    ("TEXT", "text_primary", "primary text (titles, balances, card body)"),
    ("MUTED", "text_secondary", "muted secondary text and input hints"),
    ("ACCENT", "accent", "amber section labels, selected tab, unconfirmed badge"),
    ("RED", "danger", "error lines and outgoing amounts"),
    ("GREEN", "success", "incoming amounts"),
)


def hardcoded_int_constants(path):
    """{'TEXT': '#FFFFFFFF', ...} from `private static final int X = 0x........;`"""
    if not os.path.exists(path):
        return {}
    return {m.group(1): "#" + m.group(2).upper()
            for m in _JAVA_INT_CONST.finditer(read_text(path))}


def build_out_of_territory_pairings():
    found = []
    if not PALETTES:
        return found
    for filename, path, surfaces in OUT_OF_TERRITORY_SOURCES:
        constants = hardcoded_int_constants(path)
        for constant, palette_key, what in OUT_OF_TERRITORY_INKS:
            if constant not in constants:
                # Constant gone: the file was converted to resources, so the
                # pairing is no longer out of territory. Nothing to record.
                continue
            ink = constants[constant]
            for surface in surfaces:
                row = {
                    "pairing": "hardcoded %s (%s) on palette %s" % (constant, filename, surface),
                    "source": filename,
                    "constant": constant,
                    "palette_key": palette_key,
                    "ink": ink,
                    "surface": surface,
                    "renders": what,
                    "ratios": {},
                    "verdicts": {},
                }
                for mode, palette in PALETTES.items():
                    ratio = contrast_ratio(hex_to_rgb(ink), hex_to_rgb(palette[surface]))
                    row["ratios"][mode] = ratio
                    row["verdicts"][mode] = ("PASS" if ratio >= NORMAL_TEXT_MIN
                                             else "FAIL")
                found.append(row)
    return found


OUT_OF_TERRITORY_PAIRINGS = build_out_of_territory_pairings()


def below_threshold_out_of_territory():
    bad = []
    for row in OUT_OF_TERRITORY_PAIRINGS:
        for mode in ("dark", "light"):
            if row["verdicts"].get(mode) == "FAIL":
                bad.append((row, mode))
    return bad


# Expected-failure ledger: the exact (pairing, palette) tuples allowed to sit
# below WCAG threshold. This is a MACHINE-CHECKED gate, not prose: the gate
# test below fails the suite when reality drifts from this ledger in EITHER
# direction - a NEW below-threshold pairing appears (regression), or a ledgered
# row is fixed (in which case the row must be removed from this ledger in the
# same change so the ledger always matches reality).
#
# Wave-2 acceptance: EMPTY, and it is empty. The reskin converted both files to
# palette lookups, so no out-of-territory pairing is recorded at all; keeping
# the gate means a hardcoded ink creeping back in fails the suite on the spot
# instead of quietly rendering white-on-white in light mode.
EXPECTED_BELOW_THRESHOLD = frozenset()


# ------------------------------------------------------------------- printing

_TABLE_HEADER = "%-58s %-6s %-9s %-9s %9s %6s  %-10s %s"


def print_table(stream=None):
    out = stream or sys.stdout
    written = []
    written.append("")
    written.append("WCAG 2.1 contrast table -- MAZA wallet palettes (S-3 dark/light)")
    written.append("thresholds: %.1f:1 normal text (< 24sp, or bold < 19sp); "
                   "%.1f:1 large text / UI component" % (NORMAL_TEXT_MIN, LARGE_TEXT_MIN))
    written.append("source A rows = both colours owned by this lane, hard-asserted")
    written.append("source B rows = ink hardcoded in another lane's file: recorded, "
                   "not asserted, reported as integration blocker when red")
    written.append("")
    written.append(_TABLE_HEADER % ("pairing", "palette", "fg", "bg",
                                    "ratio", "min", "verdict", "derived from"))
    written.append("-" * 132)

    if not PALETTES:
        written.append("palette resources could not be loaded: %s" % PALETTE_LOAD_ERROR)
        out.write("\n".join(written) + "\n")
        return

    for pairing, fg_key, bg_key, sp, bold, where in IN_TERRITORY_PAIRINGS:
        minimum = threshold_for(sp, bold)
        for mode in ("dark", "light"):
            palette = PALETTES[mode]
            ratio = contrast_ratio(hex_to_rgb(palette[fg_key]), hex_to_rgb(palette[bg_key]))
            verdict = "PASS" if ratio >= minimum else "FAIL"
            written.append(_TABLE_HEADER % (
                pairing, mode, palette[fg_key][-6:], palette[bg_key][-6:],
                "%.2f:1" % ratio, "%.1f" % minimum, verdict,
                "A: %s" % where))

    for pairing, fg_key, bg_key in DECORATIVE_PAIRINGS:
        for mode in ("dark", "light"):
            palette = PALETTES[mode]
            ratio = contrast_ratio(hex_to_rgb(palette[fg_key]), hex_to_rgb(palette[bg_key]))
            written.append(_TABLE_HEADER % (
                pairing, mode, palette[fg_key][-6:], palette[bg_key][-6:],
                "%.2f:1" % ratio, "-", "DECORATIVE",
                "A: separator, WCAG 1.4.11 exempt"))

    written.append("-" * 132)
    for row in OUT_OF_TERRITORY_PAIRINGS:
        for mode in ("dark", "light"):
            written.append(_TABLE_HEADER % (
                row["pairing"], mode, row["ink"][-6:],
                PALETTES[mode][row["surface"]][-6:],
                "%.2f:1" % row["ratios"][mode], "%.1f" % NORMAL_TEXT_MIN,
                row["verdicts"][mode],
                "B: %s, %s" % (row["source"], row["renders"])))

    asserted = len(IN_TERRITORY_PAIRINGS) * 2
    recorded = len(OUT_OF_TERRITORY_PAIRINGS) * 2
    bad = below_threshold_out_of_territory()
    written.append("-" * 132)
    written.append("rows: %d asserted (source A, both palettes), %d recorded "
                   "(source B, both palettes), %d decorative"
                   % (asserted, recorded, len(DECORATIVE_PAIRINGS) * 2))
    written.append("source B failures: %d of %d recorded pairs "
                   "(each is an integration blocker, not a green result)" % (len(bad), recorded))
    written.append("")
    out.write("\n".join(written) + "\n")
    out.flush()


def setUpModule():
    print_table()


# ---------------------------------------------------------------- test cases

class PaletteResourceTest(unittest.TestCase):
    """colors.xml must define a complete, opaque palette for both modes."""

    def test_palette_resources_load(self):
        self.assertIsNone(PALETTE_LOAD_ERROR, PALETTE_LOAD_ERROR)

    def test_both_palettes_define_the_same_slots(self):
        colors = parse_color_resources(COLORS_XML)
        dark = {n[len("maza_dark_"):] for n in colors if n.startswith("maza_dark_")}
        light = {n[len("maza_light_"):] for n in colors if n.startswith("maza_light_")}
        self.assertEqual(dark, set(PALETTE_KEYS))
        self.assertEqual(light, set(PALETTE_KEYS))

    def test_palette_colours_are_opaque_argb(self):
        for mode, palette in PALETTES.items():
            for key, value in palette.items():
                with self.subTest(palette=mode, slot=key):
                    self.assertRegex(value, r"^#[0-9A-Fa-f]{8}$")
                    self.assertEqual(value[1:3].upper(), "FF",
                                     "%s/%s must be opaque (AA=FF)" % (mode, key))

    def test_dark_render_matches_the_frozen_baseline(self):
        """Dark mode must look IDENTICAL to the pre-reskin app.

        Before the wave-2 reskin MainActivity pinned nine ARGB ints. The dark
        palette is required to reproduce those nine hexes exactly, frozen in
        DARK_RENDER_BASELINE - so "nothing changes in dark mode" is asserted,
        not assumed, and any later edit to a maza_dark_* value fails here.
        """
        for slot, expected in DARK_RENDER_BASELINE.items():
            with self.subTest(slot=slot):
                self.assertEqual(
                    PALETTES["dark"][slot], expected,
                    "maza_dark_%s = %s but the shipping dark render used %s"
                    % (slot, PALETTES["dark"][slot], expected))

    def test_sources_resolve_every_colour_from_the_palette(self):
        """The reskin's substance: neither source may hardcode an ARGB literal
        and both must read their colours from UiTheme's live palette."""
        allowed_literals = {"0x00000000"}   # transparent tab fills, not a colour
        for path in (MAIN_ACTIVITY, SELF_CUSTODY):
            name = os.path.basename(path)
            code = _strip_comments(read_text(path))
            literals = set(re.findall(r"0x[0-9A-Fa-f]{8}", code))
            with self.subTest(source=name):
                self.assertEqual(literals - allowed_literals, set(),
                                 "%s still hardcodes ARGB literals: %s"
                                 % (name, sorted(literals - allowed_literals)))
                self.assertIn("UiTheme.Palette", code,
                              "%s must take its colours from UiTheme" % name)
                self.assertTrue(re.search(r"\bpal\.[a-zA-Z]+\(\)", code),
                                "%s must read slots from its resolved palette" % name)

    def test_host_passes_the_live_palette_to_self_custody(self):
        """SelfCustody has no theme of its own: its host resolves the palette
        once (after applyTheme) and hands it over, so the WALLET section and
        MainActivity's own surfaces can never show different palettes."""
        main = _strip_comments(read_text(MAIN_ACTIVITY))
        custody = _strip_comments(read_text(SELF_CUSTODY))
        self.assertIn("pal = UiTheme.palette(this);", main,
                      "MainActivity must resolve the palette in onCreate")
        self.assertIn("new SelfCustody(this, this, pal)", main)
        self.assertRegex(custody,
                         r"SelfCustody\(Activity activity, Host host,\s*"
                         r"UiTheme\.Palette palette\)")
        self.assertNotIn("UiTheme.palette(", custody,
                         "SelfCustody must not resolve a palette of its own")

    def test_pin_dialogs_are_palette_inked(self):
        """The PIN prompts render on a theme-owned dialog surface, so their
        body/hint/error ink must come from the palette too - this is the pair
        that used to render white-on-white in light mode."""
        code = _strip_comments(read_text(MAIN_ACTIVITY))
        for builder in ("showPinSetPrompt", "promptCurrentPin"):
            with self.subTest(dialog=builder):
                start = code.find("private void " + builder)
                self.assertGreater(start, -1, "%s not found" % builder)
                body = code[start:code.find("\n    }", start)]
                self.assertIn("pinInput(", body,
                              "%s must build its fields via pinInput()" % builder)
                self.assertNotIn("0x", body,
                                 "%s must not pin an ink literal" % builder)
        # The dialog field ink itself (text + hint) comes from the palette.
        start = code.find("private EditText input(")
        self.assertGreater(start, -1)
        field = code[start:code.find("\n    }", start)]
        self.assertIn("pal.textPrimary()", field,
                      "dialog/field body ink must come from the palette")
        self.assertIn("pal.textSecondary()", field,
                      "dialog/field hint ink must come from the palette")
        # And the dialog themes must each point at their own palette.
        styles = parse_styles()
        for theme, prefix in (("Theme.MazaWallet.Dialog", "maza_dark_"),
                              ("Theme.MazaWallet.Light.Dialog", "maza_light_")):
            with self.subTest(dialog_theme=theme):
                items = styles[theme]["items"]
                colours = [v for v in items.values() if v.startswith("@color/")]
                self.assertTrue(colours, "%s must set palette colours" % theme)
                for value in colours:
                    self.assertTrue(value.startswith("@color/" + prefix),
                                    "%s must use %s* colours, got %s"
                                    % (theme, prefix, value))

    def test_light_palette_is_distinct_from_dark(self):
        dark, light = PALETTES["dark"], PALETTES["light"]
        for key in ("background", "surface", "text_primary", "text_secondary"):
            with self.subTest(slot=key):
                self.assertNotEqual(dark[key], light[key],
                                    "light mode must actually differ for %s" % key)


class ContrastTableTest(unittest.TestCase):
    """The WCAG 2.1 table itself."""

    def _assert_palette_rows(self, mode):
        palette = PALETTES[mode]
        failures = []
        for pairing, fg_key, bg_key, sp, bold, where in IN_TERRITORY_PAIRINGS:
            minimum = threshold_for(sp, bold)
            ratio = contrast_ratio(hex_to_rgb(palette[fg_key]),
                                   hex_to_rgb(palette[bg_key]))
            with self.subTest(pairing=pairing, palette=mode):
                self.assertGreaterEqual(
                    ratio, minimum,
                    "%s [%s]: %s on %s = %.2f:1, needs %.1f:1 (%s)"
                    % (pairing, mode, palette[fg_key], palette[bg_key], ratio, minimum, where))
            if ratio < minimum:
                failures.append(pairing)
        self.assertEqual(failures, [], "in-territory contrast failures in the %s palette" % mode)

    def test_dark_palette_meets_wcag(self):
        self._assert_palette_rows("dark")

    def test_light_palette_meets_wcag(self):
        self._assert_palette_rows("light")

    def test_table_covers_every_rendered_pairing(self):
        # Both palettes for every row, and the widened surface set actually
        # shows up (background, cards, tab bar, dialog).
        self.assertGreaterEqual(len(IN_TERRITORY_PAIRINGS), 18)
        surfaces = {row[2] for row in IN_TERRITORY_PAIRINGS}
        self.assertEqual(surfaces, {"background", "surface", "bar"})
        sizes = [row[3] for row in IN_TERRITORY_PAIRINGS]
        self.assertTrue(any(is_large_text(row[3], row[4]) for row in IN_TERRITORY_PAIRINGS),
                        "large-text rows must be listed separately")
        self.assertTrue(any(not is_large_text(row[3], row[4]) for row in IN_TERRITORY_PAIRINGS))
        self.assertTrue(max(sizes) >= 28)

    def test_out_of_territory_pairings_are_recorded(self):
        """Every hardcoded ink that still exists must be recorded with a ratio
        for both palettes. An EMPTY table is the wave-2 acceptance state: both
        sources resolve their inks from the palette, so nothing is left out of
        territory to record (the two tests above prove the conversion)."""
        self.assertTrue(PALETTES, "palette resources did not load")
        if not OUT_OF_TERRITORY_PAIRINGS:
            for path in (MAIN_ACTIVITY, SELF_CUSTODY):
                with self.subTest(source=os.path.basename(path)):
                    self.assertEqual(hardcoded_int_constants(path), {},
                                     "%s still declares a hardcoded colour"
                                     % os.path.basename(path))
            return
        for row in OUT_OF_TERRITORY_PAIRINGS:
            with self.subTest(pairing=row["pairing"]):
                self.assertEqual(set(row["ratios"]), {"dark", "light"},
                                 "a ratio must be recorded for both palettes")
                for mode, ratio in row["ratios"].items():
                    self.assertGreaterEqual(ratio, 1.0)
                    self.assertLessEqual(ratio, 21.0)
                self.assertIn(row["surface"], PALETTE_KEYS)

    def test_out_of_territory_pairings_warn_but_do_not_fail(self):
        """Hardcoded inks are another lane's file: record, warn loudly, skip.

        The skip is deliberate - the suite stays green while the defect stays
        visible and machine-detectable. Compliance is NOT enforced by prose:
        the sibling gate test below (expected-failure ledger) fails the suite
        on any untracked violation and on any silent ledger drift.
        """
        bad = below_threshold_out_of_territory()
        if not bad:
            self.assertEqual(bad, [])
            return
        for row, mode in bad:
            sys.stderr.write(
                "WARNING: OUT-OF-TERRITORY CONTRAST %.2f:1 < %.1f:1 -- %s [%s palette]; "
                "ink is hardcoded in %s, surface comes from android/res/values/colors.xml\n"
                % (row["ratios"][mode], NORMAL_TEXT_MIN, row["pairing"], mode, row["source"]))
        sys.stderr.flush()
        self.skipTest("%d out-of-territory pairing(s) below threshold - tracked in "
                      "EXPECTED_BELOW_THRESHOLD (wave-2 reskin burn-down)"
                      % len(bad))

    def test_below_threshold_matches_the_expected_failure_ledger(self):
        """Burn-down gate: reality must equal the ledger, in both directions.

        Fails when a NEW below-threshold pairing appears, or when a ledgered
        row is fixed without removing it from EXPECTED_BELOW_THRESHOLD. The
        wave-2 acceptance criterion is an EMPTY ledger."""
        actual = {(row["pairing"], mode)
                  for row, mode in below_threshold_out_of_territory()}
        expected = set(EXPECTED_BELOW_THRESHOLD)
        self.assertEqual(
            expected, actual,
            "contrast ledger drifted: new=%s fixed=%s"
            % (sorted(actual - expected), sorted(expected - actual)))


class ThemeResourceTest(unittest.TestCase):
    """styles.xml must wire each theme to exactly one palette."""

    def _styles(self):
        root = ElementTree.parse(STYLES_XML).getroot()
        styles = {}
        for style in root.findall("style"):
            items = {}
            for item in style.findall("item"):
                items[item.get("name")] = (item.text or "").strip()
            styles[style.get("name")] = {"parent": style.get("parent"), "items": items}
        return styles

    def test_both_themes_exist_with_platform_parents(self):
        styles = self._styles()
        self.assertIn("Theme.MazaWallet", styles)
        self.assertIn("Theme.MazaWallet.Light", styles)
        dark = styles["Theme.MazaWallet"]
        light = styles["Theme.MazaWallet.Light"]
        self.assertEqual(dark["parent"], "@android:style/Theme.Material.NoActionBar")
        self.assertEqual(light["parent"], "@android:style/Theme.Material.Light.NoActionBar")
        # Manifests fallback theme and the dark theme must be the same family,
        # so nothing changes before applyTheme lands.
        self.assertIn("NoActionBar", dark["parent"])

    def test_dark_theme_references_only_dark_colours(self):
        styles = self._styles()
        items = styles["Theme.MazaWallet"]["items"]
        self.assertTrue(items)
        for name, value in items.items():
            if value.startswith("@color/"):
                with self.subTest(item=name):
                    self.assertTrue(value.startswith("@color/maza_dark_"),
                                    "%s must use a maza_dark_* colour, got %s" % (name, value))

    def test_light_theme_references_only_light_colours(self):
        styles = self._styles()
        items = styles["Theme.MazaWallet.Light"]["items"]
        self.assertTrue(items)
        for name, value in items.items():
            if value.startswith("@color/"):
                with self.subTest(item=name):
                    self.assertTrue(value.startswith("@color/maza_light_"),
                                    "%s must use a maza_light_* colour, got %s" % (name, value))

    def test_themes_set_the_text_attributes_the_app_depends_on(self):
        required = ("android:textColorPrimary", "android:textColorSecondary",
                    "android:windowBackground", "android:colorBackground",
                    "android:colorAccent", "android:alertDialogTheme")
        styles = self._styles()
        for theme in ("Theme.MazaWallet", "Theme.MazaWallet.Light"):
            for attribute in required:
                with self.subTest(theme=theme, attribute=attribute):
                    self.assertIn(attribute, styles[theme]["items"])

    def test_button_fill_is_palette_driven_but_the_widget_is_not_frozen(self):
        """The fill follows the palette; the label keeps the platform state
        list, so disabled buttons still dim (Connect while connecting,
        Send while sending, Unlock while verifying)."""
        styles = self._styles()
        for theme in ("Theme.MazaWallet", "Theme.MazaWallet.Light"):
            items = styles[theme]["items"]
            with self.subTest(theme=theme):
                self.assertIn("android:colorButtonNormal", items)
                self.assertNotIn("android:buttonStyle", items,
                                 "a buttonStyle override would freeze the disabled-state "
                                 "label alpha; keep the palette on the fill only")

    def test_every_theme_colour_exists_in_the_palette(self):
        colors = parse_color_resources(COLORS_XML)
        for style_name, style in self._styles().items():
            for name, value in style["items"].items():
                if value.startswith("@color/"):
                    token = value[len("@color/"):]
                    with self.subTest(style=style_name, item=name):
                        self.assertIn(token, colors, "undefined colour %s" % value)


def _strip_comments(source):
    """Java source with block and line comments removed (code checks only)."""
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line.split("//")[0] for line in without_block.splitlines())


class ThemeControllerContractTest(unittest.TestCase):
    """The settings lane compiles against this exact surface."""

    def setUp(self):
        self.source = read_text(THEME_CONTROLLER)
        self.code = _strip_comments(self.source)

    def test_contract_signatures(self):
        self.assertIn("package com.mazawallet;", self.source)
        self.assertIn("public static void applyTheme(android.app.Activity activity, String mode)",
                      self.source)
        self.assertIn("public static String normalize(String mode)", self.source)
        self.assertIn("activity.setTheme(", self.source)
        self.assertIn("R.style.Theme_MazaWallet", self.source)
        self.assertIn("R.style.Theme_MazaWallet_Light", self.source)

    def test_system_resolution_uses_the_activity_configuration(self):
        self.assertIn("getResources().getConfiguration().uiMode", self.code)
        self.assertIn("UI_MODE_NIGHT_MASK", self.code)
        self.assertIn("UI_MODE_NIGHT_YES", self.code)
        self.assertNotIn("UiModeManager", self.code,
                         "UiModeManager.getCurrentModeType() reports device type, not night mode")
        self.assertNotIn("recreate()", self.code,
                         "applying a theme must not restart the activity behind the caller's back")

    def test_no_appcompat_or_third_party_imports(self):
        for forbidden in ("androidx.", "android.support.", "com.google."):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)
        imports = [line.strip() for line in self.source.splitlines()
                   if line.strip().startswith("import ")]
        self.assertTrue(all(i.startswith("import java.") for i in imports),
                        "only java.* imports are allowed, got %r" % imports)


class ThemeControllerLogicTest(unittest.TestCase):
    """Runs the real Java logic on the desktop JVM (no Android device).

    The probe never instantiates an Activity: normalize()/resolve()/isNight
    are pure, so the android.jar stubs are only needed to compile.
    """

    PROBE = r"""
package com.mazawallet;

public final class ThemeProbe {
    private static int failed = 0;

    private static void check(String what, boolean ok) {
        System.out.println((ok ? "PASS " : "FAIL ") + what);
        if (!ok) failed++;
    }

    public static void main(String[] args) {
        check("normalize(null) == system", "system".equals(ThemeController.normalize(null)));
        check("normalize(\"\") == system", "system".equals(ThemeController.normalize("")));
        check("normalize(\"  \") == system", "system".equals(ThemeController.normalize("   ")));
        check("normalize(\"system\") == system", "system".equals(ThemeController.normalize("system")));
        check("normalize(\"light\") == light", "light".equals(ThemeController.normalize("light")));
        check("normalize(\"dark\") == dark", "dark".equals(ThemeController.normalize("dark")));
        check("normalize(\"DARK\") == dark", "dark".equals(ThemeController.normalize("DARK")));
        check("normalize(\" Dark \") == dark", "dark".equals(ThemeController.normalize("  Dark  ")));
        check("normalize(\"Light\") == light", "light".equals(ThemeController.normalize("Light")));
        check("normalize(\"purple\") == system", "system".equals(ThemeController.normalize("purple")));
        check("normalize(\"night\") == system", "system".equals(ThemeController.normalize("night")));
        int night = 0x21;   // UI_MODE_NIGHT_YES | UI_MODE_TYPE_NORMAL
        int day = 0x11;     // UI_MODE_NIGHT_NO  | UI_MODE_TYPE_NORMAL
        check("resolve(system, night) == dark", "dark".equals(ThemeController.resolve("system", night)));
        check("resolve(system, day) == light", "light".equals(ThemeController.resolve("system", day)));
        check("resolve(null, night) == dark", "dark".equals(ThemeController.resolve(null, night)));
        check("resolve(garbage, day) == light", "light".equals(ThemeController.resolve("x", day)));
        check("resolve(light, night) == light", "light".equals(ThemeController.resolve("light", night)));
        check("resolve(dark, day) == dark", "dark".equals(ThemeController.resolve("dark", day)));
        check("isNightUiMode(night)", ThemeController.isNightUiMode(night));
        check("isNightUiMode(day) == false", !ThemeController.isNightUiMode(day));
        check("styleFor(dark) != styleFor(light)",
              ThemeController.styleFor("dark") != ThemeController.styleFor("light"));
        if (failed > 0) {
            System.out.println(failed + " probe check(s) FAILED");
            System.exit(1);
        }
        System.out.println("ALL THEME PROBES PASSED");
    }
}
"""

    R_STUB = r"""
package com.mazawallet;

public final class R {
    public static final class style {
        public static final int Theme_MazaWallet = 0x7f0b0001;
        public static final int Theme_MazaWallet_Light = 0x7f0b0002;
    }
}
"""

    def test_java_logic_on_desktop_jvm(self):
        if not JAVAC or not JAVA:
            self.skipTest("javac/java unavailable - JVM probe not run")
        if not os.path.exists(ANDROID_JAR):
            self.skipTest("android.jar not found at %s - JVM probe not run" % ANDROID_JAR)
        workdir = tempfile.mkdtemp(prefix="maza-theme-probe-")
        classes = os.path.join(workdir, "classes")
        os.makedirs(classes)
        sources = {
            "ThemeController.java": read_text(THEME_CONTROLLER),
            "R.java": self.R_STUB,
            "ThemeProbe.java": self.PROBE,
        }
        for name, body in sources.items():
            with open(os.path.join(workdir, name), "w", encoding="ascii") as handle:
                handle.write(body)
        compiled = subprocess.run(
            [JAVAC, "-nowarn", "-classpath", ANDROID_JAR, "-d", classes]
            + [os.path.join(workdir, name) for name in sources],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        self.assertEqual(compiled.returncode, 0,
                         "javac failed:\n%s" % compiled.stdout.decode("utf-8", "replace"))
        run = subprocess.run(
            [JAVA, "-classpath", classes + os.pathsep + ANDROID_JAR, "com.mazawallet.ThemeProbe"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        output = run.stdout.decode("utf-8", "replace")
        self.assertEqual(run.returncode, 0, "ThemeController probe failed:\n%s" % output)
        self.assertIn("ALL THEME PROBES PASSED", output)
        self.assertNotIn("FAIL ", output)


class UiThemeResourceTest(unittest.TestCase):
    """UiTheme must resolve both palettes from resources, not from literals."""

    def setUp(self):
        self.source = read_text(UI_THEME)
        self.code = _strip_comments(self.source)

    def test_palette_of_references_every_slot_of_both_palettes(self):
        expected = {"maza_%s_%s" % (mode, key)
                    for mode in ("dark", "light") for key in PALETTE_KEYS}
        found = re.findall(r"\bmaza_(?:dark|light)_[a-z_]+\b", self.code)
        with self.subTest(check="coverage"):
            self.assertEqual(set(found), expected,
                             "UiTheme must resolve exactly the nine slots of each "
                             "palette; missing=%s extra=%s"
                             % (sorted(expected - set(found)),
                                sorted(set(found) - expected)))
        with self.subTest(check="each slot used once"):
            self.assertEqual(len(found), len(expected),
                             "a slot is referenced twice: %s"
                             % sorted({n for n in found if found.count(n) > 1}))

    def test_no_appcompat_or_third_party_imports(self):
        imports = [line.strip() for line in self.source.splitlines()
                   if line.strip().startswith("import ")]
        for name in imports:
            with self.subTest(import_=name):
                self.assertTrue(name.startswith("import android.")
                                or name.startswith("import java."),
                                "unexpected import: %s" % name)

    def test_palette_is_immutable_and_exposes_the_nine_slots(self):
        for accessor in ("background", "surface", "bar", "divider",
                         "textPrimary", "textSecondary", "accent", "danger", "success"):
            with self.subTest(accessor=accessor):
                self.assertIn("public int %s()" % accessor, self.source)
        self.assertNotIn("public void set", self.source,
                         "Palette must stay immutable: it is read from worker threads")
        # Per-activity resolution + re-resolution on recreate.
        self.assertIn("public static Palette palette(Context context)", self.source)


class UiThemeLogicTest(unittest.TestCase):
    """Runs UiTheme's pure colour math on the desktop JVM (no Android device).

    Only static, Android-free helpers are exercised (isLightCanvas /
    relativeLuminance); context-bound resolution is compile-checked against a
    generated R stub, and the attribute it reads is asserted in source.
    """

    PROBE = r"""
package com.mazawallet;

public final class UiThemeProbe {
    private static int failed = 0;

    private static void check(String what, boolean ok) {
        System.out.println((ok ? "PASS " : "FAIL ") + what);
        if (!ok) failed++;
    }

    private static void near(String what, double actual, double expected) {
        check(what + " (" + actual + ")", Math.abs(actual - expected) < 1e-9);
    }

    public static void main(String[] args) {
        near("relativeLuminance(#FFFFFFFF) == 1.0",
             UiTheme.relativeLuminance(0xFFFFFFFF), 1.0);
        near("relativeLuminance(#FF000000) == 0.0",
             UiTheme.relativeLuminance(0xFF000000), 0.0);
        check("light page background reads as a light canvas",
              UiTheme.isLightCanvas(LIGHT_BACKGROUND));
        check("dark page background reads as a dark canvas",
              !UiTheme.isLightCanvas(DARK_BACKGROUND));
        check("light card surface reads as a light canvas",
              UiTheme.isLightCanvas(LIGHT_SURFACE));
        check("dark card surface reads as a dark canvas",
              !UiTheme.isLightCanvas(DARK_SURFACE));
        check("light tab bar reads as a light canvas",
              UiTheme.isLightCanvas(LIGHT_BAR));
        check("dark tab bar reads as a dark canvas",
              !UiTheme.isLightCanvas(DARK_BAR));
        check("alpha channel is ignored (transparent white reads light)",
              UiTheme.isLightCanvas(0x00FFFFFF));
        check("unresolved canvas (0) falls back to the dark palette",
              !UiTheme.isLightCanvas(0));
        check("mid grey (0x6F) is below the split", !UiTheme.isLightCanvas(0xFF6F6F6F));
        check("light grey (0xBF) is above the split", UiTheme.isLightCanvas(0xFFBFBFBF));
        if (failed > 0) {
            System.out.println(failed + " probe check(s) FAILED");
            System.exit(1);
        }
        System.out.println("ALL UI THEME PROBES PASSED");
    }
}
"""

    def _r_stub(self):
        lines = ["package com.mazawallet;", "",
                 "public final class R {", "    public static final class color {"]
        value = 0x7F0C0000
        for mode in ("dark", "light"):
            for key in PALETTE_KEYS:
                lines.append("        public static final int maza_%s_%s = 0x%08X;"
                             % (mode, key, value))
                value += 1
        lines.extend(["    }", "}", ""])
        return "\n".join(lines)

    def _probe_source(self):
        values = {
            "LIGHT_BACKGROUND": PALETTES["light"]["background"],
            "LIGHT_SURFACE": PALETTES["light"]["surface"],
            "LIGHT_BAR": PALETTES["light"]["bar"],
            "DARK_BACKGROUND": PALETTES["dark"]["background"],
            "DARK_SURFACE": PALETTES["dark"]["surface"],
            "DARK_BAR": PALETTES["dark"]["bar"],
        }
        body = self.PROBE
        for name, hex_value in values.items():
            body = body.replace(name, "0x" + hex_value.lstrip("#"))
        return body

    def test_the_two_canvases_sit_far_from_the_luminance_split(self):
        """The fallback split only has to disambiguate OUR two palettes, so
        assert the gap is wide in Python's own WCAG math as well."""
        for mode in ("dark", "light"):
            lum = relative_luminance(hex_to_rgb(PALETTES[mode]["background"]))
            with self.subTest(palette=mode):
                if mode == "dark":
                    self.assertLess(lum, 0.1)
                else:
                    self.assertGreater(lum, 0.8)

    def test_java_logic_on_desktop_jvm(self):
        if not JAVAC or not JAVA:
            self.skipTest("javac/java unavailable - JVM probe not run")
        if not os.path.exists(ANDROID_JAR):
            self.skipTest("android.jar not found at %s - JVM probe not run" % ANDROID_JAR)
        if not PALETTES:
            self.skipTest("palette resources did not load")
        workdir = tempfile.mkdtemp(prefix="maza-uitheme-probe-")
        classes = os.path.join(workdir, "classes")
        os.makedirs(classes)
        sources = {
            "UiTheme.java": read_text(UI_THEME),
            "R.java": self._r_stub(),
            "UiThemeProbe.java": self._probe_source(),
        }
        for name, body in sources.items():
            with open(os.path.join(workdir, name), "w", encoding="ascii") as handle:
                handle.write(body)
        compiled = subprocess.run(
            [JAVAC, "-nowarn", "-classpath", ANDROID_JAR, "-d", classes]
            + [os.path.join(workdir, name) for name in sources],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        self.assertEqual(compiled.returncode, 0,
                         "javac failed:\n%s" % compiled.stdout.decode("utf-8", "replace"))
        run = subprocess.run(
            [JAVA, "-classpath", classes + os.pathsep + ANDROID_JAR,
             "com.mazawallet.UiThemeProbe"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        output = run.stdout.decode("utf-8", "replace")
        self.assertEqual(run.returncode, 0, "UiTheme probe failed:\n%s" % output)
        self.assertIn("ALL UI THEME PROBES PASSED", output)
        self.assertNotIn("FAIL ", output)


class SourceHygieneTest(unittest.TestCase):
    """Repo rule: everything this lane writes is pure ASCII."""

    def test_lane_files_are_ascii(self):
        for path in (COLORS_XML, STYLES_XML, THEME_CONTROLLER, UI_THEME,
                     MAIN_ACTIVITY, SELF_CUSTODY, os.path.abspath(__file__)):
            with self.subTest(path=os.path.basename(path)):
                with open(path, "rb") as handle:
                    raw = handle.read()
                non_ascii = [(index, byte) for index, byte in enumerate(raw) if byte > 0x7F]
                self.assertEqual(non_ascii[:3], [],
                                 "%s contains non-ASCII bytes" % os.path.basename(path))


if __name__ == "__main__":
    if "--table" in sys.argv:
        sys.argv.remove("--table")
        print_table()
        sys.exit(0)
    unittest.main(verbosity=2)
