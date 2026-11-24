# Walletbench TESTNET backend (S-6-ii controlled environment)

Operator-facing notes for the sibling service installed by
`deploy/install-walletbench-testnet.sh`. This is the backend half of
S-6-ii (testnet mode per spec Phase 7: controlled-environment testing,
never broadcast unintended mainnet transactions).

## What it is

A second walletbench instance on samihost pointed at the samihost TESTNET
mazad, sharing the SAME release tree as the mainnet bench
(`/opt/maza-wallet-bench/current`) but with its own everything else:

| | mainnet bench | testnet bench |
|---|---|---|
| systemd unit | `maza-wallet-bench.service` | `maza-wallet-bench-testnet.service` |
| env file | `/etc/maza-wallet-bench.env` | `/etc/maza-wallet-bench-testnet.env` |
| bind | tailscale IP :18701 | tailscale IP :18702 |
| node RPC | mainnet mazad (12832) | testnet mazad (`/var/lib/mazad-testnet`, RPC 18446) |
| bench account | `mobile-play` | `mobile-play-testnet` |
| state file | `/var/lib/maza-wallet-bench/state.json` | `/var/lib/maza-wallet-bench-testnet/state.json` |
| token | own | own (independent — rotating one does not affect the other) |
| RPC creds | conf path | dedicated `rpc.conf` (0600, mazad-owned) inside the state dir — parsed from the testnet node cmdline at install time; the env carries only `WB_RPC_CONF` pointing at it |

Walletbench code is network-agnostic (all of it is env-parameterized:
`WB_TOKEN`, `WB_RPC_URL/USER/PASSWORD`, `WB_LISTEN_HOST/PORT`,
`WB_ACCOUNT`, `WB_MAX_SEND`, `WB_STATE_FILE`) — this service is env + unit
only; no app or backend code changes.

## Exposure posture

TAILNET-ONLY, by decision. There is no public front door for :18702. The
app-side Settings network switch (S-6-ii) is not shipped yet, so nothing
user-visible points here; when a device proof needs it, BlueStacks on a
tailnet-joined machine reaches the tailnet bind directly. ANY future
public exposure of the testnet bench is its own decision and inherits the
public-endpoint security rule (rotate the token BEFORE exposure, verify
old tokens 401, deliver tester tokens by DM only).

## Install / verify

```bash
# on samihost, from the rsynced repo root
bash deploy/install-walletbench-testnet.sh
```

The installer is idempotent (token preserved exactly across reruns,
state.json backed up, keep 5) and gates on THREE checks before declaring
DONE:

1. `/api/state` on the bound IP answers **401** (serving + locked);
2. authenticated `GET /api/watch/utxos` with the env token answers **200
   JSON** — this exercises the real path (token -> service -> state ->
   testnet mazad RPC; the service cold-starts its bench book off the
   testnet node wallet here, so node wallet access is proven too);
3. identity: the release's own `walletbench.config` must resolve the RPC
   endpoint to `127.0.0.1:18446` with the env applied.

RPC endpoint+credentials are parsed IN-PROCESS from the testnet mazad's
`/proc` cmdline (exact `-datadir=/var/lib/mazad-testnet` match required;
that is where the testnet node carries them) and written to a dedicated
0600 mazad-owned conf file in the state dir — never echoed, never in argv,
never in the transcript, and never inside the systemd-readable env file
(which avoids the EnvironmentFile quoting layer entirely).

## Known limits (honest split-state)

- Rollback: `systemctl disable --now
  maza-wallet-bench-testnet.service` STOPS serving; the installed
  env/unit/state files remain on disk and are removed manually.

- The samihost testnet chain is EMPTY (blocks=0, headers=0, ibd=True as
  of 2026-11-23): the backend serves and generates book addresses, but
  any ON-CHAIN testnet send/broadcast proof waits until the testnet
  chain actually advances (or is mined forward). The S-6-ii DONE
  criterion stays open until then.
- The testnet mazad currently has no systemd unit (it was started
  manually); if the host reboots, restart it before this service is
  meaningful. Wiring a unit for it is separate ops work.
- The unit shares the release tree with the mainnet bench on purpose
  (one `current` symlink; every mainnet installer run also moves the
  testnet unit's code on its next restart).
