#!/usr/bin/env python3
"""Wiring contract for M8a: the ScanOrigin policy + the vendored zxing jar.

The decision MATH (every accepted/rejected scanned-content shape) is covered
BEHAVIORALLY in crypto/SelfTest.java scanOriginChecks() — 18 checks driving
ScanOrigin.parse on the desktop JVM with vector-derived + real-mainnet
addresses.

This file pins what SelfTest cannot: the jar supply-chain (pin files match
the shipped bytes, jar content census), the build wiring (the gate runs on
EVERY build, javac sees the jar, d8 packages it), the policy's origin
discipline in source (no URL fetch, no zxing import in the policy itself,
plain POJO nested result per the d8 nested-class rule), and the licensing
documentation honesty (DEPENDENCY-LICENSES.md names the artifact + pin).
"""
import hashlib
import os
import unittest
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY = os.path.join(REPO, "android", "src", "com", "mazawallet",
                      "crypto", "ScanOrigin.java")
SELFTEST = os.path.join(REPO, "android", "src", "com", "mazawallet",
                        "crypto", "SelfTest.java")
BUILD = os.path.join(REPO, "android", "build-apk.sh")
VENDORDIR = os.path.join(REPO, "android", "vendor")

# Single source of truth for the vendored version: every artifact that
# names the jar (build script, NOTICE, pin files) is asserted against THIS
# constant, so a version bump that misses one surface fails here first.
ZXING_VERSION = "3.5.3"
JAR_BASENAME = "zxing-core-%s.jar" % ZXING_VERSION

JAR = os.path.join(VENDORDIR, JAR_BASENAME)
JAR_SHA = os.path.join(VENDORDIR, JAR_BASENAME + ".sha256")
JAR_UPSTREAM_SHA1 = os.path.join(VENDORDIR, JAR_BASENAME + ".upstream-sha1")
NOTICE = os.path.join(VENDORDIR, "NOTICE.txt")
LICENSE = os.path.join(VENDORDIR, "LICENSE-zxing.txt")
DEPS = os.path.join(REPO, "docs", "DEPENDENCY-LICENSES.md")

EXPECTED_SHA256 = ("8d8064c1636fdaef7189dd9055c7d59950a8940a12f2293956"
                   "446ec3c109fd82")
EXPECTED_UPSTREAM_SHA1 = "ca1349214a356cd7958651b2d5a0e1f3811a9c4b"


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class ScanOriginPurity(unittest.TestCase):
    def test_policy_is_pure_java_and_never_imports_the_decoder(self):
        """Desktop selftest compiles this package; the policy classifies
        PAYLOAD TEXT only — com.google.zxing stays out of it entirely (the
        M8b scanner shell owns the decode-object side)."""
        src = read(POLICY)
        imports = [ln for ln in src.splitlines()
                   if ln.strip().startswith("import ")]
        self.assertFalse([ln for ln in imports if "android" in ln],
                         "ScanOrigin must stay pure Java: android imports %r"
                         % imports)
        self.assertFalse([ln for ln in imports if "zxing" in ln],
                         "ScanOrigin must not import the decoder: %r"
                         % imports)
        self.assertIn("class ScanOrigin", src)
        self.assertIn("public static final int MAX_LENGTH = 200;", src,
                      "length cap before decode work")
        self.assertIn("public static Result parse(String scanned)", src)

    def test_origin_discipline_rules_in_source(self):
        src = read(POLICY)
        self.assertIn('"URLs are never opened or fetched"', src,
                      "explicit no-fetch rule")
        self.assertIn('"Unsupported URI scheme - content is never opened"',
                      src, "unknown schemes rejected")
        self.assertIn("MazaUri.parse(s)", src,
                      "maza: params now parse via the M9 MazaUri contract")
        self.assertIn('"Multi-line content rejected"', src)
        # the address contract must match the send path exactly
        self.assertIn("Bip44Maza.ADDRESS_VERSION", src)
        self.assertIn("payload.length != 21", src)

    def test_nested_result_is_plain_pojo(self):
        """d8 nested-class rule: nested classes with a PLATFORM supertype
        crash dexing; plain POJOs extending Object are proven (Bip32.Node,
        TxBuilder.Output ship today). Pin Result as the safe shape."""
        src = read(POLICY)
        self.assertIn("public static final class Result", src)
        self.assertNotIn("extends", src.split("class Result", 1)[1]
                         .split("{", 1)[0],
                         "Result must extend Object (no supertype)")

    def test_selftest_drives_the_policy_behaviorally(self):
        st = read(SELFTEST)
        self.assertIn('section("ScanOrigin origin discipline '
                      '(M8a QR scan policy)")', st)
        self.assertIn("scanOriginChecks();", st)
        self.assertIn("private static void scanOriginChecks()", st)
        self.assertIn("ScanOrigin.parse(", st)
        # vector-derived positive + real mainnet anchor both present
        self.assertIn("MLhJ8cs5sG8YY6YcMs5rmqCV6hZjqF7LEE", st)
        self.assertIn("MWRVvgWrLRqyEEQSm7J8NuYor1X9J4J9Fa", st)


class VendorJarSupplyChain(unittest.TestCase):
    def test_pin_files_match_shipped_bytes(self):
        self.assertTrue(os.path.isfile(JAR), "vendored jar missing")
        data = open(JAR, "rb").read()
        self.assertEqual(hashlib.sha256(data).hexdigest(), EXPECTED_SHA256,
                         "shipped jar bytes != documented pin")
        pin = read(JAR_SHA).strip()
        self.assertEqual(pin, EXPECTED_SHA256,
                         "pin file disagrees with the documented sha256")
        upstream = read(JAR_UPSTREAM_SHA1).strip()
        self.assertEqual(upstream, EXPECTED_UPSTREAM_SHA1,
                         "upstream Maven .sha1 capture changed")

    def test_jar_content_census(self):
        z = zipfile.ZipFile(JAR)
        names = z.namelist()
        # FILES must live under the zxing namespace or META-INF; DIRECTORY
        # entries may only be their namespace parents (com/, com/google/).
        stray_files = [n for n in names
                       if not n.endswith("/")
                       and not (n.startswith("com/google/zxing")
                                or n.startswith("META-INF/"))]
        self.assertEqual([], stray_files,
                         "file entries outside zxing/META-INF: %r"
                         % stray_files[:5])
        stray_dirs = [n for n in names if n.endswith("/")
                      and not n.startswith("com/")
                      and not n.startswith("META-INF/")]
        self.assertEqual([], stray_dirs,
                         "directory entries outside the namespaces: %r"
                         % stray_dirs[:5])
        natives = [n for n in names
                   if n.endswith((".so", ".exe", ".dll", ".sh"))]
        self.assertEqual([], natives, "executables/natives in jar: %r"
                         % natives)
        meta = [n for n in names if n.startswith("META-INF/")]
        # license text must be VENDORED BESIDE the jar (jar carries none)
        self.assertNotIn("META-INF/LICENSE", meta)
        self.assertTrue(os.path.isfile(LICENSE))
        self.assertIn("Apache License", read(LICENSE)[:200])
        self.assertTrue(os.path.isfile(NOTICE))
        notice = read(NOTICE)
        self.assertIn("repo1.maven.org", notice)
        self.assertIn(EXPECTED_SHA256[:32], notice)
        self.assertIn("Apache-2.0", notice)

    def test_build_script_gates_and_wiring(self):
        b = read(BUILD)
        # version-drift guard: the build script must name EXACTLY the
        # version this test pins (JAR/JAR_SHA are derived from the constant)
        self.assertIn(JAR_BASENAME, b)
        self.assertIn(JAR_BASENAME + ".sha256", b)
        self.assertIn("FATAL: vendored zxing jar missing", b,
                      "missing-jar gate")
        self.assertIn("FATAL: vendored zxing jar sha256 mismatch", b,
                      "pin-mismatch gate")
        self.assertIn('-classpath "$PLATFORM:$VENDOR_JAR"', b,
                      "javac compiles against the jar")
        self.assertIn('"${CLASS_FILES[@]}" "$VENDOR_JAR"', b,
                      "d8 packages the jar into classes.dex")
        # the gate must run BEFORE packaging (before the aapt2 stage)
        gate_at = b.index("FATAL: vendored zxing jar missing")
        stage2_at = b.index('stage 2 "aapt2 compile"')
        self.assertLess(gate_at, stage2_at,
                        "supply-chain gate must precede any packaging stage")

    def test_licensing_doc_names_the_artifact(self):
        d = read(DEPS)
        self.assertIn("zxing-core-3.5.3.jar", d)
        self.assertIn(EXPECTED_SHA256, d,
                      "the report must carry the exact pinned sha256")
        self.assertIn("Apache-2.0", d)


if __name__ == "__main__":
    unittest.main()
