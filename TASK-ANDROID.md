# TASK: Native Android wallet app (bench edition) — maza-mobile-wallet/android/

Create ONLY these files under android/ in the repo root:

- android/AndroidManifest.xml
- android/src/com/mazawallet/MainActivity.java
- android/build.gradle        (metadata only; the build uses aapt2 directly)
- android/README.md           (how it maps to the API)

No other files. No git commands. Pure ASCII. NO external libraries — only
android.jar APIs (org.json is available; java.net.HttpURLConnection for HTTP;
java.util.prefs/SharedPreferences for storage).

## App behavior

Single-Activity app, all UI built PROGRAMMATICALLY (no XML layouts — skip
setContentView; construct layouts in code).

First run (no saved token): "Connect" card with two EditTexts —
- Server URL (pre-filled default `http://100.121.150.22:18701 (DNS2 tunnel; direct samihost tailnet IP is ACL-blocked for non-granted ports)`, editable)
- Token (password-style input; entered every app start — the token is
  intentionally NOT persisted, it unlocks send access)
- Connect button → POST {url}/api/unlock {"token": ...} on a background
  thread; 200 → save the server URL in SharedPreferences (the token stays in
  memory only), show wallet view;
  401/error → inline error text.

Wallet view (after unlock):
1. Header: "MAZA Wallet" + a small coin glyph TextView (no image needed).
2. Balance TextView, large, e.g. "50.0 MAZA".
3. Receive card: address in monospace, "Copy" button (ClipboardManager),
   and a QR ImageView that loads `{url}/api/qr.png` (BitmapFactory.decodeStream
   over an HttpURLConnection carrying the Bearer header — the token must
   never appear in URLs).
4. Send card: To-address EditText (monospace), Amount EditText (inputType
   numberDecimal), Send button. Result line shows shortened txid or the
   error message from the 400 body {"error": ...}. Disable Send while a
   request is in flight.
5. History: a LinearLayout list (programmatic rows — no ListView adapter
   complexity needed, max 30 rows): each row "→ -1.5 MAZA (3 confs)" or
   "← +2.0 MAZA (12 confs)" with relative time.
6. Refresh button + auto-poll /api/state every 15s. On 401 → back to the
   Connect card (clear saved token).

## Backend contract (already deployed — do not implement it)

- POST /api/unlock  {"token": "..."} → 200 + Set-Cookie, or 401.
  IMPORTANT: the app has no cookie jar — send
  `Authorization: Bearer <token>` on EVERY request (GETs and POSTs).
  NEVER put the token in URLs.
- GET /api/state (Bearer header) →
  {"balance": float, "address": "M..34", "account": str, "fee": float,
   "txs": [{"category":"receive"|"send","amount": float (signed),
            "confirmations": int, "time": unix-int, "address": str}]}
- POST /api/send  {"to": "...", "amount": float} + Bearer header →
  {"txid": "64hex"} or 400 {"error": "..."} or 401.
- GET /api/qr.png (Bearer header) → image/png QR of the receive address.

## Constraints

- minSdk 24, targetSdk 34, package com.mazawallet.
- Manifest: android:usesCleartextTraffic="true" (bench runs plain HTTP on the
  tailnet), INTERNET permission, an application label "MAZA Wallet", and
  ic_launcher referencing @mipmap/ic_launcher.
- All network I/O off the main thread (Thread + runOnUiThread or executor).
- Handle malformed JSON / unreachable host gracefully (inline error text).
- Java 8/11-compatible syntax. Pure ASCII. Concise, no dead code.

## Verify before finishing

- javac syntax check if a JDK is present (classes will not resolve without
  android.jar — in that case do a careful manual review instead and SAY SO).
- Print a short summary of the files created and any assumptions.
