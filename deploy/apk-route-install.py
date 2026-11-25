#!/usr/bin/env python3
"""M6 APK distribution channel route installer (runs ON samihost, as root).

Installs OR rotates the auth-gated /apk/* static route inside the
mazatest.sami-host.me vhost in ALL THREE caddy config sources (live Caddyfile +
guard protected-blocks.txt + .pre-guard) so panel regens preserve it.

Modes (automatic, must be uniform across the three sources):
  - ABSENT route  -> insert the full block after the indexer anchor (INSTALL).
  - PRESENT route -> replace the basic_auth hash line in place (ROTATE);
                    aborts unless exactly one route block and one hash line
                    exist per file. To rotate the password: run this script
                    again with the NEW password on stdin. Do NOT remove the
                    hash line first — an edited-out hash is an invalid config
                    this script refuses to touch (exit 3).

The password is hashed via `caddy hash-password` reading STDIN. It is never
passed as a process argument: if stdin hashing fails the script exits 3 rather
than falling back to --plaintext (which would expose the password in argv).
The plaintext therefore exists only long enough to be hashed, on the host
where the script runs, in the root-owned process memory.

Exit codes: 0 route installed/rotated + validated + reloaded; 2 config
failure, all three files restored from backup; 3 aborted before any mutation.
"""
import subprocess, sys, os, time, shutil

LIVE = "/etc/caddy/Caddyfile"
GUARD = "/var/lib/caddy-guard/protected-blocks.txt"
PREGUARD = "/var/lib/caddy-guard/protected-blocks.txt.pre-guard"
FILES = [LIVE, GUARD, PREGUARD]

ANCHOR = (
    "\t# MAZA lean chain indexer (read-only; repo docs/maza-indexer/README.md)\n"
    "\thandle_path /indexer/* {\n"
    "\t\treverse_proxy 127.0.0.1:18711\n"
    "\t}\n"
)
ROUTE_HEADER = (
    "\t# MAZA wallet APK distribution (auth-gated static; repo deploy/APK-DISTRIBUTION.md)\n"
    "\thandle_path /apk/* {\n"
    "\t\tbasic_auth {\n"
)


def route_block(hash_str):
    return (
        ROUTE_HEADER
        + "\t\t\tmaza " + hash_str + "\n"
        + "\t\t}\n"
        + "\t\troot * /opt/maza-wallet-bench/apk\n"
        + "\t\tfile_server\n"
        + "\t}\n"
    )


def run(cmd, **kw):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)


def hash_password(pw):
    """Hash via stdin ONLY — never argv. Returns the bcrypt string or None."""
    r = run("printf '%s' \"$PW\" | caddy hash-password",
            env={**os.environ, "PW": pw})
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return None


def classify(texts):
    """Return ('install'|'rotate', {file: text}) or raise ValueError."""
    kinds = {}
    for f, t in texts.items():
        n_route = t.count("\thandle_path /apk/* {\n")
        if n_route not in (0, 1):
            raise ValueError(f"{f}: {n_route} /apk route blocks (expected 0 or 1)")
        if n_route == 0:
            if t.count(ANCHOR) != 1:
                raise ValueError(f"{f}: anchor count != 1 for install")
            kinds[f] = "install"
        else:
            # count hash lines INSIDE the /apk route block only — a global
            # count could match an unrelated "maza $2..." line elsewhere
            i = t.index("\thandle_path /apk/* {\n")
            j = t.index("\t\t}\n", i)
            n_hash = t[i:j].count("\t\t\tmaza ")
            if n_hash != 1:
                raise ValueError(
                    f"{f}: {n_hash} hash lines inside the /apk route block (expected exactly 1 for rotate)")
            kinds[f] = "rotate"
    if len(set(kinds.values())) != 1:
        raise ValueError(f"inconsistent config sources: {kinds}")
    mode = next(iter(kinds.values()))
    return mode, kinds


def apply_edits(kinds, hash_str):
    """Return {file: new_text} without writing anything."""
    out = {}
    for f, kind in kinds.items():
        t = texts_global[f]
        if kind == "install":
            out[f] = t.replace(ANCHOR, ANCHOR + route_block(hash_str), 1)
        else:
            i = t.index("\thandle_path /apk/* {\n")
            j = t.index("\t\t}\n", i)  # closes basic_auth
            seg = t[i:j]
            lines = seg.split("\n")
            hash_idx = [k for k, ln in enumerate(lines)
                        if ln.startswith("\t\t\tmaza ")]
            if len(hash_idx) != 1:
                # raise the documented failure class, not a bare assert —
                # main() catches ValueError and exits 3
                raise ValueError(
                    f"{f}: {len(hash_idx)} hash lines in the /apk route block (expected exactly 1)")
            # replace the WHOLE line — a prefix replace would leave the old
            # hash's tail as residue and corrupt the bcrypt string
            lines[hash_idx[0]] = "\t\t\tmaza " + hash_str
            out[f] = t[:i] + "\n".join(lines) + t[j:]
    return out


texts_global = {}


def main(stdin):
    pw = stdin.readline().rstrip("\r\n")  # strip ONLY the line terminator —
    # a password with leading/trailing spaces is valid and must survive intact
    if not pw:
        print("FATAL: no password on stdin", file=sys.stderr)
        return 3

    hash_str = hash_password(pw)
    if not hash_str:
        print("FATAL: caddy hash-password (stdin) failed — NOT falling back "
              "to --plaintext (password must never appear in argv)",
              file=sys.stderr)
        return 3

    for f in FILES:
        if not os.path.exists(f):
            print("FATAL: missing " + f, file=sys.stderr)
            return 3
    texts_global.clear()
    for f in FILES:
        with open(f, encoding="utf-8") as fh:
            texts_global[f] = fh.read()

    try:
        mode, kinds = classify(texts_global)
        new_texts = apply_edits(kinds, hash_str)
    except ValueError as exc:
        print("FATAL: " + str(exc), file=sys.stderr)
        return 3

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backups = []
    for f in FILES:
        bak = f + ".bak-m6apk-" + stamp
        shutil.copy2(f, bak)
        backups.append((f, bak))
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(new_texts[f])
        print(("INSERTED: " if mode == "install" else "ROTATED-HASH: ")
              + f + " (backup " + bak + ")")

    def restore():
        for f, bak in backups:
            shutil.copy2(bak, f)
            print("RESTORED: " + f)

    vr = run("caddy validate --config /etc/caddy/Caddyfile")
    tail = (vr.stdout or vr.stderr).strip().splitlines()
    print("VALIDATE: " + (tail[-1] if tail else "(no output)"))
    if vr.returncode != 0:
        print("FATAL: caddy validate failed — restoring all files", file=sys.stderr)
        print(vr.stderr[-500:], file=sys.stderr)
        restore()
        return 2

    r = run("systemctl reload caddy")
    if r.returncode != 0:
        print("FATAL: caddy reload failed — restoring all files", file=sys.stderr)
        print(r.stderr[-300:], file=sys.stderr)
        restore()
        run("systemctl reload caddy")
        return 2

    print("RELOADED: caddy active")
    print("ROUTE-" + mode.upper() + " exit=0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin))
