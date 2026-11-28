#!/usr/bin/env python3
"""Ship a local file to SAMI-PC via ssh (base64 -> WriteAllBytes), then optionally run it.

usage: ship.py <local_file> <remote_path>            -> ship only
       ship.py <local_file> <remote_path> --run      -> ship, then `powershell -NoProfile -File <remote>`
       ship.py <local_file> <remote_path> --cmd      -> ship, then `cmd /c <remote>` (file must be CRLF)
stdout of the remote run goes to stdout; exit code = remote exit code (or 9 on ship failure).
"""
import base64
import subprocess
import sys
import time

HOST = "sami-pc"


def ssh(args, timeout=240):
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=25", HOST] + args,
                          capture_output=True, timeout=timeout)


def main():
    local, remote = sys.argv[1], sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else ""
    with open(local, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    # Chunk the base64 into pieces so no single command line nears Windows' 8191-char limit;
    # first chunk creates the file, later chunks append.
    chunk = 3000
    r = remote.replace("/", "\\")
    t0 = time.time()
    for i in range(0, len(b64), chunk):
        part = b64[i:i + chunk]
        if i == 0:
            ps = "[IO.File]::WriteAllBytes('%s',[Convert]::FromBase64String('%s'))" % (r, part)
        else:
            ps = ("$f=[IO.File]::Open('%s',[IO.FileMode]::Append);$x=[Convert]::FromBase64String('%s');"
                  "$f.Write($x,0,$x.Length);$f.Close()" % (r, part))
        if len(ps) > 7800:
            print("SHIP-FAIL chunk too long (%d chars) - shrink the chunk" % len(ps))
            return 9
        out = ssh(["powershell", "-NoProfile", "-Command", ps], timeout=60)
        if out.returncode != 0:
            print("SHIP-FAIL rc=%d stderr=%s" % (out.returncode, out.stderr.decode(errors="replace")[:300]))
            return 9
    # size readback
    out = ssh(["powershell", "-NoProfile", "-Command", "(Get-Item '%s').Length" % r], timeout=60)
    size = out.stdout.decode(errors="replace").strip()
    import os
    want = os.path.getsize(local)
    print("SHIPPED %s -> %s bytes=%s (want %d) %s in %.1fs" % (
        local, remote, size, want, "OK" if size == str(want) else "SIZE-MISMATCH", time.time() - t0))
    if size != str(want):
        return 9
    if mode == "--run":
        res = ssh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", r], timeout=400)
    elif mode == "--cmd":
        res = ssh(["cmd", "/c", r], timeout=400)
    else:
        return 0
    sys.stdout.write(res.stdout.decode(errors="replace").replace("\r\000", "").replace("\r", ""))
    if res.stderr.strip():
        sys.stdout.write("\n[stderr] " + res.stderr.decode(errors="replace")[:400])
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
