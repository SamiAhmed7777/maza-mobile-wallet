#!/usr/bin/env python3
"""Build <wallet repo>/android/evidence/m8b2a/rn/ from the lane scratch dir.

Public-repo safe by construction:
  - explicit copy map: device-side and bench-side captures only. Host-side
    diagnostics (process lists, memory, event logs) are NOT copied.
  - excerpts are line selections from allow-listed patterns, nothing retyped
  - aborts BEFORE writing if a source is missing, if the PIN or the bench
    token appears anywhere in the package, or if a run-log citation cannot be
    located in the staged bytes
  - PIN scan: loaded in-process from the committed s2b-pin script, never
    printed. Token scan: sha256 over 32-byte windows against a digest computed
    on the bench host; the token never leaves that host, the digest is never
    printed.
  - SHA256SUMS; then the package scanner (../scripts/scan-pkg.py) must exit 0
Usage: rn_pack.py   (no arguments)
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys

from PIL import Image

SRC = '/root/.hermes/cache/scratch/m8b2a-rn'
REPO = '/root/maza-mobile-wallet'
DST = REPO + '/android/evidence/m8b2a/rn'
UIDUMP = REPO + '/android/evidence/m8b2a/scripts/uidump.py'

# dest (relative to DST) -> source (name in SRC)
COPY = {
    'gate/ibd_probe_2.out': 'ibd_probe_2.out',
    'context/bench_state_final.out': 'bench_state_final.out',
    'context/n20.txt': 'n20.txt', 'context/n20.out': 'n20.out',
    'context/n21.txt': 'n21.txt', 'context/n21.out': 'n21.out',
    'context/n22.txt': 'n22.txt', 'context/n22.out': 'n22.out',
    'context/n23.txt': 'n23.txt', 'context/n23.out': 'n23.out',
    'context/a1.txt': 'a1.txt', 'context/a1.out': 'a1.out',
    'context/r_a0.txt': 'r_a0.txt', 'context/r_a0.out': 'r_a0.out',
    'locked/n18.txt': 'n18.txt', 'locked/n18.out': 'n18.out',
    'locked/r_rn1.txt': 'r_rn1.txt', 'locked/r_rn1.out': 'r_rn1.out',
    'locked/n24.txt': 'n24.txt', 'locked/n24.out': 'n24.out',
    'locked/send1.out': 'send1.out', 'locked/send1_watch.out': 'send1_watch.out',
    'locked/l1.txt': 'l1.txt', 'locked/l1.out': 'l1.out',
    'locked/l1_locked.png': 'l1_locked.png', 'locked/l1_locked_cover.png': 'l1_locked_cover.png',
    'backgrounded/a2.txt': 'a2.txt', 'backgrounded/a2.out': 'a2.out',
    'backgrounded/a3.txt': 'a3.txt', 'backgrounded/a3.out': 'a3.out',
    'backgrounded/a3_bg.png': 'a3_bg.png',
    'backgrounded/send2.out': 'send2.out', 'backgrounded/send2_watch.out': 'send2_watch.out',
    'denial-not-done/d1.txt': 'd1.txt', 'denial-not-done/d1.out': 'd1.out',
    'denial-not-done/d2.txt': 'd2.txt', 'denial-not-done/d2.out': 'd2.out',
    'denial-not-done/d2_blocked.png': 'd2_blocked.png',
    'denial-not-done/d3.txt': 'd3.txt', 'denial-not-done/d3.out': 'd3.out',
    'denial-not-done/d4.txt': 'd4.txt', 'denial-not-done/d4.out': 'd4.out',
    'denial-not-done/d4b.txt': 'd4b.txt', 'denial-not-done/d4b.out': 'd4b.out',
    'denial-not-done/send3.out': 'send3.out', 'denial-not-done/send3_watch.out': 'send3_watch.out',
    'faults/n0.txt': 'n0.txt', 'faults/n0.out': 'n0.out',
    'faults/n1.txt': 'n1.txt', 'faults/n1.out': 'n1.out',
    'faults/n2.txt': 'n2.txt', 'faults/n2.out': 'n2.out',
    'faults/n9.txt': 'n9.txt', 'faults/n9.out': 'n9.out',
    'faults/n10.txt': 'n10.txt', 'faults/n10.out': 'n10.out',
    'faults/n11.txt': 'n11.txt', 'faults/n11.out': 'n11.out',
    'faults/n13.txt': 'n13.txt', 'faults/n13.out': 'n13.out',
    'faults/n14.txt': 'n14.txt', 'faults/n14.out': 'n14.out',
    'faults/n15.txt': 'n15.txt', 'faults/n15.out': 'n15.out',
    'faults/n17.txt': 'n17.txt', 'faults/n17.out': 'n17.out',
    'faults/stage_token_2.out': 'stage_token_2.out',
    'faults/stage_token_3.out': 'stage_token_3.out',
    'faults/stage_token_4.out': 'stage_token_4.out',
    'scripts/pinround.py': 'pinround.py',
}
# parsed screen listings, made by the committed uidump.py (redacts password-class nodes)
SCREENS = {'context/n20': 'n20.out', 'context/r_a0': 'r_a0.out', 'locked/n24': 'n24.out',
           'denial-not-done/d3': 'd3.out'}
HOST_SOURCES = ['d5diag.out', 'hostdiag3.out', 'hostdiag4.out', 'hostdiag5.out', 'snapshot_poll.out', 'stop.out',
                'bench_state_0.out', 'restart_errcount.out', 'errcount_boot3_final.out', 'memcommit.out']


def die(msg, code=3):
    sys.stderr.write('REFUSED: ' + msg + '\n')
    sys.exit(code)


def lines(name):
    with open(os.path.join(SRC, name), encoding='utf-8', errors='replace') as fh:
        return [l.rstrip('\r\n') for l in fh]


def pick(name, patterns, limit=None):
    out = []
    for l in lines(name):
        if any(re.search(p, l) for p in patterns):
            out.append(l)
            if limit and len(out) >= limit:
                break
    return out


def block_from_last(name, start_pat, keep, drop, must=None):
    """Lines of the LAST block that starts with start_pat and, when must is given,
    holds a line matching it. Keeps the lines matching keep."""
    ls = lines(name)
    starts = [i for i, l in enumerate(ls) if re.search(start_pat, l)]
    for idx in reversed(starts):
        if not must:
            break
        end = next((j for j in range(idx + 1, len(ls)) if re.search(start_pat, ls[j])), len(ls))
        if any(re.search(must, l) for l in ls[idx:end]):
            break
    out = []
    for l in ls[idx:]:
        if re.search(start_pat, l) and out:
            break
        if not re.search(drop, l) and re.search(keep, l):
            out.append(l)
    return out


RATIOS = {}


def mem_ratios():
    def grab(name, pat):
        m = re.search(pat, '\n'.join(lines(name)))
        return [float(x) for x in m.groups()]
    total, free, used, limit = grab('memcommit.out', r'MEM total_GB=([\d.]+) free_GB=([\d.]+) commit_used_GB=([\d.]+) commit_limit_GB=([\d.]+)')
    RATIOS['episode_free'] = free / total
    RATIOS['episode_commit'] = used / limit
    _, _, used2, limit2 = grab('hostdiag5.out', r'MEM now: total_GB=([\d.]+) free_GB=([\d.]+) commit_used_GB=([\d.]+) commit_limit_GB=([\d.]+)')
    RATIOS['off_commit'] = used2 / limit2
    lows = re.findall(r'free_GB=([\d.]+)', '\n'.join(lines('restart_errcount.out')))
    RATIOS['low_free'] = float(min(lows)) / total


EXCERPTS = {}


def build_excerpts():
    # 1. the 22:20 close, from the read-only diagnosis run
    ex = ['# Excerpt of the BlueStacks Player.log lines for the 22:20 close. Line selection by scripts/rn_pack.py',
          '# from the lane diagnosis run of 22:28:55 PST (read-only). The full output is in the private archive.']
    ex += pick('d5diag.out', [r'^== time: '])
    ex += pick('d5diag.out', [r'^2026-11-27 22:20:(18|24|26|27)\.'])
    joined = '\n'.join(ex)
    for n in ['Topbar: Close clicked', 'reason Close_by_user', 'VM is powered off', 'Exiting err: 0']:
        assert n in joined, 'close excerpt lacks: ' + n
    EXCERPTS['denial-not-done/close_by_user_2220.txt'] = ex

    # 2. guest disk errors of boot 1 and the Nov 15-16 precedent (guest kernel lines only)
    ex = ['# Excerpt: guest kernel error lines of boot 1 (launched 20:14:54) and the Nov 15-16 precedent.',
          '# Line selection by scripts/rn_pack.py from the host diagnosis captures (private archive).',
          '## boot 1, 2026-11-27']
    ex += pick('hostdiag3.out', [r'GUEST: \['], limit=22)
    ex += pick('hostdiag3.out', [r'^print_req_error lines this boot',
                                 r'^  first: 2026-11-27 .*print_req_error', r'^  last:  2026-11-27 .*print_req_error',
                                 r'^distinct devices/sectors:', r'^    sd[ab] sector \d+  x\d+',
                                 r'^EXT4 error lines: first / last:', r'^  count=\d+',
                                 r'^  first: 2026-11-27 20:23:18', r'^  last:  2026-11-27 20:36:08',
                                 r'^EXT4 error lines per minute:', r'^  2026-11-27 20:[23]\d  x\d+'])
    ex += ['## Nov 15-16 episode in the same log (precedent)']
    ex += pick('hostdiag4.out', [r'^  error lines on Nov 15-16',
                                 r'^  first: 2026-11-15 .*print_req_error', r'^  last:  2026-11-15 .*print_req_error',
                                 r'^  distinct Nov-15 kernel error shapes', r'^      22  print_req_error'])
    EXCERPTS['faults/guest_disk_errors_boot1.txt'] = ex

    # 3. host event-log answers during the fault window; memory as ratios only
    ex = ['# Excerpt: host event-log answers during the fault window, and memory pressure as ratios.',
          '# Line selection by scripts/rn_pack.py. Memory figures are reduced to ratios (machine privacy).']
    ex += pick('hostdiag5.out', [r'^now 20:51', r'^System\+Application warnings/errors', r'^  none returned',
                                 r'^storage / power / hardware events', r'^low-memory \(Resource-Exhaustion 2004\) events'])
    ex.append('commit charge with the emulator off (20:51): %d%% of the commit limit'
              ' | during the episodes (21:16): %d%% of the commit limit, free memory %d%% of physical'
              ' | lowest free reading of the night (21:19): %d%% of physical' % (
                  round(100 * RATIOS['off_commit']), round(100 * RATIOS['episode_commit']),
                  round(100 * RATIOS['episode_free']), round(100 * RATIOS['low_free'])))
    EXCERPTS['faults/host_events_summary.txt'] = ex

    # 4. disk-image snapshot read-back
    ex = ['# Excerpt: engine disk images read whole and copied before the relaunch (20:42-21:01).',
          '# Line selection by scripts/rn_pack.py. Free-space lines are left out.']
    ex += pick('snapshot_poll.out', [r'^started ', r'^STEP[123] ', r'^finished ', r'^SNAPSHOT-DONE'])
    EXCERPTS['faults/snapshot_readback.txt'] = list(dict.fromkeys(ex))  # the poll repeated step lines

    # 5. BlueStacks program versions
    ex = ['# Excerpt: BlueStacks program files (version, last write) during the fault window.']
    ex += pick('hostdiag4.out', [r'^BlueStacks executables \(version \+ last write\):', r'^  HD-Player\.exe', r'^  BstkSVC\.exe'])
    EXCERPTS['faults/bluestacks_version.txt'] = ex

    # 6. the ADB reboot attempt: last block of the boot-2 counter
    ex = ['# Excerpt: last reading of the boot-2 error counter, taken during the ADB reboot attempt.',
          '# Process and memory lines are left out.']
    ex += block_from_last('restart_errcount.out', r'^now ',
                          r'^(now |boot launched at|player-state lines|guest error lines|guest kernel last line)', r'^(processes|MEM)',
                          must=r'Restarting system with command')
    EXCERPTS['faults/adb_reboot_hang.txt'] = ex

    # 7. boot-2 error counts, all readings
    ex = ['# Boot 2 (launched 21:03:17): every reading of the guest error counter. Process and memory lines are left out.']
    ex += [l for l in lines('restart_errcount.out')
           if re.match(r'^(now |boot launched at|player-state lines|guest error lines|guest kernel last line)', l)]
    EXCERPTS['faults/boot2_error_counts.txt'] = ex

    # 8. boot-3 error count, whole life
    ex = ['# Boot 3 (launched 21:21:52): the guest error counter read after the window was closed, so it covers the whole boot.']
    ex += [l for l in lines('errcount_boot3_final.out')
           if re.match(r'^(now |boot launched at|player-state lines|guest error lines|guest kernel last line)', l)]
    EXCERPTS['faults/boot3_error_counts.txt'] = ex

    # 9. first bench state reading (an unrelated leading line of the capture is left out)
    ex = ['# First bench state reading of the night. Line selection by scripts/rn_pack.py;',
          '# one unrelated leading line of the capture is left out.']
    ex += pick('bench_state_0.out', [r'^\[2026-11-2[78] \d\d:\d\d:\d\d CET\] '])
    assert len(ex) == 4, 'bench_state_0 excerpt shape'
    EXCERPTS['context/bench_state_0.txt'] = ex

    # 10. boot-1 timeline: Player.log lines the stop round quoted, and that round's stop time
    ex = ["# Excerpt: Player.log lines quoted by the lane stop round, and that round's stop time.",
          '# Line selection by scripts/rn_pack.py.']
    ex += pick('stop.out', [r'^  2026-11-27 03:50:02\.\d+.*Exiting err: 0',
                            r'^  2026-11-27 20:14:55\.\d+.*launched with args',
                            r'^  2026-11-27 20:16:03\.\d+.*Player state: ready',
                            r'^  2026-11-27 20:40:58\.\d+.*EXT4-fs error',
                            r'^stopped-at: '])
    assert len(ex) == 7, 'boot1 timeline shape'
    EXCERPTS['faults/boot1_timeline.txt'] = ex

    # 11. every loop tick since the hold line: the decision lines of its output file, and
    #     the entry it wrote to the backlog run log when that output was silent
    #     (locals carry a lt_ prefix so that none shadows a name used elsewhere in this function)
    with open('/root/maza-mobile-backlog.md', encoding='utf-8') as fh:
        lt_bl = fh.read().split('\n')
    lt_hold = next(i for i, l in enumerate(lt_bl) if l.startswith('- 2026-11-27 ~20:1x PST (interactive lane'))
    lt_dir = '/root/.hermes/cron/output/24a7311de928'
    lt_dec = (r'^\*\*Why no item pick:\*\*', r'^- \*\*No repo work\*\*: the interactive lane',
              r'^\*\*Stand-down still engaged:\*\*', r'^Summary of the tick: ', r'^\[SILENT\]$')
    lt_ticks = sorted(f for f in os.listdir(lt_dir) if f.endswith('.md') and f > '2026-11-27_20-10-00.md')
    assert len(lt_ticks) >= 2, 'loop ticks since the hold line'
    ex = ['# Excerpt: every loop tick of loop 24a7311de928 since the hold line (written about 20:10 PST),',
          '# taken at package build time; a tick that lands later is not in here.',
          '# Line selection by scripts/rn_pack.py: from each tick output file, the lines of its own answer',
          '# that state the decision (cut at 700 characters); from the backlog run log, for a tick that',
          '# answered [SILENT], the entry it wrote there (header and next three non-empty lines, cut at 200).']
    for lt_tick in lt_ticks:
        with open(os.path.join(lt_dir, lt_tick), encoding='utf-8', errors='replace') as fh:
            lt_lines = [l.rstrip('\r\n') for l in fh]
        lt_body = lt_lines[len(lt_lines) - 1 - lt_lines[::-1].index('## Response'):]
        lt_got = [l for l in lt_body[1:] if any(re.search(p, l) for p in lt_dec)]
        assert lt_got, 'tick decision line not found: ' + lt_tick
        ex.append('## ' + lt_tick)
        ex.extend(l[:700] for l in lt_got[:2])
        if lt_got[0].strip() == '[SILENT]':
            lt_hour = '~' + lt_tick[11:13] + ':'
            lt_heads = [i for i in range(lt_hold) if lt_bl[i].startswith('- 2026-11-2') and lt_hour in lt_bl[i]
                        and 'MAINTENANCE-ONLY TICK' in lt_bl[i]]
            assert lt_heads, 'no run-log entry for the silent tick ' + lt_tick
            ex.append('backlog run log, line %d:' % (lt_heads[0] + 1))
            lt_shown = 0
            for j in range(lt_heads[0], lt_heads[0] + 8):
                if lt_bl[j].strip():
                    ex.append(lt_bl[j].strip()[:200])
                    lt_shown += 1
                    if lt_shown == 4:
                        break
    EXCERPTS['context/loop_ticks_stood_down.txt'] = ex

    # 12. script exit statuses, one line per round
    ex = ['# Script exit status of every round that kept one (round.py prints this line when it ends).',
          '# A status of 0 means the script ran to its end; it does not mean the device answered.']
    for name in sorted(os.listdir(SRC)):
        if not name.endswith('.sum'):
            continue
        for l in lines(name):
            m = re.match(r'-- round rc=(\d+) (\S+) xml-lines=(\d+)', l)
            if m:
                ex.append('%-6s rc=%s %s xml-lines=%s' % (name[:-4], m.group(1), m.group(2), m.group(3)))
            m = re.match(r'pinround rc=(\d+)', l)
            if m:
                ex.append('%-6s pinround rc=%s (PIN substituted at run time; rendered file and transcript deleted)' % (name[:-4], m.group(1)))
    assert len(ex) > 2, 'no exit statuses found'
    EXCERPTS['exit_statuses.txt'] = ex


RUNLOG = r'''# M8B-II-A evening run: receive-notification check (M14-ii), two of three states done

Evening of 2026-11-27, Pacific time. The package runs from boot 1 at ⟦grab:faults/boot1_timeline.txt::(20:14:55)\.\d+.*launched with args⟧ to a final bench reading at ⟦grab:context/bench_state_final.out::\[(2026-11-28 \d\d:\d\d:\d\d) CET⟧ CET ⟦context/bench_state_final.out::GET /api/state⟧. The bench host prints CET (UTC+1, nine hours ahead).

This package holds device-side and bench-side captures only. Host-side diagnostics (process lists, memory figures, Windows event logs) stay out of this public repo and are archived privately on the lane host. Nothing was edited by hand: each `.out` file is the raw capture of the command file beside it (`.txt`), each `*_screen.txt` is a parsed listing of the screen dump in that capture, each `*.ocr.txt` is unedited machine OCR of the screenshot beside it, and the other excerpt files are line selections made by `scripts/rn_pack.py`.

## Authorization and coordination
- The emulator had been closed by a person on the morning run (powered off at 03:50:02 ⟦faults/boot1_timeline.txt::03:50:02\.\d+.*Exiting err: 0⟧). It was reopened tonight only after the owner's "reopen as needed".
- A hold line was written to the backlog run log before the launch. Every loop tick since then stood down and left the repo alone: ⟦count:context/loop_ticks_stood_down.txt::^## 2026-⟧ ticks are captured in context/loop_ticks_stood_down.txt, from ⟦grab:context/loop_ticks_stood_down.txt::^## (2026-11-27_20-39-25)⟧ on, each with its decision line ⟦context/loop_ticks_stood_down.txt::Stand-down still engaged⟧. A tick that lands later is not captured here.

## What happened to the emulator (PST)
- Boot 1 ready at ⟦grab:faults/boot1_timeline.txt::(20:16:03)\.\d+.*Player state: ready⟧ ⟦faults/boot1_timeline.txt::Player state: ready⟧.
- ⟦grab:faults/guest_disk_errors_boot1.txt::first: 2026-11-27 (20:19:07)\.\d+⟧ first guest block error, ⟦grab:faults/guest_disk_errors_boot1.txt::\[ *(\d+\.\d+)\] print_req_error: I/O error, dev sdb, sector 252312408⟧ s into the boot: `I/O error, dev sdb, sector 252312408` ⟦faults/guest_disk_errors_boot1.txt::20:19:07\.329.*dev sdb, sector 252312408⟧.
- ⟦grab:faults/guest_disk_errors_boot1.txt::(20:23:12)\.\d+.*dev sda, sector 9152456⟧ `sda` starts failing too ⟦faults/guest_disk_errors_boot1.txt::20:23:12\.912.*dev sda, sector 9152456⟧.
- From ⟦grab:faults/guest_disk_errors_boot1.txt::first: 2026-11-27 (20:23:18)\.\d+⟧ the filesystem logs ext4 errors: ⟦grab:faults/guest_disk_errors_boot1.txt::  count=(\d+)⟧ lines up to ⟦grab:faults/guest_disk_errors_boot1.txt::last:  2026-11-27 (20:36:08)\.\d+⟧ ⟦faults/guest_disk_errors_boot1.txt::EXT4 error lines: first / last:⟧, peaking at ⟦grab:faults/guest_disk_errors_boot1.txt::  2026-11-27 20:34  x(\d+)⟧ a minute ⟦faults/guest_disk_errors_boot1.txt::EXT4 error lines per minute:⟧. The last log line before the stop names the partition: `EXT4-fs error (device sda1)` ⟦faults/boot1_timeline.txt::EXT4-fs error⟧.
- The guest shell then fails. `pm` itself returns `/system/bin/cmd: I/O error` ⟦faults/n0.out::/system/bin/cmd: I/O error⟧. In the next round `exec '/system/bin/sh' failed: I/O error` on ⟦count:faults/n1.out::exec '/system/bin/sh' failed⟧ of its ⟦count:faults/n1.txt::^shell ⟧ commands ⟦faults/n1.out::exec '/system/bin/sh' failed::1⟧; in the retries after that, ⟦count:faults/n2.out::exec '/system/bin/sh' failed⟧ of ⟦count:faults/n2.txt::^shell ⟧ ⟦faults/n2.out::exec '/system/bin/sh' failed::1⟧.
- ⟦grab:faults/boot1_timeline.txt::stopped-at: 2026-11-27 (20:41:08)⟧ instance stopped ⟦faults/boot1_timeline.txt::^stopped-at:⟧. No repair of any kind. The host diagnosis was read-only: no warnings or errors during the fault window ⟦faults/host_events_summary.txt::none returned::1⟧ and no storage, power or hardware events in the prior 48 h ⟦faults/host_events_summary.txt::none returned::2⟧. BlueStacks had not changed: program files dated ⟦grab:faults/bluestacks_version.txt::HD-Player\.exe  (\d{4}-\d\d-\d\d)⟧ ⟦faults/bluestacks_version.txt::HD-Player\.exe⟧.
- ⟦grab:faults/snapshot_readback.txt::^started (2026-11-27 20:42:43)⟧ to ⟦grab:faults/snapshot_readback.txt::^finished (2026-11-27 21:01:19)⟧ ⟦faults/snapshot_readback.txt::^finished ⟧ both engine disk images were read whole ⟦faults/snapshot_readback.txt::STEP1 Root\.vhd::1⟧ ⟦faults/snapshot_readback.txt::STEP1 Data\.vhdx::1⟧, copied, and the copies read back identical ⟦faults/snapshot_readback.txt::STEP3 Data\.vhdx::1⟧. Two starts are on record, the second at ⟦grab:faults/snapshot_readback.txt::^started (2026-11-27 20:48:35)⟧. The copy is kept on the host until the owner decides.
- ⟦grab:faults/boot2_error_counts.txt::boot launched at: 2026-11-27 (21:03:17)⟧ relaunch, boot 2 ⟦faults/boot2_error_counts.txt::boot launched at: 2026-11-27 21:03:17⟧: zero guest error lines at every reading from ⟦grab:faults/boot2_error_counts.txt::^now (21:04:45)⟧ to ⟦grab:faults/boot2_error_counts.txt::^now (21:20:57)⟧ ⟦faults/boot2_error_counts.txt::guest error lines this boot: 0⟧. Boot 1's first error had come 244.9 s in ⟦faults/guest_disk_errors_boot1.txt::first: 2026-11-27 20:19:07.*\[ *244\.9⟧.
- ⟦grab:faults/n9.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*#3 unlock ok⟧ the app unlocks (`POST /api/unlock -> 200`, `unlock ok`) ⟦faults/n9.out::#3 unlock ok⟧ and at ⟦grab:faults/n9.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*Fatal signal 6⟧ dies with `Fatal signal 6 (SIGABRT)` in `RenderThread` ⟦faults/n9.out::Fatal signal 6⟧.
- ⟦grab:faults/n11.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*Fatal signal 6⟧ the same abort after an app relaunch (two of two). The renderer logs `Impossible totalDuration 0` ⟦faults/n11.out::Impossible totalDuration 0⟧ and the process aborts ⟦faults/n11.out::Fatal signal 6 \(SIGABRT\)⟧.
- One ADB `reboot` was then tried. The guest kernel log stops at `reboot: Restarting system with command 'adb'` ⟦faults/adb_reboot_hang.txt::Restarting system with command⟧, and the device answers `offline` ⟦faults/n13.out::emulator-5554\toffline⟧ ⟦faults/n13.out::error: device offline⟧.
- The instance was stopped and launched again: boot 3, launched ⟦grab:faults/boot3_error_counts.txt::boot launched at: 2026-11-27 (\d\d:\d\d:\d\d)⟧ ⟦faults/boot3_error_counts.txt::boot launched at: 2026-11-27 21:21:52⟧. Zero guest error lines for its whole life: ⟦grab:faults/boot3_error_counts.txt::log lines since launch: (\d+)⟧ log lines, powered down ⟦grab:faults/boot3_error_counts.txt::\[ *(\d+\.\d+)\] reboot: Power down⟧ s in ⟦faults/boot3_error_counts.txt::guest error lines this boot: 0⟧ ⟦faults/boot3_error_counts.txt::Power down⟧. A search of the app's log for `Fatal` and `totalDuration` returns nothing ⟦faults/n17.out::tail -4⟧.
- ⟦grab:denial-not-done/close_by_user_2220.txt::2026-11-27 (\d\d:\d\d:\d\d)\.\d+.*Topbar: Close clicked⟧ a person closed the window: `Topbar: Close clicked` ⟦denial-not-done/close_by_user_2220.txt::Topbar: Close clicked⟧, then `reason Close_by_user` ⟦denial-not-done/close_by_user_2220.txt::Close_by_user⟧, clean power-down at ⟦grab:denial-not-done/close_by_user_2220.txt::2026-11-27 (\d\d:\d\d:\d\d)\.\d+.*VM is powered off⟧ ⟦denial-not-done/close_by_user_2220.txt::VM is powered off⟧.
- Not reopened. Every device command after that failed with `device 'emulator-5554' not found`: ⟦count:denial-not-done/d4.out::not found⟧ of ⟦count:denial-not-done/d4.txt::^shell ⟧ commands, at script exit status 0 ⟦exit_statuses.txt::^d4 ⟧.

Memory pressure was present in every episode: commit charge about ⟦grab:faults/host_events_summary.txt::during the episodes \(21:16\): (\d+)%⟧% of the commit limit during the episodes and about ⟦grab:faults/host_events_summary.txt::emulator off \(20:51\): (\d+)%⟧% with the emulator off ⟦faults/host_events_summary.txt::commit charge with the emulator off⟧ (ratios only; figures in the private archive).

Root cause of the disk fault and of the renderer abort: not determined (see Open questions).

## The check
The app polls every 15 s while locked and while backgrounded, and announces a receive on a strict increase of a watched balance between two consecutive samples. Each state needs its own confirmed send to the wallet's self-custody receive address, which is in the app's watch set.

- Gate, bench node synced: ⟦gate/ibd_probe_2.out::chain=main⟧, block count ⟦grab:gate/ibd_probe_2.out::blocks=(\d+)⟧ and header count ⟦grab:gate/ibd_probe_2.out::headers=(\d+)⟧, ⟦gate/ibd_probe_2.out::initialblockdownload=⟧. The probe ran on the bench host.
- The poll runs while locked, with the lock cover in front. In the State 1 capture the log holds a full cycle at ⟦grab:locked/l1.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*#418 GET /api/state⟧ ⟦locked/l1.out::#418 GET /api/state⟧, then unspent coins ⟦locked/l1.out::#419 GET /api/watch/utxos⟧ and history ⟦locked/l1.out::#420 GET /api/watch/history⟧, and the screenshots taken seconds later in the same round show `Wallet locked` locked/l1_locked_cover.ocr.txt:5 with the wallet the resumed activity ⟦locked/l1.out::mResumedActivity.*com\.mazawallet⟧. Two earlier cycles, at ⟦grab:locked/r_rn1.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*#198 GET /api/state⟧ ⟦locked/r_rn1.out::#198 GET /api/state⟧ and at ⟦grab:locked/r_rn1.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*#201 GET /api/state⟧ ⟦locked/r_rn1.out::#201 GET /api/state⟧, were read as the first step of a round that then typed the PIN and pressed UNLOCK ⟦locked/r_rn1.txt::input tap 800 496⟧. No screen was captured before that unlock, so the lock state at those two times rests on the app's own rule (it locks after an inactivity window and on return from background, `android/src/com/mazawallet/crypto/LockPolicy.java`) and not on a screen.
- The poll runs while backgrounded: cycle at ⟦grab:context/n22.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*#319 GET /api/watch/utxos⟧ ⟦context/n22.out::21:53:08\.\d+ .*#319 GET /api/watch/utxos⟧.
- Starting balances: bench account `mobile-play` ⟦grab:context/bench_state_0.txt::balance=(\d+\.\d+) account=mobile-play⟧ MAZA ⟦context/bench_state_0.txt::GET /api/state⟧; watch set ⟦grab:context/bench_state_0.txt::watch set: balance=(\d\.\d{4})⟧ MAZA in ⟦grab:context/bench_state_0.txt::utxos=(\d) confirmations⟧ coin ⟦context/bench_state_0.txt::watch set: balance=⟧, shown on the wallet's own screen at receive address ⟦grab:context/n20_screen.txt::(index \d)⟧ ⟦context/n20_screen.txt::index 4⟧.

### State 1, locked: PASS
- Send 1: ⟦grab:locked/send1.out::amount=(\d+\.\d+)⟧ MAZA at ⟦grab:locked/send1.out::\[(\S+ \S+) CET\] POST /api/send⟧ CET, HTTP ⟦grab:locked/send1.out::HTTP (\d+)⟧ ⟦locked/send1.out::POST /api/send⟧.
- Watch set ⟦grab:locked/send1_watch.out::try 3: \[[^\]]*\] watch set: balance=(\d\.\d{4})⟧ at ⟦grab:locked/send1_watch.out::^(21:59:52) try⟧ ⟦locked/send1_watch.out::21:59:52.*balance=1\.4999⟧, then ⟦grab:locked/send1_watch.out::try 4: \[[^\]]*\] watch set: balance=(\d\.\d{4})⟧ at ⟦grab:locked/send1_watch.out::^(22:00:11) try⟧ ⟦locked/send1_watch.out::22:00:11.*balance=1\.9999⟧: the coin confirmed.
- Posted at ⟦grab:locked/l1.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*hcallOnAppNotificationReceivedRpc.*\+0\.50000000⟧: `MAZA received`, `+0.50000000 MAZA - self-custody wallet` ⟦locked/l1.out::hcallOnAppNotificationReceivedRpc.*\+0\.50000000 MAZA - self-custody wallet⟧. The wallet was the resumed activity, on its lock cover ⟦locked/l1.out::mResumedActivity.*com\.mazawallet⟧.
- `l1_locked.png` (shade over the lock cover; OCR ⟦locked/l1_locked.ocr.txt::\+0\.50000000 MAZA - self-custody wallet⟧), `l1_locked_cover.png` (cover alone, OCR ⟦locked/l1_locked_cover.ocr.txt::Wallet locked⟧). Commands: ⟦locked/l1.txt::expand-notifications⟧.
- The same shade holds a second wallet notification, `+46.49977740 MAZA - bench account`, and nothing was sent to the bench account. See Defect ⟦locked/l1_locked.ocr.txt::\+46\.49977740 MAZA - bench account⟧.

### State 2, backgrounded: PASS
- Unlocked, then Android Settings put on top: the wallet's activity is paused at ⟦grab:backgrounded/a2.out::^(?:11-27 )(\d\d:\d\d:\d\d\.\d+) .*am_on_paused_called.*com\.mazawallet⟧ ⟦backgrounded/a2.out::22:08:31\.964.*am_on_paused_called.*com\.mazawallet⟧, Settings is the resumed activity ⟦backgrounded/a2.out::mResumedActivity.*com\.android\.settings⟧, the process is alive ⟦backgrounded/a2.out::^5011$⟧, and a full poll cycle runs at ⟦grab:backgrounded/a2.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*#528 GET /api/state⟧ ⟦backgrounded/a2.out::22:09:06\.\d+ .*#528 GET /api/state⟧ through ⟦backgrounded/a2.out::22:09:07\.\d+ .*#530 GET /api/watch/history⟧.
- Send 2: ⟦grab:backgrounded/send2.out::amount=(\d+\.\d+)⟧ MAZA at ⟦grab:backgrounded/send2.out::\[(\S+ \S+) CET\] POST /api/send⟧ CET ⟦backgrounded/send2.out::POST /api/send⟧, to the app's current receive address. The app had moved past the used address: ⟦context/r_a0_screen.txt::moved past a used address⟧.
- Watch set still ⟦grab:backgrounded/send2_watch.out::try 3: \[[^\]]*\] watch set: balance=(\d\.\d{4})⟧ at ⟦grab:backgrounded/send2_watch.out::^(22:11:12) try⟧ ⟦backgrounded/send2_watch.out::22:11:12.*balance=1\.9999⟧, then ⟦grab:backgrounded/send2_watch.out::try 4: \[[^\]]*\] watch set: balance=(\d\.\d{4})⟧ at ⟦grab:backgrounded/send2_watch.out::^(22:11:31) try⟧ ⟦backgrounded/send2_watch.out::22:11:31.*balance=2\.1999⟧, so the advanced address is watched too.
- Posted at ⟦grab:backgrounded/a3.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*hcallOnAppNotificationReceivedRpc.*\+0\.20000000⟧ while paused: `+0.20000000 MAZA - self-custody wallet` ⟦backgrounded/a3.out::hcallOnAppNotificationReceivedRpc.*\+0\.20000000⟧. The last activity events are the wallet's pause at ⟦grab:backgrounded/a3.out::^(?:11-27 )(\d\d:\d\d:\d\d\.\d+) .*am_on_paused_called⟧ ⟦backgrounded/a3.out::22:08:31\.964.*am_on_paused_called⟧ and Settings resuming at ⟦grab:backgrounded/a3.out::^(?:11-27 )(\d\d:\d\d:\d\d\.\d+) .*am_on_resume_called.*settings⟧ ⟦backgrounded/a3.out::22:08:32\.243.*am_on_resume_called⟧; nothing for the wallet follows.
- After the shade was opened and closed, Settings is still the resumed activity ⟦backgrounded/a3.out::mResumedActivity.*com\.android\.settings::2⟧ and the wallet is still the background process ⟦backgrounded/a3.out::Proc # 0: prev.*com\.mazawallet/.*\(previous\)⟧.
- `a3_bg.png`: shade over Settings, no wallet screen behind it. OCR ⟦backgrounded/a3_bg.ocr.txt::\+0\.20000000 MAZA - self-custody wallet⟧.

### State 3, notifications denied: NOT DONE
- Switch used: `cmd appops set com.mazawallet POST_NOTIFICATION ignore` ⟦denial-not-done/d1.txt::appops set⟧, read back as `POST_NOTIFICATION: ignore` before the send ⟦denial-not-done/d1.out::POST_NOTIFICATION: ignore⟧ and after it ⟦denial-not-done/d2.out::POST_NOTIFICATION: ignore⟧.
- Send 3: ⟦grab:denial-not-done/send3.out::amount=(\d+\.\d+)⟧ MAZA at ⟦grab:denial-not-done/send3.out::\[(\S+ \S+) CET\] POST /api/send⟧ CET ⟦denial-not-done/send3.out::POST /api/send⟧. Watch set still ⟦grab:denial-not-done/send3_watch.out::try 6: \[[^\]]*\] watch set: balance=(\d\.\d{4})⟧ at ⟦grab:denial-not-done/send3_watch.out::^(22:16:28) try⟧ ⟦denial-not-done/send3_watch.out::22:16:28.*balance=2\.1999⟧, then ⟦grab:denial-not-done/send3_watch.out::try 7: \[[^\]]*\] watch set: balance=(\d\.\d{4})⟧ at ⟦grab:denial-not-done/send3_watch.out::^(22:16:46) try⟧ ⟦denial-not-done/send3_watch.out::22:16:46.*balance=2\.2999⟧.
- The notification was posted anyway, at ⟦grab:denial-not-done/d2.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*hcallOnAppNotificationReceivedRpc.*\+0\.10000000⟧: `+0.10000000 MAZA - self-custody wallet` ⟦denial-not-done/d2.out::hcallOnAppNotificationReceivedRpc.*\+0\.10000000⟧. On this Android 9 guest that switch does not gate delivery, so this round is a non-result: neither a pass nor a fail of the denial path.
- The system's own per-app switch is Settings, Apps, MAZA Wallet, Notifications, "Show notifications" - not yet exercised here. That screen was opened in the round after ⟦denial-not-done/d3.txt::APP_NOTIFICATION_SETTINGS⟧; the switch is `ON` ⟦denial-not-done/d3_screen.txt::Switch .* ON \| switch_widget⟧. It was never flipped: the window was closed ⟦denial-not-done/close_by_user_2220.txt::Topbar: Close clicked⟧ before the next round could reach the device ⟦denial-not-done/d4.out::\[e\] error::1⟧.
- Still to do: switch it off, send a fourth distinct amount, show no notification and the wallet unaffected, switch it back on.

## Defect: the app announces its own change as a receive
Every bench send produced a second notification:
- Send 1, locked: `+46.49977740 MAZA - bench account`, read off the shade screenshot by OCR ⟦locked/l1_locked.ocr.txt::\+46\.49977740 MAZA - bench account⟧. The capture lists two wallet notification records ⟦locked/l1.out::pkg=com\.mazawallet .* id=2⟧ ⟦locked/l1.out::pkg=com\.mazawallet .* id=1⟧, but the system dump redacts their bodies ⟦locked/l1.out::android\.text=String⟧, and its log excerpt was cut to four lines, which dropped the hook line of the bench post.
- Send 2, backgrounded: `+46.29967740 MAZA - bench account` ⟦backgrounded/a3.out::\+46\.29967740 MAZA - bench account⟧, posted at ⟦grab:backgrounded/a3.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*bench account⟧. The shade screenshot reads the same ⟦backgrounded/a3_bg.ocr.txt::\+46\.29967740 MAZA - bench account⟧.
- Send 3, notifications switched off: `+46.19957740 MAZA - bench account` ⟦denial-not-done/d2.out::\+46\.19957740 MAZA - bench account⟧, posted at ⟦grab:denial-not-done/d2.out::^(?:11-27 )(\d\d:\d\d:\d\d)\.\d+ .*bench account⟧ ⟦denial-not-done/d2_blocked.ocr.txt::\+46\.19957740 MAZA - bench account⟧.

Three of three. Each is the change of that send, and the balances read before the sends give it to the digit. Before send 2: ⟦grab:backgrounded/send2.out::before: bench balance=(\d+\.\d+)⟧ ⟦backgrounded/send2.out::before: bench balance=46\.4997774⟧. Before send 3: ⟦grab:denial-not-done/send3.out::before: bench balance=(\d+\.\d+)⟧ ⟦denial-not-done/send3.out::before: bench balance=46\.2996774⟧. The difference is send 2's ⟦grab:backgrounded/send2.out::amount=(\d+\.\d+)⟧ MAZA plus a fee of 0.0001. Cause:
- The balance the app samples is the confirmed-unspent sum ⟦code:walletbench/api.py::listunspent_for\(addrs\)::809⟧, and the node call keeps coins with at least one confirmation ⟦code:walletbench/chain.py::minconf: int = 1::115⟧.
- A send spends the largest coin whole ⟦code:walletbench/chain.py::sorted\(utxos, key=lambda u: -float::142⟧ and pays the change to a freshly derived address ⟦code:walletbench/api.py::change_addr = self\._new_change_address\(\)::890⟧ ⟦code:walletbench/api.py::change = self\.chain\.getnewaddress\(\)::349⟧; the change is the total minus amount minus fee ⟦code:walletbench/chain.py::change = round\(total - amount - FLAT_FEE, 8\)::151⟧.
- So the account's reported balance drops to zero and comes back lower. The zero is captured: `GET /api/state -> 200 balance=0` ⟦backgrounded/send2.out::GET /api/state -> 200 balance=0⟧ at ⟦grab:backgrounded/send2.out::\[(\S+ \d\d:\d\d:\d\d) CET\] GET /api/state -> 200 balance=0⟧ CET, the send having gone out at ⟦grab:backgrounded/send2.out::\[(\S+ \d\d:\d\d:\d\d) CET\] POST /api/send⟧ CET; the same after send 3 ⟦denial-not-done/send3.out::GET /api/state -> 200 balance=0⟧.
- The app fires on any strict increase between two samples ⟦code:android/src/com/mazawallet/crypto/NotifyPolicy.java::newSats > prevSats::56⟧, so the change confirming looks like a receive.

The wallet's own self-custody send path probably has the same shape; it was not exercised tonight. Proposed as backlog item M32. The fix needs its own lane, with tests and a gate.

## State left behind
- Bench: ⟦grab:context/bench_state_final.out::watch set: balance=(\d\.\d{4}) utxos=(\d)⟧ MAZA in the wallet's self-custody watch set, against ⟦grab:context/bench_state_0.txt::watch set: balance=(\d\.\d{4})⟧ before, out of the bench account, plus the fees. Bench account at the final reading ⟦grab:context/bench_state_final.out::balance=(\d+\.\d+) account=mobile-play⟧ ⟦context/bench_state_final.out::balance=46\.1995774⟧.
- Guest: the app-ops entry `POST_NOTIFICATION: ignore` for `com.mazawallet` was left set (last read ⟦denial-not-done/d2.out::POST_NOTIFICATION: ignore⟧). It had no observed effect. Its reset never ran: the shell rejected `appops reset`, and the `set ... default` came when the device was already gone ⟦denial-not-done/d4.out::\[e\] error::1⟧. Whether it survived the power-down is unchecked. Reset it at the next launch and read it back.
- Guest: the wallet's "Show notifications" switch is unchanged ⟦denial-not-done/d3_screen.txt::Switch .* ON \| switch_widget⟧.
- Host: the disk-image copy is kept until the owner decides.
- Bench host: the send helper stays in the private lane directory for the remaining send.

## Lessons, each verified tonight
1. `round.py` writes its raw capture to `<cmds>.out` and also prints a copy of each line to its own stdout, cut at 240 characters and without the XML lines (`scripts/round.py`, the loop after the capture is written). Redirecting that stdout onto the capture path overwrites the first part of the raw capture with the printed copy. `locked/n18.out` was taken that way and is spoiled: two end markers ⟦locked/n18.out::^## ROUND-DONE⟧ ⟦locked/n18.out::^## ROUND-DONE::2⟧, the script's summary line inside the capture ⟦locked/n18.out::^-- round rc=⟧, the first screen dump's output missing where its command stands ⟦locked/n18.out::cat /sdcard/ui.xml⟧, and after the summary the tail of the raw capture, the same commands again ⟦locked/n18.out::input tap 1440 858::2⟧. The HISTORY tab reading of that round is not in the file. stdout goes to a `.sum` file.
2. A round's exit status 0 means the script ran, not that the device answered ⟦exit_statuses.txt::^d4 ⟧. Read the capture for `[e]` lines ⟦denial-not-done/d4.out::\[e\] error::1⟧.
3. Opening the shade over the BlueStacks launcher dismisses the launcher and brings the previous app back: launcher paused at ⟦grab:context/n23.out::^(?:11-27 )(21:52:28\.\d+) .*HomeActivity,performPause⟧ ⟦context/n23.out::21:52:28\.983.*HomeActivity,performPause⟧, wallet resumed at ⟦grab:context/n23.out::^(?:11-27 )(21:52:28\.\d+) .*am_set_resumed_activity.*com\.mazawallet⟧ ⟦context/n23.out::21:52:28\.990.*am_set_resumed_activity.*com\.mazawallet⟧. Use Android Settings as the cover app for backgrounded captures.
4. ADB `reboot` parks this instance ⟦faults/adb_reboot_hang.txt::Restarting system with command⟧. Use stop and launch.
5. After the renderer abort an app relaunch does not help ⟦faults/n10.txt::am start⟧: the abort recurs ⟦faults/n11.out::Fatal signal 6⟧. A full instance restart cleared it ⟦faults/n17.out::tail -4⟧.
6. `cmd appops set ... POST_NOTIFICATION ignore` does not block notifications on this guest ⟦denial-not-done/d2.out::POST_NOTIFICATION: ignore⟧ ⟦denial-not-done/d2.out::\+0\.10000000 MAZA - self-custody wallet⟧.
7. An empty `pidof` ⟦context/a1.txt::pidof⟧ with no log lines ⟦context/a1.txt::logcat⟧ was a capture glitch, not a kill: the next round shows the process alive ⟦context/n21.out::^5011$⟧.
8. A log excerpt cut to the last four matching lines dropped the hook line of a second post one second older ⟦locked/l1.txt::tail -4⟧. When two posts are expected, take a wider excerpt.

## Open questions
- Disk fault. The host disk images read whole ⟦faults/snapshot_readback.txt::STEP1 Root\.vhd::1⟧ ⟦faults/snapshot_readback.txt::STEP1 Data\.vhdx::1⟧, Windows logged no storage or hardware events ⟦faults/host_events_summary.txt::none returned::2⟧, and BlueStacks was unchanged ⟦faults/bluestacks_version.txt::HD-Player\.exe⟧. Memory pressure was present in every episode ⟦faults/host_events_summary.txt::commit charge with the emulator off⟧. The same error shape is in this log from Nov 15 and 16 ⟦faults/guest_disk_errors_boot1.txt::error lines on Nov 15-16: 22⟧ ⟦faults/guest_disk_errors_boot1.txt::2026-11-15 23:47:01.*dev sda, sector 8391736⟧.
- Renderer abort. Two of two on boot 2 ⟦faults/n11.out::Fatal signal 6 \(SIGABRT\)⟧, gone after a full instance restart ⟦faults/n17.out::tail -4⟧; the memory readings of that boot are the tightest of the night ⟦faults/host_events_summary.txt::lowest free reading of the night⟧.
- Denial state: pending one short emulator window, by the owner's leave.

## Files
- `gate/`, `context/`, `locked/`, `backgrounded/`, `denial-not-done/`, `faults/`: captures (`.txt` command file, `.out` raw capture, `.png` screenshot) and excerpts.
- `*_screen.txt`: parsed listings of the screen dumps, made by `scripts/uidump.py`, which redacts password-class nodes.
- `*.ocr.txt`: unedited machine OCR (tesseract) of the screenshot of the same name.
- `exit_statuses.txt`: script exit status per round.
- `scripts/pinround.py`: runs a command file holding the `[PIN]` placeholder; the PIN is substituted at run time from the committed `s2b-pin` script, and the rendered file and transcript are deleted.
- `scripts/rn_pack.py`: built this package (copy map, excerpt rules, PIN and token scans, citation check).
- `scripts/round.py`, `scripts/uidump.py`: byte-exact copies of the round runner and the screen-dump parser from the earlier package (`android/evidence/m8b2a/scripts/`), the two tools this package's captures went through.
- The package scanner this package was checked with (`scan-pkg.py`, in the same earlier package) stays outside it: it carries the secret-shaped patterns it searches for.
- `SHA256SUMS`: every file in this package.
'''

CIT = re.compile(r'⟦(count:|code:|grab:)?([^⟧]+?)⟧')


def main():
    for s in list(COPY.values()) + HOST_SOURCES + [n for n in SCREENS.values()] + ['pinround.py', 'rn_pack.py']:
        if not os.path.isfile(os.path.join(SRC, s)):
            die('missing source: ' + s)
    assert DST == REPO + '/android/evidence/m8b2a/rn'
    mem_ratios()
    build_excerpts()

    # stage everything in memory first; scan; only then write
    staged = {}
    for dest, src in COPY.items():
        with open(os.path.join(SRC, src), 'rb') as fh:
            staged[dest] = fh.read()
    for dest, ls in EXCERPTS.items():
        staged[dest] = ('\n'.join(ls) + '\n').encode('utf-8')
    for dest, src in SCREENS.items():
        r = subprocess.run([sys.executable, UIDUMP, os.path.join(SRC, src)], capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not r.stdout.strip():
            die('screen listing failed for ' + src + ': ' + r.stderr.strip()[:200])
        staged[dest + '_screen.txt'] = ('# parsed from %s by scripts/uidump.py\n' % src + r.stdout).encode('utf-8')
    tv = subprocess.run(['tesseract', '--version'], capture_output=True, text=True, timeout=30).stdout.split()[1]
    for dest in [d for d in COPY if d.endswith('.png')]:
        data = staged[dest]
        im = Image.open(io.BytesIO(data)).convert('L')
        im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
        tmp = os.path.join(SRC, '.ocr-tmp.png')
        im.save(tmp)
        try:
            r = subprocess.run(['tesseract', tmp, 'stdout', '--psm', '6'], capture_output=True, text=True, timeout=120)
        finally:
            os.unlink(tmp)
        if r.returncode != 0 or not r.stdout.strip():
            die('OCR failed for ' + dest)
        staged[dest[:-4] + '.ocr.txt'] = (
            '# OCR of %s (sha256 %s): tesseract %s, --psm 6, on a 2x grayscale upscale. Unedited machine output.\n'
            % (os.path.basename(dest), hashlib.sha256(data).hexdigest(), tv)).encode('utf-8') + r.stdout.encode('utf-8')
    for name in ('pinround.py', 'rn_pack.py'):
        with open(os.path.join(SRC, name), 'rb') as fh:
            staged['scripts/' + name] = fh.read()
    # the round runner and the screen-dump parser the captures went through:
    # byte-exact copies of the earlier package's scripts, so the run log cites
    # files that are inside this package
    for name in ('round.py', 'uidump.py'):
        with open(os.path.join(os.path.dirname(UIDUMP), name), 'rb') as fh:
            staged['scripts/' + name] = fh.read()

    # PIN scan: in-process, never printed. A PIN typed as a command is a standalone
    # 4-digit token; digits inside longer numbers, times or amounts are not that.
    sys.path.insert(0, SRC)
    import pinround  # noqa: E402  (the lane helper; carries no digits)
    pin = pinround.load_pin(os.path.join(REPO, 'android', 'evidence', 's2b-pin', 'unlock-for-p4b.ps1'))
    standalone = re.compile(rb'(?<![\d.:])' + pin.encode() + rb'(?![\d.:])')
    for dest, data in staged.items():
        hits = [m.start() for m in standalone.finditer(data)]
        if hits:
            die('PIN digits found as a standalone token in %s (%d hits); nothing written' % (dest, len(hits)))
        if dest.endswith(('.txt', '.out', '.py', '.md')) and re.search(rb'input text \d{4}\b', data):
            die('a literal 4-digit input appears in ' + dest)

    # token scan: sha256 over 32-byte windows against a digest computed on the bench host
    key = 'WB_' + 'TOKEN'
    remote = ("import hashlib,re\n"
              "v=None\n"
              "for l in open('/etc/maza-wallet-bench.env'):\n"
              "    if l.startswith(%r + '='):\n"
              "        v=l.rstrip('\\r\\n')[len(%r) + 1:].strip('\\\"\\'')\n"
              "print(hashlib.sha256(v.encode()).hexdigest() if v else 'NO-TOKEN')\n" % (key, key))
    import time
    for attempt in range(3):  # a dropped connection is retried; a scan that never ran still refuses
        r = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'samihost', 'python3', '-'],
                           input=remote.encode(), capture_output=True, timeout=60)
        digest = r.stdout.decode().strip()
        if r.returncode == 0 and re.fullmatch(r'[0-9a-f]{64}', digest):
            break
        time.sleep(5)
    if r.returncode != 0 or not re.fullmatch(r'[0-9a-f]{64}', digest):
        die('token scan unavailable (rc=%d); not building without it' % r.returncode)
    target = bytes.fromhex(digest)
    windows = 0
    for dest, data in staged.items():
        windows += max(0, len(data) - 31)
        for i in range(len(data) - 31):
            if hashlib.sha256(data[i:i + 32]).digest() == target:
                die('bench token found in ' + dest)
    print('pin scan: clean | token scan: clean (%d windows compared; neither value shown)' % windows)

    # run-log citations are resolved against the staged bytes
    log = RUNLOG
    unresolved = []

    def resolve(m):
        kind, body = m.group(1), m.group(2)
        parts = body.split('::')
        if kind == 'code:':
            path, pat, ln = parts[0], parts[1], int(parts[2])
            with open(os.path.join(REPO, path), encoding='utf-8') as fh:
                text = fh.read().split('\n')
            if re.search(pat, text[ln - 1]):
                return '%s:%d' % (path, ln)
            unresolved.append(body)
            return '??'
        path, pat = parts[0], parts[1]
        nth = int(parts[2]) if len(parts) > 2 else 1
        text = staged[path].decode('utf-8', errors='replace').split('\n')
        hits = [i + 1 for i, l in enumerate(text) if re.search(pat, l)]
        if kind == 'count:':
            return str(len(hits))
        if kind == 'grab:':
            if len(hits) >= nth:
                return re.search(pat, text[hits[nth - 1] - 1]).group(1)
            unresolved.append(body)
            return '??'
        if len(hits) >= nth:
            return '%s:%d' % (path, hits[nth - 1])
        unresolved.append(body)
        return '??'

    log = CIT.sub(resolve, log)
    if unresolved:
        print('UNRESOLVED CITATIONS (%d):' % len(unresolved))
        for u in unresolved:
            print('  ', u)
        die('run log has citations that cannot be located; nothing written')

    staged['RUNLOG.md'] = log.encode('utf-8')
    staged['SHA256SUMS'] = ('\n'.join('%s  %s' % (hashlib.sha256(staged[d]).hexdigest(), d)
                                      for d in sorted(staged)) + '\n').encode('utf-8')
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    for dest, data in staged.items():
        p = os.path.join(DST, dest)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as fh:
            fh.write(data)
    print('package written: %d files, %d bytes -> %s' % (len(staged), sum(len(v) for v in staged.values()), DST))
    print('run log: %d chars, %d citations, sha256 %s' % (
        len(log), len(CIT.findall(RUNLOG)), hashlib.sha256(staged['RUNLOG.md']).hexdigest()))
    for dest in sorted(staged):
        print('  %7d  %s' % (len(staged[dest]), dest))


if __name__ == '__main__':
    main()
