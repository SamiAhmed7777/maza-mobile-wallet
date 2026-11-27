package com.mazawallet.crypto;

/**
 * Scan-flow decision table (M8b code half one). Pure Java, no Android or
 * zxing imports: the desktop selftest drives every row (SelfTest.scanFlowChecks).
 *
 * MainActivity applies the returned action verbatim:
 *  - TAPPING the Scan button: with the CAMERA permission granted the scan
 *    overlay opens; without it the runtime permission request fires (the
 *    request lands WITH the surface - the overlay opens immediately on grant).
 *  - The permission RESULT: grant opens the overlay; a denial keeps the send
 *    form usable and shows a user-safe hint (the typed address path is the
 *    full-featured fallback, never a dead end).
 *  - A DECODED payload always goes through ScanOrigin.parse first (the
 *    origin-discipline contract, M8a): only a validated MAZA address fills
 *    the SEND field and closes the scanner; any rejection shows the reason
 *    on the overlay and KEEPS scanning (the user re-aims, nothing hostile
 *    ever reaches the form).
 *
 * The camera itself is never opened by this class; it carries no content
 * and no state beyond the decision rows.
 */
public final class ScanFlowPolicy {

    public static final int OPEN_SCAN = 0;    // show the scan overlay now
    public static final int REQUEST_PERM = 1; // fire the CAMERA runtime request
    public static final int SHOW_HINT = 2;    // inline user-safe copy, stay on SEND
    public static final int FILL_AND_CLOSE = 3; // write address into SEND, close overlay
    public static final int KEEP_SCANNING = 4;  // show reason on overlay, keep camera live
    public static final int DETACH_OVERLAY = 5;   // M30: remove overlay, re-enable send form
    public static final int RELEASE_OFF_MAIN = 6; // M30: schedule scanner release off-main

    /** User-safe copy for a denied CAMERA permission (never mentions
     *  internals; points at the typed-address fallback). */
    public static final String DENIED_HINT =
            "Camera permission is needed to scan. You can still type the address.";

    private ScanFlowPolicy() { }

    /** Row 1: the Scan button was tapped on the SEND tab. */
    public static int onScanTapped(boolean cameraPermissionGranted) {
        return cameraPermissionGranted ? OPEN_SCAN : REQUEST_PERM;
    }

    /** Row 2: the CAMERA runtime request returned. */
    public static int onPermissionResult(boolean granted) {
        return granted ? OPEN_SCAN : SHOW_HINT;
    }

    /** Row 3: the decoder produced payload text (already passed through
     *  ScanOrigin.parse by the caller - the ok flag here IS that verdict). */
    public static int onDecoded(boolean scanOriginAccepted) {
        return scanOriginAccepted ? FILL_AND_CLOSE : KEEP_SCANNING;
    }

    /** Row 4 (M30): any scan close request - CANCEL tap, accepted decode,
     *  lock cover, pause, destroy, rebuild. Returns the MANDATORY ORDER of
     *  the two close steps: the overlay detaches and the send form re-enables
     *  BEFORE the scanner release is scheduled, and the release itself must
     *  run OFF the main thread. A wedged camera close (witnessed on the
     *  emulator 2026-11-27: CameraCaptureSession.close() never returned) can
     *  then never freeze the UI or stop the balance/history poll. */
    public static int[] onCloseScanRequested() {
        return new int[]{DETACH_OVERLAY, RELEASE_OFF_MAIN};
    }
}
