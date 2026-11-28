#!/bin/bash
# M8b2a lane: fetch the live WB_TOKEN from samihost and pipe it over ssh STDIN to token.ps1 on SAMI-PC.
# Never echoed, never in argv, never written to disk on this host. Prints length + character class only.
set -u
PAT="^WB""_TOKEN="
T=$(ssh -o BatchMode=yes -o ConnectTimeout=20 samihost "grep -E '$PAT' /etc/maza-wallet-bench.env" | head -1 | cut -d= -f2-)
[ -n "$T" ] || { echo "NO-TOKEN-FOUND"; exit 1; }
case "$T" in \"*\") T="${T#\"}"; T="${T%\"}";; \'*\') T="${T#\'}"; T="${T%\'}";; esac
[ -n "$T" ] || { echo "EMPTY-AFTER-UNQUOTE"; exit 1; }
if printf '%s' "$T" | grep -qE '^[A-Za-z0-9_-]+$'; then CLASS=safe; else CLASS=NEEDS-ESCAPING; fi
echo "TOKEN len=${#T} class=$CLASS"
[ "$CLASS" = safe ] || { echo "STOP: token needs shell escaping - not typing it"; exit 1; }
printf '%s\n' "$T" | ssh -o BatchMode=yes -o ConnectTimeout=25 sami-pc 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\hello\maza-bench-lane\token.ps1' 2>&1 | tr -d '\r\000'
rc=${PIPESTATUS[1]}
unset T
echo "token.ps1 rc=$rc"
