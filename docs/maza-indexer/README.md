# Running a MAZA indexer - the community operator's guide

Goal of this document: you have a small VPS and some patience, and you want
to run **your own** MAZA indexer so that wallets and explorers can answer
address, transaction, block and Merkle-proof questions without trusting
somebody else's server. Everything referenced here lives in this
repository. If a step needs knowledge that only the maintainers have, that
is a bug - open an issue.

Companion documents: [API.md](API.md) (the HTTP contract, verbatim) and
[PROBE.md](PROBE.md) (the measurement that proves the indexer can read the
chain without a txindex).

The files you need for a deployment:

| File | What it is |
|---|---|
| `deploy/maza-indexer-install.sh` | The installer. One command does the whole job. |
| `deploy/maza-indexer.service.example` | The systemd unit template. The installer installs it as `maza-indexer.service`. |
| `deploy/maza-indexer-launcher.example` | The launcher the unit execs. It is a plain script; the unit names it by absolute path. |
| `maza_indexer/` (repo root) | The indexer package itself. The installer copies it into the release tree. |

## What you are building

```
mazad (your own full node)  <--  MAZA lean indexer  <--  wallets, explorers
      (no txindex!)                 (this guide)
```

- **mazad** holds the chain and answers RPC calls. You already run one, or
  you can point the indexer at one you trust.
- **The lean indexer** walks the chain through that RPC and builds its own
  index: addresses, transactions, blocks, Merkle proofs. It serves them over
  plain HTTP.
- **Wallets and explorers** query the indexer over HTTP instead of talking
  to a full node themselves.

### The one thing that matters: NO txindex

The old ElectrumX path required the node to run with `txindex=1`, and
building that txindex on this chain **deadlocked** the node. The chain never
finished it. So that path was a dead end.

This indexer does not need a txindex. It reads **whole blocks** - block by
block, in order - and extracts the transactions out of them itself. That is
a normal thing for a daemon to do, and it is **proven against the live
chain**: see [PROBE.md](PROBE.md), where a live node returned full
transactions for a block with `getblock` at verbosity 2 and no txindex
running.

So: **you do not need to turn on `txindex` in your node's config, and you
should not.** A lean node that has synced and stays synced is all this
indexer needs.

### What this indexer is not

- It is **read-only**. It serves public chain data. It does not accept
  transactions, does not broadcast, and does not sign anything.
- It does **not** replace a full node for wallet privacy. If you run a
  wallet that talks to your own node, keep doing that; the indexer is for
  *public* queries (an explorer, a block explorer plugin, a third-party
  wallet app that only speaks HTTP).
- It does **not** validate proof of work. It trusts your daemon's chain and
  checks the block *links* (the prevhash chain) as it walks. See the "What
  this does NOT prove" section of [PROBE.md](PROBE.md).

## Requirements

- **A synced MAZA node you can reach by RPC.** Operators run their own
  `mazad`; point `MAZA_INDEXER_RPC_URL` at it. On the same machine that is
  `http://127.0.0.1:12832` (12832 is mazad's default RPC port). The
  credentials are the `rpcuser` and `rpcpassword` lines from your
  `maza.conf`, and they go in their own keys - do not put them in the URL.
- **A 2GB-RAM-class VPS.** That is the smallest sensible box: the index
  process, the node's RPC connection and the database all live there. A
  2GB box running the node *and* the indexer is tight but workable; a 4GB
  box is comfortable.
- **Python 3.10 or newer.** The installer checks this and refuses to
  continue on anything older.
- **Disk space** - see the next section, because the honest answer is "we
  have not measured it yet".
- **systemd** and **curl** (the installer needs `curl` for its health
  gate). Both are on every current Ubuntu/Debian VPS.

## How much disk?

**Honest answer: the address index for the full chain has not been measured
yet.** Nobody has run a full sync of this indexer on real hardware and
recorded the size, so this guide does not quote a number it cannot back up.

What to expect, as a rough shape rather than a promise: the index is a
**single-digit number of gigabytes** for a full mainnet chain. Treat that
as an order of magnitude, not a figure to plan a disk around.

**Measure it yourself after your first sync and report it back** - this is
the number the community is missing:

```sh
du -sh /var/lib/maza-indexer
```

(If you chose a different data directory, `du -sh` that one instead.) If
your index is wildly bigger or smaller than a few GB, that is worth
reporting too - it would mean something is wrong with the indexer.

## How long does the first sync take?

**Honest answer: the first full sync takes real time on this chain.** The
indexer has to walk every block from the beginning, one RPC round trip at a
time, and the chain is not small.

Two things that are true and worth knowing:

- **The cursor persists and resumes.** If the indexer stops - a reboot, a
  crash, an OOM kill - it picks up where it left off. You do **not** start
  from block zero again.
- **Never trust a sync-rate number you have not measured.** This guide does
  not give you an ETA, because nobody has published a measured one. If you
  measure your own rate, it is worth reporting.

To watch the progress:

```sh
journalctl -u maza-indexer -f          # live log
curl -s http://127.0.0.1:18711/health  # current height
```

If `/health` answers but the height is not moving, the indexer is stuck -
read the journal.

## Install

The installer is a **staged cutover**: every run creates a new release
directory under `/opt/maza-indexer/releases/<timestamp>`, installs the unit,
moves the `current` symlink, restarts the service, and only then checks
that it is healthy. Nothing is edited in place, so a bad release can be
rolled back by moving one symlink.

### Step 1 - get the repository onto the box

From your own machine:

```sh
rsync -a --delete --exclude '.git' \
      /path/to/maza-mobile-wallet/  \
      operator@your-vps:/root/maza-indexer-src/
```

### Step 2 - run the installer

On the box, as root:

```sh
cd /root/maza-indexer-src
sudo bash deploy/maza-indexer-install.sh
```

That is the whole command. It installs the unit, the launcher, the
environment file and the service, then verifies the result.

> The installer is **not** something to run on a machine you care about
> without reading it first. It writes to `/etc`, `/opt` and `/var/lib`, it
> creates a system user, it restarts a systemd service, and - if the health
> check fails - it rolls back to the previous release. It never touches
> your node, your wallet, or anything outside the paths listed above.

### Step 3 - answer the questions

The installer asks seven questions. Each one can also be answered by
piping a file into it, or by editing `/etc/maza-indexer.env` afterwards
(the installer keeps any value it finds there, so you never re-answer a
question you have already answered).

These are **exactly** the variables the indexer package reads. The
installer writes no other key - there is no chain key, because the chain
identity comes from your node.

| Question | Default | What it is |
|---|---|---|
| `MAZA_INDEXER_RPC_URL` | `http://127.0.0.1:12832` | Full URL of your node's RPC. Must start with `http://` or `https://` and have a host part. |
| `MAZA_INDEXER_RPC_USER` | *(required)* | The `rpcuser` line from `maza.conf`. |
| `MAZA_INDEXER_RPC_PASSWORD` | *(required)* | The `rpcpassword` line from `maza.conf`. Read with `read -s`: **it is not echoed, not logged, and never printed.** |
| `MAZA_INDEXER_DATADIR` | `/var/lib/maza-indexer` | Where the index database lives. (The package's own default is the *relative* `./maza-indexer-data`; a systemd service needs an absolute path, so the installer sets one.) |
| `MAZA_INDEXER_BIND` | `127.0.0.1:18711` | Address and port the indexer listens on, in `host:port` form. |
| `MAZA_INDEXER_BATCH` | `24` | Block-hash lookups per crawl batch. |
| `MAZA_INDEXER_RATE` | `60` | Per-IP requests per minute the indexer serves before answering `429`. |

> **One launcher-only variable, not part of the app contract:**
> `MAZA_INDEXER_PYTHON` lets the launcher choose an interpreter (it
> defaults to `python3`). The package does not read it and the installer
> never writes it into the env file - if you want it, add the line to
> `/etc/maza-indexer.env` by hand and the installer will preserve it.

> **About the scheme in `MAZA_INDEXER_RPC_URL`:** the installer accepts
> `http://` and `https://`, as the key's contract says. Be aware that the
> current RPC client rewrites the scheme to `http` when it splits the URL,
> so the connection to your node is plain HTTP today. For a node on your
> own machine that is what you want anyway; keep the credentials in their
> own keys rather than in the URL.

Prefer to script it? Answer on stdin, one line per question, in the order
above (an empty line means "use the default"):

```sh
sudo bash deploy/maza-indexer-install.sh --non-interactive <<'EOF'
http://127.0.0.1:12832
my_rpc_user
my_rpc_password
/var/lib/maza-indexer
127.0.0.1:18711
24
60
EOF
```

The last three lines are optional if you are happy with the defaults. Note
that a password typed on stdin is visible in your shell history - prefer
the interactive prompt, or write the answers to a file with mode `600`,
use it, and delete it.

### Step 4 - check that it works

```sh
systemctl status maza-indexer
curl -s http://127.0.0.1:18711/health
```

`/health` should answer with something like:

```json
{"ok":true,"height":123456,"chain":"main","txs_indexed":987654}
```

The installer already did this check for you (30 tries, one second apart)
and fails loudly if the service never answered `200`. If you get here and
the health check fails, the journal says why:

```sh
journalctl -u maza-indexer -n 50 --no-pager
```

## Everyday commands

```sh
# Is it running?
systemctl status maza-indexer

# Is it enabled at boot?
systemctl is-enabled maza-indexer

# Follow the log
journalctl -u maza-indexer -f

# The last 200 log lines
journalctl -u maza-indexer -n 200 --no-pager

# Restart it (after editing the env file)
sudo systemctl restart maza-indexer

# Stop / start
sudo systemctl stop maza-indexer
sudo systemctl start maza-indexer
```

### The indexer's own `--status`

The package has its own status command, which reports the index state from
the inside (height, how far the cursor has got, how many addresses and
transactions are indexed). The service unit never passes arguments, so run
it by hand:

```sh
sudo bash -c 'set -a; . /etc/maza-indexer.env; set +a; \
  /opt/maza-indexer/current/bin/maza-indexer-launcher --status'
```

The env file is `0600 root:root`, so it can only be read as root - that is
why the command above runs as root. If that command writes anything into
the data directory, restore the ownership afterwards:

```sh
sudo chown -R maza-indexer:maza-indexer /var/lib/maza-indexer
```

To run it as the service user instead (no ownership fix-up needed), keep
the password out of the process list with `sudo --preserve-env`:

```sh
sudo bash -c 'set -a; . /etc/maza-indexer.env; set +a; exec sudo -u maza-indexer --preserve-env=MAZA_INDEXER_RPC_URL,MAZA_INDEXER_RPC_USER,MAZA_INDEXER_RPC_PASSWORD,MAZA_INDEXER_DATADIR,MAZA_INDEXER_BIND,MAZA_INDEXER_BATCH,MAZA_INDEXER_RATE /opt/maza-indexer/current/bin/maza-indexer-launcher --status'
```

The flag names come from the package CLI. If one ever differs, the package
is the authority - run `python3 -m maza_indexer --help`.

If you added extra keys to `/etc/maza-indexer.env` by hand (the installer
preserves them), add those names to the `--preserve-env` list as well, or
the command will run without them.

## Updating

**Re-run the installer.** That is the whole update procedure.

```sh
cd /root/maza-indexer-src        # after rsyncing the newer tree
sudo bash deploy/maza-indexer-install.sh
```

It answers no questions you have already answered (your answers are kept in
`/etc/maza-indexer.env`), builds a new release directory, archives the
previous release to `/opt/maza-indexer/backups/`, moves the `current`
symlink, restarts the service and health-checks the result. If the health
check fails, it rolls back to the previous release by itself and tells you.

The **old release stays on disk**, so you can always go back:

```sh
sudo ln -sfn /opt/maza-indexer/releases/<old-stamp> /opt/maza-indexer/current
sudo systemctl restart maza-indexer
```

Your index database in `/var/lib/maza-indexer` is **not** touched by an
update. If a new release needs a schema change it will say so in the log.

## Recovery: the indexer aborted on a prevhash mismatch

If the indexer stops with a **prevhash mismatch**, read this.

Every block header contains the hash of the block before it (its
*prevhash*). The indexer walks the chain and checks that link on every
block: the block it just read must have the hash of the block it read
before as its prevhash. When that check fails, the indexer **stops on
purpose** instead of continuing, because the chain it has indexed so far
and the chain the node now reports are two different histories - the chain
reorganised underneath it (a reorg), or the node is serving a different
chain than before.

Stopping is the safe behaviour. The indexer would rather stop than quietly
serve an index built from blocks that are no longer in the chain.

**What to do:**

1. Read the log - it names the height where the mismatch was found:
   ```sh
   journalctl -u maza-indexer -n 100 --no-pager | grep -i -A5 -B5 mismatch
   ```
2. Check that your node is fine and synced:
   ```sh
   <your-node-cli> getblockchaininfo | head -20
   ```
3. Delete the index data for the affected range so the indexer re-ingests
   it from the new chain. `--reorg-delete` **requires the height** - it
   deletes every block at or above that height:
   ```sh
   sudo bash -c 'set -a; . /etc/maza-indexer.env; set +a; \
     /opt/maza-indexer/current/bin/maza-indexer-launcher --reorg-delete <height>'
   ```
   The command does the deletion in one transaction, recomputes the
   affected address balances, rewinds the cursor to just below the height
   you gave it, and exits. The next `run` re-crawls that span. Use the
   height the mismatch was reported at.
4. Restore ownership if the command wrote into the data directory as root:
   ```sh
   sudo chown -R maza-indexer:maza-indexer /var/lib/maza-indexer
   ```
5. Restart and watch it re-ingest:
   ```sh
   sudo systemctl restart maza-indexer
   journalctl -u maza-indexer -f
   ```

**Do not delete the whole data directory** unless the package tells you to.
It throws away the index you already built and turns one reorg into a full
re-sync.

## Putting it behind HTTPS - the front door

The indexer binds `127.0.0.1` by default, which means **nothing outside
the box can reach it**. That is the recommended starting shape. To let
people use your indexer, put a TLS-terminating reverse proxy in front of
it. [Caddy](https://caddyserver.com/) is the easy option: it gets you a
real certificate automatically.

Add this to your Caddyfile and reload Caddy:

```caddyfile
# Public indexer endpoint. TLS is terminated by Caddy; the indexer itself
# stays on 127.0.0.1 and speaks plain HTTP.
indexer.example.org {
    encode zstd gzip

    # handle_path strips the "/indexer" prefix, so the upstream sees the
    # paths in the API contract unchanged:
    #   /indexer/health              -> /health
    #   /indexer/api/v0/address/<a>  -> /api/v0/address/<a>
    handle_path /indexer/* {
        reverse_proxy 127.0.0.1:18711
    }

    handle {
        respond "This host serves a MAZA indexer. Try /indexer/health" 404
    }
}
```

Then the public URLs are:

```
https://indexer.example.org/indexer/health
https://indexer.example.org/indexer/api/v0/address/<address>
https://indexer.example.org/indexer/api/v0/tx/<txid>
https://indexer.example.org/indexer/api/v0/block/<height>
https://indexer.example.org/indexer/api/v0/proof/<height>/<txid>
https://indexer.example.org/indexer/api/v0/search?q=<query>
https://indexer.example.org/indexer/api/v0/stats
```

(If you would rather have no path prefix at all, use a subdomain and drop
the `handle_path` block: `indexer.example.org { reverse_proxy 127.0.0.1:18711 }`.
Then `/health` and `/api/v0/...` map one-to-one, exactly as the contract in
[API.md](API.md) is written.)

**If you bind the indexer to a public address instead**
(`MAZA_INDEXER_BIND=0.0.0.0:18711`), read this: the indexer ships with a
**rate limiter, and that rate limiter is the only abuse control** it has.
There is no authentication, no API key and no per-user quota. Caddy in
front is the recommended shape - it gives you TLS, connection limits, and
a place to put request logging and firewall rules. A publicly bound indexer
with no proxy in front is an open relay of public chain data, and somebody
will find a way to make it expensive for you.

Whichever shape you pick, put the indexer and the proxy on the same box and
keep the indexer on loopback.

## Security notes

- **The service serves public chain data and nothing else.** It is
  read-only. There is no admin API, no key, no wallet, and no signing
  material anywhere near it.
- **Your node's RPC credentials live in `/etc/maza-indexer.env`, mode
  `0600`, owned by `root:root`.** systemd reads that file as root and
  injects the values into the service's environment. The service user
  cannot read the file itself.
- **The password is never printed.** The installer reads it with `read -s`
  (nothing appears on screen, nothing lands in your scrollback or shell
  history), never writes it to the log, and never passes it on a command
  line where `ps` could show it.
- **The service runs as its own unprivileged user** (`maza-indexer`), not as
  root. The unit is hardened: `NoNewPrivileges`, `ProtectSystem=strict`
  with a single writable path (the data directory), `PrivateTmp`,
  `ProtectHome`, and a handful of kernel protections.
- **The indexer only needs to read the chain over RPC.** Nothing about
  your node's wallet is exposed by the indexer, and the indexer never asks
  the node for anything wallet-related.
- **Updates are a re-run of the installer.** Staged cutover, the previous
  release is kept, a bad release is rolled back automatically.
- **Do not put a real credential in this repository.** The files in
  `deploy/` and `docs/maza-indexer/` contain placeholders only.

## More than one operator

**Every operator's instance is independent.** Your indexer and someone
else's indexer do not talk to each other, do not share a database and do
not need to. Each one builds its own index from its own node. Two operators
can disagree about a chain detail only in the way two independent readers
of the same chain can.

That independence is the point, and it is also where the roadmap is:
**wallets will cross-check instances** - asking a second indexer for the
same transaction or block and comparing the two answers, so a single
misbehaving or compromised server cannot lie to a wallet. Two-source
verification is planned, not shipped. Today the only cross-check you get is
the one you build yourself by running two instances.

## Troubleshooting

**`/health` never answers.**
```sh
journalctl -u maza-indexer -n 100 --no-pager
systemctl status maza-indexer
```
The usual causes: the RPC credentials are wrong, the node is not reachable
from this box, or the service cannot write its data directory.

**The service restarts in a loop.**
`Restart=on-failure` means it retries every 5 seconds. The log tells you
why it died. A wrong RPC password is the usual cause.

**The installer fails at the health gate.**
It rolls back to the previous release if there was one, and prints the
last 40 journal lines. If the journal shows the indexer making normal
progress and only the *bind* was late, start it by hand and wait:
`sudo systemctl restart maza-indexer && journalctl -u maza-indexer -f`.

**`systemd-analyze verify` complains about the unit.**
The installer runs that check itself and refuses to start a unit that does
not verify. If you edited the unit by hand, look at what you changed - the
usual mistake is putting a variable in the `ExecStart` path. That is fatal:
systemd will not accept `${VAR}` as the executable, which is exactly why
the unit execs a **fixed absolute path** to the launcher script
(`/opt/maza-indexer/current/bin/maza-indexer-launcher`) and lets the
launcher do the expansion.

**The indexer is stuck at one height.**
Probably a prevhash mismatch (see "Recovery" above) or a node that is still
in IBD (`ibd=True`). Check the node first: an indexer cannot index a chain
that its node has not finished syncing.

**You need to check the unit file on the box:**
```sh
systemctl cat maza-indexer
```

## Honest limits

- The **disk usage** of a full index has not been measured. Measure it and
  report it.
- The **sync rate** has not been measured. Do not believe a sync ETA from
  anyone, including this document, until you have measured it yourself.
- The **indexer does not validate proof of work.** It trusts the node's
  chain and checks block links. See [PROBE.md](PROBE.md).
- The **API contract is frozen**, but the code behind it is young. Treat
  the contract in [API.md](API.md) as the agreement and the implementation
  as the thing still being finished.
- The **multi-operator cross-check** is a roadmap item, not a feature.
