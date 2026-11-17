# MAZA ElectrumX troubleshooting

Symptom → cause → fix, with the source for every claim — no invented
constants: every value below appears in the named in-repo source, and the
quick-reference table in [CHAIN-PARAMS.md](CHAIN-PARAMS.md) carries the
same constants with their citations. Anything marked **[TBD/community]**
has no measured number yet — PR what you observe instead of debugging by
folklore.

## 1. `mazad -regtest` aborts at startup

**Symptom:** the daemon exits immediately when launched with `-regtest`
(genesis merkle assertion fails against its own constant).

**Cause:** broken in MazaCore itself. Recorded in README Step 2 ("do not
debug these, they are in-tree") and in DECISIONS.md. Not your config, not
your build.

**Fix:** the only in-tree chain alternative is `-testnet` — but go in with
open eyes about what it is: testnet is a **public, shared** network, not a
private sandbox, and (see #2 below) solo mining on it stalls after the
first difficulty adjustment. It is the closest available stand-in for
regtest, not an equivalent of it. Also note the in-repo ElectrumX profile
is mainnet-only (`NET = "mainnet"`, `indexer/maza_coin.py`): there is no
testnet profile, so ElectrumX itself cannot be pointed at testnet with
this kit today — a testnet profile needs its own genesis hash and version
bytes. (App-side testnet support is a separate tracked item, S-6 in the
repo backlog; this repo's own controlled-environment testing used a
token-gated, cap-limited mainnet bench instead.)

**Source:** docs/electrumx/README.md Step 2 quirks; DECISIONS.md quirks
note; `indexer/maza_coin.py` line 184.

## 2. Testnet mining stalls after the first difficulty adjustment

**Symptom:** `generatetoaddress` mines testnet blocks fine, then produces
nothing (or takes enormous time) after the network's first retarget.

**Cause (as recorded):** LWMA difficulty spike. Before the first adjustment
the apparent-stall rule allowed floor difficulty, so blocks mined easily;
after it, target difficulty jumps and a solo testnet miner's hash rate
cannot reach it. README Step 2: "`generatetoaddress` only mines while the
apparent-stall rule allows floor difficulty."

**What to do:**
- Budget testnet mining **before** you depend on it; do not burn time
  debugging your own setup — this is in-tree behavior.
- Existing UTXOs are chain state: a stall blocks the creation of NEW
  blocks and mined-before-the-stall coins remain on-chain. (That is
  general blockchain behavior, not a MazaCore-specific measurement —
  DECISIONS.md records only the stall itself.)
- **[TBD/community]** a measured characterization (how long the window
  lasts at a given hash rate) is a welcome PR.

**Source:** docs/electrumx/README.md Step 2 quirks; DECISIONS.md quirks
note.

## 3. ElectrumX refuses to start, or history queries fail — txindex

**Symptom A:** ElectrumX refuses to start against your synced daemon. The
profile declares `REQUIRED_DAEMON_INDEXES = ("txindex",)`
(`indexer/maza_coin.py` line 195), so an index-less daemon is rejected by
the server itself.

**Symptom B:** RPC history queries fail on the daemon — `getrawtransaction`
of a days-old, non-wallet txid refuses with an error pointing at txindex.

**Cause:** `maza.conf` has no `txindex=1` line (a missing line means the
index is OFF — there is no default-on), or the flag was added after the
first sync completed, in which case the transaction index must be rebuilt
from scratch.

**Fix — enabling txindex on a chain that already synced** (README Step 2:
"adding it later forces a full `-reindex`"):

1. Stop mazad cleanly; set `txindex=1` in `maza.conf`.
2. Start mazad **with `-reindex` once** (e.g. `mazad -reindex` in the
   foreground, or your service manager's override/one-shot form). README
   Step 2 records that adding the flag later "forces a full `-reindex`";
   the standard Bitcoin-family 0.16 semantics MazaCore forks — `-reindex`
   rebuilds the block/chain index from the on-disk block files, building
   the full transaction index in the same pass when `txindex=1` is set —
   are what makes that a single pass. Verify the exact behavior on YOUR
   daemon rather than assuming it: the reindex log shows whether the
   transaction index is being built, and the completion checks below are
   the authority. Afterwards run the daemon normally (config alone) —
   `-reindex` is a one-shot, not a setting.
3. Budget the window: the coin profile's disk/tx anchor is ~14M
   transactions at height 4.4M (`TX_COUNT`/`TX_COUNT_HEIGHT`,
   `indexer/maza_coin.py`). Watch reindex progress in the daemon log.
   **[TBD/community]** measured full-sync + txindex replay time on real
   hardware — README Step 1 invites it.
4. Completion checks (README Step 2 item 4): `getblockchaininfo` shows
   `headers == blocks` and `initialblockdownload: false`; then re-run the
   Symptom-B probe — `getrawtransaction` of the same old txid now
   succeeds.

**Set `txindex=1` BEFORE the first sync whenever you can** — the first
sync builds the index as it goes, which is the cheapest moment. Adding it
later is not a config error, just a one-time rebuild you must schedule.

**Source:** README Step 2 items 2-4; `indexer/maza_coin.py` line 195;
`requirements-dev.txt`.

## 4. Access-control pitfalls

The recurring shape: "it works on the host, refused from outside" — or the
reverse, "it works from outside" in a way that means something is exposed
that should not be.

- **Public TCP 50002 must be allowed at BOTH firewalls** — the host
  firewall AND the cloud provider's. A 50002 that answers on-host but times
  out from outside is almost always the missing cloud-provider layer.
  (`ip6tables`/`ufw`/`firewalld` count as host layers; AWS/GCP/security
  groups/DigitalOcean firewalls count as provider layers. Check both.)
- **The ElectrumX listener itself stays on loopback.** systemd path:
  `SERVICES=tcp://127.0.0.1:50001` (`deploy/electrumx.env.example`).
  compose path: the container binds 0.0.0.0 but the HOST mapping is
  loopback-only `127.0.0.1:50001:50001` (`deploy/docker-compose.yml`).
  Public traffic terminates at the nginx `stream {}` proxy
  (`50002 ssl` → `127.0.0.1:50001`, README Step 4). Never widen 50001 to
  the network — "fix" reachability by opening the firewalls for 50002
  instead.
- **The daemon's RPC port (12832) never faces the network**, and
  `DAEMON_URL` carries `rpcuser:rpcpass`, so where those credentials live
  matters:
  - systemd path: the env file is installed
    `install -m 600 -o root -g electrumx` → `/etc/electrumx-maza.env`
    (README Step 4b), i.e. mode 600 owned by root. This works even though
    the service runs as the `electrumx` user, because **systemd parses
    `EnvironmentFile=` itself, as root, and injects the variables into the
    process** — the service process never opens the file, so root-only
    permissions are exactly right.
  - compose path: `deploy/.env` and `deploy/electrumx.env` are gitignored
    (never committed). The Step 4b walkthrough has you create `.env` with
    plain redirection — it also ends with `chmod 600` on both files, which
    matters because a default umask otherwise leaves a credentials-bearing
    file world-readable. If your copy predates that line, run
    `chmod 600 deploy/.env deploy/electrumx.env` now.
  - Never commit a copy carrying real credentials, whatever the mode.
- **The Electrum SERVICE surface is exactly one TLS port (50002)** in
  front of one loopback listener (50001) — nothing else for the SERVICE.
  One documented exception outside the Electrum service: TCP 80 must stay
  publicly reachable for the README Step 4 certbot/nginx certificate
  issuance and automatic renewal (HTTP-01) — do not "close port 80" while
  following that procedure, or renewal breaks. If you find yourself
  binding a second service port "temporarily", stop and re-read
  README Step 4.

**Source:** README Steps 2, 4, 4b; `deploy/electrumx.env.example`;
`deploy/docker-compose.yml` port comments; `deploy/electrumx.service`.

## 5. "My server disagrees with the explorer" — hash byte order

**Symptom:** a block hash you compute (or a fixture check) does not match
the explorer's value, although the server otherwise behaves fine.

**Cause:** byte order. ElectrumX works with hashes in **internal** order
(raw double-SHA256 digest). Explorers print the **reversed** display form.
`header_hash()` in `indexer/maza_coin.py` returns internal order by design
— it is what the server calls (`Coin.header_hash_rev`).

**Fix:** convert with `hash_to_display_hex()` before comparing with
explorer-style hex. README Step 5's HEX check reproduces the pinned mainnet
fixtures from `ALL_FIXTURES` as-written; `tools/oracle.py` is the
independent instrument for address/tx-value work.

**Source:** `indexer/maza_coin.py` lines 111-127, 155-165; README Step 5.

## 6. Startup failures — quick table

| Message / fingerprint | Meaning | Fix |
|---|---|---|
| installer fails at a git step (`git clone`, `fetch origin master`, `checkout <sha>`) | the destination is not the electrumx repo, the pin sha does not exist there, or there is no network — these abort via `set -e` with git's own error, before any custom message | confirm the destination is upstream `spesmilo/electrumx`; check connectivity; re-run (an EXISTING checkout at another commit is normalized: the installer checks it out at the pin rather than refusing) |
| installer: `REFUSING to install: checkout HEAD <sha> != pin <sha>` | rare guard: git reported checkout success but HEAD verified to a different commit — broken/exotic repository state | re-clone upstream into a fresh destination and re-run; report it upstream if reproducible |
| installer: `REFUSING to install: ... older than Python 3.10` | the pinned tree declares `requires-python = ">=3.10"` | pass a >= 3.10 interpreter as the installer's 2nd argument (`bash deploy/install-electrumx-dev.sh <dest-dir> <venv-python>`) |
| installer's `pip install` step fails with a plyvel build error | most commonly the LevelDB C headers are absent, so the plyvel wheel cannot compile (other build tooling gaps look similar) | install the per-distro headers listed in the installer (Debian/Ubuntu `libleveldb-dev build-essential python3-dev python3-venv`; Fedora `leveldb-devel gcc-c++ python3-devel`; Alpine `leveldb-dev g++ python3-dev`; macOS `brew install leveldb`) and re-run |
| installer exits with `plyvel is not importable — the leveldb DB backend is missing` | the post-install fingerprint could not import plyvel from THE VENV IT INSTALLED INTO — the headers may be fine but the package is missing from that interpreter | re-run the installer with the SAME venv python you are serving with; if it still fails, resolve the pip-build case above first |
| installer: `unexpected e-x dist: <version>` | the venv holds a different electrumx build than the pinned `e-x` 2.0.1 | re-run the installer at the pin; do not `pip install electrumx` from PyPI |
| `run_indexer.py --check-only` exits **2** printing `missing required env vars: ...` | one of `DB_DIRECTORY` / `DAEMON_URL` / `DB_ENGINE` unset | fill the env file (`deploy/electrumx.env.example` is the template); systemd imports it via `EnvironmentFile=/etc/electrumx-maza.env` |
| `--check-only` exits **3** printing `electrumx not importable` | the pinned tree is not installed into THAT interpreter's environment | run `deploy/install-electrumx-dev.sh` with the same venv python you are invoking the runner with |
| `--check-only` exits **4** printing `coin class failed to build...` | electrumx is importable but the MAZA coin class cannot be built from it — either a broken/partial install, or the stale PyPI 1.20.2 altcoin-stripped build (the diagnostic names the missing attribute, e.g. `no attribute 'DeserializerSegWit'`) | reinstall the pinned git tree (`deploy/install-electrumx-dev.sh`); the suite's integration tests also FAIL with a named diagnostic (they do NOT skip) when an importable electrumx is not dist `e-x` |
| systemd unit restart-loops | the `ExecStartPre` wiring gate (`--check-only`) is failing before every start | `journalctl -u electrumx` shows the check's output — it names the missing env var or broken wiring; fix the env file, `systemctl restart electrumx` |
| `systemd-analyze verify` rejects a modified unit with "neither a valid executable name nor an absolute path" for the ExecStart first word | a `${VAR}` was put where systemd expects an executable — systemd does NOT shell-expand the executable path | keep the shipped launcher-script pattern (`deploy/electrumx-launcher.sh`); env expansion belongs inside the launcher |
| port already in use on 50001 at start | an old electrumx process is still running (restart raced, or a second copy) | `systemctl status electrumx`; list listeners with `ss -ltnp` (look for 50001), stop the stale copy, restart the unit |

**Source:** `deploy/install-electrumx-dev.sh` (refusals + fingerprint
block); `indexer/run_indexer.py` `check_only()` exit codes; README Step 4b
(unit + restart-loop behavior); `deploy/electrumx.service`.
