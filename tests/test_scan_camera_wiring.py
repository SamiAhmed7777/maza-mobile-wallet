#!/usr/bin/env python3
"""Wiring contract for M8b code half one: the camera scan surface.

The decision MATH (every ScanFlowPolicy row) is covered BEHAVIORALLY in
crypto/SelfTest.java scanFlowChecks() - 10 checks driving the policy on the
desktop JVM; the origin discipline of the scanned PAYLOAD is covered by
ScanOrigin.parse's own rows (M8a).

This file pins what SelfTest cannot: the d8 nested-class shape (the camera's
platform-typed callbacks are TOP-LEVEL classes - the S-2b-ii bisect proved
nested platform supertypes crash dexing), the origin discipline in source
(the ONLY consumer of decoder output is ScanOrigin.parse; the engine never
fetches/opens/stores anything), the QR-only decode configuration, the
manifest permission (CAMERA declared, runtime-requested by the policy flow),
and the lifecycle hooks (lock cover / pause / destroy / rebuild release the
camera).
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "android", "src", "com", "mazawallet")
SCANNER = os.path.join(SRC, "QrScanner.java")
CALLBACKS = os.path.join(SRC, "QrCallbacks.java")
MAIN = os.path.join(SRC, "MainActivity.java")
POLICY = os.path.join(SRC, "crypto", "ScanFlowPolicy.java")
MANIFEST = os.path.join(REPO, "android", "AndroidManifest.xml")
STRINGS = os.path.join(REPO, "android", "res", "values", "strings.xml")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TopLevelShape(unittest.TestCase):
    """d8 8.2.2-dev bisect (S-2b-ii): ANY nested class whose direct supertype
    resolves to a platform class NPEs during dexing. The camera callbacks are
    exactly that shape - they must stay top-level."""

    def test_scanner_is_top_level_without_platform_supertype(self):
        src = read(SCANNER)
        decl = re.search(r"public final class QrScanner[^{]*\{", src)
        self.assertIsNotNone(decl, "QrScanner class declaration not found")
        self.assertNotIn("extends Camera", decl.group(0))
        self.assertNotIn("implements android", decl.group(0))
        self.assertNotIn("implements SurfaceHolder", decl.group(0))
        self.assertNotIn("implements ImageReader", decl.group(0))

    def test_callbacks_file_declares_three_top_level_classes(self):
        src = read(CALLBACKS)
        for pat, what in [
            (r"^class QrDeviceCallback extends CameraDevice\.StateCallback \{",
             "QrDeviceCallback extends CameraDevice.StateCallback"),
            (r"^class QrSessionCallback extends CameraCaptureSession\.StateCallback \{",
             "QrSessionCallback extends CameraCaptureSession.StateCallback"),
            (r"^class QrSurfaceCallback implements SurfaceHolder\.Callback \{",
             "QrSurfaceCallback implements SurfaceHolder.Callback"),
        ]:
            self.assertIsNotNone(re.search(pat, src, re.M),
                                 "missing top-level: " + what)

    def test_callbacks_are_package_private_top_level_not_nested(self):
        # column-0 'class' lines only: a nested copy would be indented.
        src = read(CALLBACKS)
        decls = [l for l in src.splitlines()
                 if re.match(r"^(final )?class ", l)]
        self.assertEqual(len(decls), 3,
                         "QrCallbacks.java must hold exactly the three "
                         "top-level callback classes, got: %r" % decls)

    def test_scanner_declares_no_nested_platform_supertype(self):
        src = read(SCANNER)
        for m in re.finditer(r"\bclass\s+(\w+)[^{]*\{", src):
            seg = m.group(0)
            if m.group(1) == "QrScanner":
                continue
            self.assertNotIn("extends Camera", seg,
                             "nested class with platform supertype: " + seg)
            self.assertNotIn("implements android", seg)

    def test_rotation_math_lives_in_pure_lumarotate(self):
        """Judge r1 blocker fix: the CCW rotation is a PURE class with the
        W-1-r bound (the old h-1-r form crashed every portrait frame on a
        640x480 landscape buffer), desktop-tested in SelfTest."""
        lr = read(os.path.join(SRC, "crypto", "LumaRotate.java"))
        self.assertNotIn("import android", lr)
        self.assertIn("src[c * w + (w - 1 - r)]", lr,
                      "the CCW source column bound must be W-1-r")
        self.assertNotIn("h - 1 - r", lr, "the buggy index must stay gone")
        src = read(SCANNER)
        self.assertIn("import com.mazawallet.crypto.LumaRotate;", src)
        self.assertNotIn("byte[] rotate90(", src,
                         "the rotation must live only in LumaRotate")

    def test_selftest_pins_the_rotation_math(self):
        st = read(os.path.join(SRC, "crypto", "SelfTest.java"))
        self.assertIn("lumaRotateChecks", st)
        self.assertIn("640x480 landscape rotates without OOB", st,
                      "the blocker shape must stay a pinned regression row")

    def test_decode_attempt_is_guarded_skip_not_crash(self):
        src = read(SCANNER)
        # the per-attempt block wraps rotation AND decode; a RuntimeException
        # inside skips only that attempt
        decode_fn = src[src.index("private void decode(Image img)"):]
        head = decode_fn[:decode_fn.index("private void report(")]
        self.assertIn("catch (RuntimeException e)", head)
        self.assertIn("decodeStreak", head)

    def test_image_reader_listener_is_a_method_reference(self):
        src = read(SCANNER)
        self.assertIn("setOnImageAvailableListener(this::onImageAvailable",
                      src, "the reader listener must stay a method reference "
                      "(desugared to a top-level synthetic; never a nested "
                      "class implementing the platform interface)")


class OriginDiscipline(unittest.TestCase):
    """The decoder output has exactly ONE consumer: ScanOrigin.parse."""

    def test_mainactivity_routes_decoded_text_through_scan_origin(self):
        src = read(MAIN)
        self.assertIn("ScanOrigin.parse(payloadText)", src)

    def test_scanner_never_fetches_or_opens_content(self):
        src = read(SCANNER)
        for banned in ["java.net", "openConnection", "HttpClient",
                       "startActivity", "new Intent(", "MediaStore",
                       "FileOutputStream", "getExternalStorage", "BitmapFactory",
                       "takePicture", "ImageCapture", "openInputStream"]:
            self.assertNotIn(banned, src,
                             "scan engine must never reference " + banned)

    def test_decode_is_qr_only(self):
        src = read(SCANNER)
        self.assertIn("BarcodeFormat.QR_CODE", src)
        self.assertIn("POSSIBLE_FORMATS", src)

    def test_policy_reject_never_fills_the_field(self):
        main = read(MAIN)
        # The fill branch is gated on r.ok via the policy action; the reject
        # branch writes only the reason to the overlay status.
        self.assertIn("ScanFlowPolicy.FILL_AND_CLOSE", main)
        self.assertIn("scanStatusTv.setText(r.reason)", main)


class PermissionFlow(unittest.TestCase):
    """CAMERA: declared in the manifest, runtime-requested via the policy."""

    def test_manifest_declares_camera_only_addition(self):
        mf = read(MANIFEST)
        perms = sorted(set(re.findall(r"android\.permission\.[A-Z_]+", mf)))
        self.assertEqual(perms, ["android.permission.CAMERA",
                                 "android.permission.INTERNET",
                                 "android.permission.POST_NOTIFICATIONS",
                                 "android.permission.USE_BIOMETRIC"])

    def test_mainactivity_requests_camera_through_policy_rows(self):
        src = read(MAIN)
        self.assertIn("ScanFlowPolicy.onScanTapped(", src)
        self.assertIn("ScanFlowPolicy.onPermissionResult(", src)
        self.assertIn('requestPermissions(\n                    new String[]{"android.permission.CAMERA"}',
                      src)
        self.assertIn("onRequestPermissionsResult", src)

    def test_denied_hint_lives_in_the_policy_not_duplicated(self):
        main = read(MAIN)
        self.assertIn("ScanFlowPolicy.DENIED_HINT", main)
        # exactly one definition site (the policy class)
        self.assertEqual(main.count("Camera permission is needed to scan"), 0,
                         "hint copy must live only in ScanFlowPolicy")


class LifecycleHooks(unittest.TestCase):
    """A locked wallet / backgrounded screen / rebuilt UI holds no camera."""

    def test_show_lock_closes_the_scanner_first(self):
        src = read(MAIN)
        show_lock = src[src.index("private void showLock()"):]
        self.assertLess(show_lock.index("closeScan()"),
                        show_lock.index("lockOverlay.setVisibility(View.VISIBLE)"),
                        "the camera must be released before the cover renders")

    def test_onpause_closes_the_scanner(self):
        src = read(MAIN)
        pause = src[src.index("protected void onPause()"):]
        self.assertLess(pause.index("closeScan()"),
                        pause.index("pinGuard.onBackground()"))

    def test_ondestroy_closes_the_scanner(self):
        src = read(MAIN)
        destroy = src[src.index("protected void onDestroy()"):]
        self.assertIn("closeScan()", destroy)

    def test_wallet_rebuild_closes_the_scanner(self):
        src = read(MAIN)
        build = src[src.index("private void buildWalletUi()"):]
        self.assertIn("closeScan()", build[:build.index("{") + 400],
                      "buildWalletUi (unlock + theme repaint) must drop any "
                      "live scan surface")

    def test_overlay_stacks_below_the_lock_cover(self):
        src = read(MAIN)
        self.assertIn("walletWrap.addView(scanOverlay, 1,", src,
                      "scan overlay must insert at index 1 (above wallet root, "
                      "below the lock cover)")

    def test_listener_shape_is_the_activity_itself(self):
        src = read(MAIN)
        self.assertIn("implements SelfCustody.Host, QrScanner.Listener", src,
                      "the top-level activity implementing OUR OWN interface "
                      "is the d8-safe listener shape")


class OverlayCopy(unittest.TestCase):
    def test_strings_declare_scan_chrome(self):
        src = read(STRINGS)
        self.assertIn('name="scan_hint"', src)
        self.assertIn('name="scan_cancel"', src)

    def test_policy_class_is_pure_java(self):
        src = read(POLICY)
        self.assertNotIn("import android", src)
        self.assertNotIn("import com.google", src)
        self.assertNotIn("import java", src)


if __name__ == "__main__":
    unittest.main()
