# MAZA Mobile Wallet — Decisions (all inherited from existing wallet code)

Rule (Sami, 2026-11-15): "For all of the decisions just choose what already
exists in the wallet code." No invented policy. Source of truth: MazaCoin/maza
HEAD 326935b (= tag v0.16.3, 2022-01-13) — the code our samihost node runs.
Komodo's coins-config MAZA profile is NOT the source of truth; it deviates from
chain code on three fields (noted per item).

## D1 — Confirmation policy
- Incoming tx trusted/spendable at **1 confirmation** (`CWalletTx::IsTrusted`,
  src/wallet/wallet.cpp:1954; own change may count at 0 via code default
  `-spendzeroconfchange=1`).
- UI badge: "Confirming (n of 6 recommended)" until **6**
  (`RecommendedNumConfirmations = 6`, src/qt/transactionrecord.h:89).
- Mobile wallet mirrors: spend at 1 conf, badge until 6. NOT Komodo's 3.

## D2 — Trust model (light client)
- On-device SPV is ruled out BY THE CODE: current-era header validation needs
  MinotaurX + Hive PoW, and Hive consensus requires chain state
  (`BeePopGraph`, src/pow.cpp:22) that a header-only client cannot rebuild.
- Adopt the light-client pattern that already exists for MAZA: Electrum-style
  server merkle proofs (precedent: mazaclub/tate + tate-server, 2015).
- We run the indexer next to the existing samihost `mazad` (RPC 127.0.0.1:12832).
- Header pinning follows the code's own checkpoint pattern
  (`checkpointData`, chainparams.cpp:185; mainnet latest embedded checkpoint
  height 2036783).
- Finding (2026-11-16): block IDENTITY hash is double-SHA256 for every block
  regardless of PoW algo (primitives/block.cpp:18-21 `GetHash()` =
  `SerializeHash`; verified live on genuine minotaurx type-1 blocks) —
  MinotaurX/Hive affect mining VALIDITY only. The indexer needs no PoW-hash
  oracle; PoW validation stays the daemon's job, as for every ElectrumX
  fork. Client-side (SPV) validation remains ruled out per the hive-state
  argument above.

## D3 — Keys, addresses, derivation
- P2PKH pubtype **50** (addresses start "M"), P2SH **9**, bech32 HRP **"maza"**
  (chainparams.cpp:171-177).
- WIF version **224** per chain code (chainparams.cpp:173). NOTE: Komodo config
  says 244 — discrepancy; code wins per rule. Empirically verify via testnet
  WIF round-trip during build phase before any import/export UI ships.
- Derivation: **m/0'/0'/k** — MazaCore's own scheme (wallet.cpp:185-202),
  the same derivation the official MAZA-qt desktop wallet uses. NOTE:
  derivation equivalence alone does not establish seed portability — the
  desktop wallet.dat stores a raw HD seed, and importing it is a PLANNED
  lane pending verification against the wallet format. NOT Komodo's
  m/44'/13'.

## D4 — Fees
- Default paytxfee **0** (wallet.h:47) — fee is calculated per tx, not flat.
- Relay floor **1000 sat/kB** (validation.h:53), dust threshold at
  **3000 sat/kB** relay fee (policy.h:46). NOT Komodo's flat 10000 sat.

## D5 — Block timing (for UI copy only)
- Target spacing **120 s per algo** (chainparams.cpp:89, "Maza: 2 minutes");
  multi-algo + hive make effective network blocks faster (community/Komodo
  observed avg ~60 s). UI derives estimates from code target, states the range.

## D6 — Build-vs-Komodo
- Build ours on chain-code defaults (this doc). Komodo stays a community option;
  its MAZA profile provably drifts from chain code (WIF 244, m/44'/13',
  blocktime 60, flat fee) — per the rule, code wins. Our differentiator:
  MazaPay-native checkout (scan merchant QR → pay), regular-user usability.

## Status
- Decisions locked 2026-11-15. No Payu-routing needed for these defaults — all
  inherited. Coin-policy changes (e.g. proposing a different confirmation
  default) would still route through Payu per standing directive.
- Repo: `github.com/SamiAhmed7777/maza-mobile-wallet` (created 2026-11-16).
- Next: scaffold repo (default plan: `maza-mobile-wallet` under
  SamiAhmed7777, MazaPay-style lanes, Codex-graded commits) + light-client
  indexer spike on samihost.
