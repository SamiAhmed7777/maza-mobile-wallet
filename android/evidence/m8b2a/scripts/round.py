#!/usr/bin/env python3
"""Run one adb round on SAMI-PC: cmds file -> base64 argv -> adbrun.ps1 over ONE ssh call.

usage: round.py <cmds.txt>            (output saved to <cmds>.out; XML lines hidden from stdout)
The command list is carried in the argv (-B64), not stdin: Windows OpenSSH stdin to PowerShell
truncated a piped command list mid-line (lost every line after byte 265 in the first round).
"""
import base64
import subprocess
import sys
import time

HOST = "sami-pc"
RUNNER = r"C:\Users\hello\maza-bench-lane\adbrun.ps1"


def main():
    src = sys.argv[1]
    text = open(src, encoding="utf-8").read()
    b64 = base64.b64encode(text.encode()).decode()
    if len(b64) > 7600:
        print("ROUND-TOO-LONG b64=%d (cmd.exe 8191-char line limit) - split the round" % len(b64))
        return 9
    t0 = time.time()
    res = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=25", HOST,
         "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", RUNNER, "-B64", b64],
        capture_output=True, timeout=420)
    out = res.stdout.decode("utf-8", errors="replace").replace("\r\000", "").replace("\r", "")
    dest = src[:-4] + ".out" if src.endswith(".txt") else src + ".out"
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(out)
        if res.stderr.strip():
            fh.write("\n[stderr]\n" + res.stderr.decode("utf-8", errors="replace"))
    xml = 0
    for line in out.split("\n"):
        if line.startswith("<?xml"):
            xml += 1
            continue
        print(line[:240])
    if res.stderr.strip():
        print("[stderr] " + res.stderr.decode("utf-8", errors="replace")[:400])
    print("-- round rc=%d %.1fs xml-lines=%d -> %s" % (res.returncode, time.time() - t0, xml, dest))
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
