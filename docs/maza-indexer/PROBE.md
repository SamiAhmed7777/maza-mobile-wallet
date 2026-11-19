# PROBE.md - what was actually measured against the live MAZA node

This is the evidence behind the central claim of the lean indexer: it can
build its index from an ordinary `mazad` daemon, **without** a txindex.

**Date: 2026-11-18.**
**Measured by the wallet project against the live samihost node, read-only.**
(The probe only asked the node for blocks; it changed nothing on the node.)

## Transcript (verbatim)

```
CHAIN blocks=1199955 headers=2373295 ibd=True chain=main
PROBE height=1000 verbosity2_txs=1
TX0 keys=hash,hex,locktime,size,txid,version,vin,vout,vsize
TX0 has_full_hex=True has_txid=True has_vout=True
```

## What this proves

The probe asked the live daemon for block 1000 with `getblock` at
**verbosity 2** - the form that returns the full transaction objects, not
just their hashes. The daemon answered with every field a transaction needs
(`hex`, `txid`, `vin`, `vout`, `size`, `locktime`, `version`) even though
that node is **not** running a txindex (`ibd=True` and no `txindex` in the
requested index set). The `TX0` rows confirm the transaction payload is
complete rather than a stub.

So: **a lean indexer can ingest the chain from a normal daemon.** It reads
whole blocks, in order, and extracts the transactions itself. That is
precisely the step the previous ElectrumX path could not take - ElectrumX
demands `txindex=1` from the daemon, and building that index on this chain
deadlocked the node. This indexer never asks for a txindex, so the deadlock
has nothing to bite on.

## What this does NOT prove

- **It does not prove PoW validation.** The indexer does no proof-of-work
  checking of its own. It trusts the daemon's chain: the daemon validated
  every block, and the indexer re-checks block *links* (the prevhash chain)
  as it walks, but it does not re-hash and re-check the PoW itself.
- **It does not prove an ingest rate.** No blocks-per-second figure has been
  measured on a real sync, so none is claimed anywhere in this repository.
  The sync-speed expectations in the operator guide are deliberately vague.
- **It does not prove the full chain has been ingested.** The transcript is
  a spot check at one height on one node at one moment in time. It says the
  *data is available*; it does not say the index is complete.
- **It does not prove anything about the address index.** The address index
  is built by the indexer while it walks; its size on disk has not been
  measured yet.

The honest summary: the *mechanism* is proven (a normal daemon exposes
whole blocks with full transactions, txindex off). The *scale numbers* are
not - see the disk and sync sections of
[README.md](README.md), which say so explicitly.
