# POLISH-FOLD — m21-unlock-reimport

Graded bundle (frozen, byte-exact as submitted to the judge): `graded-bundle/`
— judge grade **A, zero blockers**, round 1,
URN `urn:ump:7fsgukdr75jbyfasbasl63tkewasn6roiqszad6txjzfvdtwnmsa`.

## What was folded after the grade

Judge polish item 2 (verbatim intent): "Consider refreshing self-custody
state immediately after a successful asynchronous import so the landing
session need not wait for the next poll to reflect newly watched funds."

Folded change, shipped in `android/src/com/mazawallet/SelfCustody.java`
`ensureWatchImported()`: on import success the wallet now calls `refresh()`
(one call; thread-safe — refresh spawns its own worker and posts UI updates
via ui.post; self-guards on `state != ST_WALLET` / null token) instead of
returning without a refresh. Comment marks it "Judge polish fold".

Scope: **behavioral** (one call on the import success path), not docs-only.
Polish item 1 (backend count-only access log + device E2E) is NOT folded —
it is the planned M21 follow-up tick and would change the deployed backend.

## Graded vs shipped bytes

- `MainActivity.java`: identical graded↔shipped
  (sha256 475643c6a45a6541c9930cf84e0b22a2b3b478b8c2059a8fcf360e683f0c9b17
  both).
- `SelfCustody.java`: graded 344d2bed608d123768d621a988f42252c41dba46474db840efb077719090c59a
  → shipped 9cb22534f594ba8d1cc060b84ed8a3e83f28fe51cdb987e0a234f3929d306685.
  The only delta is the fold above (see `m21.diff`, regenerated from the
  shipped tree).

## Verification re-run on the FOLDED bytes

Fresh transcripts in `EVIDENCE.txt` (regenerated after the fold, same
commands):

- `bash android/build-apk.sh`: selftest gate ALL 19 CHECKS PASSED, javac OK,
  SIGNED OK (271316 bytes).
- `python3 -m unittest discover -s tests`: Ran 95 tests, OK (skipped=4).

The graded-bundle BRIEF.md describes the pre-fold bytes; the fold is
described here and in the code comment. Bundle != commit by design of this
fold; the shipped diff in `m21.diff` is authoritative for the commit.
