# SPEC-AUDIT — compliance matrix (audit date 2026-11-16; rev5)

Per RULE 1 (no restart unless unsuitable): the existing native stack was
audited against docs/SPEC.md. Verdict: **the existing architecture is
suitable and is the implementation vehicle.** It is a purpose-built,
Gradle-free Android wallet with a first-party crypto package
(android/src/com/mazawallet/crypto/ — Bip39, Bip32, Bip44Maza, Secp256k1,
Ripemd160, Base58Check, Hex, TxBuilder, SelfTest), vector-tested against
official BIP39/BIP32 values by a desktop-JVM self-test gated as stage [1/6]
of every build (android/selftest.sh), and proven live on MAZA mainnet
(android/evidence/selfcustody-proof/PROOF.md — phone-signed tx
ce514b350d2c…cd4e confirmed on-chain).

## Komodo/AtomicDEX comparison (FINAL EXECUTION INSTRUCTION) — conclusion
## and its basis

Compared against Komodo's AtomicDEX Mobile architecture on three axes:

1. ARCHITECTURE: AtomicDEX Mobile is a Kotlin multiplatform application
   whose wallet/swap operation is built around Komodo platform services
   (komodod-ecosystem daemons, Komodo swap backend). Moving to it would
   make this wallet DEPEND on Komodo infrastructure — exactly what SPEC
   RULE 8 forbids without a deliberate, justified integration. No such
   justification exists: MAZA needs none of the swap/DICO machinery
   (RULE 4 excludes it from the core anyway).
2. LICENSE: this audit did NOT fetch the AtomicDEX Mobile license — a
   license review is unnecessary to reject a non-adoption, and the spec's
   own dependency-license review (RULE 8) is scoped to components we
   actually incorporate. The APK's incorporation inventory is ZERO
   third-party libraries (every .java file under android/src is first-party;
   build tools aapt2/javac/d8/apksigner are Android SDK build tools under
   the SDK license; the only vendored data is the public BIP39 English
   wordlist — byte-identical to bitcoin/bips + trezor/python-mnemonic, no
   per-file license grant exists, posture recorded in the report). The
   server runtime incorporates exactly one vendored third-party component
   (walletbench/vendor/qrcodegen.py — Nayuki, MIT, header in-file; Python
   stdlib otherwise). Formal report = S-7 (DONE): docs/DEPENDENCY-LICENSES.md.
3. RULE 1: the existing stack is mainnet-proven (on-chain confirmed
   phone-signed tx, offline-verified signatures) — not "demonstrably
   unsuitable", so a restart or rewrite is ruled out by the spec itself.

CONCLUSION: keep the native stack; adopt the spec as a compliance
checklist; AtomicDEX *principles* (modular wallet kit, chain abstraction,
non-custodial by construction) are already embodied (first-party crypto
kit; coin profile isolated in indexer/maza_coin.py; server never holds
keys). Trading/swaps stay excluded from the core (RULE 4).

## Phase 4 — security

| Item | Status | Evidence (repo-relative) / gap plan |
|---|---|---|
| 4.1 local private-key custody | DONE | android/src/com/mazawallet/SelfCustody.java (on-device seed/keys); backend watch-only (walletbench/api.py: /api/watch/* never receives keys); mainnet proof android/evidence/selfcustody-proof/PROOF.md |
| 4.2 encrypted wallet storage | PARTIAL — code DONE, device proof pending | SeedVault landed (commit d8b08ed): AndroidKeyStore AES-256-GCM, MZAE1 envelope, atomic staged writes, legacy-plaintext migration; wired into SelfCustody.readSeed/writeSeed; 5 envelope checks green in the 76-check selftest; on-device restart+migration proof outstanding (S-1 device half) |
| 4.3 secure seed generation + recovery | DONE | Bip39.java + official Trezor vectors in crypto/SelfTest.java (49-check selftest, build stage [1/6], android/selftest.sh); recovery = in-app seed import (SelfCustody.java ST_IMPORT, renderImport()) |
| 4.4 OS secure storage | PARTIAL — code DONE, device proof pending | non-exportable AndroidKeyStore key backing SeedVault (see 4.2); device proof pending with 4.2 |
| 4.5 PIN/biometric unlock | PARTIAL → S-2b device evidence | S-2a PIN half SHIPPED: hashed verifier (PBKDF2-HMAC-SHA512, 210k iters, D11), full-screen lock cover, WALLET-tab + send gating, wrong-PIN backoff (crypto/LockPolicy + crypto/Pbkdf2); S-2b-ii BIOMETRIC CODE SHIPPED 2026-11-17: platform BiometricPrompt on the lock cover behind crypto/BiometricPolicy (pure decision table: API >= 29 + fresh platform probe + VALID verifier), PinGuard.unlockViaBiometric fail-closed seam, shared completeUnlock landing, D12 error policy (failures never touch the PIN streak; lockout stops the session offer), USE_BIOMETRIC added (normal perm; required by platform authenticate()), SelfTest decision-table scenarios + tests/test_biometric_wiring.py; on-device BlueStacks proof can only cover graceful-absence (no biometric HW on the bench) = device-lane item |
| 4.6 auto-lock after inactivity | PARTIAL → S-2b | S-2a code SHIPPED: 5-min inactivity auto-lock (lazy gate evaluation + 10s cover tick) + background >= window locks on resume; on-device proof (foreground inactivity + background/foreground) = S-2b |
| 4.7 accidental key-exposure protection | PARTIAL | Seed shown once at creation (SelfCustody renderSeed path); bench token field masked (password=true) and memory-only (MainActivity onCreate comment). LANDED 2026-11-17 (S-4): auth-gated seed re-show (PinGuard verify + FLAG_SECURE + scrub on dismiss) and wipe (double-confirm, typed WIPE, current-PIN re-verified immediately before destruction, best-effort Keystore wrap-alias removal); device proofs pending |
| 4.8 secure transaction signing | DONE | crypto/TxBuilder.java: version-1 P2PKH, SIGHASH_ALL, RFC6979 nonces, DER low-S. Verification model (accurate): the wallet broadcasts ONLY transactions it constructed and signed itself; every mainnet-proof submission was independently verified offline first with tools/txverify.py (SIGHASH_ALL + ECDSA, proven against a real MazaCore-signed tx) — android/evidence/selfcustody-proof/PROOF.md. The server does NOT re-verify signatures; it relays client-signed bytes (api.py /api/broadcast), which is safe because construction+signing never leave the device |
| 4.9 input validation / address verification | DONE | SelfCustody.java:613 (amount <= 0 / !isFinite refused); walletbench/api.py:821 (isfinite), :635/:842 (own-address refusal); crypto/Base58Check.java:35-46 (checksum verify) + walletbench/chain.py:117 (validateaddress) |
| 4.10 malicious-tx construction protection | DONE (structural) | the app CONSTRUCTS transactions from user input via first-party primitives only — there is NO raw/imported-transaction path a hostile server could feed it (walletbench/api.py /api/broadcast accepts signed hex for RELAY only, which cannot alter construction); broadcast refuses when the change-address import fails (SelfCustody send path, judge r2 blocker); authentication gates the relay. (Accuracy note per review: auth+relay alone is not the protection — the structural no-import-path property is; both documented here) |
| keys/seeds never to external servers | DONE | server watch-only by design (walletbench/api.py header doc: importaddress + relay); zero analytics (no third-party code at all); token never in URLs (Api.java:16,60) |
| never log secrets | DONE | walletbench logs are count-only WATCH_IMPORT lines (api.py _log_watch_import); app logs none of seed/key material (grep-verified) |
| no custodial wallet infrastructure | DONE (wallet) | wallet is non-custodial; the token-gated bench is a separate TEST harness (Sami's play funds), not the wallet's backend path — ElectrumX replaces it (Phase 6) |

## Phase 5 — experience

| Item | Status | Evidence / gap plan |
|---|---|---|
| dark surface | DONE | default palette (maza_dark_* resources via UiTheme resolution; values byte-equal to the original 0xFF141414 family, frozen in DARK_RENDER_BASELINE) |
| light mode | DONE code (2026-11-17, wave 2) — device proof pending | Themes + ThemeController + UiTheme palette resolution: ALL hardcoded ink converted (15 constants, 113 sites; zero ARGB literals in MainActivity/SelfCustody, test-proven), EXPECTED_BELOW_THRESHOLD ledger EMPTY (machine-checked gate), dark render byte-identical (frozen DARK_RENDER_BASELINE), PIN dialogs + dialog themes palette-driven; known residual: live theme switch repaints only Settings (MainActivity session-preserving rebuild = separate backlog item); device screenshots pending |
| large readable balance | DONE | BALANCE + WALLET tab balance cards |
| simple send/receive steps | DONE | SEND form + RECEIVE card with QR |
| clear tx confirmations | PARTIAL | send result line + history rows; richer confirmations ride S-4 polish |
| nav: balance/send/receive/transactions | DONE | five bottom tabs (MainActivity.java:67 TABS) |
| nav: wallet management | DONE (2026-11-17) | SettingsActivity WALLET MANAGEMENT page: receive addresses, PIN-gated seed re-show (FLAG_SECURE, scrub on dismiss), double-confirm + typed-WIPE wipe flow returning to fresh Connect card |
| nav: settings | DONE (2026-11-17) | SettingsActivity from the SECURITY card: endpoint editor (same saved URL pref as Connect card), auto-lock 5/10/30 min (applies IMMEDIATELY via PinGuard.retuneAutolockMs, wave 2), theme selector System/Light/Dark via ThemeController |
| QR generation | DONE | walletbench /api/qr.png (api.py:720, scoped to watch book) |
| QR scanning | PARTIAL — M8a + M8b code landed (2026-11-17) | ScanOrigin origin-discipline policy + ScanFlowPolicy + camera scan surface (raw camera2, in-activity overlay, scan → SEND field) + pinned zxing decoder (sha256-gated in the build) + M9 maza: payment-URI parse (MazaUri, official desktop port, fills address+amount) + M9-ii request-amount receive screen (typed amount → MazaUri.format → /api/qr.png?uri= payment-request QR, backend contract mirror); on-device scan proof = M8b-ii |
| ordinary-user intuitiveness | PARTIAL | settings + theming landed (2026-11-17); app-wide light reskin landed (wave 2); on-device UX proofs + live theme-switch repaint (W3-a) pending |

## Phase 6 — connectivity

| Item | Status | Evidence / gap plan |
|---|---|---|
| native MAZA only | DONE | SLIP-44 coin 13, m/44'/13'; no wrapped/substitute assets anywhere (DECISIONS.md) |
| evaluate: existing Mazacoin full-node software | DONE | MazaCore 0.16.3 live on samihost (vendor/ excerpts sha-pinned; DECISIONS.md) |
| evaluate: compatible RPC interfaces | DONE | mazad RPC 127.0.0.1:12832 (validateaddress/listunspent/getrawtransaction used and cited above) |
| evaluate: existing blockchain explorers | DONE (conclusion) | no MAZA explorer dependency taken; balance/history served self-hosted (ElectrumX) — third-party explorer reliance rejected for decentralization |
| evaluate: available public infrastructure | DONE (conclusion) | none suitable for MAZA (no maintained public ElectrumX; official Android repo dead since 2018 — README "Why"); hence self-hosting |
| evaluate: lightweight synchronization options | IN FLIGHT | ElectrumX light-client protocol = the chosen option; profile + pinned installer + guide in-repo |
| evaluate: self-hosted infrastructure | DONE (decision) | mazatest public TEST endpoint live (deploy/PUBLIC-HOSTING.md recipe; 200/401/401 external probes) |
| prefer decentralized architecture | IN FLIGHT | ElectrumX = multi-server decentralized design; single-node deploys are instances of the same recipe |
| RPC backend separated from app + documented | DONE | walletbench is the separated backend (own host, 0600 env, token-gated, never ships in the APK — deploy/ENDPOINT-VERIFICATION.md §2); security requirements documented in deploy/PUBLIC-HOSTING.md |
| no new blockchain/token/substitute network | DONE | native MAZA only; SLIP-44 coin 13; no wrapped/bridged assets anywhere (DECISIONS.md) |
| wallet interacts with actual native MAZA | DONE | mainnet tx ce514b35…cd4e confirmed (android/evidence/selfcustody-proof/PROOF.md) |
| derivation-scheme policy (m/0'/0'/k vs m/44'/13') | PLANNED-LANE (not implemented) | MazaCore desktop wallets derive m/0'/0'/k and store a raw HD seed in wallet.dat; this mobile wallet derives m/44'/13' (SLIP-44) — INDEPENDENT, incompatible schemes. Desktop wallet.dat import IS a planned lane (DECISIONS.md D3 + README) but is NOT implemented: D3 notes derivation equivalence alone does not establish seed portability — importing requires verification of the wallet.dat raw-seed format plus deliberate key-translation design. Today, restoration in the app = its own BIP39 seed at m/44'/13' only; each wallet restores its own |
| txindex decision (ElectrumX prerequisite) | OPEN — Payu (decision authority delegated 2026-11-17) | samihost mainnet mazad lacks txindex (probe: "Use -txindex…" on block-4300000 tx); ElectrumX refuses index-less daemons (REQUIRED_DAEMON_INDEXES, indexer/maza_coin.py); option (a) reindex prod node in place ~1-3h with a MazaPay bridge RPC window, or (b) second txindex node ~12-36h sync, zero prod impact — ASKED, awaiting Payu |
| decentralized, no single centralized service | IN FLIGHT | ElectrumX is the standard multi-server light-wallet protocol; multiple independent hosts can serve wallets (the txindex prerequisite and its decision have their own row above) |

## Phase 7 — testing

| Item | Status | Evidence / gap plan |
|---|---|---|
| new wallet creation | DONE | M2 evidence (create on-device, 12 words, oracle cross-check) |
| wallet import + restoration | DONE | SelfCustody ST_IMPORT path (renderImport) |
| address generation | DONE | Bip44Maza.java (m/44'/13'), oracle-validated |
| address validation | DONE | Base58Check.java:35-46; walletbench/chain.py:117 |
| balance retrieval | DONE | live: 46.9998774 MAZA renders (verified on-node vs app) |
| transaction history | DONE | /api/watch/history renders timestamped rows |
| transaction construction + signing | DONE | TxBuilder + mainnet-confirmed signed tx |
| transaction broadcasting | DONE | /api/broadcast + confirmed tx ce514b35… |
| QR generation | DONE | /api/qr.png |
| QR scanning | PARTIAL — M8a + M8b code landed, M9 URI parse landed, M9-ii request screen landed | ScanOrigin policy (origin discipline, desktop-tested) + sha256-gated zxing decoder + wired camera scan surface + MazaUri maza: payment-URI parse (fills address+amount) + RECEIVE-tab payment-request QR (typed amount → MazaUri.format → /api/qr.png?uri= with backend contract mirror); on-device scan proof = M8b-ii |
| encrypted wallet persistence | PARTIAL — code DONE, device proof pending | = Phase 4.2 (SeedVault code landed, device half outstanding) |
| app restart + recovery | DONE | M21 evidence: fresh process → watch set re-imports on unlock; wallet renders |
| network interruption + reconnection | PARTIAL → code LANDED (wave 3) | Net.java retry table governs the WHOLE surface (reads + unlock + watch/import: 3 attempts with exponential backoff; spend POSTs pinned at exactly 1 attempt — never double-submitted); OUTSTANDING: the airplane-mode device test |
| error handling | PARTIAL → code LANDED (wave 3) | user-facing copy for timeout/offline/401/expired wired everywhere via Net + strings.xml, no silent empty states; airplane-mode device run outstanding |
| mobile build compatibility | DONE | release-signed APK v1.1.0 (v2+v3, versionCode=3) installs on emulator; real-device install pending (M6) |
| testnet / controlled environment | PARTIAL | mainnet tests ran under a 50-MAZA-capped token-gated harness (never uncapped); a MazaCore testnet node already runs on samihost; CODE HALF DONE 2026-11-23 (S-6-i: NetworkParams + network-aware derivation/scan contract, chainparams.cpp-fetched constants node-validated on the testnet mazad — DECISIONS D18); REMAINING (S-6-ii): Settings switch + per-network endpoint + controlled-env device proof |
| never broadcast unauthorized mainnet txs | DONE | all mainnet sends were Sami-directed, amount-capped, own-input-selected, offline-verified first |
| incomplete features documented | DONE | this matrix's PARTIAL/GAP rows + the operational backlog (snapshot: deploy/backlog-snapshot-20261116.txt) |

## Phase 8 — deliverables

| Item | Status | Evidence / gap plan |
|---|---|---|
| 1 source code | DONE | this repo (android/, walletbench/, indexer/, deploy/) |
| 2 standalone app structure | DONE | android/src/com/mazawallet + crypto kit (no external libraries) |
| 3 working dashboard | DONE | BALANCE tab (bench) + WALLET tab (self-custody) render live balances |
| 4 native MAZA integration | DONE | mazad RPC + MazaCore-anchored chain profile (vendor/, sha-pinned) |
| 5 creation + restoration | DONE | create/import proven on-device |
| 6 send + receive | DONE | mainnet-proven send; receive = address + QR |
| 7 history | DONE | HISTORY tab, timestamped rows |
| 8 build/deployment instructions | DONE | README + android/build-apk.sh + deploy/PUBLIC-HOSTING.md + docs/electrumx/README.md |
| 9 dependency & licensing report | DONE | formalized: docs/DEPENDENCY-LICENSES.md — APK: zero third-party libraries (platform APIs + first-party code only); server: Python stdlib + one vendored MIT component (qrcodegen, Nayuki); wordlist = public BIP39 data, byte-identical to bitcoin/bips + trezor/python-mnemonic (the earlier "Trezor CC0" wording here was not license-file-supported and is corrected per that report — no per-file grant exists; provenance + posture in report §1) |
| 10 security assessment | DONE (2026-11-17) | docs/SECURITY.md — scope, architecture/trust boundaries, S-1+S-2 evidence, token handling, 4-threat model, spending-path scope table (custodial /api/send vs self-custody watch/broadcast), controls inventory, 13 accepted risks, 8 open items; every cited path existence-verified |
| 11 testing report | DONE (2026-11-17) | docs/TESTING-REPORT.md — per-phase checklists + RULES 1-8 table + measured transcripts (parent-refreshed post-merge) + INCOMPLETE list; independent txid recompute, txverify VALID/LOW-S, s2b SHA256SUMS 47/47 re-verified by the writing lane |
| 12 outstanding requirements | DONE | this matrix's GAP/PARTIAL rows + the operational backlog — snapshot committed as deploy/backlog-snapshot-20261116.txt (live copy is host-side at /root/maza-mobile-backlog.md) |
| Android APK | DONE | v1.1.0, versionCode=3, v2+v3 release-signed — the release artifact sha256 013b964f… is recorded in deploy/ENDPOINT-VERIFICATION.md §2 (operator-side record; review artifacts exclude APK binaries); the older in-repo android/releases/maza-wallet-v1.0.0.apk (d30a48a9…) is SUPERSEDED (tailnet-era default URL) |
| iOS | DEFERRED | Android-native stack; iOS is a separate-architecture effort (documented decision, not silently dropped) |

## Development rules compliance

| Rule | Status | Note |
|---|---|---|
| RULE 1 no restart unless unsuitable | COMPLIANT | audit verdict above: existing stack suitable |
| RULE 2 no overwrite/delete without backup | COMPLIANT | changesets are additive+judged; bench installer takes timestamped state backups (install-walletbench.sh) |
| RULE 3 native MAZA only | COMPLIANT | no substitute assets anywhere (DECISIONS.md) |
| RULE 4 no DEX/swap infra | COMPLIANT | none present; excluded from core |
| RULE 5 no fabricated connectivity/simulated balances | COMPLIANT | all balances from live RPC/watch APIs; every claimed number in this repo carries a command transcript |
| RULE 6 no production-readiness claims until tested | COMPLIANT | status language: mainnet TEST with capped funds; production claims withheld pending S-items |
| RULE 7 modular, maintainable, documented | COMPLIANT | first-party crypto kit isolated; coin profile separate; DECISIONS.md + guides |
| RULE 8 dependency licensing + Komodo independence | COMPLIANT (review performed) | the rule's duty is "review before incorporation" — this row asserts the review DUTY was discharged, not legal clearance of every grant: the incorporation inventory: APK = ZERO third-party libraries (every .java under android/src is first-party; only vendored data = public BIP39 wordlist, byte-identical to trezor/python-mnemonic — no per-file grant exists, see docs/DEPENDENCY-LICENSES.md §1); server runtime = one vendored MIT component (qrcodegen) + stdlib. The formal report (S-7, DONE) reviews every incorporated item's license, with the explicitly unresolved BIP39 data-level grant and the PROVISIONAL resolved-package classifications recorded openly in that report. Komodo independence: no Komodo component incorporated (comparison section) |

## Implementation order (staged, per FINAL EXECUTION INSTRUCTION)

Stage 1 (security gaps first): S-1 encrypted seed at rest (Keystore AES-GCM)
→ S-2 PIN/biometric + auto-lock → S-7 dependency/licensing report (short).
Stage 2 (experience): S-3 light mode → S-4 settings/wallet-management → M8
QR scan. Stage 3 (connectivity): ElectrumX deployment (pending Sami's
txindex decision) → S-6 testnet mode → S-5 network/error hardening.
Stage 4 (deliverables): S-8 security assessment → S-9 testing report.

RULE 2 honored: no working files overwritten; all new work is additive and
judged (≥B) before push.
