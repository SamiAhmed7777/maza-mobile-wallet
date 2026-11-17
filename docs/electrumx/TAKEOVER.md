# Taking over the MAZA ElectrumX kit — maintainer runbook

You did not write this kit. This page is how you keep it alive and change
it safely. Companion docs: [README.md](README.md) (zero-to-serving
walkthrough), [CHAIN-PARAMS.md](CHAIN-PARAMS.md) (every constant + source),
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) (symptom → fix).

## Reading order (day one)

1. `README.md` — the whole deployment, end to end.
2. `DECISIONS.md` — every wallet/chain parameter with its citation. This is
   the ledger of record: if a parameter has no citation there, ask before
   inventing one.
3. `CHAIN-PARAMS.md` — the quick-reference table distilled from the same
   sources.
4. `indexer/maza_coin.py` — the coin profile is ~200 lines; read all of it.
   `ALL_FIXTURES` at the top pins the header-hash behavior with real
   mainnet headers from both PoW eras.
5. `tests/test_chain_params.py` — what the suite pins, and how integration
   tests skip cleanly without the pinned electrumx tree.
6. `TROUBLESHOOTING.md` — the known in-tree traps (regtest genesis abort,
   testnet stall) so you do not re-debug them.
7. `deploy/` — the systemd unit, launcher, env template, compose files,
   installer.

**Change discipline:** consensus-adjacent values are checked against
`tools/oracle.py` (BIP39/BIP32 official vectors + MAZA profile) and
`tools/txverify.py` (proven against a real MazaCore-signed mainnet tx).
Never edit expected vector values to make code pass — if the oracle and
your code disagree, your code is wrong. Coin-policy questions (fee floors
beyond relay minimums, confirmation counts, URI semantics) are MazaCoin
governance territory, not unilateral repo changes (see README "Taking over
/ contributing").

## Monthly checklist

- **Daemon health:** `maza-cli getblockchaininfo` — `headers == blocks`,
  `initialblockdownload: false`; compare height against a reference
  endpoint to catch a silently stalled sync.
- **Disk:** node data dir + txindex + ElectrumX DB all grow with chain
  history. Anchor: the profile's ~14M tx at height 4.4M estimate
  (`TX_COUNT`/`TX_COUNT_HEIGHT`). Keep headroom, record what you see —
  README Step 1's **[TBD/community]** measured numbers still want real
  hardware data.
- **ElectrumX process:** journal is free of error loops
  (`journalctl -u electrumx`); the `--check-only` wiring gate still exits 0
  after any env change.
- **Verification battery:** README Step 5 still passes end to end (the
  server answers for known addresses/blocks match a reference). Note for
  a fresh, unfunded operator: the full battery includes UTXO/broadcast
  checks that need a funded address and a safely disposable signed
  transaction — run the read-only protocol checks first and defer the
  spend checks until you have test funds.
- **Certificates:** the public TLS cert renews — exercise
  `certbot renew --dry-run` on the `--nginx` path from README Step 4 before
  expiry, not after.
- **mazad `wallet.dat`:** back it up off-host monthly and DRILL the
  restore. The ElectrumX DB is a cache (deletable, rebuildable from the
  node); `wallet.dat` is not a cache — it is the only copy of the node's
  keys.
- **Exposure review:** mazad RPC still loopback-only; ElectrumX listener
  still `127.0.0.1:50001` on the host; the Electrum service surface still
  exactly one TLS port (50002) — plus public TCP 80, which MUST stay open
  for the documented certbot HTTP-01 issuance/renewal (README Step 4);
  the systemd env file still mode 600 root-owned
  (`install -m 600 -o root -g electrumx` — safe because systemd parses
  `EnvironmentFile=` as root and injects the variables, so the service
  process never needs to read the file); compose `deploy/.env` +
  `deploy/electrumx.env` still gitignored AND mode 600. Before pushing,
  scan your diff for real credentials — tracked files carry placeholders
  only.

## Upgrading ElectrumX safely

The hazard this procedure manages: the installer does an editable
(`pip install -e`) install **into the checkout directory you name** — so
re-running it against the production destination mutates the live
installation in place, before anything has validated the new version. The
procedure below therefore stages and validates FIRST, and only cuts over
once the candidate is proven. The DB-compatibility question is answered
BEFORE the first restart, never after one.

0. **Record current state:** the pin sha (`ELECTRUMX_PIN` in
   `indexer/maza_coin.py`), the installed `e-x` version, a clean journal,
   and a green README Step 5 run. You are about to change all four.
1. **Change the pin in BOTH places** — `ELECTRUMX_PIN`
   (`indexer/maza_coin.py`) AND `PIN` (`deploy/install-electrumx-dev.sh`).
   The duplication is deliberate: if the two constants drift, a wrong
   build fails loudly anyway — the installer's post-checkout HEAD
   verification, its fingerprint block (dist `e-x` version,
   `DeserializerSegWit` present, > 100 coin classes, plyvel importable),
   and the suite's pinned-tree tests each reject a build neither constant
   describes. (This step changes repo constants only — nothing is
   installed yet.)
2. **Stage the new pin away from production.** The installer pip-installs
   into WHATEVER interpreter you pass as its second argument — so passing
   the production venv's python here would upgrade production before
   anything validated it. Create a scratch venv and pass ITS python:
   ```
   python3 -m venv /tmp/e-x-stage-venv
   bash deploy/install-electrumx-dev.sh /tmp/e-x-stage-src \
        /tmp/e-x-stage-venv/bin/python
   ```
   The installer checks out the pin into the scratch dir, installs the
   `leveldb` extra, and runs its fingerprint block (dist `e-x` version,
   `DeserializerSegWit` present, > 100 coin classes, plyvel importable).
   If an expectation legitimately changed with the upstream bump, update
   the fingerprint block AND the tests' expectations together — do not
   loosen a check to make a round trip faster.
3. **Validate the staging install before touching production.** Root
   access alone does NOT put the production variables into your shell —
   systemd injects `EnvironmentFile=` at unit start; a bare shell has none
   of the three required vars, so a bare `--check-only` exits 2. Load them
   explicitly, in a form that never prints the `DAEMON_URL` credentials
   (never pass them as command arguments — shell history and process lists
   leak):
   ```
   cd /path/to/maza-mobile-wallet        # repo root — commands below are relative to it
   set -a; . /etc/electrumx-maza.env; set +a
   /tmp/e-x-stage-venv/bin/python indexer/run_indexer.py --check-only
   # must print: wiring OK  (exit 0)
   /tmp/e-x-stage-venv/bin/python -m unittest discover -s tests
   # suite green with the candidate tree importable
   ```
   If the electrumx integration tests SKIP in that run, know exactly why —
   a run where they silently skipped proves nothing about the upgrade.
4. **Decide the DB question BEFORE any restart**, from the new version's
   release notes/changelog:
   - **Compatible** → keep the DB; cutover touches only code.
   - **Incompatible or unclear** → at cutover, PRESERVE the old DB by
     renaming it aside rather than deleting it (stop the service first):
     `systemctl stop electrumx` then
     `mv /var/lib/electrumx-maza /var/lib/electrumx-maza.old-<old-pin>`,
     and let the new version create a fresh DB and reindex from the node
     (StateDirectory on the systemd path; the DB is a cache — README
     "Operating notes"). The rename is what keeps rollback cheap: the
     known-good old-format DB still exists on disk. Check free disk first —
     during the rebuild, both DBs exist on disk at once.
5. **Cutover:** re-run the installer with the PRODUCTION destination and
   the production venv's python (your `ELECTRUMX_VENV`, e.g.
   `/opt/venvs/electrumx-maza/bin/python` — the same pin you validated in
   staging), then that same venv's `--check-only` with the production
   variables loaded the same way as in step 3
   (`set -a; . /etc/electrumx-maza.env; set +a` — must print
   `wiring OK`), then `systemctl restart electrumx` (the unit's
   `ExecStartPre` runs the wiring gate first). Note: `systemctl enable
   --now` does NOT restart an already-active unit — always use `restart`
   after a deploy.
6. **Verify:** the full README Step 5 battery against the running server;
   watch `journalctl -u electrumx` through the first minutes of indexing.
7. **Rollback — three cases, by where you failed:**
   - *Staging validation failed* (steps 2-4): delete the scratch dirs;
     production never changed. Restore the pin constants in both files if
     you want the repo back on the old pin.
   - *Production restart failed, DB untouched* (compatible case): stop the
     unit, restore BOTH pins, re-run the production installer, restart,
     re-run Step 5. Only code moved; the DB is the same one the old
     version wrote.
   - *Production restart failed after a DB rebuild* (incompatible/unclear
     case): stop the unit, restore BOTH pins, re-run the production
     installer, then swap the DBs back — `mv` moves INTO an existing
     directory rather than replacing it, so move the candidate DB aside
     first and only then rename the preserved one into place:
     ```
     systemctl stop electrumx
     mv /var/lib/electrumx-maza /var/lib/electrumx-maza.candidate-partial
     mv /var/lib/electrumx-maza.old-<old-pin> /var/lib/electrumx-maza
     stat -c '%U:%G %a' /var/lib/electrumx-maza
     # expect electrumx ownership — renames preserve it; this catches drift
     ```
     then restart — the old version reads its own old-format DB. Delete
     the `.candidate-partial` dir once the old version is verified
     serving (Step 5's battery); until then leave it for forensics.
   Worst case in every branch: the DB is a cache and rebuilds from the
   node, so a failed upgrade costs sync time, never chain data — but with
   the rename-preserve in step 4, a rollback usually does not even pay
   that cost.

## House deploy patterns (what this repo does, reuse them)

- **Health-gated deploys:** install into a new release directory, gate on a
  real health probe before switching over, and take a timestamped backup of
  any durable state file before every restart. `deploy/install-walletbench.sh`
  in this repo is the worked example.
- **Count-only logging:** services log structure (`seq=N status=S`), never
  payloads — no addresses, no tokens, no credentials. The walletbench
  `WATCH_IMPORT` / `BOOK_RECONCILE` journal lines are the pattern.
- **Refuse loudly, fail closed:** the installer verifies pins (post-checkout
  HEAD check) and refuses old interpreters and missing backends with named
  diagnostics and loud nonzero failure (shell exit 1 / SystemExit) — never
  a silent skip — and the suite's fingerprint tests reject stale builds.
  Copy that shape.
- **Judge-gated commits:** every repo commit carries an independent judge
  grade (>= B) with the verdict URN in the commit message. That is how the
  repo's history stays reviewable after the original authors leave.

## What the kit still wants (community invitations)

- **[TBD/community]** measured numbers on real hardware: mazad full sync +
  txindex replay time; ElectrumX DB size at current height; the testnet
  post-retarget stall window (README Step 1, TROUBLESHOOTING #2).
- A protocol-level smoke script automating README Step 5 checks — the
  repo's crypto instruments (`tools/oracle.py`, `tools/txverify.py`)
  already cover the address/tx-value side; the wire-protocol side is open.
- PRs that fix the `CHAIN-PARAMS.md` table when `indexer/maza_coin.py`
  moves keep the quick reference trustworthy.
