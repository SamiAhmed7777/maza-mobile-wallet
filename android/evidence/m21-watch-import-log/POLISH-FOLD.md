# POLISH-FOLD — m21-watch-import-access-log

Round-1 verdict: grade **B**, zero blockers,
URN `urn:ump:ud37ynbyau6o5zv6wiutupb3qm5hbcs7cjlwbojoidaaa7b6qeqq`
(judge-gate.sh, Codex primary, 2026-11-16 ~04:3x PST).

## Polish items and disposition

1. "Add explicit regression coverage for the 502 ChainError path and
   malformed-body/oversized-list paths." — FOLDED.
   `test_chain_error_502_logs_imported_zero` (exploding MockChain ->
   `WATCH_IMPORT seq=N imported=0 status=502`) and
   `test_malformed_body_and_oversized_list_log_400` (invalid JSON body and
   a 201-address list -> one `status=400` line each).
2. "Assert the complete log line against a strict regex so extra fields or
   unexpected text cannot silently pass." — FOLDED. Every new assertion uses
   `^WATCH_IMPORT seq=\d+ imported=<c> status=<s>$` (fullmatch shape via
   anchored regex on the single captured line).
3. "Clarify the brief's statement that an observed response proves the log
   line 'landed': logging exceptions are intentionally swallowed, so this
   guarantee holds only when stdout remains writable." — ACCEPTED as a
   documentation note; no code artifact changes. The guarantee is:
   log-write FIRST, then response; if stdout is unwritable the write failure
   is swallowed (by design — a log failure must never 500 an import) and the
   response can then outrun the line. The code comments in
   `_log_watch_import`/`_watch_json` state exactly this contract.

## Graded vs shipped bytes

- Graded bundle frozen in `graded-bundle/` (api.py, test_walletbench.py,
  brief, evidence transcript) exactly as submitted to the judge.
- Shipped `walletbench/api.py` is BYTE-IDENTICAL to the graded copy
  (cmp clean, sha256 8956096f…2ccf) — the fold touched ONLY tests.
- Shipped `tests/test_walletbench.py` (73acb909…5914) differs from the
  graded copy (a2a58bc3…8bed) by exactly the fold: strict-regex assert +
  two new tests; no assertions were weakened or removed.

## Post-fold verification (on the SHIPPED bytes)

### CMD: python3 -m unittest discover -s tests 2>&1 | tail -3
Ran 131 tests in 49.920s

OK (skipped=4)

(skips are the 4 pre-existing electrumx integration skips; suite was 129 at
the graded bytes — the fold adds exactly 2 test methods.)
