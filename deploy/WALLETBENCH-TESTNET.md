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
| client transport | tunnel-host listener :18701 | tunnel-host listener :18702 (same tunnel unit, second `-L` forward) |
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
user-visible points here.

Client transport (measured 2026-11-23): direct cross-node tailnet TCP to the
bench host's tailnet bind FAILED FROM BOTH TESTED CLIENTS on BOTH ports
(:18701 and :18702 — fresh probe matrix: connection refused/timeout, HTTP
000), the tailscale netstack-filter behavior the mainnet bench already lived
through; the same clients reach BOTH ports fine through the tunnel host's
listener. The working path mirrors the mainnet bench's proven topology: the
maintainers' tunnel unit carries BOTH forwards
(`-L <local-bind-ip>:18701:<bench-host-ip>:18701
-L <local-bind-ip>:18702:<bench-host-ip>:18702` — placeholder vocabulary as
in `deploy/maza-bench-tunnel.service.example`; the maintainers' real unit
stays off-repo), so tailnet clients reach `<tunnel-host>:18702` exactly like
`<tunnel-host>:18701`. Client-side
verified 2026-11-23: both ports answer 401 from a tailnet-joined
machine (authenticated gates reachable, token still required per port).
For a self-hosted twin of this setup, add the matching second `-L` to
your own tunnel unit (`deploy/maza-bench-tunnel.service.example` shows
the shape). ANY future public exposure of the testnet bench is its own
decision and inherits the public-endpoint security rule (rotate the
token BEFORE exposure, verify old tokens 401, deliver tester tokens by
DM only).

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
