# TASK: MAZA Wallet Android UX upgrade — branded, multi-view, timestamps

Upgrade the EXISTING app at `android/src/com/mazawallet/MainActivity.java`
(+ `android/AndroidManifest.xml`, `android/res/`). Rewrite MainActivity for a
proper multi-view mobile wallet UX. Create NO other files. No git commands.
Pure ASCII. No external libraries — android.jar APIs only.

## Branding

- `android/res/drawable-nodpi/logo.png` EXISTS (the official MazaCoin roundel,
  square with black background). Use it: header logo (48dp) at the top of
  every view, and as the app's launcher icon is already wired — leave mipmap
  alone.
- Brand colors: amber #f0a000 accents, near-black #141414 background,
  #1e1e1e cards, white text, muted #b3b3b3 secondary, #6fd66f receive,
  #ff6b6b send/error. WCAG AA contrast everywhere.

## Navigation — bottom tab bar, one view per tab

Four tabs, ALWAYS visible at the bottom in the wallet session:
`BALANCE` / `RECEIVE` / `SEND` / `HISTORY`.

- Implement as a horizontal LinearLayout of 4 equal-weight Buttons pinned to
  the screen bottom (programmatic — no XML layouts); selected tab gets the
  amber text color, others muted. Tapping a tab swaps the content area above
  it (ViewFlipper or manual View visibility — your choice, keep it simple).
- Tab state survives /api/state polls (do not rebuild the tab bar on poll).

## Views

1. **BALANCE** (default): logo + "MAZA Wallet" header, big balance
   `<balance> MAZA`, small line `account mobile-play · fee 0.0001 MAZA`,
   last-sync timestamp, REFRESH button.
2. **RECEIVE**: the address in monospace (wrap), COPY button
   (ClipboardManager + "Copied" toast/inline), the QR
   (`/api/qr.png` Bearer-authed bitmap, ~320dp).
3. **SEND**: To address EditText (monospace), Amount EditText
   (numberDecimal), fee hint `fee 0.0001 MAZA`, SEND button; result line:
   success = shortened txid; error = backend error message. Disable while
   in flight.
4. **HISTORY**: one row per transaction, NEWEST FIRST, each row showing:
   - direction glyph: `←` received / `→` sent
   - signed amount: `+2.5` green / `-1.0` red
   - ABSOLUTE timestamp: `yyyy-MM-dd HH:mm` in the device's local time zone
     (from the unix `time` field; use SimpleDateFormat)
   - relative time in a muted smaller line: "3m ago" / "2h 15m ago" /
     "5d ago" (compute from System.currentTimeMillis)
   - confirmations: "3 confs" (or "unconfirmed" when 0)
   - empty state: "No transactions yet"

## Unchanged contract & behavior

- Same backend API (Bearer on every request, /api/unlock, /api/state,
  /api/send, /api/qr.png). Token entered on the Connect card, memory-only,
  NEVER in URLs, never persisted. 401 anywhere → Connect card.
- Poll /api/state every 15s while unlocked; keep the manual refresh.
- Connect card: server URL (default `http://100.121.150.22:18701`) + token,
  manual CONNECT only — no auto-connect, no default token.

## Verify before finishing

- Self-review: every view reachable via its tab; no view unreachable; ASCII
  only; no external URLs; no `?t=` auth anywhere; timestamps use the device
  local timezone.
- Report a summary of what changed.
