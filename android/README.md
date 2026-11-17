# MAZA Wallet — Android app

Native single-Activity app (no external libraries, programmatic UI)
talking to a walletbench API over HTTPS (a LAN or SSH-tunnel endpoint may
use plain HTTP on a trusted local transport).

## Connect flow

- **Server URL** — pre-filled with the maintainers' public TEST endpoint
  `https://mazatest.sami-host.me`; the field is user-editable, so any
  walletbench host works (your own instance on a LAN, an SSH tunnel, a
  reverse proxy — whatever you self-host; see the repo README Quickstart).
- **Token** — the bench token for that endpoint, delivered out of band by
  whoever runs it. Entered EVERY app start: the token is intentionally
  memory-only — it unlocks send access and is never persisted to storage.
  Only the server URL is saved in SharedPreferences.

## Auth

Every request (GET and POST) carries `Authorization: Bearer <token>`. The
token never appears in URLs. The backend accepts no URL-borne credentials
at all (query-param auth was removed — regression-tested).

## Wallet tabs

- **BALANCE / RECEIVE / HISTORY** — the watched wallet view (UTXOs,
  receive addresses + QR, transaction history).
- **SEND** — sends from the custodial bench account (server-side funds,
  capped; the header says so).
- **WALLET** — the self-custody wallet: seed create/import, its own send
  form (signed on-device from your own seed balance), seed reveal.

## Build

`bash android/build-apk.sh` — aapt2/javac/d8/apksigner against an Android
SDK (build-tools 34, platform android-34) on JDK 21. Stage 1 of the build
is the crypto selftest gate: any vector FAIL aborts before packaging.
Bench builds sign with the repo-local debug keystore (bench-only);
`bash android/build-apk.sh --release` signs with the maintainer release
keystore (paths + env overrides documented in the script header). The
manifest declares versionCode/versionName and minSdk 24 / targetSdk 34 —
REQUIRED: missing version attributes crash BlueStacks' host UI on install
(0xC0000409) and manifest as installs that "succeed then wipe themselves".
