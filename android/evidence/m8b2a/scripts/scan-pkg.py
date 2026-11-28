#!/usr/bin/env python3
"""Scan the m8b2a evidence package before it is copied anywhere.

Checks (all read-only, prints a summary, exits non-zero on a finding):
  1. secret-shaped strings: Bearer headers, WB_TOKEN=<value>, rpcuser/rpcpassword, authorization:
  2. password-class nodes in every UI dump inside transcripts: only bullets, empty, or a
     known hint string are accepted
  3. host machine details: monitor/GPU/OS-build/browser-process lines (Sami's machine privacy)
"""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
HINTS = {'bench token', 'PIN or passphrase'}
# value-bearing shapes only: a key NAME read in code (conf.get("rpcpassword")) is not a secret
SECRET_RE = re.compile(
    r'Bearer |WB_TOKEN=[^ "]|rpc(user|password)\s*=\s*[^\s"\')]{3,}|authorization:', re.I)
HOST_RE = re.compile(r'ASUS|GeForce|Radeon|Windows 1[01]|firefox|logon time', re.I)

bad = 0
files = sorted(f for f in glob.glob(ROOT + '/**/*', recursive=True) if os.path.isfile(f))
hits_secret, hits_host = [], []
for f in files:
    if f.endswith('scan-pkg.py'):
        continue  # the scanner carries the patterns it searches for
    try:
        raw = open(f, encoding='utf-8', errors='replace').read()
    except OSError as e:
        print('unreadable', f, e)
        bad += 1
        continue
    for m in SECRET_RE.finditer(raw):
        hits_secret.append((f, raw[max(0, m.start() - 20):m.start() + 30].replace('\n', ' ')))
    for m in HOST_RE.finditer(raw):
        hits_host.append((f, raw[max(0, m.start() - 20):m.start() + 30].replace('\n', ' ')))

pw = {}
dumps = 0
for f in files:
    if not f.endswith('.out'):
        continue
    raw = open(f, encoding='utf-8', errors='replace').read()
    for x in re.findall(r'<\?xml.*?</hierarchy>', raw, flags=re.S):
        dumps += 1
        try:
            root = ET.fromstring(x)
        except ET.ParseError as e:
            print('XML parse fail', f, e)
            bad += 1
            continue
        for n in root.iter('node'):
            if n.get('password') == 'true':
                t = n.get('text') or ''
                if not t:
                    k = 'empty'
                elif set(t) <= set('\u2022\u25cf\u2219*'):
                    k = 'bullets'
                elif t in HINTS:
                    k = 'hint'
                else:
                    k = 'UNEXPECTED'
                    bad += 1
                    print('UNEXPECTED password text in', f, repr(t))
                pw[k] = pw.get(k, 0) + 1

for f, ctx in hits_secret:
    bad += 1
    print('SECRET-SHAPED', f, '::', ctx)
for f, ctx in hits_host:
    print('HOST-DETAIL', f, '::', ctx)

print('files scanned:', len(files), '| ui dumps parsed:', dumps, '| password nodes:', pw)
print('secret-shaped hits:', len(hits_secret), '| host-detail hits:', len(hits_host), '| findings:', bad)
sys.exit(1 if bad or hits_host else 0)
