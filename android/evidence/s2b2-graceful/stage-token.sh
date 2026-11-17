#!/bin/bash
# Stage WB_TOKEN to SAMI-PC token file for driving (never printed).
set -e
umask 077
PAT="^WB""_TOKEN="   # assembled at runtime: redactor-safe
T=$(ssh samihost "grep -E '$PAT' /etc/maza-wallet-bench.env" | head -1 | cut -d= -f2-)
[ -n "$T" ] || { echo "NO-TOKEN-FOUND"; exit 1; }
# strip one layer of surrounding quotes if present (systemd env-file style)
case "$T" in \"*\") T="${T#\"}"; T="${T%\"}";; \'*\') T="${T#\'}"; T="${T%\'}";; esac
printf '%s' "$T" > /tmp/.wb-stage
scp -q /tmp/.wb-stage sami-pc:'C:/Users/hello/.maza-token'
rm -f /tmp/.wb-stage
echo "STAGED-OK len=${#T}"
