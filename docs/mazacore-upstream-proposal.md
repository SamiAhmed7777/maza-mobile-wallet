# MazaCore 0.16.3 — upstream findings and proposal (DRAFT for governance review)

Status: **DRAFT** — prepared 2026-11-20 by the MAZA mobile wallet project
(github.com/SamiAhmed7777/maza-mobile-wallet) for review by MazaCoin
governance (Payu). Nothing here is merged anywhere; no node was modified to
produce it; every decision it raises belongs to governance. Once reviewed,
this document should either be superseded by an upstream issue/PR (authored
or approved by governance) or parked with the recorded decision.

Audience: MazaCoin governance and MazaCore maintainers.

## Summary

Three independent findings from operating MazaCore 0.16.3 as the daemon
behind a mobile wallet and its chain indexer:

- **A — the `-reindex` transaction-index scan deadlocks** at the Hive-era
  boundary (~height 2.07M) and restarts re-enter the stall (crash loop).
  Consensus-neutral: the scan only rebuilds the optional txindex.
- **B — the shipped `libbitcoinconsensus` carries the pre-0.15 ABI** (no
  `amount` parameter in the main entry point; a separate `_with_amount`
  variant exists). Integrators following Bitcoin Core's 0.15+ ABI segfault
  on first call. The library itself verifies mainnet script validation
  correctly once the right variant is called.
- **C — three undocumented chain/RPC facts** that cost third-party tooling
  authors real time; documenting them upstream is a doc-only change.

Each finding lists what was observed, what works around it, and a concrete
ask. None of the asks proposes a consensus-behavior change.

## Finding A — txindex `-reindex` deadlock at the Hive-era boundary

### Observed behavior

With `txindex=1` newly enabled on a chain whose blk files already extend
past the Hive-era boundary (~height 2.07M), `mazad -reindex`'s txindex scan
stalls inside that boundary:

- the in-scan blk file offset sits at EOF while the txindex directory's
  byte size stays parked (measure `du -sb` on the txindex directory twice,
  a few minutes apart: growing = alive; parked + offset at EOF = stalled);
- the daemon stays up but makes no index progress and never finishes;
- restarting with `-reindex` still set and the FULL blk set present
  re-enters the deadlocking scan: a crash loop was observed (12 restarts)
  with the daemon refusing RPC over an inconsistent partial index.

### Recovery that works (validated)

1. Stop the daemon. Record `getblockchaininfo` and the stall evidence.
   Never touch `wallet.dat` — this recovery operates on index/chainstate
   only.
2. Split the blk files AT the stall boundary: move every blk (+ matching
   rev) file at and beyond the frozen one into a hold directory, keeping
   ownership and mode.
3. `-reindex` the safe prefix (with `txindex=1` if that is the goal). The
   prefix scan completes in minutes-to-an-hour instead of hanging.
4. Restore the held files (only AFTER the scan phase has ended — restoring
   earlier re-enters the deadlock).
5. Run `-reindex-chainstate` once (then remove the flag). Validation replay
   was observed at roughly 33k blocks/min and passes THROUGH the former
   stall zone, because chainstate replay does not use the txindex scanner.
6. Start normally: the import extends the chain through the held range the
   same way every node bootstraps from blk files, then catches up from the
   network.

Validation status: steps 1–4 validated end-to-end; steps 5–6 were observed
running and passing the former stall zone, with the tail confirmation still
outstanding at last check. The procedure is written up as an operator
runbook in the wallet project's ops notes; it should live upstream.

### Asks

- **A1** — fix the txindex scan so it either completes past the Hive-era
  boundary or fails LOUDLY with a named, actionable error. A silent stall
  is the worst outcome for operators: it looks like progress and ends in
  the crash loop above. (Consensus-neutral: index-only code.)
- **A2** — document the boundary and the "do not restart with `-reindex`
  while the full blk set is present" trap in release notes or docs, along
  with the recovery recipe.

## Finding B — `libbitcoinconsensus` ships the pre-0.15 ABI

### Observed behavior

The 0.16.3 release ships `libbitcoinconsensus` whose main entry point is
the PRE-0.15 signature (no `amount` parameter), with a separate
`..._with_amount` variant alongside (read directly from the shipped
header). Bitcoin Core changed this ABI at 0.15; documentation and bindings
written against the 0.15+ single-call shape therefore call the library
wrong — measured consequence: an immediate segfault, not an error return.

The library is otherwise healthy. A differential channel drove the shipped
C++ consensus from an independent (Python/ctypes) driver:

- real mainnet transactions verified through the shipped library agree with
  the daemon's acceptance of those same transactions;
- corruption probes (single-byte flips in transaction and script bytes)
  NEVER verify VALID — no false-accept was observed.

### Asks

- **B1** — document the shipped ABI explicitly (release notes and a comment
  in the installed header naming both entry points and which to use).
- **B2** *(optional, governance's call)* — adopt the 0.15+ unified entry
  point in a future release, or keep both variants but name them clearly.
  Either resolves the segfault-on-first-call trap for integrators.

## Finding C — three undocumented chain/RPC facts (doc-only asks)

These cost this project real time to discover and are the difference
between "build an indexer" being a weekend or a dead end. All three are
pure documentation; behavior is fine.

- **C1 — block identity hash is `double-SHA256(header)` for EVERY block,
  regardless of PoW algorithm.** MAZA's multi-algo design (sha256d era,
  MinotaurX, Hive) makes it LOOK like a validator needs every PoW
  implementation. It does not: the mining algorithms live only in
  `GetPoWHash()` (`primitives/block.cpp:18-21`), the validity check the
  daemon already performed. An indexer that verifies block identity by
  double-SHA256 alone indexes the whole chain — proven against live
  mainnet blocks from both PoW eras.
- **C2 — `getblock <hash> 2` (verbosity 2) works with txindex OFF.** It
  returns every transaction in the block (full hex, txid, vin, vout)
  straight from the block files. Only `getrawtransaction`-by-txid of
  non-mempool transactions needs txindex. An indexer that ingests WHOLE
  blocks therefore runs against a normally-synced daemon with no txindex —
  this is exactly how the project's lean indexer (`maza_indexer/`) serves
  the wallet without a txindex node.
- **C3 — `getblockheader` takes a BOOLEAN verbosity.** Calling it with `2`
  is rejected ("JSON value is not a boolean as expected"); `[hash, false]`
  returns the raw 80-byte header as hex, and verbosity-2 block responses
  carry no block-level `hex` field — the raw-header call is the only
  header-bytes source.

Asks: **C1/C2/C3** — state these in upstream docs (doc-only changes). The
wallet project's community guides already carry C1 and C2
(`docs/electrumx/README.md`, `docs/maza-indexer/README.md`,
`docs/electrumx/TROUBLESHOOTING.md`); C3 was found live and is pinned by a
regression test in this repo's indexer test suite — the guides can be the
source text for all three.

## Context: what the project shipped meanwhile

So governance can weigh urgency: the mobile wallet's serving path no longer
depends on Finding A being fixed. `maza_indexer/` (stdlib-only, sqlite,
merkle proofs, JSON API) provides balances/history/proofs/broadcast
watch-support from a normally-synced non-txindex node, and is deployed.
The community ElectrumX kit remains parked for operators who specifically
want the Electrum wire protocol — THAT path requires txindex, so Finding A
is the open blocker for Electrum-server operators on MazaCore 0.16.3.

## Safety frame

- Nothing in this document was merged upstream; nothing here authorizes a
  change to any running node. Live-node work stays with the operators and
  governance.
- Findings A and C are observability/documentation-level (A1/A2 touch
  index-rebuild code only — consensus-neutral by construction: the txindex
  is an optional lookup aid and is not consulted by validation).
- Finding B documents an ABI hazard; B2 is a release-engineering choice,
  not a consensus change.
- Any FUTURE proposal that would change consensus behavior is a
  governance-only decision and is explicitly out of scope here.

## Verification instruments available for review

If governance wants any of these findings or fixes independently checked,
the wallet project maintains vector-anchored instruments:

- `tools/oracle.py` — BIP39/BIP32 official vectors + the MAZA address
  profile, validated against a live daemon;
- `tools/txverify.py` — offline SIGHASH_ALL + ECDSA verification, proven
  against a real MazaCore-signed mainnet transaction;
- `maza_indexer/` — an independent third implementation of chain ingestion
  and merkle proofs (useful as a differential reference for A/C work);
- the `libbitcoinconsensus` differential channel described in Finding B.

## Questions for governance

1. A1 — is a txindex scan fix wanted upstream? If yes, should the fix
   complete past the boundary or fail loudly (we recommend fail-loud as
   the minimum, completion as the goal)?
2. A2 — where should the deadlock + recovery documentation live (release
   notes vs docs/), and may we submit it as a PR?
3. B1 — add the ABI note to release notes/header? B2 — adopt the 0.15+
   entry point in a future release, or document both variants as-is?
4. C1/C2/C3 — may we submit the documentation PRs (source text already
   written in this repo)?
5. Is a full differential campaign against `libbitcoinconsensus` (beyond
   the opening probes) wanted now, or should it wait for a release that
   settles B2?

---
*Prepared 2026-11-20 · MAZA mobile wallet project · decisions rest with
MazaCoin governance (Payu) per the project's standing directive.*
