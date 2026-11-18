# MAZA Mobile Wallet - user guide

This guide is for people using the MAZA wallet app. It covers install,
first wallet, everyday send/receive, locking, backup, and recovery.
Security details live in `docs/SECURITY.md`; inherited chain parameters
(derivation path, fees, confirmations) live in `DECISIONS.md`.

## 1. What this wallet is

The app has **two money surfaces**, and it labels both so you always know
which one you are using:

- **Bench account (SEND / RECEIVE / BALANCE / HISTORY tabs)** - a custodial
  play wallet run by the server you connect to. The server holds the funds
  and spends from them on your instruction. Sends are capped (50 MAZA per
  send) with a flat 0.0001 MAZA fee.
- **My Wallet (WALLET tab)** - your own self-custody wallet. A 12-word seed
  phrase is generated on your device, keys never leave it, and transactions
  are signed on the device. The server only watches your addresses and
  passes on the signed bytes - it cannot sign or spend from this wallet on
  its own.

Rule of thumb: the SEND tab says "SEND · BENCH ACCOUNT" and spends the
server's play funds; the send card inside the WALLET tab says
"SEND · SELF-CUSTODY" and spends your own seed balance.

## 2. Install and connect

1. Install the APK (from the tester link your operator sent, or build it
   yourself: `bash android/build-apk.sh`).
2. Open the app. You land on the Connect screen.
3. Enter the **server URL** (the app pre-fills the public test endpoint,
   `https://mazatest.sami-host.me`; leave it unless you were told
   otherwise) and the **token** your operator sent you.
4. Tap **Connect**. The token is kept in memory for this session only -
   it is never written to the device, and you re-type it next session.

The default endpoint is ordinary HTTPS on the public internet: it works
from mobile data, Wi-Fi, or any network. No VPN is needed. The endpoint
can be changed later in Settings - SERVER.

## 3. Your seed phrase (My Wallet)

Open the **WALLET** tab. If no wallet exists yet you see two buttons:

- **Create new wallet** - generates a fresh 12-word seed phrase.
- **Import seed phrase** - restores an existing wallet from its 12 words.

**Write the words down on paper, in order, and keep them safe.** The app
shows them once at creation with exactly this warning: anyone with those
words can spend this wallet. There is no password reset and no server
copy - the seed lives only on your device (stored encrypted with a key
that never leaves the phone's secure hardware - envelope and key-custody
evidence in `docs/SECURITY.md` section 3) and on your paper backup.

You can re-check the words later: Settings - WALLET MANAGEMENT -
**Reveal seed phrase** (asks for your PIN; screen capture is blocked while
the words are on screen).

**Set a PIN** (button on the WALLET tab) as soon as you have a seed. Once
a PIN exists it protects the WALLET tab, sending, seed reveal, and wiping.
A wallet without a PIN has no lock - set one.

## 4. Receiving MAZA

- **Into My Wallet (self-custody):** WALLET tab - the RECEIVE ADDRESS card
  shows your current receiving address. Settings - WALLET MANAGEMENT -
  RECEIVE ADDRESSES lists the addresses derived from your seed and marks
  the current one. Give the address (or show its QR) to the sender.
- **Into the bench account:** the RECEIVE tab shows the bench address with
  a Copy button and a QR code. Funds sent here are held by the server.

## 5. Sending MAZA

- **SEND tab (bench account):** enter an address and amount; the server
  spends from its own play wallet. Per-send cap 50 MAZA; fee 0.0001 MAZA.
- **WALLET tab send (self-custody):** enter an address and amount; the app
  builds and signs the transaction on the device and the server just
  broadcasts the signed bytes. Fee 0.0001 MAZA.

Confirmations follow the chain's defaults: one confirmation is enough to
spend, and blocks arrive about once a minute on average (inherited node
parameters - see `DECISIONS.md`), so a normal send settles within a
couple of minutes. HISTORY (bench) and the WALLET tab's history list both
show incoming and outgoing transactions with timestamps.

**The one rule that protects your money:** if a send ends in an unclear
state ("Send not confirmed ..."), the app tells you to **check HISTORY
before trying again** - the transaction may already be on its way, and
sending twice sends twice. Never re-tap a send because it seemed slow.

## 6. Locking the wallet

- **PIN cover:** with a PIN set, the wallet locks behind a PIN pad. Wrong
  PINs trigger an escalating wait (each streak of failures doubles the
  lockout), and a locked wallet cannot be used until the correct PIN is
  entered.
- **Auto-lock:** the wallet locks after a period of inactivity (default
  5 minutes) and after being in the background that long. Change the
  delay in Settings - AUTO-LOCK (5/10/30 minutes); it applies
  immediately, including to the session you are in.
- **Biometric:** on devices that support it (Android 10+ with an enrolled
  fingerprint or face), the lock screen offers "Unlock with biometrics".
  The PIN pad is always available as the fallback ("Use PIN"). Inside the
  wallet, protected actions (sending, seed reveal, create/import, wipe)
  use the PIN.

## 7. Settings reference

| Section | What it does |
| --- | --- |
| SERVER | The URL the Connect screen uses. Save, then reconnect to apply. |
| AUTO-LOCK | Minutes of inactivity (and background time) before the wallet locks. Applies immediately. |
| APPEARANCE | System / Light / Dark. System follows the device's day/night setting, switching live. |
| WALLET MANAGEMENT | Receive addresses, reveal seed phrase (PIN-gated), and wipe. Wipe deletes the seed phrase, the PIN, the endpoint, and all settings from the device. |

**Wipe wallet** deletes the seed phrase, the PIN, the endpoint, and all
settings from the device. It asks twice, makes you type WIPE, and then
re-verifies your current PIN before doing anything. Funds are gone from
the device - recoverable only from your written seed. Never wipe without
your seed written down.

## 8. Backup and recovery (lost-phone drill)

Your wallet is your seed phrase. Losing the phone does not lose the
money if you have the 12 words.

1. Install the app on the new device.
2. Connect (same server URL and token as before).
3. WALLET tab - **Import seed phrase** - enter the 12 words in order.
4. Set a PIN again. The app re-derives all its addresses from the seed
   and tells the server to watch them again.
5. Balances and history appear for your addresses once the server has
   them under watch and the chain data is available.

If you lose the phone AND the seed, the funds are not recoverable. This
is why the words go on paper before anything else.

## 9. When something looks wrong

The app always tells you what happened instead of failing silently:

- "No network connection" / "did not answer in time" / "Cannot reach the
  server" - the phone cannot get to the server; check connectivity, then
  retry. Reads (balance, history) retry automatically a few times.
- "Invalid token" / "Session expired" - re-enter the token (Connect
  screen). Tokens are per-session by design.
- "Server error (HTTP N)" - the server had a problem; try again shortly.
- "Update failed ... showing the last loaded balance" - stale display;
  the balance refreshes on the next successful sync.
- After any spend attempt with an unclear result: **check HISTORY first**
  (section 5).

Balances read through the connected server. If a balance looks wrong,
confirm the server itself is healthy before troubleshooting the phone.

## 10. Security model in brief

- Self-custody surface: the seed and every private key stay on the device
  (encrypted at rest, key in the phone's secure hardware). The server
  only watches addresses and broadcasts signed bytes - it cannot move
  self-custody funds on its own.
- Bench surface: the token you type authorizes the server to spend its
  own capped play wallet. Treat the token like cash for that account;
  it is delivered to you privately, kept in memory only, and never
  written to the device.
- Full threat model (device theft, server compromise, endpoint attacks)
  and the evidence behind each claim: `docs/SECURITY.md`.

## 11. Current limitations

- Biometric unlock is offered only on the lock screen and only on
  Android 10+ devices with biometrics enrolled; everything inside the
  wallet is PIN-based.
- QR camera scanning is in the app from 2026-11-17 (SEND tab "Scan QR":
  the camera reads a MAZA QR and the validated address lands in the
  recipient field; scanned content is never opened as a link). Since
  the M9 code landed, a `maza:` payment URI (with `?amount=`) fills
  BOTH the recipient and the amount field — you still confirm the send
  yourself; nothing is ever auto-sent from a scan. The Request-amount
  receive screen (generating a `maza:` request QR), testnet mode, and
  receive notifications are not in the app yet (see `README.md` - What
  works today, and `docs/SPEC-AUDIT.md` for the plan).
- The bench account is a shared capped play wallet for testing, not a
  place to hold real amounts.
