# MAZA Wallet — Android bench app

Native single-Activity app (no external libraries, programmatic UI) talking
to the walletbench API on the tailnet.

## Connect flow

- **Server URL** — pre-filled with `http://100.121.150.22:18701`, the DNS2
  tunnel endpoint (`deploy/maza-bench-tunnel.service`, bound to DNS2's
  tailnet IP only; it forwards to the bench service on samihost). The
  samihost tailnet IP directly (100.98.140.83:18701) is blocked by the
  tailnet ACL for non-granted ports.
- **Token** — the unlock token (delivered by DM). Entered EVERY app start:
  the token is intentionally memory-only — it unlocks send access and is
  never persisted to storage. Only the server URL is saved in
  SharedPreferences.

## Auth

Every request (GET and POST) carries `Authorization: Bearer <token>`. The
token never appears in URLs. The backend accepts no URL-borne credentials
at all (query-param auth was removed — regression-tested).

## Build

`bash android/build-apk.sh` — aapt2/javac/d8/apksigner against
`/opt/android-sdk` (build-tools 34, platform android-34). Signed with the
repo-local debug keystore (pass mazabench). The manifest declares
versionCode/versionName and minSdk 24 / targetSdk 34 — REQUIRED: missing
version attributes crash BlueStacks' host UI on install (0xC0000409) and
manifest as installs that "succeed then wipe themselves".
