# MAZA bench watchdogs (M16 ops hardening)

Self-healing guards for the serving surfaces of the MAZA mobile wallet
bench, mirroring the fleet-proven `/usr/local/bin/dashcaddy-watchdog`
pattern (selfhealing-service-watchdogs skill, kill-tested on DashCaddy@DNS2)
with the mazapay notifier's alert-once semantics (cooldown stamp written
only after a confirmed Telegram delivery).

## Roles

| Role | Host | Script | Guards | Heal | Alert-only classes |
|---|---|---|---|---|---|
| `bench` | samihost | `maza-bench-watchdog.sh bench` | `maza-wallet-bench.service` API probe (`/api/state` = 401/200 = healthy) | bounded restart + readiness poll | `DISK-HIGH`, `STATE-FILE-MISSING` |
| `tunnel` | DNS2 | `maza-bench-watchdog.sh tunnel` | full-chain probe of the local tunnel bind (`/api/state` through the ssh -L forward) + listener check on the bind port | bounded restart when the unit is inactive OR active with NO bound listener (dead/wedged channel — the ssh -L listener binds only after auth); alert-only when active WITH a bound listener | `BACKEND-DOWN` (tunnel active, listener bound, chain dead — a restart cannot fix a remote backend), `DISK-HIGH`, `CONFIG` |
| `indexer` | samihost | `maza-indexer-watchdog.sh` (single role) | `maza-indexer.service` `/health` probe (200 = answering) + crawler-stall check on `crawler_progress_age_s` | bounded restart + readiness poll on probe-down OR sustained stall | none (an unavailable stall signal never triggers a heal — see below) |

### Indexer watchdog: why the stall class is age-based (IDX-9c-ii)

`/health` carries `crawler_progress_age_s` — seconds since the crawl thread
last made a scheduling move. HEIGHT FROZEN alone is normal in two live
shapes: tip rest (no new blocks to ingest) and an RPC pause (a mazad
restart window; the crawl retries with capped backoff and marks progress
on every wake, so the age stays fresh). A height-only watchdog would
restart a healthy indexer every quiet stretch. The age field grows only
when the crawl thread is genuinely wedged; that, and only that, is the
healable stall class. A long node outage is loud in the journal
(RPC-PAUSE lines) and does NOT trip this watchdog. Startup tolerance:
age = null (crawler never ran in this process) or an unparsable body ->
NO stall eval that cycle. The stall heal restarts a service whose ingest
is idempotent (IDX-9b same-hash skip), so a restart mid-catch-up is safe.

The indexer watchdog also logs the probe latency's p95 over a rolling
50-sample window every cycle (`OK code=200 lat=..ms p95=..ms h=.. age=..
samples=..`) — the keep-measuring instrument for the RW-split + cheap-counts
fixes during full-chain catch-up. It deliberately has NO disk guard: the
bench watchdog on the same host owns that class; duplicating it would
double-alert.

### Failure-class inventory (history-based, not hypothetical)

- **Tunnel ssh blackhole** — an `ssh -N -L` forward can die or hang; the
  unit carries `Restart=always`, but a hung transport looks active while
  the chain is dead, hence the full-chain probe plus the listener check.
  WITNESSED 2026-11-18 (M16-b): a pre-auth ssh wedged on a starved remote
  sat "active" for 51 minutes holding its TCP connection, binding nothing,
  while the remote backend was healthy — the old active-vs-inactive
  classification alert-onlyed it as BACKEND-DOWN and only a manual restart
  healed it. The listener check distinguishes a dead channel (no bound
  listener → heal by restart) from a genuinely down remote backend
  (listener bound → alert-only).
- **walletbench wedge/crash** — `Restart=always RestartSec=3` covers clean
  exits; the watchdog covers the alive-but-not-answering case and verifies
  recovery by polling, never assuming.
- **Bench state file vanished once** (run log 2026-11: the address book
  `state.json` disappeared, deleter unknown) — content loss is not
  restartable, so this class is alert-only, pointing at the
  `state.json.bak-*` restore path.
- **Disk pressure** — both hosts have sat >90% full historically; alert
  only, manual cleanup (a watchdog must never delete anything).

## Alert classes

| Class | Meaning | Cooldown |
|---|---|---|
| `HEALED` | probe failed twice, restart recovered | 15 min |
| `HEAL-FAILED` | restart did not recover within the readiness window | 15 min |
| `ESCALATE` | MAX_CONSEC_HEALS (3) consecutive failed heals — manual help needed | 15 min |
| `TUNNEL-DOWN` | tunnel unit active but its forward is NOT bound — dead/wedged ssh channel; the watchdog heals by bounded restart (backend reachability unknown while the channel is down) | 15 min |
| `BACKEND-DOWN` | tunnel unit active with the listener BOUND but the full-chain probe failing (remote problem). When the listener check itself is unavailable (no `ss`, an `ss` that exits non-zero, unparsable probe URL) the watchdog treats the listener as bound and stays in this class — the log line then reads `listener check UNAVAILABLE`. Note: a MISCONFIGURED `MAZA_TUNNEL_PROBE_URL` (pointed at something other than the local tunnel bind) presents as this same class by design — the watchdog cannot distinguish it locally, so verify the URL first when this alert fires. | 15 min |
| `CONFIG` | required role config missing (e.g. `MAZA_TUNNEL_PROBE_URL` unset) | 6 h |
| `DISK-HIGH` | filesystem usage >= threshold (default 90%) | 6 h |
| `STATE-FILE-MISSING` | bench address book missing/empty | 6 h |

Alerts go to `MAZA_WATCHDOG_CHAT` (default: the fleet default Sami DM, the
same audience as the DashCaddy watchdog). Deliveries are counted by
`"ok":true` in the Telegram response; the cooldown stamp is written ONLY on
a confirmed send, so a Telegram outage can never burn an alert window.
Second occurrence of the same class inside the cooldown heals silently and
logs `ALERT-SUPPRESSED`.

## Install (per host)

Deploy only after the graded commit lands on origin (repo rule). The
deployed script must stay byte-identical to the repo copy.

samihost (bench role):

```bash
scp deploy/watchdog/maza-bench-watchdog.sh samihost:/usr/local/bin/maza-bench-watchdog
scp deploy/watchdog/maza-bench-watchdog.service deploy/watchdog/maza-bench-watchdog.timer \
    samihost:/etc/systemd/system/
ssh samihost 'install -d -m 700 /var/lib/maza-bench-watchdog
  printf "%s\n" "MAZA_WATCHDOG_CHAT=637130179" > /etc/maza-bench-watchdog.env   # + tunnel URL on DNS2
  install -m 600 /dev/null /etc/maza-bench-watchdog.token && cat > /etc/maza-bench-watchdog.token  # paste token, Ctrl-D
  chmod 600 /etc/maza-bench-watchdog.env /etc/maza-bench-watchdog.token
  systemctl daemon-reload && systemctl enable --now maza-bench-watchdog.timer'
```

DNS2 (tunnel role): same, with `maza-tunnel-watchdog.{service,timer}`, role
arg `tunnel`, and `MAZA_TUNNEL_PROBE_URL=http://<tunnel-bind-ip>:18701/api/state`
set in `/etc/maza-bench-watchdog.env` (the bind address is host-specific and
stays out of the repo, per the M19 IP-hygiene rule).

samihost (indexer watchdog):

```bash
scp deploy/watchdog/maza-indexer-watchdog.sh samihost:/usr/local/bin/maza-indexer-watchdog
scp deploy/watchdog/maza-indexer-watchdog.service deploy/watchdog/maza-indexer-watchdog.timer \
    samihost:/etc/systemd/system/
ssh samihost 'install -d -m 700 /var/lib/maza-indexer-watchdog
  printf "%s\n" "MAZA_WATCHDOG_CHAT=637130179" > /etc/maza-indexer-watchdog.env
  install -m 600 /dev/null /etc/maza-indexer-watchdog.token && cat > /etc/maza-indexer-watchdog.token  # paste token, Ctrl-D
  chmod 600 /etc/maza-indexer-watchdog.env /etc/maza-indexer-watchdog.token
  systemctl daemon-reload && systemctl enable --now maza-indexer-watchdog.timer'
```

The unit's ExecStart is an absolute path (`/usr/local/bin/maza-indexer-watchdog`);
the M18 install rule applies — the unit files above are part of the install,
not optional.

The Telegram token is staged to a 0600 file (`/etc/maza-bench-watchdog.token`,
one line) via stdin — it is never placed in argv, env files, or the repo, and
the script never logs or prints it.

## Post-install verification

```bash
systemctl list-timers --all | grep maza-.*-watchdog     # timers armed
systemctl start maza-bench-watchdog.service && journalctl -u maza-bench-watchdog -n 5   # healthy cycle is silent, exit 0
cat /var/log/maza-bench-watchdog.log                     # no HEAL/GUARD lines on a healthy cycle
bash deploy/watchdog/maza-bench-watchdog-selftest.sh     # 37 offline assertions, exit 0
systemctl start maza-indexer-watchdog.service && journalctl -u maza-indexer-watchdog -n 5
cat /var/log/maza-indexer-watchdog.log                   # OK code=200 lat=.. p95=.. h=.. age=.. samples=..
bash deploy/watchdog/maza-indexer-watchdog-selftest.sh   # 61 offline assertions, exit 0
```

## Kill-test (the M16 acceptance criterion)

1. `systemctl stop maza-wallet-bench` (a stop suppresses systemd's own
   `Restart=always` — whatever recovers next is the WATCHDOG, not systemd).
2. Wait one 60s cycle. Expect in the log: `HEAL-START` → `HEAL-OK`, an
   `ALERT-SENT class=HEALED` (with the token staged) or `ALERT-NO-TOKEN`
   (without), and the service active + answering 401 again.
3. Repeat the stop inside the alert cooldown: the service must recover
   again while the log shows `ALERT-SUPPRESSED` — healing continues, alert
   spam does not.
4. Kill-test the tunnel role the same way with
   `systemctl stop maza-bench-tunnel` on DNS2.
5. `systemctl kill --signal=KILL maza-wallet-bench` (the item's literal
   criterion): systemd auto-restarts in ~3s; the next watchdog cycle
   confirms healthy and stays silent (no heal needed, no alert).

## Scope fence

This watchdog only ever touches `maza-wallet-bench.service` and
`maza-bench-tunnel.service`. It never edits mazad, the mazapay tree, the
node wallet, or any key/config outside its own state/log/env files. Probes
are read-only HTTP status reads; no token is ever sent or logged (a 401 IS
the healthy answer).
