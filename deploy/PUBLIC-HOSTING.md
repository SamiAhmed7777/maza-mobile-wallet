# Hosting a public wallet endpoint (the mazatest recipe)

This is the complete recipe for what `mazatest.sami-host.me` is: a public
HTTPS front door in front of a walletbench instance, so the Android wallet
works from any machine with no VPN, no signup, and no special network.

The live `mazatest` endpoint is a TEST deployment and is expected to be
dismantled when the project ends. Whoever hosts the official server repeats
these steps on their own box — nothing here is specific to our machines
except the example values, which are marked as such.

## Architecture (3 pieces)

```
phone (APK) --HTTPS--> Caddy (public :443, auto-TLS) --HTTP--> walletbench (:18701, bound to a private IP)
```

1. **walletbench** — the watch/broadcast backend from this repo
   (`deploy/install-walletbench.sh`). Holds NO private keys: it watches
   addresses and broadcasts client-signed transactions. Token-gated.
2. **Caddy** — public HTTPS with automatic Let's Encrypt certificates.
3. **DNS** — one A record pointing at the Caddy host.

## Steps

### 1. Deploy walletbench

On the server, from a checkout of this repo:

```bash
sudo bash deploy/install-walletbench.sh
```

The installer: creates a release dir, generates `/etc/maza-wallet-bench.env`
(0600) with a fresh random `WB_TOKEN` (reruns preserve an existing token
byte-identically), binds `WB_LISTEN_HOST` (tailscale IPv4 if present, else
127.0.0.1 — override in the env file if you want a different bind), starts
`maza-wallet-bench.service`, and health-gates on `GET /api/state` → 401.
State (address book) lives at `/var/lib/maza-wallet-bench/state.json`;
the installer takes a timestamped backup before every restart.

### 2. DNS

One A record at your DNS provider:

```
mazatest.example.com.   3600   IN   A   <public-IP-of-the-caddy-host>
```

Verify before continuing (NXDOMAIN breaks Caddy's ACME issuance):

```bash
dig +short mazatest.example.com @1.1.1.1     # -> your IP
```

### 3. Caddy site block

First, read the bind walletbench actually uses (it is written to
`/etc/maza-wallet-bench.env` as `WB_LISTEN_HOST` / `WB_LISTEN_PORT`; the
walletbench default is `127.0.0.1:18701` — the installer overrides it to a
private IP when the host has one):

```bash
grep -E '^WB_LISTEN_(HOST|PORT)=' /etc/maza-wallet-bench.env
```

Append to `/etc/caddy/Caddyfile`, proxying to THAT bind. Same-host example
(Caddy and walletbench on one box, walletbench on its default bind):

```caddyfile
# MAZA wallet bench (TEST endpoint — temporary; repo recipe: deploy/PUBLIC-HOSTING.md)
mazatest.example.com {
	log {
		output file /var/log/caddy/mazatest.example.com.access.log {
			roll_size 100MB
			roll_keep 5
		}
		format json
	}
	reverse_proxy 127.0.0.1:18701
}
```

Pre-create the log file with the caddy user's ownership if
`/var/log/caddy` is not writable by the caddy user (else the reload fails
with `open ...access.log: permission denied`):

```bash
sudo touch /var/log/caddy/mazatest.example.com.access.log
sudo chown caddy:caddy /var/log/caddy/mazatest.example.com.access.log
```

Then (root shell — `/etc/caddy` and the reload are root operations):

```bash
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy        # reload, never restart: no listener gap
```

Caddy obtains the Let's Encrypt certificate automatically on the first
request once DNS resolves publicly.

### 4. Token

The endpoint is token-gated by walletbench itself — there is no auth at the
Caddy layer. Rotate the token before first public exposure if it has ever
left your control. The replacement env file must be created atomically with
mode 0600 — never a world-readable intermediate (run as root):

```bash
sudo python3 - <<'EOF'
import secrets, re, os
p = "/etc/maza-wallet-bench.env"
env = re.sub(r"^WB_TOKEN=.+$", "WB_TOKEN=" + secrets.token_hex(16),
             open(p).read(), flags=re.M)
tmp = p + ".tmp." + secrets.token_hex(4)          # unique temp name
fd = None
try:
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)                          # enforce before first write
    data = env.encode()
    n = os.write(fd, data)
    if n != len(data):
        raise IOError("short write")
    os.close(fd)
    fd = None
    os.replace(tmp, p)                            # atomic publish
except BaseException:
    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    try:
        os.unlink(tmp)                            # no secret litter on failure
    except OSError:
        pass
    raise
EOF
sudo systemctl restart maza-wallet-bench
# verify: OLD token must now 401, NEW token must pass /api/state
```

The token is typed into the app's Connect card by each user (it is never
embedded in the APK — verified: the release APK's dex contains no token
material). Deliver the token to testers over a private channel, never a
group chat.

### 5. Verify from an external machine (not the server)

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://mazatest.example.com/        # expect 200
curl -s -o /dev/null -w "%{http_code}\n" https://mazatest.example.com/api/state  # expect 401
curl -s -H "Authorization: Bearer <token>" https://mazatest.example.com/api/state | head -c 200  # expect JSON
```

TLS check (verify the certificate is valid FOR THIS HOSTNAME and chains to
a trust store — the issuer itself is whichever ACME CA Caddy negotiated,
Let's Encrypt or ZeroSSL by default):

```bash
echo | openssl s_client -connect mazatest.example.com:443 \
  -servername mazatest.example.com -verify_hostname mazatest.example.com \
  -verify_return_error 2>/dev/null | grep -E "Verify return code"
# expect: Verify return code: 0 (ok)
```

### 6. Point the app at it

Install the APK → the Connect card's Server URL field →
`https://mazatest.example.com` → paste the token → CONNECT. The URL field
is free-text: any walletbench endpoint works, which is the point — the
default baked into a build is a convenience, never a requirement.

## Dismantling (the mazatest test endpoint)

1. Remove the DNS A record.
2. Remove the Caddy site block; `caddy validate` + `systemctl reload caddy`.
3. `sudo systemctl stop maza-wallet-bench && sudo systemctl disable maza-wallet-bench`
4. Optionally archive `/var/lib/maza-wallet-bench/` (address book + backups)
   and delete `/opt/maza-wallet-bench` + `/etc/maza-wallet-bench.env`.
5. Anything funded through the bench book that should be kept is recovered
   on-chain first (see README "The state file can vanish" note).

## Security posture of the test endpoint (deliberate differences)

- **Token is the only auth layer.** Caddy adds TLS + access logs only — no
  IP allowlisting, no rate-limit module (stock Caddy has none installed on
  this host). Exposure is bounded because walletbench itself: requires the
  bearer token on every API route, caps sends at 50 MAZA, flat 0.0001 MAZA
  fee, refuses NaN/non-finite amounts, and holds no private keys.
- **Access logs** at `/var/log/caddy/mazatest.example.com.access.log`
  (100MB × 5 rolls) — request lines and IPs, never headers; the token rides
  the `Authorization` header which Caddy does not log.
- **A production/official deployment** should revisit: per-user auth (or
  the ElectrumX protocol, which needs no token at all), rate limiting, and
  monitoring. See `docs/electrumx/README.md` for the no-token
  self-hostable path already packaged in this repo.

# Live verification of the mazatest deployment (2026-11-16, from a separate
# network-enabled host against the public name)

Re-run after review round 2 with identical results (same commands, same
outputs): root 200, /api/state 401, /api/watch/import 401, TLS
`Verify return code: 0 (ok)`.

```
$ curl -s -o /dev/null -w "%{http_code}" https://mazatest.sami-host.me/
200
$ curl -s -o /dev/null -w "%{http_code}" https://mazatest.sami-host.me/api/state
401          # 401 = no token -> correctly refused
$ curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
    -d '{"addresses":["..."]}' https://mazatest.sami-host.me/api/watch/import
401          # 401 = no token -> correctly refused
$ echo | openssl s_client -connect mazatest.sami-host.me:443 \
    -servername mazatest.sami-host.me -verify_hostname mazatest.sami-host.me \
    -verify_return_error 2>/dev/null | grep "Verify return code"
Verify return code: 0 (ok)
```

### Re-run capture (review round 3→4, verbatim transcript from an externally
### reachable host over the public path; executed 2026-11-16 20:51:26 UTC;
### `-w` now emits an explicit trailing newline per code)

```
$ date -u
Mon Nov 16 20:51:26 UTC 2026
$ curl -s -o /dev/null -w "%{http_code}\n" https://mazatest.sami-host.me/
200
$ curl -s -o /dev/null -w "%{http_code}\n" https://mazatest.sami-host.me/api/state
401
$ curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" -d '{"addresses":["MPHoBsbsNUduo7fsvMCREpDSMWpyeUxq2H"]}' https://mazatest.sami-host.me/api/watch/import
401
$ echo | openssl s_client -connect mazatest.sami-host.me:443 -servername mazatest.sami-host.me -verify_hostname mazatest.sami-host.me -verify_return_error 2>/dev/null | grep "Verify return code"
Verify return code: 0 (ok)
```
