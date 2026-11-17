# MAZA chain parameters — quick reference

One page of every constant the ElectrumX kit depends on, each with its
source. When this table and the code disagree, **the code wins** — fix the
table by PR, never the other way round. Values below are quoted from the
repo at the current tree; if you edit `indexer/maza_coin.py`, re-check every
row in the "Source" column (symbol names are grep-stable; line numbers are
tree-relative).

Companion docs: [README.md](README.md) (zero-to-serving walkthrough),
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) (symptom → fix),
[TAKEOVER.md](TAKEOVER.md) (maintainer runbook).

## Chain identity

| Parameter | Value | Source |
|---|---|---|
| Reference client | MazaCore 0.16.3 | github.com/MazaCoin/maza, tag v0.16.3; DECISIONS.md D1/D2 |
| Genesis hash | `00000c7c73d8ce604178dae13f0fc6ec0be3275614366d44b1b4b5c6e238c60c` | `indexer/maza_coin.py` `GENESIS_HASH` (line 46) |
| Block spacing | 120 s **per algo**; multi-algo makes effective block intervals shorter | `indexer/maza_coin.py` `BLOCK_SPACING_SECS` (line 52); DECISIONS.md D5 |
| Block identity hash | double-SHA256 of the 80-byte header for **every** block, algorithm-independent | `indexer/maza_coin.py` `header_hash` (lines 155-165); MazaCore `primitives/block.cpp:18-21` |
| PoW display names | `sha256d` / `minotaurx` selected by the version type byte (bits 16..23); versions >= 0x20000000 display as `sha256d` regardless (legacy floor, `LEGACY_SHA256D_VERSION_FLOOR`) | `indexer/maza_coin.py` lines 55-63, 130-152 |
| Hive PoW | sits in the consensus mix per DECISIONS.md D2 — mining-validity only; needs **zero** indexer code | DECISIONS.md D2; README "The multi-algo trap, solved" |
| Hash byte order | `header_hash()` returns the **internal** order (raw digest). Explorer-style hex is the **reversed** display form — convert with `hash_to_display_hex()` before comparing | `indexer/maza_coin.py` lines 111-127 |

## Addressing and keys

| Parameter | Value | Source |
|---|---|---|
| P2PKH address version byte | 50 (0x32) — addresses start with `M` | `indexer/maza_coin.py` `P2PKH_VERSION_BYTE` (line 47) |
| P2SH address version byte | 9 | `indexer/maza_coin.py` `P2SH_VERSION_BYTE` (line 48) |
| WIF (private key) version byte | 224 (0xE0). Komodo config text says 244 — the chain code wins per DECISIONS.md D3 | `indexer/maza_coin.py` lines 49-50; DECISIONS.md D3 |
| Bech32 HRP | `maza` | `indexer/maza_coin.py` `BECH32_HRP` (line 51); chainparams.cpp:177 |
| Desktop MazaCore derivation | `m/0'/0'/k` | DECISIONS.md D3 |
| This repo's mobile wallet derivation | `m/44'/13'` | DECISIONS.md D8 |
| Light clients | pick their own derivation; the server does not care | README "MAZA chain facts" |

## Daemon requirements

| Parameter | Value | Source |
|---|---|---|
| RPC port | 12832 | `indexer/maza_coin.py` `DAEMON_RPC_PORT` (line 53) |
| Minimum daemon version | 0.16.3 (ElectrumX's Bitcoin-class default does not apply to this chain) | `indexer/maza_coin.py` `MIN_REQUIRED_DAEMON_VERSION` (line 193) |
| Required daemon indexes | `("txindex",)` — the server refuses an index-less daemon | `indexer/maza_coin.py` `REQUIRED_DAEMON_INDEXES` (line 195) |
| Synced check | `getblockchaininfo`: `headers == blocks`, `initialblockdownload: false` | README Step 2 item 4 |

## ElectrumX profile

`build_coin_class()` in `indexer/maza_coin.py` (lines 168-210) defines the
coin class. Registration is programmatic: `Env(coin=<class>)` via
`indexer/run_indexer.py` — the `COIN=` env-name lookup scans only
`electrumx.lib.coins` and cannot see out-of-module classes (run_indexer.py
module docstring).

| Parameter | Value | Source |
|---|---|---|
| NAME / SHORTNAME / NET | MazaCoin / MAZA / mainnet | `indexer/maza_coin.py` lines 182-184 |
| Deserializer | `lib_tx.DeserializerSegWit` | `indexer/maza_coin.py` line 189 |
| Entry point | `python3 indexer/run_indexer.py` (the `Env(coin=...)` runner) | `indexer/run_indexer.py` |
| Source pin | git commit `ee28cd8ddcc61019d78880ad59582b9b4ce3cc99`, dist name `e-x`. PyPI `electrumx` 1.20.2 is a stale altcoin-stripped build and is rejected (tests FAIL with a named diagnostic when an importable electrumx is not dist `e-x`; the installer's fingerprint block refuses it with `unexpected e-x dist`, including the not-installed-as-e-x case) | `indexer/maza_coin.py` `ELECTRUMX_PIN` (line 108); `deploy/install-electrumx-dev.sh` `PIN` + fingerprint block; `requirements-dev.txt`; `tests/test_chain_params.py` `_coin_cls_or_skip` |
| Python floor | >= 3.10 (`pyproject.toml` at the pin); installer refuses older interpreters | `deploy/install-electrumx-dev.sh` lines 29-33 |
| DB backend | the pinned tree ships **none**; serving with `DB_ENGINE=leveldb` needs the `leveldb` extra (plyvel), which the installer installs and import-asserts | `deploy/install-electrumx-dev.sh` pip step + post-install fingerprint block (lines 52-95) |
| Install fingerprint | dist `e-x` == 2.0.1; `DeserializerSegWit` present; > 100 coin classes; plyvel importable | `deploy/install-electrumx-dev.sh` post-install fingerprint block |
| DB size estimate | `TX_COUNT` 14,000,000 at height `TX_COUNT_HEIGHT` 4,400,000; `TX_PER_BLOCK` 2 — preallocation/disk-budget anchors, not promises | `indexer/maza_coin.py` lines 196-198 |

## Listeners and environment

| Parameter | Value | Source |
|---|---|---|
| Required env vars | `DB_DIRECTORY`, `DAEMON_URL`, `DB_ENGINE` (leveldb or rocksdb) | `indexer/run_indexer.py` `REQUIRED_ENV_VARS` (line 38) |
| systemd listener | `SERVICES=tcp://127.0.0.1:50001` — loopback only; public TLS is a proxy's job | `deploy/electrumx.env.example` |
| compose listener | in-container `tcp://0.0.0.0:50001`; HOST mapping loopback-only `127.0.0.1:50001:50001` | `deploy/docker-compose.yml` lines 42, 45-48 |
| Public TLS | nginx `stream {}` proxy: `50002 ssl` to `127.0.0.1:50001`, certbot certs read by the nginx root master | README Step 4 |
| systemd env file | `/etc/electrumx-maza.env` (chmod 600 — `DAEMON_URL` carries RPC credentials) | `deploy/electrumx.service` line 41; `deploy/electrumx.env.example` header |
| systemd unit name | `electrumx` (`journalctl -u electrumx`); launcher at `/usr/local/sbin/electrumx-maza-launcher`; `Restart=on-failure`, `RestartSec=10`; `StateDirectory=electrumx-maza` | `deploy/electrumx.service` |
| `--check-only` exit codes | 0 wiring OK; 2 missing required env; 3 electrumx not importable; 4 coin class failed to build | `indexer/run_indexer.py` `check_only()` (lines 41-66) |
| serve exit codes | 1 abnormal termination (logged with traceback), 0 clean | `indexer/run_indexer.py` `serve()` |

## Verification anchors

- `ALL_FIXTURES` (`indexer/maza_coin.py` lines 67-106): 6 real mainnet
  headers harvested live — 4 sha256d-era (genesis `h0`, `h2000000`,
  `h2105603`, `h4480773`) plus 2 genuine MinotaurX type-1 headers
  (`h4480797`, `h4480789`), which pin the finding that identity hashing is
  algorithm-independent. Their raw hex lives in the source file; the README
  Step 5 HEX check reproduces them as-written.
- `tests/test_chain_params.py` pins the profile against those fixtures;
  electrumx integration tests skip cleanly without the pinned tree.
- Independent instruments: `tools/oracle.py` (BIP39/BIP32 official vectors +
  MAZA profile, node-validated) and `tools/txverify.py` (offline
  SIGHASH_ALL + ECDSA, proven against a real MazaCore-signed mainnet tx).
