# TASK: MAZA wallet bench frontend (v0)

Build the mobile wallet web UI for the MAZA wallet bench service. Create ONLY
these files (relative to repo root):

- walletbench/templates/wallet.html
- walletbench/static/wallet.js
- walletbench/static/style.css

Do NOT touch any other file. No git commands. No network fetches at build
time, and NO external resources at runtime (no CDN links — the page CSP is
`default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self';
connect-src 'self'`).

## Runtime API contract (the backend already exists — do not implement it)

- `POST /api/unlock` body `{"token":"..."}` → 200 (cookie set) or
  `401 {"error":"invalid token"}`
- `GET /api/state` → `401` if locked, else
  `{"balance": <float MAZA>, "address": "M...34chars", "account": "mobile-play",
    "txs": [{"category":"receive"|"send","amount":<float signed>,"confirmations":<int>,
             "time":<unix int>, "address":"M..."}]}` (txs newest first, may be empty)
- `POST /api/send` body `{"to":"M...","amount":<float>}` →
  `200 {"txid":"<64 hex>"}` or `400 {"error":"<human message>"}`
- `GET /api/qr.svg` → `image/svg+xml` QR encoding the current receive address
- `GET /static/icon.png` → app icon (asset supplied separately; reference it as
  the page icon, tolerate 404 gracefully)

## UI requirements

- Mobile-first single page, dark theme: background near-black #141414, cards
  #1e1e1e, accent amber #f0a000 (official MazaCoin brand amber). All text
  must meet WCAG AA contrast (>=4.5:1) against its rendered surface.
- Locked state: centered card with token input + Unlock button. On 401 show
  the error inline. On success, swap to wallet view (store nothing in
  localStorage; keep state in memory only).
- Wallet view:
  1. Header: icon.png + "MAZA Wallet" wordmark text.
  2. Balance card: big balance number + " MAZA", subtle "unconfirmed amounts
     included" is NOT needed — just show balance from /api/state.
  3. Receive card: the address in a monospace, wrap-anywhere block + the QR
     (`<img src="/api/qr.svg">`, ~180px) + a Copy button using
     navigator.clipboard (fallback: select text).
  4. Send card: "To address" input (monospace), "Amount (MAZA)" numeric input,
     Send button; result line shows txid (shortened, monospace) on success or
     the error message on 400. Disable the button while a send is in flight.
  5. History card: list txs (newest first): direction arrow (← received /
     → sent), amount with sign, confirmations count ("3 confs"), human
     relative time from the unix timestamp. Empty state: "No transactions yet".
- Poll /api/state every 15s while unlocked; a manual Refresh button too.
- Handle 401 on any poll by returning to the locked state silently.
- Buttons disabled while requests are in flight; show a small "…" busy state.
- All copy in English, concise. No lorem ipsum, no placeholders left in code.

## Style constraints

- Vanilla HTML/CSS/JS only (ES2019-safe, no build step, no frameworks).
- Pure ASCII in all files.
- wallet.js reads nothing from the DOM except its own ids/classes; keep ids
  stable and descriptive (balance-value, address-text, qr-img, send-to,
  send-amount, send-btn, send-result, tx-list, unlock-card, wallet-view,
  token-input, unlock-btn, unlock-error, refresh-btn).

## Verify before finishing

- Open the three files and self-check: no external URLs, ASCII only, every
  id listed above exists, JS has no syntax errors (node --check wallet.js if
  node is available; otherwise careful manual review), HTML references the
  correct paths (/static/wallet.js, /static/style.css, /api/qr.svg).
- Print a short summary of what you created.
