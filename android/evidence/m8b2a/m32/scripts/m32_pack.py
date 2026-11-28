#!/usr/bin/env python3
"""Build <wallet repo>/android/evidence/m8b2a/m32/ from the lane scratch dir.

Window of 2026-11-28 02:02-02:53 PST: the M14-ii denial state and the M32
device proof.

Public-repo safe by construction:
  - explicit copy map: device-side and bench-side captures only. Two
    host-side captures (the launch/stop record and the boot error count) go
    in as TRIMMED excerpts of allow-listed lines; their memory figures and
    process lists never leave the private archive. No PNG leaves scratch.
  - RUNLOG.md and DERIVED.txt are generated from values this script parses
    out of the captures. Nothing is typed by hand. A value that cannot be
    parsed, or that fails a consistency check, aborts before anything is
    written.
  - aborts BEFORE writing if a source is missing, if the PIN or the bench
    token appears anywhere in the package, or if a script copy differs from
    its source.
  - SHA256SUMS; then the package scanner (../scripts/scan-pkg.py) must exit 0
Usage: m32_pack.py facts   (parse and print every fact; write nothing)
       m32_pack.py build   (build the package)
facts() is imported by the landing-text and judge-brief builders.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

S = '/root/.hermes/cache/scratch/m8b2a-rn'
W = S + '/m32/win2'
X = S + '/m32'                       # the rebuild (APK identity) scratch dir
REPO = '/root/maza-mobile-wallet'
E = REPO + '/android/evidence/m8b2a'
DST = E + '/m32'
OLD = E + '/rn'                      # the committed package of 2026-11-27
SCANNER = E + '/scripts/scan-pkg.py'
CET_OFFSET = datetime.timedelta(hours=9)   # the bench host prints CET; PST is CET - 9 h


class Fail(Exception):
    pass


def rd(p):
    return open(p, encoding='utf-8', errors='replace').read().replace('\r\n', '\n').replace('\r', '\n')


def w(name):
    return rd(os.path.join(W, name))


def grab(text, pat, what, flags=re.M):
    ms = list(re.finditer(pat, text, flags))
    if len(ms) != 1:
        raise Fail('%s: expected exactly 1 match, found %d' % (what, len(ms)))
    return ms[0].group(1)


def count_cmd(text, needle):
    """The number a `grep -c -e <needle>` command printed inside one capture."""
    return grab(text, r'grep -c -e ' + re.escape(needle) + r'\n(\d+)\n', 'count line for ' + needle)


def rec_ids(text):
    return sorted(set(re.findall(r'NotificationRecord\(0x[0-9a-f]+: pkg=com\.mazawallet user=UserHandle\{0\} id=(\d+)', text)))


def amounts(text, dec):
    """Amounts shown as `text="<number> MAZA"`. The bench balance prints with 6 to 8 decimals; the watch set with 4."""
    pat = r'text="(\d+\.\d{%s}) MAZA"' % ('6,8' if dec == 8 else str(dec))
    return sorted(set(re.findall(pat, text)))


def pid_of(text):
    """The wallet's pid as a capture shows it: a `ps` row, or the `pidof` line (empty when the app is backgrounded)."""
    m = re.search(r'u0_a68 +(\d+) ', text) or re.search(r'> shell pidof com\.mazawallet\n(\d+)\n', text)
    return m.group(1) if m else 'GONE'


def clock(s):
    return datetime.datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')


def hms(s):
    """A bare HH:MM:SS (same day) as a datetime, for differences."""
    return datetime.datetime.strptime(s, '%H:%M:%S')


def hhmm(s):
    return s[11:16]


def posts(text):
    out = []
    for m in re.finditer(r'(\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) +\d+ +\d+ I HCALL +: hcallOnAppNotificationReceivedRpc\((\{.*)$', text, re.M):
        line = m.group(2)
        try:
            j = json.loads(line)
            out.append((m.group(1), j.get('packageName'), j.get('contentTitle'), j.get('contentText')))
        except ValueError:
            g = re.search(r'"packageName":"([^"]*)".*?"contentTitle":"([^"]*)","contentText":"([^"]*)"', line)
            out.append((m.group(1), g.group(1), g.group(2), g.group(3)))
    return out


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def src_file(path):
    """a source file as commit b819df1 holds it: its lines and the sha256 of the blob, read with git show"""
    r = subprocess.run(['git', '-C', REPO, 'show', 'b819df1:' + path], capture_output=True, text=True)
    if r.returncode != 0:
        raise Fail('git show b819df1:%s failed' % path)
    return r.stdout.split('\n'), hashlib.sha256(r.stdout.encode('utf-8')).hexdigest()


def facts():
    F = {}
    # ---------- window (host-side captures; only trimmed lines go to the package) ----------
    st = w('w26_stop.out')
    F['launched'] = grab(st, r'^\s*(2026-11-28 \d\d:\d\d:\d\d\.\d{3})-0700 \d+ \d+ PLR +\[Initializing\] I: main: .*Player state : launched with args', 'launch line')
    F['ready'] = grab(st, r'^\s*(2026-11-28 \d\d:\d\d:\d\d\.\d{3})-0700 \d+ \d+ PLR +Pie64 \[StartingAndroid\] I: Player state: ready', 'ready line')
    F['stopped'] = grab(st, r'^stopped-at: (2026-11-28 \d\d:\d\d:\d\d)', 'stop line')
    F['close_path'] = grab(st, r'^(falling back to Stop-Process \(the lane stop; writes no stop line of its own\))', 'stop path line')
    F['no_player'] = grab(w('w26_tasklist.out'), r'^(INFO: No tasks are running which match the specified criteria\.)', 'tasklist line')
    ec = w('w_errcount.txt')
    F['err_boot'] = grab(ec, r'^boot launched at: (2026-11-28 \d\d:\d\d:\d\d\.\d{3})', 'boot line of the error count')
    F['err_zero'] = grab(ec, r'^(guest error lines this boot: 0)', 'zero line of the error count')
    F['err_when'] = grab(ec, r'^now (\d\d:\d\d:\d\d)$', 'clock line of the error count')
    if F['err_boot'] != F['launched']:
        raise Fail('launch time differs between the two host captures')
    F['boot_secs'] = '%d seconds' % int((clock(F['ready']) - clock(F['launched'])).total_seconds())
    secs = int((clock(F['stopped']) - clock(F['launched'])).total_seconds())
    F['window'] = '%d minutes %d seconds' % (secs // 60, secs % 60)

    # ---------- connect and unlock on the old build ----------
    tk = w('w_token.out')
    F['tok_len'] = grab(tk, r'^TOKEN len=(\d+) class=(\w+)$', 'token line').split(' ')[0]
    F['tok_class'] = re.search(r'^TOKEN len=\d+ class=(\w+)$', tk, re.M).group(1)
    F['tok_typed'] = grab(tk, r'^TYPED-LEN (\d+)$', 'typed length line')
    F['tok_connect'] = grab(tk, r'^(CONNECT-TAPPED)$', 'connect line')
    F['w1_ops'] = grab(w('w1.out'), r'^(POST_NOTIFICATION: \w+)$', 'app-ops line of w1')
    F['w2_ops'] = re.findall(r'^(POST_NOTIFICATION: \w+)$', w('w2.out'), re.M)[-1]
    w3 = w('w3.out')
    F['w3_bal'] = amounts(w3, 8)
    F['w3_lock'] = 'Wallet locked' in w3
    w4 = w('w4.out')
    F['addr6'] = open(W + '/to_addr.txt').read().strip()
    if not re.fullmatch(r'M[A-Za-z1-9]{25,40}', F['addr6']) or ('text="%s"' % F['addr6']) not in w4:
        raise Fail('index-6 address not found in the w4 dump')
    F['addr6_index'] = re.search(r'text="index (\d+)"[^>]*/>\s*<node [^>]*text="%s"' % F['addr6'], w4).group(1)
    F['w4_unlocked'] = 'Wallet locked' not in w4

    # ---------- the denial switch ----------
    w5 = w('w5.out')
    sw = [n for n in re.findall(r'<node [^>]*?/>', w5)
          if 'class="android.widget.Switch"' in n and 'text="ON"' in n and 'checked="true"' in n and 'checkable="true"' in n]
    if len(sw) != 1:
        raise Fail('the ON switch widget is not in the w5 dump: %d candidates' % len(sw))
    x1, y1, x2, y2 = [int(v) for v in re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', sw[0]).groups()]
    F['w5_sw'] = 'ON'
    F['tap_xy'] = '(%d,%d)' % ((x1 + x2) // 2, (y1 + y2) // 2)
    w7 = w('w7.out')
    F['w7_none'] = 'importance=NONE' in w7
    F['w7_banner'] = grab(w7, r'(At your request, Android is blocking this app[^"<]*)', 'banner line')
    polls = re.findall(r'(\d\d:\d\d:\d\d\.\d{3}) +\d+ +\d+ I MAZA +: \S+ \S+ #\d+ GET /api/state -> 200', w7)
    F['w7_poll_first'], F['w7_poll_last'] = polls[0], polls[-1]
    F['w7_poll_n'] = str(len(polls))
    F['pid_old'] = pid_of(w7)
    w8 = w('w8.out')
    F['w8_front'] = bool(re.search(r'mResumedActivity: ActivityRecord\{\w+ u0 com\.mazawallet/\.MainActivity', w8))
    F['w8_unlocked'] = 'Wallet locked' not in w8
    F['w8_none'] = 'importance=NONE' in w8
    F['w6_ocr'] = [l.strip() for l in w('w6_off_red.ocr.txt').split('\n') if l.strip()]

    # ---------- denial watch: 22 rounds ----------
    names = ['w9_%02d' % k for k in range(0, 22)]
    rows, counts, recs, nones, pids, bals = [], set(), set(), set(), set(), {}
    for n in names:
        t = w(n + '.out')
        c, r, ne, pid = count_cmd(t, 'hcallOnAppNotificationReceivedRpc'), tuple(rec_ids(t)), 'importance=NONE' in t, re.search(r'u0_a68 +(\d+) ', t)
        b = amounts(t, 4)
        rows.append((n, c, r, ne, pid.group(1) if pid else 'GONE', b))
        counts.add(c); recs.add(r); nones.add(ne); pids.add(pid.group(1) if pid else 'GONE'); bals[n] = b
    tm = [l.split() for l in w('w9_times.txt').strip().split('\n') if re.match(r'w9_\d\d start=', l)]
    F['w9_first_start'] = [p for p in tm if p[0] == 'w9_01'][0][1].split('=')[1]
    F['w9_last_end'] = tm[-1][3].split('=')[1]
    F['w9_counts'] = sorted(counts, key=int)
    F['w9_recs'] = sorted(recs)
    F['w9_nones'] = sorted(nones)
    F['w9_pids'] = sorted(pids)
    first_new = next((n for n in names if bals[n] == ['2.3999']), None)
    F['w9_change_round'] = first_new
    F['w9_change_times'] = [p for p in tm if p[0] == first_new][0][1:]
    F['w9_before_bals'] = sorted({b for n in names for b in bals[n] if b != ['2.3999']}, key=str) if False else sorted({tuple(bals[n]) for n in names if n < first_new})
    F['w9_after_bals'] = sorted({tuple(bals[n]) for n in names if n >= first_new})
    F['w9_rows'] = rows
    F['w9_rounds'] = str(len(names))
    s4 = w('send4.out')
    m = re.search(r'^\[(2026-11-28 \d\d:\d\d:\d\d) CET\] POST /api/send to=(\S+) amount=([\d.]+) -> HTTP (\d+) \{"txid": "([0-9a-f]+)', s4, re.M)
    if not m:
        raise Fail('send 4 line not parsed')
    F['send4_cet'], F['send4_to'], F['send4_amt'], F['send4_http'], F['send4_tx'] = m.groups()
    F['send4_pst'] = (datetime.datetime.strptime(F['send4_cet'], '%Y-%m-%d %H:%M:%S') - CET_OFFSET).strftime('%H:%M:%S')
    if F['send4_to'] != F['addr6']:
        raise Fail('send 4 did not go to the index-6 address')
    m = re.search(r'before: bench balance=([\d.]+) \| watch set: balance=([\d.]+)', s4)
    F['send4_pre_bal'], F['send4_pre_watch'] = m.groups()
    F['send4_post_watch'] = grab(s4, r'after: watch set: balance=([\d.]+)', 'send 4 after line')
    s4s = w('send4_state.out')
    m = re.search(r'^\[(2026-11-28 \d\d:\d\d:\d\d) CET\] GET /api/state -> 200 balance=([\d.]+)', s4s, re.M)
    F['state_cet'], F['state_bal'] = m.groups()
    m = re.search(r'watch set: balance=([\d.]+) utxos=(\d+) confirmations=\[([0-9, ]+)\]', s4s)
    F['state_watch'], F['state_utxos'], F['state_conf'] = m.groups()
    F['state_pst'] = (datetime.datetime.strptime(F['state_cet'], '%Y-%m-%d %H:%M:%S') - CET_OFFSET).strftime('%H:%M:%S')
    F['w10_count'] = count_cmd(w('w10.out'), 'hcallOnAppNotificationReceivedRpc')
    sw = w('w11_switch.txt')
    F['w11_before'] = grab(sw, r"^before the tap +Switch +'(OFF)' checked=(false)", 'switch before line').replace("'", '')
    F['w11_before_x'] = re.search(r"^before the tap +Switch +'OFF' checked=false$", sw, re.M).group(0).strip()
    F['w11_after_x'] = re.search(r"^after the tap +Switch +'ON' checked=true$", sw, re.M).group(0).strip()
    w11 = w('w11.out')
    F['w11_none'] = 'importance=NONE' in w11
    dumps = [l for l in w11.split('\n') if l.startswith('<?xml')]
    F['w11_dumps'] = len(dumps)
    F['w11_after_on'] = bool(re.search(r'<node [^>]*text="ON"[^>]*class="android.widget.Switch"[^>]*checked="true"', dumps[-1]))
    F['w11_after_banner'] = 'At your request, Android is blocking' in dumps[-1]
    F['w11_before_off'] = bool(re.search(r'<node [^>]*text="OFF"[^>]*class="android.widget.Switch"[^>]*checked="false"', dumps[0]))

    # ---------- the old build's identity, the failed pushes ----------
    w12 = w('w12.out')
    F['old_code'] = grab(w12, r'codePath=(/data/app/com\.mazawallet-\S+)', 'old code path')
    F['old_update'] = grab(w12, r'lastUpdateTime=(2026-11-27 \d\d:\d\d:\d\d)', 'old update time')
    F['old_first'] = grab(w12, r'firstInstallTime=(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)', 'first install time')
    F['w12_recs'] = [l.strip()[:60] for l in w12.split('\n') if 'NotificationRecord' in l]
    w13 = w('w13.out')
    F['old_md5'] = grab(w13, r'^([0-9a-f]{32})  /data/app/com\.mazawallet-\S+/base\.apk', 'old base.apk md5')
    F['w13_err'] = grab(w13, r"(adb: error: cannot stat ':[^']*')", 'push error of w13')
    F['w14_err'] = grab(w('w14.out'), r"(adb: error: cannot stat ':[^']*')", 'push error of w14')
    adr = rd(REPO + '/android/evidence/m8b2a/scripts/adbrun.ps1')
    F['adb_push_line'] = re.search(r"^.*StartsWith\('push '\).*$", adr, re.M).group(0).strip()
    F['adb_pull_line'] = re.search(r"^.*StartsWith\('pull '\).*$", adr, re.M).group(0).strip()
    F['adb_push_no'] = str([i + 1 for i, l in enumerate(adr.split('\n')) if "StartsWith('push ')" in l][0])

    # ---------- APK identity ----------
    apk = REPO + '/android/maza-wallet-bench.apk'
    data = open(apk, 'rb').read()
    F['apk_sha'] = hashlib.sha256(data).hexdigest()
    F['apk_md5'] = hashlib.md5(data).hexdigest()
    F['apk_size'] = str(len(data))
    F['pc_sha'] = w('w13_pc_sha.txt').strip()
    F['pc_equal'] = F['pc_sha'].lower() == F['apk_sha']
    bo = rd(X + '/build.out')
    F['build_checks'] = grab(bo, r'^(ALL \d+ CHECKS PASSED)$', 'crypto self-test line')
    F['build_bytes'] = grab(bo, r'^SIGNED OK: \S+ \((\d+) bytes\)', 'signed line')
    a, b = rd(X + '/cmpA.sha'), rd(X + '/cmpB.sha')
    F['cmp_equal'] = a == b
    F['cmp_lines'] = str(len(a.strip().split('\n')))
    ok = True
    for line in a.strip().split('\n'):
        h, rel = line.split(None, 1)
        rel = rel.strip()
        for d in ('cmpA', 'cmpB'):
            if sha_file(os.path.join(X, d, rel[2:])) != h:
                ok = False
    F['cmp_recheck'] = ok
    F['dex_line'] = [l for l in a.split('\n') if l.endswith('classes.dex')][0]
    F['rebuild_sha'] = sha_file(X + '/m32-b819df1.apk')
    F['rebuild_equal_whole'] = F['rebuild_sha'] == F['apk_sha']
    F['loop_full'] = subprocess.run(['git', '-C', REPO, 'rev-parse', 'b819df1'], capture_output=True, text=True).stdout.strip()
    msg = subprocess.run(['git', '-C', REPO, 'log', '-1', '--format=%B', 'b819df1'], capture_output=True, text=True).stdout
    F['loop_grade'], F['loop_urn'] = re.match(r'\[grade=([A-F]) urn=(urn:ump:[a-z0-9]+)\]', msg).groups()
    F['loop_subject'] = msg.split('\n')[0].split('] ', 1)[1]
    F['loop_short'] = F['loop_full'][:7]
    F['loop_date'] = grab(subprocess.run(['git', '-C', REPO, 'log', '-1', '--format=%cd', '--date=iso', 'b819df1'],
                                capture_output=True, text=True).stdout,
                          r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) -0800$', 'committer date of b819df1, as git prints it')

    # ---------- push, install, identity of the installed file ----------
    w15 = w('w15.out')
    F['dev_sha'] = grab(w15, r'^([0-9a-f]{64})  /data/local/tmp/m32\.apk', 'device sha256 line')
    F['dev_size'] = grab(w15, r'^-rw-rw-rw- +\d+ +\w+ +\w+ +(\d+) +\S+ +[\d:]+ /data/local/tmp/m32\.apk', 'device size line')
    F['dev_push'] = grab(w15, r'^(\[100%\] /data/local/tmp/m32\.apk)$', 'push complete line')
    w16 = w('w16.out')
    F['inst_result'] = grab(w16, r'^(Success)$', 'install result line')
    F['new_code'] = grab(w16, r'codePath=(/data/app/com\.mazawallet-\S+)', 'new code path')
    F['new_update'] = grab(w16, r'lastUpdateTime=(2026-11-28 \d\d:\d\d:\d\d)', 'new update time')
    F['new_first'] = grab(w16, r'firstInstallTime=(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)', 'first install time after the update')
    F['new_version'] = grab(w16, r'versionName=(\S+)', 'version name')
    w17 = w('w17.out')
    m = re.search(r'^([0-9a-f]{32})  /data/app/com\.mazawallet-\S+/base\.apk\n', w17, re.M)
    F['inst_md5'] = m.group(1)
    m = re.search(r'^([0-9a-f]{64})  /data/app/com\.mazawallet-\S+/base\.apk\n', w17, re.M)
    F['inst_sha'] = m.group(1)
    F['inst_md5_ok'] = F['inst_md5'] == F['apk_md5']
    F['inst_sha_ok'] = F['inst_sha'] == F['apk_sha']
    F['dev_equal'] = F['dev_sha'] == F['apk_sha'] and F['dev_size'] == F['apk_size']
    ls = re.search(r'> shell ls /data/local/tmp/\n(.*?)\n> ', w17, re.S)
    F['temp_gone'] = 'm32.apk' not in (ls.group(1) if ls else 'm32.apk')
    F['badge_line'] = grab(w17, r'(AppSettings: com\.mazawallet \(10068\) showBadge=\w+)', 'app settings line')
    F['w17_none'] = 'importance=NONE' in w17
    F['w17_pid'] = pid_of(w17)
    F['w17_crash'] = len([l for l in w17.split('\n') if 'FATAL' in l])

    # ---------- connect, unlock, the form ----------
    F['w18_tok'] = w('w18_token.out') == tk
    w18 = w('w18.out')
    F['w18_bal'] = amounts(w18, 8)
    F['addr7'] = open(W + '/to_addr2.txt').read().strip()
    w19 = w('w19.out')
    if not re.fullmatch(r'M[A-Za-z1-9]{25,40}', F['addr7']) or ('text="%s"' % F['addr7']) not in w19:
        raise Fail('index-7 address not found in the w19 dump')
    F['addr7_index'] = re.search(r'text="index (\d+)"[^>]*/>\s*<node [^>]*text="%s"' % F['addr7'], w19).group(1)
    F['w19_unlocked'] = 'Wallet locked' not in w19
    F['w20_count'] = count_cmd(w('w20.out'), 'hcallOnAppNotificationReceivedRpc')
    btns = [b for b in re.findall(r'<node [^>]*text="SEND"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', w('w20.out'))]
    form = [b for b in btns if int(b[1]) < 700]          # the tab bar's own SEND sits at y=816
    if len(form) != 1 or len(btns) != 2:
        raise Fail('SEND button: expected the form button and the tab button, found %s' % btns)
    F['send_btn'] = '[%s,%s][%s,%s]' % form[0]
    F['send_btn_xy'] = '(%d,%d)' % ((int(form[0][0]) + int(form[0][2])) // 2, (int(form[0][1]) + int(form[0][3])) // 2)
    w21 = w('w21.out')
    F['w21_err'] = grab(w21, r'\[e\] (ERROR: null root node returned by UiTestAutomationBridge\.)', 'dump error line')
    F['w21_typed'] = ('shell input text ' + F['addr7']) in w21 and 'shell input text 0.1' in w21
    F['w21_api'] = str(len(re.findall(r'POST /api/send', w21)))
    typed = re.findall(r'shell input text (\S+)', w('w21.txt'))
    if len(typed) != 2 or typed[0] != F['addr7']:
        raise Fail('the command file does not hold the lifted address and one more typed value')
    F['s5_amt'] = typed[1]
    w22 = w('w22.out')
    ed = [re.search(r'text="([^"]*)"', n).group(1) for n in re.findall(r'<node [^>]*?/>', w22) if 'class="android.widget.EditText"' in n]
    F['w22_addr_ok'] = F['addr7'] in ed
    F['w22_amt_ok'] = '0.1' in ed
    F['w22_api'] = str(len(re.findall(r'POST /api/send', w22)))      # the round grep'd the log for the send route; nothing printed means none
    F['w22_ime'] = grab(w22, r'(mInputShown=\w+)', 'IME line')
    F['w23_api'] = str(len(re.findall(r'POST /api/send', w('w23.out'))))
    F['w23_ocr'] = [l.strip() for l in w('w23_form_red.ocr.txt').split('\n') if l.strip() and len(l.strip()) > 3]

    # ---------- the send and the watch ----------
    s1 = w('s1.out')
    F['s1_tap'] = grab(w('s1_times.txt'), r'^SEND TAP at (\d\d:\d\d:\d\d)$', 'tap clock line')
    m = re.search(r'(\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) +\d+ +\d+ I MAZA +: \S+ \S+ #(\d+) POST /api/send -> (\d+)', s1)
    F['s1_post_time'], F['s1_req_no'], F['s1_http'] = m.groups()
    F['s1_post_hms'] = F['s1_post_time'][6:]
    F['s1_result'] = grab(s1, r'text="(Sent \(bench account\): [^"]+)"', 'result line on the SEND tab')
    F['s1_bal'] = amounts(s1.split('> shell input tap 160 858')[1], 8)
    F['s1_sync_full'] = re.search(r'Last sync (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)', s1).group(1)   # the screen's whole string; it is quoted whole
    F['s1_sync'] = F['s1_sync_full'][11:]
    F['s1_count'] = re.findall(r'grep -c -e hcallOnAppNotificationReceivedRpc\n(\d+)\n', s1)[-1]

    def batch(prefix, ks):
        rows, counts, ids, pids, bals, present = [], set(), set(), set(), set(), {}
        F.setdefault('_sync_full', {})     # filled by both watch batches
        for k in ks:
            n = '%s_%02d' % (prefix, k)
            t = w(n + '.out')
            c, r = count_cmd(t, 'hcallOnAppNotificationReceivedRpc'), tuple(rec_ids(t))
            pid = pid_of(t)
            b = amounts(t, 8)
            sync = re.search(r'Last sync (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)', t)
            present[n] = posts(t)
            rows.append((n, c, list(r), pid, b, sync.group(1)[11:] if sync else '?', len(present[n])))
            F['_sync_full'][n] = sync.group(1) if sync else '?'
            counts.add(c); ids.add(r); pids.add(pid); bals.add(tuple(b))
        tm = [l.split() for l in w('%s_times.txt' % prefix).strip().split('\n') if re.match(prefix + r'_\d\d start=', l)]
        return rows, counts, ids, pids, bals, present, (tm[0][1].split('=')[1], tm[-1][3].split('=')[1])
    r1, c1, i1, p1, b1, h1, t1 = batch('m1', range(1, 13))
    r2, c2, i2, p2, b2, h2, t2 = batch('m2', range(1, 10))
    F['m1_rows'], F['m2_rows'] = r1, r2
    F['m1_start'], F['m1_end'] = t1
    F['m2_start'], F['m2_end'] = t2
    allposts = [p for n in h1 for p in h1[n]]
    F['m1_posts'] = sorted(set(allposts))
    if not F['m1_posts'][0][3].startswith('+%.8f ' % float(F['s5_amt'])):
        raise Fail('the posted amount is not the typed amount')
    F['m1_first_post_round'] = next(n for n in sorted(h1) if h1[n])
    F['sync_full'] = F.pop('_sync_full')
    F['m1_counts'] = sorted(c1, key=int)
    F['m1_ids'] = sorted(i1)
    F['m1_pids'] = sorted(p1)
    F['m1_bals'] = sorted(b1)
    F['m2_counts'] = sorted(c2, key=int)
    F['m2_ids'] = sorted(i2)
    F['m2_pids'] = sorted(p2)
    F['m2_bals'] = sorted(b2)
    F['m2_posts'] = sorted(set(p for n in h2 for p in h2[n]))
    F['targets'] = sum(w(p + '_times.txt').count('TARGET-SEEN') for p in ('m1', 'm2'))     # early stops of the watcher in the two M32 batches
    bo = rd(X + '/build.out')
    F['st_pass_n'] = len(re.findall(r'^PASS sendecho: ', bo, re.M))
    k_ = re.findall(r'^(PASS sendecho: own change settling never fires)$', bo, re.M)
    if len(k_) != 1:
        raise Fail('the key self-test line is not exactly once in the rebuild log')
    F['st_pass_key'] = k_[0]
    F['m1_recs_before'] = sorted({tuple(r[2]) for r in r1 if r[0] < F['m1_first_post_round']})
    F['m1_recs_after'] = sorted({tuple(r[2]) for r in r1 if r[0] >= F['m1_first_post_round']})
    F['m1_counts_before'] = sorted({r[1] for r in r1 if r[0] < F['m1_first_post_round']}, key=int)
    F['m1_counts_after'] = sorted({r[1] for r in r1 if r[0] >= F['m1_first_post_round']}, key=int)
    w24 = w('w24.out')
    F['w24_code'] = grab(w24, r'codePath=(/data/app/com\.mazawallet-\S+)', 'code path in w24')
    F['w24_update'] = grab(w24, r'lastUpdateTime=(2026-11-28 \d\d:\d\d:\d\d)', 'update time in w24')
    F['w24_ids'] = rec_ids(w24)
    F['w24_front'] = bool(re.search(r'mResumedActivity: ActivityRecord\{\w+ u0 com\.mazawallet/\.MainActivity', w24))
    F['w24_other'] = next(re.search(r'NotificationRecord\(0x[0-9a-f]+: pkg=(\S+) user=UserHandle\{-?\d+\} id=(\d+)', l).groups()
                         for l in w24.split('\n') if 'NotificationRecord(' in l and 'pkg=com.mazawallet ' not in l)
    F['null_root'] = sorted(f for f in os.listdir(W) if f.endswith('.out') and 'null root node' in w(f))
    w25 = w('w25.out')
    ext = re.findall(r'^\[ +[\d.]+\] (EXT4-fs \([^)]*\): mounted filesystem with ordered data mode\. .*)$', w25, re.M)
    F['w25_ext4'] = ext
    F['w25_err'] = grab(w25, r'^\[ +[\d.]+\] (.*)$', 'the one dmesg error line') if False else re.search(r'> shell dmesg \| grep -i -e error\n(?:.*\n)*?> ', w25).group(0).split('\n')[1]
    F['w25_blk'] = len([l for l in w25.split('\n') if 'blk_update' in l and not l.startswith('> shell')])   # the round grep'd the kernel log; nothing printed means none
    F['w25_fatal'] = grab(w25, r'(\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} +\d+ +\d+ E \w+: Fatal exception in non ad network)', 'fatal line')
    F['w25_fatal_pid'] = re.search(r'\s(\d+)\s+\d+ E FlutterAdsFragment', F['w25_fatal']).group(1)
    F['w25_pid'] = grab(w25, r'u0_a68 +(\d+) ', 'process line in w25')
    ba = w('bench_state_m32.out')
    m = re.search(r'^\[(2026-11-28 \d\d:\d\d:\d\d) CET\] GET /api/state -> 200 balance=([\d.]+) account=(\S+)', ba, re.M)
    F['bench_cet'], F['bench_bal'], F['bench_acct'] = m.groups()
    m = re.search(r'watch set: balance=([\d.]+) utxos=(\d+) confirmations=\[([0-9, ]+)\]', ba)
    F['bench_watch'], F['bench_utxos'], F['bench_conf'] = m.groups()
    F['fee4'] = '%.4f' % (float(F['send4_pre_bal']) - float(F['state_bal']) - float(F['send4_amt']))
    F['fee5'] = '%.4f' % (float(F['state_bal']) - float(F['bench_bal']) - float(F['s5_amt']))
    if F['fee4'] != F['fee5']:
        raise Fail('the two sends did not cost the same fee')
    F['bench_pst'] = (datetime.datetime.strptime(F['bench_cet'], '%Y-%m-%d %H:%M:%S') - CET_OFFSET).strftime('%H:%M:%S')

    # ---------- the app's source and the previous build's behaviour ----------
    rn, F['rn_blob'] = src_file('android/src/com/mazawallet/ReceiveNotify.java')
    F['src_bench'] = next('%d: %s' % (i + 1, l.strip()) for i, l in enumerate(rn) if 'private static final int ID_BENCH = 1;' in l)
    F['src_wallet'] = next('%d: %s' % (i + 1, l.strip()) for i, l in enumerate(rn) if 'private static final int ID_WALLET = 2;' in l)
    F['src_notify'] = next('%d: %s' % (i + 1, l.strip()) for i, l in enumerate(rn) if 'nm.notify(id, b.build());' in l)
    F['src_text'] = next('%d: %s' % (i + 1, l.strip()) for i, l in enumerate(rn) if '.setContentText("+" + fmtMaza(deltaSats)' in l)
    # the previous build, same test, from the committed package of 2026-11-27: every notification the host log shows after each send, and its latency
    F['old'] = []
    for d, sfile in (('locked', 'send1.out'), ('backgrounded', 'send2.out'), ('denial-not-done', 'send3.out')):
        s = re.search(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) CET\] POST /api/send to=\S+ amount=([\d.]+) -> HTTP (\d+)', rd(OLD + '/' + d + '/' + sfile), re.M)
        st = datetime.datetime.strptime(s.group(1), '%Y-%m-%d %H:%M:%S') - CET_OFFSET
        seen, ids = {}, set()
        for f in sorted(os.listdir(OLD + '/' + d)):
            if f.endswith('.out'):
                txt = rd(OLD + '/' + d + '/' + f)
                ids |= set(rec_ids(txt))
                for p in posts(txt):
                    seen.setdefault(p[0], p[3])
        F['old_ids_' + d] = sorted(ids)
        for lt, txt in sorted(seen.items()):
            pt = datetime.datetime.strptime('2026-' + lt[:14], '%Y-%m-%d %H:%M:%S')     # the guest's clock is PST
            lat = int((pt - st).total_seconds())
            if lat < 0:
                continue                                   # a notification that belongs to the previous send
            F['old'].append((d, s.group(2), st.strftime('%H:%M:%S'), lt, txt, lat))
    F['old_echo'] = [o for o in F['old'] if o[4].endswith('bench account')]
    F['old_echo_txt'] = '; '.join('%d seconds after the %s MAZA send' % (o[5], o[1]) for o in F['old_echo'])
    i = next(i for i, l in enumerate(rn) if 'Distinct ids so a bench receive' in l)
    F['src_comment'] = ' '.join(' '.join(re.sub(r'^\s*/?\*+\s?|\s?\*+/\s*$', '', x) for x in (rn[i], rn[i + 1])).split())
    F['src_c1'], F['src_c2'] = ('%d: %s' % (i + 1, rn[i].strip()), '%d: %s' % (i + 2, rn[i + 1].strip()))   # the comment above the two id lines
    ma, F['ma_blob'] = src_file('android/src/com/mazawallet/MainActivity.java')
    j = next(j for j, l in enumerate(ma) if 'exactly ONE attempt' in l)
    F['src_send_no'] = str(j + 1)
    F['src_send_comment'] = ma[j].strip().lstrip('/').strip()
    k_ = next(k for k, l in enumerate(ma) if 'Net.withRetry("POST", "/api/send",' in l)
    F['src_send_call'] = '%d: %s' % (k_ + 1, ma[k_].strip())
    F['src_send_call2'] = '%d: %s' % (k_ + 2, ma[k_ + 1].strip())
    et, F['et_blob'] = src_file('android/src/com/mazawallet/crypto/SendEchoTracker.java')
    F['et_class'] = next('%d: %s' % (k + 1, l.strip()) for k, l in enumerate(et) if l.startswith('public final class SendEchoTracker'))
    F['et_window'] = next('%d: %s' % (k + 1, l.strip()) for k, l in enumerate(et) if 'public static final long WINDOW_MS =' in l)
    st, F['st_blob'] = src_file('android/src/com/mazawallet/crypto/SelfTest.java')
    F['st_section'] = next('%d: %s' % (k + 1, l.strip()) for k, l in enumerate(st) if 'section("SendEchoTracker' in l)
    # every source line the run log quotes: (path, line number, the line as stripped text); build() checks each against the commit
    F['st_files'] = [('android/src/com/mazawallet/ReceiveNotify.java', F['rn_blob']), ('android/src/com/mazawallet/MainActivity.java', F['ma_blob']), ('android/src/com/mazawallet/crypto/SendEchoTracker.java', F['et_blob']), ('android/src/com/mazawallet/crypto/SelfTest.java', F['st_blob'])]
    F['src_q'] = [('android/src/com/mazawallet/ReceiveNotify.java', int(F[k].split(': ', 1)[0]), F[k].split(': ', 1)[1]) for k in ('src_bench', 'src_wallet', 'src_notify', 'src_text', 'src_c1', 'src_c2')]
    F['src_q'] += [('android/src/com/mazawallet/MainActivity.java', j + 1, ma[j].strip()), ('android/src/com/mazawallet/MainActivity.java', k_ + 1, ma[k_].strip()), ('android/src/com/mazawallet/MainActivity.java', k_ + 2, ma[k_ + 1].strip())]
    F['src_q'] += [('android/src/com/mazawallet/crypto/SendEchoTracker.java', int(F[k].split(': ', 1)[0]), F[k].split(': ', 1)[1]) for k in ('et_class', 'et_window')]
    F['src_q'] += [('android/src/com/mazawallet/crypto/SelfTest.java', int(F['st_section'].split(': ', 1)[0]), F['st_section'].split(': ', 1)[1])]
    # the run-log line that opened the window (the backlog, a private file) and the judge's verdict on it (a private capture)
    m_hold = re.search(r'^- 2026-11-28 (\d\d:\d\d) PST \(interactive lane, thread 54\): NEW WINDOW, HOLD LINE\.\n(.*?)(?=^- 20\d\d-|\Z)', rd('/root/maza-mobile-backlog.md'), re.M | re.S)
    if not m_hold:
        raise Fail('the hold line is not in the backlog')
    F['hold_hm'] = m_hold.group(1)
    hm_ = re.findall(r'about (\d+) minutes', m_hold.group(2))
    if len(hm_) != 1:
        raise Fail('the length the hold line announced is not stated exactly once')
    F['hold_min'] = hm_[0]
    g = re.search(r'^GRADE=(\w) (urn=urn:ump:\w+)\s*$', rd(S + '/m32/judge_run2.out'), re.M)
    F['hold_grade'], F['hold_urn'] = g.group(1), g.group(2)
    return F


def derived(F):
    L = ['# DERIVED - every row below is recomputed by scripts/m32_pack.py from the .out capture named in it.', '']
    L.append('## Denial watch (Part A): one row per round. posts = output of `logcat -d | grep -c -e hcallOnAppNotificationReceivedRpc` in that capture;')
    L.append('records = notification ids the service holds for com.mazawallet in that capture; blocked = the capture holds `importance=NONE` for the app;')
    L.append('watch-set balance = the amounts the screen showed on the WALLET tab (the self-custody watch set).')
    L.append('%-7s | %-5s | %-6s | %-6s | %-5s | %s' % ('round', 'posts', 'recs', 'blocked', 'pid', 'watch-set balance on screen'))
    for n, c, r, ne, pid, b in F['w9_rows']:
        L.append('%-7s | %-5s | %-6s | %-6s | %-5s | %s' % (n, c, ','.join(r) or 'none', 'yes' if ne else 'NO', pid, ', '.join(b) or '?'))
    L.append('')
    L.append('## M32 watch (Part B), batch 1 and batch 2. bench balance = the amount on the BALANCE tab; sync = its "Last sync" time;')
    L.append('line = notification host calls printed in that capture (the log line itself); records as above.')
    L.append('%-7s | %-5s | %-5s | %-6s | %-5s | %-14s | %-2s | %s' % ('round', 'posts', 'line', 'recs', 'pid', 'bench balance', 'sy', 'last sync'))
    for n, c, r, pid, b, sync, k in F['m1_rows'] + F['m2_rows']:
        L.append('%-7s | %-5s | %-5d | %-6s | %-5s | %-14s | %-2s | %s' % (n, c, k, ','.join(r) or 'none', pid, ', '.join(b) or '?', '', sync))
    L.append('')
    L.append('## Facts (name: value <- capture the value was parsed from)')
    for k in sorted(F):
        if k.endswith('_rows'):
            continue
        L.append('%s: %s' % (k, F[k]))
    return '\n'.join(L) + '\n'


def yn(x):
    return 'yes' if x else 'NO'


def runlog(F):
    L = []
    A = L.append
    A('# M8B-II-A window of 2026-11-28 %s-%s PST: the M14-ii denial state and the M32 device proof\n' % (hhmm(F['launched']), hhmm(F['stopped'])))
    A('Lane: interactive lane, thread 54 (MAZA Skunkworks). Device: the BlueStacks Pie64 guest on the owner\'s PC, driven over adb by the lane\'s round helper. '
      'Every figure in sections 1 to 3 is parsed from a capture in this package by `scripts/m32_pack.py`; `DERIVED.txt` holds the parsed values and the two watch tables. '
      'Section 0 quotes the owner and the run log; of the run log itself only the judge\'s verdict line is in this package (timing/hold_grade.txt). Source lines quoted below are in source/source-lines.txt.\n')
    A('## 0. Authority and scope\n')
    A('- The owner\'s words that opened the window: "Keep fixing it till it\'s done" (Telegram message 1225, thread 54, 11-28). It answered the lane\'s report, which had asked for an OK to reopen the emulator for a 0.1 MAZA send. '
      'The run log line of %s PST (in the backlog file, not in this package) recorded the lane\'s reading of that answer openly - it went through the judge before it was written (judge grade %s, %s) - and scoped the window to two things: '
      'the M14-ii denial state, and the M32 device send once a graded M32 commit was on origin. The owner did not use the runbook\'s words ("the window is OK"); that is on record in that line. [timing/hold_grade.txt]\n'
      % (F['hold_hm'], F['hold_grade'], F['hold_urn']))
    A('- Money: two sends in this window, 0.1 MAZA each, both from the bench account, each to a receive address of the same wallet (indices %s and %s), so the funds stayed in the test wallet: '
      'send 4 for the denial state and send 5 for M32. The bench balance moved by the amount plus a %s MAZA fee each time (sections 2 and 3).\n' % (F['addr6_index'], F['addr7_index'], F['fee4']))
    A('- Not touched: no uninstall, no data clear, no repair or disk check on the PC, nothing in the app source (the M32 code is the loop\'s, commit `%s`; this lane adds evidence files only).\n' % F['loop_short'])
    A('## 1. The window\n')
    A('- Launched %s PST, player ready %s (%s). [timing/launch-stop.txt]\n' % (F['launched'], F['ready'], F['boot_secs']))
    A('- Closed by this lane at %s PST. The stop script tries the window\'s own close path first and fell back to its usual stop ("%s"); it touches no guest data. '
      'Read-back: `tasklist` for the player process -> "%s". [timing/launch-stop.txt, timing/w26_tasklist.out]\n' % (F['stopped'], F['close_path'], F['no_player']))
    A('- Length: %s. DISCLOSED OVERRUN: the %s line announced about %s minutes. When the denial test was done the lane found the loop\'s M32 commit on origin, '
      'so it went on to the M32 device send in the same boot instead of closing and reopening. The window is closed; the veto stands again until the owner says the window is OK.\n'
      % (F['window'], F['hold_hm'], F['hold_min']))
    A('- Guest disk: the boot error count at %s PST reads "%s". At the end of the window the kernel log holds %d `EXT4-fs` lines (the boot-time mount message for %s), '
      'one boot-time firmware note ("%s"), and %d `blk_update` lines. [timing/launch-stop.txt, after/w25.out]\n'
      % (F['err_when'], F['err_zero'], len(F['w25_ext4']), ' and '.join(re.search(r'\((\w+)\)', e).group(1) for e in F['w25_ext4']), F['w25_err'], F['w25_blk']))
    A('## 2. Part A - M14-ii, the third state: notifications denied (PASS)\n')
    A('The app-ops route was shown not to gate delivery on this guest on 11-27 (the rn/ package). The switch tried here is the app\'s own notification-settings screen.\n')
    A('1. Build on the device: the 11-27 build (`codePath=%s`, `lastUpdateTime=%s`). Its `POST_NOTIFICATION` app-ops entry still read `ignore` from the evening ("%s"); set back to `default` and read back ("%s"). '
      '[boot/w1.out, boot/w2.out, old-build/w12.out]\n' % (F['old_code'], F['old_update'], F['w1_ops'], F['w2_ops']))
    A('2. Connect: the bench token staged by the lane\'s script - "%s", "TYPED-LEN %s", "%s"; no token value is in any capture. Balance on screen after the connect: %s MAZA. [boot/w_token.out, boot/w3.out]\n'
      % ('TOKEN len=%s class=%s' % (F['tok_len'], F['tok_class']), F['tok_typed'], F['tok_connect'], ', '.join(F['w3_bal'])))
    A('3. Unlock with the PIN (placeholder `[PIN]` in the command list; the digits are substituted at run time and never written): %s. WALLET tab, receive address index %s. [unlock/w4.txt, unlock/w4.out, unlock/to_addr.txt]\n'
      % ('unlocked: ' + yn(F['w4_unlocked']), F['addr6_index']))
    A('4. The app\'s notification settings: the master "Show notifications" switch reads ON at %s; tapped once. The notification service then reports the app with `importance=NONE` '
      'and the screen shows "%s". The wallet was not killed by this: process %s; its log in that capture ends with a `GET /api/state -> 200` answer at %s. '
      '[switch/w5.out, switch/w6.out, switch/w7.out, switch/w6_off_red.ocr.txt]\n'
      % (F['tap_xy'], F['w7_banner'], F['pid_old'], F['w7_poll_last']))
    A('5. Wallet back to the front (in front: %s), unlocked: %s, still blocked (`importance=NONE` present: %s). Baseline capture w9_00. [switch/w8.out, denial/w9_00.out]\n'
      % (yn(F['w8_front']), yn(F['w8_unlocked']), yn(F['w8_none'])))
    A('6. SEND 4: %s PST (%s on the bench host\'s clock, CET), %s MAZA to the index-%s address, HTTP %s, txid %s. Bench balance before: %s MAZA. [denial/send4.out]\n'
      % (F['send4_pst'], F['send4_cet'], F['send4_amt'], F['addr6_index'], F['send4_http'], F['send4_tx'], F['send4_pre_bal']))
    A('7. Watch: %s captures, read-only - the baseline w9_00 before the send, then %d rounds from %s to %s PST. The wallet\'s own poll picked the coin up '
      '(watch-set balance on screen %s MAZA before round %s, %s MAZA from that round on). Notification posts in every capture: %s. Notification records for the app in every capture: %s. '
      '`importance=NONE` in every capture: %s. Wallet process in every capture: %s. [denial/w9_00.out .. w9_21.out, denial/w9_times.txt, DERIVED.txt]\n'
      % (F['w9_rounds'], int(F['w9_rounds']) - 1, F['w9_first_start'], F['w9_last_end'], '/'.join(','.join(b) for b in F['w9_before_bals']), F['w9_change_round'],
         '/'.join(','.join(b) for b in F['w9_after_bals']), ','.join(F['w9_counts']), ','.join(','.join(r) for r in F['w9_recs']) or 'none',
         yn(F['w9_nones'] == [True]), ','.join(F['w9_pids'])))
    A('   The previous build (11-27, the committed rn/ package): its false echo reached the host log %s. The last capture of the watch is stamped %d seconds after the send time. '
      'That length is as recorded: the send time is the bench host\'s clock, the round times the lane\'s. '
      'The record count is the cumulative check; the log count is the immediate one. Both read zero throughout.\n'
      % (F['old_echo_txt'], int((hms(F['w9_last_end']) - hms(F['send4_pst'])).total_seconds())))
    A('8. Bench state after send 4, %s PST: balance %s MAZA (= %s - %s - %s fee); watch set %s MAZA, %s unspent coins, the least-confirmed of them with %d confirmations. [denial/send4_state.out]\n'
      % (F['state_pst'], F['state_bal'], F['send4_pre_bal'], F['send4_amt'], F['fee4'], F['state_watch'], F['state_utxos'], min(int(x) for x in F['state_conf'].split(','))))
    A('9. Switch restored. The dump before the tap shows the switch OFF (%s); the dump after it shows ON (%s) and no longer holds the banner (%s); `importance=NONE` is %s in the whole capture. '
      '[switch/w11_switch.txt, switch/w11.out]\n'
      % (yn(F['w11_before_off']), yn(F['w11_after_on']), 'gone' if not F['w11_after_banner'] else 'STILL SHOWN', 'absent' if not F['w11_none'] else 'STILL PRESENT'))
    A('Not used as evidence: the notification-shade screenshot of this part (switch/w10_shade_red.ocr.txt). Its OCR text shows only the clock and the date: the privacy box covers the card area. '
      'The denial claim rests on the service records and the log, not on that picture.\n')
    A('## 3. Part B - M32: an app-initiated send without the echo (PASS)\n')
    A('The defect: after a send the sampled bench balance dips to zero (the change is unconfirmed), then settles - a strict increase, which the poll announced as "MAZA received". '
      'The fix is the loop\'s: commit `%s` - %s - judge grade %s, %s - on origin before the device work started (the lane found it there after the denial test). '
      '`SendEchoTracker` is a Java class of the app\'s `com.mazawallet.crypto` package (android/src/com/mazawallet/crypto/SendEchoTracker.java: line %s declares it, line %s its settle window); '
      'the tree\'s build-time self-test has a section for it (SelfTest.java line %s), and the lane\'s independent rebuild ran it: %s lines starting "PASS sendecho:", among them "%s". '
      '[source/source-lines.txt, apk/build.out]\n'
      % (F['loop_short'], F['loop_subject'], F['loop_grade'], F['loop_urn'], F['et_class'].split(':')[0], F['et_window'].split(':')[0],
         F['st_section'].split(':')[0], F['st_pass_n'], F['st_pass_key']))
    A('- Git dates the loop\'s commit `%s` %s -0800 (committer date, read with `git log -1 --format=%%cd --date=iso`): after the denial test the lane fetched and found it on origin. '
      'This log does not compare the clocks of different hosts; the time is given as recorded.\n' % (F['loop_short'], F['loop_date']))
    A('### 3.1 Is the APK in the tree a build of that commit? (checked independently by this lane)\n')
    A('- The APK on origin: %s bytes, sha256 %s. The PC copy, hashed on the PC: %s - %s. [old-build/w13_pc_sha.txt]\n'
      % (F['apk_size'], F['apk_sha'], F['pc_sha'], 'the same digest' if F['pc_equal'] else 'DIFFERENT'))
    A('- Rebuilt by this lane from `git archive %s` with the tree\'s own build script: "%s", "%s bytes". The whole-file hashes differ; the unpacked entries do not: '
      '%s of %s entries are identical, `classes.dex` included, and the two unpacked trees were hashed again while this package was built (%s). [apk/build.out, apk/cmpA.sha, apk/cmpB.sha]\n'
      % (F['loop_short'], F['build_checks'], F['build_bytes'], F['cmp_lines'], F['cmp_lines'], 'identical' if F['cmp_equal'] and F['cmp_recheck'] else 'DIFFERENT'))
    A('- So the file installed below is the tree\'s own APK, and that APK is a build of commit `%s`.\n' % F['loop_short'])
    A('### 3.2 Install in place\n')
    A('- First push attempt failed: "%s". Second attempt, forward slashes: "%s". Cause, read from the round helper itself (`adbrun.ps1`, a script of the earlier android/evidence/m8b2a/ package, which is not committed yet; not changed in this window): '
      'line %s reads `%s`; line %s reads `%s`. Both handlers cut their first argument with `Substring(6, ...)`, but `push ` and `pull ` are 5 characters, so the first character is dropped: '
      'the drive letter of a local path on `push`; the leading slash of the remote path on `pull`, which resolves to the same file, so pulls worked. The `raw` verb passes its arguments through untouched. '
      '[old-build/w13.out, old-build/w14.out]\n'
      % (F['w13_err'], F['w14_err'], F['adb_push_no'], F['adb_push_line'], int(F['adb_push_no']) - 1, F['adb_pull_line']))
    A('- `raw push` to the guest temp dir: "%s"; on the device: %s bytes, sha256 %s - %s. [install/w15.out]\n'
      % (F['dev_push'], F['dev_size'], F['dev_sha'], 'the same digest as host, PC and origin' if F['dev_equal'] else 'DIFFERENT'))
    A('- `pm install -r` inside the guest: "%s". Read back: `codePath=%s`, `lastUpdateTime=%s`, `firstInstallTime=%s` - the same as before the update (%s), so nothing was uninstalled or reinstalled; '
      'the app\'s PIN was still set afterwards (the same unlock worked: %s). [install/w16.out, old-build/w12.out, connect/w19.out]\n'
      % (F['inst_result'], F['new_code'], F['new_update'], F['new_first'], F['old_first'], yn(F['w19_unlocked'])))
    A('- The installed file itself, hashed inside the guest: md5 %s, sha256 %s - %s. Temp copy removed: %s. The notification service no longer lists the app as blocked '
      '(`importance=NONE` %s), so the switch restored in Part A survived the update. [install/w17.out]\n'
      % (F['inst_md5'], F['inst_sha'], 'both equal the APK on origin' if F['inst_md5_ok'] and F['inst_sha_ok'] else 'DIFFERENT',
         yn(F['temp_gone']), 'absent' if not F['w17_none'] else 'PRESENT'))
    A('### 3.3 The form\n')
    A('- The new build started on its Connect card; FATAL lines in that capture: %d. Token staged again (the same three lines as before: %s), connected, balance on screen %s MAZA; unlocked: %s; receive address index %s. '
      '[install/w17.out, connect/w18_token.out, connect/w18.out, connect/w19.out, connect/to_addr2.txt]\n'
      % (F['w17_crash'], 'identical capture' if F['w18_tok'] else 'DIFFERENT capture', ', '.join(F['w18_bal']), yn(F['w19_unlocked']), F['addr7_index']))
    A('- SEND tab layout read from a dump: the form\'s button is `text="SEND"` at %s (the theme upper-cases it). Post count in the log at this point: %s. [form/w20.out]\n' % (F['send_btn'], F['w20_count']))
    A('- The two fields were typed from a command file the lane generated from the lifted address (nothing hand-typed: %s). The dump in that round failed ("%s"); that round sent nothing '
      '(`/api/send` lines in its log read: %s). A fresh dump read the fields back: address field equal to the lifted address: %s; amount field equal to 0.1: %s; `/api/send` lines in the log: %s. '
      '[form/w21.txt, form/w21.out, form/w22.out]\n'
      % (yn(F['w21_typed']), F['w21_err'], F['w21_api'], yn(F['w22_addr_ok']), yn(F['w22_amt_ok']), F['w22_api']))
    A('- Screenshot before the tap (redacted; its OCR text is in the package): `/api/send` lines in the log: %s. [form/w23.out, form/w23_form_red.ocr.txt]\n' % F['w23_api'])
    A('### 3.4 The send\n')
    A('- The send round started at %s PST by the lane\'s clock: one tap on the form\'s SEND button. The app logged "POST /api/send -> %s" (request no. %s) at %s by the guest\'s clock; result on the tab: "%s". '
      'In the source at that commit the send path is marked "%s" (MainActivity.java line %s; the send call is at lines %s-%s); the log holds one POST for the one tap. [send/s1_times.txt, send/s1.out, source/source-lines.txt]\n'
      % (F['s1_tap'], F['s1_http'], F['s1_req_no'], F['s1_post_hms'], F['s1_result'], F['src_send_comment'], F['src_send_no'],
         F['src_send_call'].split(':')[0], F['src_send_call2'].split(':')[0]))
    A('- BALANCE tab right after: %s MAZA at "Last sync %s" - the dip. Post count: %s. [send/s1.out]\n' % (', '.join(F['s1_bal']), F['s1_sync_full'], F['s1_count']))
    A('### 3.5 The watch\n')

    def why(r):
        return r[0] + (' (its dump came back with the transient error of section 5)' if 'null root node' in w(r[0] + '.out') else ' (reason not determined)')
    unread = lambda rows: ', '.join(why(r) for r in rows if not r[4]) or 'none'      # noqa: E731
    A('- Batch 1, %d rounds from %s to %s PST, read-only. (The watcher stops early only when a screen dump matches a target text it was given; in the two M32 batches it stopped early %s times.) Round m1_01: post count %s, no record yet, and the balance tab already reads %s MAZA '
      'with "Last sync %s" - the climb. From round %s on every capture holds exactly one notification host call: %s, package %s, "%s", "%s" - the genuine receive of the %s MAZA into the wallet\'s own address '
      '(the watch set went from %s to %s MAZA between the two bench-state reads). Post count before that round: %s; from it on: %s. Notification records for the app before that round: %s; from it on: %s. '
      'Wallet process: %s in every round. The balance tab was not readable in round %s; every other round shows %s MAZA. [watch/m1_01.out .. m1_12.out, watch/m1_times.txt, DERIVED.txt]\n'
      % (len(F['m1_rows']), F['m1_start'], F['m1_end'], F['targets'], ','.join(F['m1_counts_before']), ', '.join(F['m1_rows'][0][4]), F['sync_full'][F['m1_rows'][0][0]], F['m1_first_post_round'],
         F['m1_posts'][0][0], F['m1_posts'][0][1], F['m1_posts'][0][2], F['m1_posts'][0][3], F['send4_amt'], F['state_watch'], F['bench_watch'],
         ','.join(F['m1_counts_before']), ','.join(F['m1_counts_after']), ','.join(','.join(r) for r in F['m1_recs_before']) or 'none',
         ','.join(','.join(r) for r in F['m1_recs_after']), ','.join(F['m1_pids']), unread(F['m1_rows']), ', '.join(F['m1_rows'][1][4])))
    A('- Batch 2, %d rounds from %s to %s PST: notification records for the app id %s in every round; wallet process %s in every round; post count %s in every round. '
      'That count is lower than batch 1\'s: `logcat -d` is not a fixed record. The 02:41:41 line is in every capture of batch 1 from round %s on and in none of batch 2 '
      '(my reading is that the log buffer had moved on; I did not check that). The service records are the cumulative evidence. '
      'The balance tab was not readable in round %s; every other round shows %s MAZA. [watch/m2_01.out .. m2_09.out, watch/m2_times.txt, DERIVED.txt]\n'
      % (len(F['m2_rows']), F['m2_start'], F['m2_end'], ','.join(','.join(r) for r in F['m2_ids']), ','.join(F['m2_pids']), ','.join(F['m2_counts']),
         F['m1_first_post_round'], unread(F['m2_rows']), ', '.join(F['m2_rows'][0][4])))
    A('- At the end of the window: `codePath=%s`, `lastUpdateTime=%s`; the notification service holds %d record(s): the wallet\'s id %s and one %s record (id %s); wallet in front: %s. [after/w24.out]\n'
      % (F['w24_code'], F['w24_update'], len([l for l in w('w24.out').split('\n') if 'NotificationRecord(' in l]), ','.join(F['w24_ids']), F['w24_other'][0], F['w24_other'][1], yn(F['w24_front'])))
    A('- Bench state at %s PST: balance %s MAZA (= %s - %s - %s fee); watch set %s MAZA, %s unspent coins, confirmations [%s]. [after/bench_state_m32.out]\n'
      % (F['bench_pst'], F['bench_bal'], F['state_bal'], F['s5_amt'], F['fee5'], F['bench_watch'], F['bench_utxos'], F['bench_conf']))
    A('### 3.6 Why "one record" proves "no echo"\n')
    A('- From the app\'s source at commit `%s`: `%s`; `%s` - the comment above them reads "%s". The post call is `%s`, the text `%s`. '
      'So the echo would be its own record, id 1; it cannot hide behind the genuine one. [source/source-lines.txt]\n'
      % (F['loop_short'], F['src_bench'], F['src_wallet'], F['src_comment'], F['src_notify'], F['src_text']))
    for d, sfile, cap in (('locked', 'send1.out', 'l1.out'), ('backgrounded', 'send2.out', 'a3.out'), ('denial-not-done', 'send3.out', 'd2.out')):
        rows_ = [o for o in F['old'] if o[0] == d]
        echo = [o for o in rows_ if o[4].endswith('bench account')]
        A('- The previous build, send of %s MAZA at %s PST (11-27): the service held records %s for the app; the host log in the committed capture shows %s. [rn/%s/%s, rn/%s/%s]\n'
          % (rows_[0][1], rows_[0][2], ' and '.join(F['old_ids_' + d]),
             '; '.join('%s "%s" (%d s after)' % (o[3], o[4], o[5]) for o in rows_) +
             ('' if echo else ' - the echo\'s own log line is not in that capture; its record, id 1, is'), d, cap, d, sfile))
    last_check = int((hms(F['m2_end']) - hms(F['s1_post_hms'][:8])).total_seconds())
    A('- So the echo\'s log line was captured in %d of those 3 cases: %s. This build: the dip and the climb happened (0.00000000 at %s, %s at %s) '
      'and the service held id %s only - read in every round of batch 1 from round %s on and in every round of batch 2, the last one ending %d seconds after the send as recorded '
      '(guest clock for the POST, lane clock for the rounds). No record with id 1 appeared in any capture of this window.\n'
      % (len(F['old_echo']), F['old_echo_txt'], F['s1_sync'], '/'.join(','.join(b) for b in F['m1_bals'] if b),
         next(r[5] for r in F['m1_rows'] if r[0] == F['m1_first_post_round']),
         ','.join(','.join(r) for r in F['m2_ids']), F['m1_first_post_round'], last_check))
    A('## 4. What this package does not claim\n')
    A('- It does not claim the previous build\'s echo latency beyond what the rn/ package records, and it does not claim the log count after %s: from %s the record check is the evidence.\n' % (F['m1_end'], F['m2_start']))
    A('- The gap between the two batches (%s to %s) was not watched round by round. An echo in that gap would have left a record with id 1, and none exists afterwards.\n' % (F['m1_end'], F['m2_start']))
    A('- The shade screenshot taken at the end (after/w24_redact.txt) is not evidence of anything: the privacy box covers the cards.\n')
    A('- Three clocks feed this log: the bench host\'s (send times of part A and of the 11-27 sends), the lane\'s (round times) and the guest\'s (the app\'s own log). '
      'No capture in this package compares them, so every "N seconds" figure is as recorded.\n')
    A('- One send on one device. The tracker\'s own limits are covered by the loop\'s tests for commit `%s`, not by this package.\n' % F['loop_short'])
    A('- The M14-ii denial result is for the app\'s master switch on this guest. App-ops `ignore` was shown not to gate delivery on 11-27 (rn/ package).\n')
    A('## 5. Faults met in this window\n')
    A('- The round helper\'s `push` and `pull` handlers drop the first character of their first argument (section 3.2). Not changed in this window: it belongs to the earlier package, which is not committed yet. Use `raw push` until its owner fixes it.\n')
    A('- A UI dump taken right after a tap failed with "%s" in these captures: %s. A second dump a moment later worked each time.\n'
      % (F['w21_err'], ', '.join(F['null_root'])))
    A('- The log (section 3.5): a count read from `logcat -d` is evidence for minutes, not for the whole window.\n')
    A('## 6. Privacy\n')
    A('- This is a public repository. Two captures are host-side (the owner\'s PC): the launch/stop record and the boot error count. They go in as trimmed excerpts of allow-listed lines only (timing/launch-stop.txt); '
      'their memory figures and process lists stay in the lane\'s private archive. No PNG is in the package: the redacted screenshots stay in the lane\'s private archive and the OCR text of three of them is here. '
      'The PIN and the bench token are not in any capture: the PIN is substituted at run time, the token travels only as a header.\n')
    A('- Addresses and transaction ids are test-wallet public data, as in the rn/ package.\n')
    A('## 7. Files\n')
    A('- timing/ launch-stop.txt (trimmed excerpt of two host-side captures), hold_grade.txt (the judge\'s verdict line for the run-log line that opened the window), w26_tasklist.out\n- source/ source-lines.txt (the source lines quoted in this log, read from commit %s with `git show`)\n- boot/ w1-w3 (boot check, app-ops reset, first start), w_token.out (token staged)\n'
      '- unlock/ w4 (PIN unlock, WALLET tab), to_addr.txt (receive address, index %s)\n- switch/ w5-w8, w10, w11 (the switch off, the checks around it, on again), the OCR of the OFF screenshot, w11_switch.txt\n'
      '- denial/ w9_00-w9_21 (baseline and the watch), w9_times.txt, the watcher logs, send4.out, send4_state.out\n'
      '- old-build/ w12-w14 (identity before the update, the two failed pushes), w13_pc_sha.txt\n- apk/ build.out, cmpA.sha, cmpB.sha (the independent rebuild)\n'
      '- install/ w15-w17 (push, install, identity of the installed file)\n- connect/ w18-w19 (reconnect on the new build), w18_token.out, to_addr2.txt (receive address, index %s)\n'
      '- form/ w20-w23 (layout, typing, read-back, screenshot)\n- send/ s1 (the send)\n- watch/ m1_01-m1_12, m2_01-m2_09 (the two watch batches), their times and logs\n'
      '- after/ w24-w25 (final state, kernel and crash lines), bench_state_m32.out\n- scripts/ watch.sh (the watcher), m32_pack.py (this builder)\n- DERIVED.txt, RUNLOG.md, SHA256SUMS\n'       % (F['loop_short'], F['addr6_index'], F['addr7_index']))
    A('Round mechanics: a `.txt` file is the command list (one adb or host command per line), the `.out` file is what the device and the helper printed, the `.sum` file is the round\'s own one-line summary with its exit status. '
      'The round runner is `round.py` in the committed `rn/scripts` set; the PC-side helper `adbrun.ps1` belongs to the earlier package, which is not committed yet.\n')
    A('## 8. Rebuild\n')
    A('On the lane host only: the script reads the raw captures in the lane\'s scratch directory, which is not in the repository.\n')
    A('    python3 m32_pack.py facts   # parses every fact from the captures and prints it; writes nothing\n')
    A('    python3 m32_pack.py build   # rebuilds this package; it refuses to write on any value it cannot parse\n')
    return '\n'.join(L) + '\n'



COPY_GROUPS = [('boot', ['w1', 'w2', 'w3']), ('unlock', ['w4']), ('switch', ['w5', 'w6', 'w7', 'w8', 'w10', 'w11']),
               ('denial', ['w9_%02d' % k for k in range(0, 22)]), ('old-build', ['w12', 'w13', 'w14']),
               ('install', ['w15', 'w16', 'w17']), ('connect', ['w18', 'w19']), ('form', ['w20', 'w21', 'w22', 'w23']),
               ('send', ['s1']), ('watch', ['m1_%02d' % k for k in range(1, 13)] + ['m2_%02d' % k for k in range(1, 10)]),
               ('after', ['w24', 'w25'])]
COPY_SINGLES = ['boot/w_token.out', 'unlock/to_addr.txt', 'switch/w6_redact.txt', 'switch/w6_off_red.ocr.txt', 'switch/w10_redact.txt',
                'switch/w10_shade_red.ocr.txt', 'switch/w11_switch.txt', 'denial/w9_times.txt', 'denial/w9_base.log', 'denial/w9_watch.log',
                'denial/w9_watch2.log', 'denial/send4.out', 'denial/send4_state.out', 'old-build/w13_pc_sha.txt', 'connect/w18_token.out',
                'connect/to_addr2.txt', 'form/w23_redact.txt', 'form/w23_form_red.ocr.txt', 'send/s1_times.txt', 'watch/m1_times.txt',
                'watch/m1_watch.log', 'watch/m2_times.txt', 'watch/m2_watch.log', 'after/w24_redact.txt', 'after/bench_state_m32.out',
                'timing/w26_tasklist.out']
TRIM = {  # dest -> (source, regex of the lines kept)  host-side captures: allow-listed lines only
    'timing/launch-stop.txt': [('w_errcount.txt', r'^(boot launched at: \S+ \S+|now \d\d:\d\d:\d\d|guest error lines this boot: \d+)$'),
                               ('w26_stop.out', r'^\s*(2026-11-28 \S+-0700 .*Player state: ready|falling back to Stop-Process .*|stopped-at: 2026-11-28 \d\d:\d\d:\d\d)$'),
                               ('w26_stop.out', r'^\s*(2026-11-28 \S+-0700 .*Player state : launched with args.*)$')]}


def copy_map():
    m = {}
    for d, rounds in COPY_GROUPS:
        for n in rounds:
            for ext in ('.txt', '.out', '.sum'):
                if os.path.exists(os.path.join(W, n + ext)):
                    m['%s/%s%s' % (d, n, ext)] = os.path.join(W, n + ext)
    for rel in COPY_SINGLES:
        m[rel] = os.path.join(W, os.path.basename(rel))
    for rel, src in (('apk/build.out', X + '/build.out'), ('apk/cmpA.sha', X + '/cmpA.sha'), ('apk/cmpB.sha', X + '/cmpB.sha'),
                     ('scripts/watch.sh', W + '/watch.sh'), ('scripts/m32_pack.py', S + '/m32_pack.py')):
        m[rel] = src
    return m


def build(F):
    staged = {}
    for dest, src in copy_map().items():
        if not os.path.isfile(src):
            raise Fail('source missing: ' + src)
        staged[dest] = open(src, 'rb').read()
    for dest, parts in TRIM.items():
        out = ['# Excerpt of host-side captures (the owner\'s PC). Only the lines matching an allow-list are here;', '# in the order: the boot error count, then the stop record. Full captures: lane private archive.', '']
        for name, pat in parts:
            out.append('## %s' % name)
            for line in w(name).split('\n'):
                if re.match(pat, line):
                    out.append(line[:200])
        staged[dest] = ('\n'.join(out) + '\n').encode('utf-8')
    # the judge's verdict on the run-log line that opened the window: one allow-listed line of a private capture
    verdict = [l for l in rd(S + '/m32/judge_run2.out').split('\n') if re.match(r'^GRADE=\w urn=urn:ump:\w+$', l)]
    if len(verdict) != 1:
        raise Fail('the hold-line verdict is not exactly one line')
    staged['timing/hold_grade.txt'] = ('\n'.join([
        '# Excerpt of a private capture: the stand-in judge\'s stdout for the run-log line that opened this window.',
        '# Only the verdict line is here. Source file sha256: %s' % sha_file(S + '/m32/judge_run2.out'), '',
        verdict[0]]) + '\n').encode('utf-8')
    # the source lines the run log quotes, each read from commit b819df1 and compared with it here
    src = ['# Source lines quoted in RUNLOG.md. Each was read with `git show b819df1:<path>`; line numbers are those of that commit.', '']
    for path in sorted(set(p for p, _, _ in F['src_q'])):
        lines, blob = src_file(path)
        if blob != dict(F['st_files'])[path]:
            raise Fail('%s changed under the build' % path)
        src += ['', '## %s   (sha256 of the file at that commit: %s)' % (path, blob)]
        for no, tx in sorted((n, x) for p, n, x in F['src_q'] if p == path):
            if lines[no - 1].strip() != tx:
                raise Fail('%s line %d is not what the commit holds' % (path, no))
            src.append('%5d  %s' % (no, tx))
    staged['source/source-lines.txt'] = ('\n'.join(src) + '\n').encode('utf-8')
    staged['DERIVED.txt'] = derived(F).encode('utf-8')
    staged['RUNLOG.md'] = runlog(F).encode('utf-8')
    # every value the run log prints must be the parsed value, and every cited package path must exist
    for rel in re.findall(r'\[([^\]]+)\]', staged['RUNLOG.md'].decode('utf-8')):
        for part in rel.split(', '):
            p = part.split(' ')[0]
            if '/' in p and p.split(' ')[0] not in staged and not p.startswith('rn/'):
                raise Fail('run log cites a file that is not in the package: ' + p)
    # PIN scan: in-process, never printed
    sys.path.insert(0, S)
    import pinround  # noqa: E402  (the lane helper; carries no digits)
    pin = pinround.load_pin(os.path.join(REPO, 'android', 'evidence', 's2b-pin', 'unlock-for-p4b.ps1'))
    standalone = re.compile(rb'(?<![\d.:])' + pin.encode() + rb'(?![\d.:])')
    for dest, data in staged.items():
        hits = [m.start() for m in standalone.finditer(data)]
        if hits:
            raise Fail('PIN digits found as a standalone token in %s (%d hits); nothing written' % (dest, len(hits)))
        if dest.endswith(('.txt', '.out', '.py', '.md')) and re.search(rb'input text \d{4}\b', data):
            raise Fail('a literal 4-digit input appears in ' + dest)
    # token scan: sha256 over 32-byte windows against a digest computed on the bench host
    # the bench host prints only a sha256 digest of its token; the token itself never crosses the wire, and the digest is not written anywhere
    remote = open(S + '/m32/tokdigest_remote.py').read()
    import time
    for attempt in range(3):
        r = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'samihost', 'python3', '-'],
                           input=remote.encode(), capture_output=True, timeout=60)
        digest = r.stdout.decode().strip()
        if r.returncode == 0 and re.fullmatch(r'[0-9a-f]{64}', digest):
            break
        time.sleep(5)
    if r.returncode != 0 or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise Fail('token scan unavailable (rc=%d); not building without it' % r.returncode)
    target = bytes.fromhex(digest)
    windows = 0
    for dest, data in staged.items():
        windows += max(0, len(data) - 31)
        for i in range(len(data) - 31):
            if hashlib.sha256(data[i:i + 32]).digest() == target:
                raise Fail('bench token found in ' + dest)
    print('pin scan: clean | token scan: clean (%d windows compared; neither value shown)' % windows)
    if os.path.isdir(DST):                        # only ever replace this builder's own previous output
        if not (os.path.isfile(DST + '/SHA256SUMS') and os.path.isfile(DST + '/scripts/m32_pack.py')):
            raise Fail('refusing to replace a directory this script did not build: ' + DST)
        shutil.rmtree(DST)
    for dest in sorted(staged):
        p = os.path.join(DST, dest)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(staged[dest])
    staged['SHA256SUMS'] = ('\n'.join('%s  %s' % (hashlib.sha256(staged[d]).hexdigest(), d) for d in sorted(staged) if d != 'SHA256SUMS')).encode('utf-8')
    open(DST + '/SHA256SUMS', 'wb').write(staged['SHA256SUMS'])
    r = subprocess.run(['python3', SCANNER, DST], capture_output=True, text=True)
    open(S + '/m32/scan.out', 'w').write(r.stdout + r.stderr)
    print('package: %d files, %d bytes | scanner exit %d | %s' % (len(staged), sum(len(v) for v in staged.values()), r.returncode,
                                                              [l for l in r.stdout.split('\n') if 'findings' in l or 'scanned' in l]))
    if r.returncode != 0:
        raise Fail('the package scanner did not exit 0; see m32/scan.out')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'facts'
    try:
        F = facts()
        if mode == 'facts':
            for k in sorted(F):
                v = F[k]
                print('%s: %s' % (k, v if not isinstance(v, (list, tuple)) or len(str(v)) < 200 else str(v)[:200] + '...'))
        else:
            build(F)
    except Fail as e:
        sys.exit('ABORT, nothing written: %s' % e)
