# APK distribution channel (M6)

The MAZA mobile wallet release APK is downloadable over the public HTTPS front
door at an auth-gated static path. This is the standing channel Sami (and later
testers, if Payu widens distribution) use to fetch the current signed release
build without SSH or Telegram file-transfer round trips.

    https://mazatest.sami-host.me/apk/maza-wallet-v1.1.0.apk
    https://mazatest.sami-host.me/apk/INDEX.txt
    https://mazatest.sami-host.me/apk/maza-wallet-v1.1.0.apk.sha256

Auth: HTTP Basic, user `maza`. The password is a DEDICATED download credential,
delivered to Sami by Telegram DM only; it is NOT the walletbench API token and
the two rotate independently. The credential never appears in a URL (no query
params — URL tokens leak into logs and parser surfaces; same rule as the API).

## Serving layout (samihost)

- Files: `/opt/maza-wallet-bench/apk/` — the APK, a `sha256sum -c`-compatible
  `.sha256` sidecar, and `INDEX.txt` (version, sha256, size, build date).
  World-readable (0644); the HTTP auth layer is the gate, not filesystem perms.
  All three files sit behind the SAME auth deliberately: the channel discloses
  nothing to anonymous clients — no version or checksum metadata without the
  credential, and `file_server` runs without browse so there is no directory
  listing either.
- Route (inside the guard-protected `mazatest.sami-host.me` vhost; must live in
  ALL THREE of `/etc/caddy/Caddyfile`,
  `/var/lib/caddy-guard/protected-blocks.txt`, and
  `/var/lib/caddy-guard/protected-blocks.txt.pre-guard` so panel regens
  preserve it — same rule as the `/indexer/*` route):

```
	handle_path /apk/* {
		basic_auth {
			maza <BCRYPT-HASH>
		}
		root * /opt/maza-wallet-bench/apk
		file_server
	}
```

- Only the bcrypt hash lives on samihost. The plaintext lives on the operator
  host (DNS2) at `/root/.maza-wallet/apk-download.cred` (0600, `user=` /
  `password=` lines) — read in-process by scripts, never printed, never logged,
  never put in argv where a shared transcript could capture it.

## Install / update procedure

Installer (in-repo, runs ON samihost as root): `deploy/apk-route-install.py` —
reads the password on STDIN, hashes it with `caddy hash-password`, and CLASSIFIES
each config source: route absent → anchor-insert (asserts exactly one anchor);
route present → in-place hash ROTATION (asserts exactly one route block and one
hash line per file; refuses a mixed install/rotate state across the three
sources). Timestamped backups of all three files, `caddy validate`, reload, and
RESTORE-ALL-FILES-from-backup (exit 2) if validate or reload fails; exit 3
before any mutation on a bad anchor/missing file. Rotate the download password
by simply re-running it with the NEW password on stdin — there is no
remove-the-line-then-rerun dance (an edited-out hash line would leave the route
block present, which a skip-style installer would then never re-fill).

Version updates: bump `android/release.properties` (versionCode + versionName
together), `bash android/build-apk.sh --release`, run the beta-gate battery
(`bash /root/.hermes/skills/maza-mobile-wallet/scripts/beta-gate.sh <repo-root>`
— zero FAIL required), then scp the APK + regenerated `.sha256` + updated
`INDEX.txt` into `/opt/maza-wallet-bench/apk/` (0644). Old versions may remain
alongside; INDEX.txt names the current one.

## Verification (captured from DNS2 against the public path, 2026-11-25)

Transcript: `android/evidence/m6-distribution/VERIFY-TRANSCRIPT.txt`
(no-auth 401, wrong-pass 401, correct-pass 200 with byte-exact sha256 match
against the staged file, `/indexer/health` 200, front-door root 200,
`/api/state` 401 — the API surface is untouched by the static route).

Credential rotation: re-run `deploy/apk-route-install.py` on samihost with the
NEW password on stdin — it classifies the route as present and replaces the
whole hash line in place in all three sources (validate + reload + backup +
restore-on-failure, same as install). NEVER remove the old hash line first:
an edited-out hash leaves the route block present with an invalid `basic_auth`
body, which is precisely the state this installer refuses to touch (exit 3).
The plaintext password exists transiently on samihost only inside the
installer's root-owned process memory while it is being hashed; the persistent
copy lives only in the operator host's 0600 credential file.
