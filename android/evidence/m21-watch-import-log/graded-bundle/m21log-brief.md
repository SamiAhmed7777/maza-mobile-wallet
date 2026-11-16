# BRIEF — m21-watch-import-access-log (round 1)

Operator directive: Codex grades this artifact before commit; grade >= B gates the commit (Sami standing rule; MAZA mobile wallet backlog loop, cron 24a7311de928).

Scope of claims — term definitions: "WATCH_IMPORT line" = the single stdout line emitted per POST /api/watch/import request by walletbench/api.py _log_watch_import, format exactly `WATCH_IMPORT seq=<int> imported=<int> status=<int>`. "count-only" = the line carries only integer counts (sequence number, how many addresses the request carried, HTTP status); it structurally cannot contain addresses, tokens, or IPs because the logger accepts only int arguments. "deploy" = out of scope for this grade; the walletbench deploy to samihost happens only after the graded commit lands.

Artifact history: round 1, no prior rounds, no prior verdict URNs. Blocker disposition: n/a (first round).

Why this change exists (M21 remaining half, part 1): the Android app re-imports its 40-address watch window on every unlock (commit 3d31c25). The unlock-path proof needs "did the import fire at unlock?" to be observable on the live bench. The backend previously logged nothing per request (log_message suppressed, zero watch/import lines in 3h of journald), so the property was unobservable. journald captures this service's stdout, so one count-only line per request closes that gap. Never addresses/tokens/IPs — the bench token and wallet data must never reach a log surface.

Behavior contract:
1. Exactly one WATCH_IMPORT line per /api/watch/import request, for every outcome (200, 400, 401, 502).
2. The line is flushed BEFORE the HTTP response is sent — a client that observed the response knows the line landed (the M21 device proof reads "unlock observed -> new line" from journald).
3. Success line reports imported=<deduped count>; failure lines report imported=0 with the response status.
4. Sequence numbers are process-lifetime monotonic.
5. A stdout write failure must never fail the request (log is observability, not the request path).
6. Response bodies, status codes, and auth behavior are UNCHANGED; no other endpoint touched.

### CMD: python3 -m unittest discover -s tests 2>&1 | tail -3
Ran 129 tests in 51.554s

OK (skipped=4)

### CMD: python3 -W ignore::ResourceWarning -m unittest tests.test_walletbench.TestWatchImportAccessLog -v 2>&1 | grep -E "^(test_success|test_seq|test_failure|Ran|OK)"
test_failure_paths_log_without_leaking_input (tests.test_walletbench.TestWatchImportAccessLog.test_failure_paths_log_without_leaking_input) ... ok
test_seq_increments_per_request (tests.test_walletbench.TestWatchImportAccessLog.test_seq_increments_per_request) ... ok
test_success_logs_one_count_only_line (tests.test_walletbench.TestWatchImportAccessLog.test_success_logs_one_count_only_line) ... ok
Ran 34 tests in 14.733s
OK

### CMD: git diff --stat
 tests/test_walletbench.py | 70 +++++++++++++++++++++++++++++++++++++++++++++
 walletbench/api.py        | 73 +++++++++++++++++++++++++++++++++++++++--------
 2 files changed, 131 insertions(+), 12 deletions(-)

Test-count arithmetic, single-sourced: the targeted run shows 34 = 31 methods defined directly on the shared BenchTestCase base class (every subclass inherits and re-runs them — pre-existing layout, verified: test_bearer_token_auth and test_send_rejects_nan resolve to BenchTestCase.__dict__) + the 3 new tests this change adds. Full suite 129 total, 4 pre-existing electrumx skips. HEAD-vs-worktree delta verified by grep: tests/test_walletbench.py has 47 -> 50 four-space "def test_" methods; tests/test_chain_params.py unchanged at 17. Exactly 2 files changed.

Design notes for review attention:
- _watch_import's auth refusal now calls self._authorized() directly and then _watch_json(401, {"error": "locked"}, 0) — payload and status byte-identical to the previous _require_auth() refusal, so the access line is emitted without double-writing a response.
- print happens INSIDE _watch_log_lock (whole-line atomicity under ThreadingHTTPServer) and is wrapped in try/except (a closed stdout must not turn an import into a 500).
- The invalid-address 400 RESPONSE body still echoes the malformed input (pre-existing behavior, unchanged by this diff); the LOG LINE never does — test_failure_paths_log_without_leaking_input asserts "not-an-address" is absent from the emitted line.
- The logger takes only int arguments (int(status), int(imported) at the single call site), so address/token leakage into the line is structurally impossible.

Judge-rerunnable static checks: grep -c "_watch_json(" walletbench/api.py shows 10 call sites (1 helper-internal log+send, 9 response paths — every return path of _watch_import); grep -n "WATCH_IMPORT" lands only in walletbench/api.py and tests/test_walletbench.py.

Attachments: walletbench/api.py and tests/test_walletbench.py (the complete change — nothing else was touched).
