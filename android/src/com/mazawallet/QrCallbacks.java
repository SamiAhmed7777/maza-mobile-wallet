package com.mazawallet;

import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraDevice;
import android.view.SurfaceHolder;

/**
 * M8b: the three platform-typed camera callbacks, deliberately TOP-LEVEL
 * package-private classes (d8 8.2.2-dev NPEs while dexing ANY nested class
 * whose direct supertype resolves to a platform class - the S-2b-ii bisect,
 * pinned by tests/test_scan_camera_wiring.py). Each forwards to the
 * package-private handler methods on QrScanner; none carries state.
 */
class QrDeviceCallback extends CameraDevice.StateCallback {
    private final QrScanner scanner;

    QrDeviceCallback(QrScanner scanner) {
        this.scanner = scanner;
    }

    @Override
    public void onOpened(CameraDevice camera) {
        scanner.onDeviceOpened(camera);
    }

    @Override
    public void onDisconnected(CameraDevice camera) {
        try {
            camera.close();
        } catch (RuntimeException ignored) {
            // release-path failure is never user-facing
        }
        scanner.onDeviceError();
    }

    @Override
    public void onError(CameraDevice camera, int error) {
        try {
            camera.close();
        } catch (RuntimeException ignored) {
            // release-path failure is never user-facing
        }
        scanner.onDeviceError();
    }
}

class QrSessionCallback extends CameraCaptureSession.StateCallback {
    private final QrScanner scanner;

    QrSessionCallback(QrScanner scanner) {
        this.scanner = scanner;
    }

    @Override
    public void onConfigured(CameraCaptureSession session) {
        scanner.onSessionConfigured(session);
    }

    @Override
    public void onConfigureFailed(CameraCaptureSession session) {
        try {
            session.close();
        } catch (RuntimeException ignored) {
            // release-path failure is never user-facing
        }
        scanner.onDeviceError();
    }
}

class QrSurfaceCallback implements SurfaceHolder.Callback {
    private final QrScanner scanner;

    QrSurfaceCallback(QrScanner scanner) {
        this.scanner = scanner;
    }

    @Override
    public void surfaceCreated(SurfaceHolder holder) {
        scanner.onSurfaceCreated(holder);
    }

    @Override
    public void surfaceChanged(SurfaceHolder holder, int format, int width, int height) {
        // fixed-size buffer; nothing to reconfigure per layout pass
    }

    @Override
    public void surfaceDestroyed(SurfaceHolder holder) {
        scanner.onSurfaceDestroyed();
    }
}
