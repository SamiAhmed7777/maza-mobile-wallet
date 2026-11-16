# POLISH-FOLD — M5 round-3 grade B (urn:ump:i47snqui7cgt2bvj3ipxppc362mocd7hvtjcmbgtiwwk7yurjlnq)

The r3 verdict was a CLEAN B (zero blocking issues, three polish_suggestions).
Per the multi-round protocol the polish is folded into the same commit. This
file documents shipped-vs-graded honesty:

## GRADED BYTES — untouched by the fold (hashes re-verified at fold time)

- android/build-apk.sh      9a7a7a2400bd8ecb2f5c18593ba0bb91830a5e13c4a856f857d1eb707d42ca89
  (= build-transcript.txt input anchor, unchanged)
- android/release.properties de11640a30066eb56587a56f974cfc72ed4769e39001d125277567640a9a8ea3
  (= build-transcript.txt input anchor, unchanged)
- android/releases/maza-wallet-v1.0.0.apk d30a48a9b6ccf04708d51b7494ccebff3d88aafe97e2bad894afd299f4bd1b77
  (= the pinned APK sha, unchanged; not committed — gitignored, attached to
  the judge worktree as the 11_ index-prefixed copy)

## EVIDENCE FILES — changed after grading (fold content)

1. verify-battery.txt — REGENERATED IN FULL. The r3 judge's polish found the
   round's file truncated at 15 lines (ended mid-battery at the
   "apksigner verify --verbose" heading). Root cause identified honestly: the
   generation pipeline was `{…} | tee file | head -12` — head exited after 12
   display lines and SIGPIPE killed tee mid-write, truncating the FILE too
   (the display had shown more earlier in the session from the r2 run).
   Regenerated with direct `> file` capture (no downstream consumer), against
   the SAME immutable APK — every command re-run, EXIT codes captured:
   badging versionCode='2'/versionName='1.0.0'/sdk 24/34, zipalign ALIGNED OK
   exit 0, apksigner v2+v3 true, print-certs = keystore fingerprint, final
   sha256 = pinned d30a48a9…. 35 lines, complete.
2. secret-scan.txt — sha-consistency counts now SCOPE-STATED: 5 occurrences
   of the pinned APK sha within .txt evidence transcripts (the regenerated
   verify-battery added one), plus separate counts for the non-txt artifacts
   (PROOF.md, the judge brief). The r3 text said "4" with an implicit
   narrower scope — corrected per the judge's polish.
3. PROOF.md — wording updates only: scoped sha-occurrence counts, the
   worktree index-renaming note (the judge worktree prefixes --files entries
   0_…N_; the APK was referenced as 0_ in the brief but delivered as 11_ —
   basenames are what identify files), and a pointer to this POLISH-FOLD.md.

No code, config, or binary artifact changed after grading. The claim set is
unchanged; the evidence files now show exactly what was always claimed.
