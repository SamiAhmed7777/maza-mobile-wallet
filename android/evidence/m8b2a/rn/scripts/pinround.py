#!/usr/bin/env python3
"""Run one round.py command file that contains the [PIN] placeholder.

The bench PIN never appears in a transcript or in any file outside the
committed lane script it already lives in:
  - the digits are read at run time from --pin-src (a committed s2b-pin
    lane script; the first `shell input text NNNN` literal in it);
  - they are substituted into a scratch copy of the command file, which
    round.py runs; round.py writes its transcript next to that copy;
  - both files (the rendered copy AND the transcript) are removed, in a
    finally block, win or lose;
  - the captured stdout is scrubbed (every occurrence -> [PIN]) BEFORE it
    is written to the output file or printed.
Nothing about the digits is ever printed, not even their length. The
script ends by asserting that neither scratch file still exists.

Usage: pinround.py <cmds-with-[PIN]> <out-file> [--pin-src PATH]
Exit status: the round's own status (0 = every command ran).
"""
import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def find_repo(start):
    """Nearest ancestor that is the wallet repo (holds walletbench/config.py)."""
    d = start
    while True:
        if os.path.exists(os.path.join(d, "walletbench", "config.py")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


REPO = find_repo(HERE)
DEFAULT_PIN_SRC = (os.path.join(REPO, "android", "evidence", "s2b-pin", "unlock-for-p4b.ps1")
                   if REPO else None)
PIN_RE = re.compile(r"shell input text (\d{4})\b")


def load_pin(path):
    if not path:
        sys.exit("NO-PIN-SOURCE (run from inside the wallet repo, or pass --pin-src)")
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    m = PIN_RE.search(text)
    if not m:
        sys.exit("PIN-SOURCE-NOT-FOUND (no `shell input text NNNN` literal in --pin-src)")
    return m.group(1)


def resolve_round(pin_src):
    """round.py: beside this script, or the evidence package's copy when
    --pin-src points inside the wallet repo."""
    cand = os.path.join(HERE, "round.py")
    if os.path.exists(cand):
        return cand
    if pin_src:
        ev = os.path.abspath(os.path.join(os.path.dirname(pin_src), ".."))
        cand = os.path.join(ev, "m8b2a", "scripts", "round.py")
        if os.path.exists(cand):
            return cand
    sys.exit("ROUND-NOT-FOUND (round.py must sit next to pinround.py, "
             "or --pin-src must point inside the wallet repo)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmds")
    ap.add_argument("out")
    ap.add_argument("--pin-src", default=DEFAULT_PIN_SRC)
    ap.add_argument("--max-line", type=int, default=170)
    args = ap.parse_args()

    pin = load_pin(args.pin_src)
    with open(args.cmds, encoding="utf-8") as fh:
        template = fh.read()
    if "[PIN]" not in template:
        sys.exit("NO-PLACEHOLDER (the command file has no [PIN])")
    if pin in template.replace("[PIN]", ""):
        sys.exit("REFUSED: the digits already appear in the template")

    tmp = os.path.join(HERE, ".pin-rendered.tmp")
    round_py = resolve_round(args.pin_src)
    stdout_text = ""
    rc = 1
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(template.replace("[PIN]", pin))
        proc = subprocess.run([sys.executable, round_py, tmp],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, errors="replace")
        rc = proc.returncode
        stdout_text = proc.stdout
    finally:
        # The transcript round.py wrote holds the typed digits: keep its
        # CONTENT (scrubbed), never the file.
        tmp_out = tmp + ".out"
        try:
            with open(tmp_out, encoding="utf-8", errors="replace") as fh:
                transcript_text = fh.read()
        except OSError:
            transcript_text = ""
        for path in (tmp, tmp_out):
            try:
                os.remove(path)
            except OSError:
                pass

    if os.path.exists(tmp) or os.path.exists(tmp + ".out"):
        sys.exit("SCRATCH-FILE-SURVIVED (nothing printed)")

    scrubbed = stdout_text.replace(pin, "[PIN]")
    scrubbed += "\n<!-- transcript (digits scrubbed before this file was written) -->\n"
    scrubbed += transcript_text.replace(pin, "[PIN]")
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(scrubbed)
    for line in scrubbed.splitlines():
        if line.startswith("<?xml"):
            continue
        print(line[: args.max_line])
    print(f"-- pinround rc={rc} scrubbed-out={args.out}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
