#!/usr/bin/env bash
# End-to-end verification of the LIVE MAZA wallet bench API.
#
# Usage:  WB_TOKEN=... bash verify_backend.sh
#         (or export WB_TOKEN_FILE=/path/to/tokenfile)
# Never prints the token. Exits non-zero if any check fails.
set -uo pipefail

BASE="${WB_BASE:-http://100.121.150.22:18701}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- token (never echoed) -----------------------------------------------------
TOK="${WB_TOKEN:-}"
if [ -z "$TOK" ] && [ -n "${WB_TOKEN_FILE:-}" ] && [ -f "${WB_TOKEN_FILE}" ]; then
  TOK="$(tr -d '\r\n' < "$WB_TOKEN_FILE")"
fi
if [ -z "$TOK" ]; then
  echo "FATAL: no token (set WB_TOKEN or WB_TOKEN_FILE)" >&2
  exit 2
fi
echo "token: applied (${#TOK} chars, value withheld)"

FAILED=0
declare -a RESULTS=()

# check <name> <pass:0|1> <detail>
check() {
  local name="$1" ok="$2" detail="$3"
  if [ "$ok" -eq 1 ]; then
    RESULTS+=("PASS  $name  [$detail]")
  else
    RESULTS+=("FAIL  $name  [$detail]")
    FAILED=$((FAILED + 1))
  fi
}

# http <method> <path> [authmode] [json-body]
#   authmode: bearer | query | none
#   echoes "<status>" and leaves body in $WORK/body, headers in $WORK/hdrs
http() {
  local method="$1" path="$2" auth="${3:-none}" body="${4:-}"
  local url="$BASE$path"
  local -a args=(-sS -m 20 -o "$WORK/body" -D "$WORK/hdrs" -X "$method")
  case "$auth" in
    bearer) args+=(-H "Authorization: Bearer $TOK") ;;
    query)  url="$BASE$path?t=$TOK" ;;
  esac
  if [ -n "$body" ]; then
    args+=(-H "Content-Type: application/json" --data "$body")
  fi
  curl "${args[@]}" "$url" -w '%{http_code}' 2>/dev/null
}

ct() { grep -i '^content-type:' "$WORK/hdrs" | tr -d '\r' | sed 's/.*: *//'; }

echo "=== MAZA wallet bench E2E verification ==="
echo "base: $BASE"
echo

# --- (a) unlock ---------------------------------------------------------------
ST="$(http POST /api/unlock none "{\"token\":\"$TOK\"}")"
B="$(cat "$WORK/body" 2>/dev/null)"
if [ "$ST" = "200" ] && grep -qi 'Set-Cookie:' "$WORK/hdrs" \
   && echo "$B" | jq -e '.ok == true' >/dev/null 2>&1; then
  check "a) POST /api/unlock -> 200 + ok:true + Set-Cookie" 1 "status=$ST body=$B cookie=yes"
else
  check "a) POST /api/unlock -> 200 + ok:true + Set-Cookie" 0 "status=$ST body=$B"
fi

# unlock must reject a wrong token (sanity: proves compare is real)
ST_BAD="$(http POST /api/unlock none '{"token":"definitely-not-the-token-000000"}')"
if [ "$ST_BAD" = "401" ]; then
  check "a2) POST /api/unlock bad token -> 401" 1 "status=$ST_BAD"
else
  check "a2) POST /api/unlock bad token -> 401" 0 "status=$ST_BAD"
fi

# --- (b) state with Bearer ----------------------------------------------------
ST="$(http GET /api/state bearer)"
B="$(cat "$WORK/body" 2>/dev/null)"
ADDR="$(echo "$B" | jq -r '.address // empty' 2>/dev/null)"
BAL="$(echo "$B" | jq -r '.balance // empty' 2>/dev/null)"
BAL_OK=$(awk -v b="$BAL" 'BEGIN{ d=b-48.9999; if (d<0) d=-d; print (d < 0.0002) ? 1 : 0 }' 2>/dev/null)
[ -z "$BAL_OK" ] && BAL_OK=0
ADDR_OK=0
case "$ADDR" in M*) ADDR_OK=1 ;; esac
if [ "$ST" = "200" ] && [ "$BAL_OK" = "1" ] && [ "$ADDR_OK" = "1" ]; then
  check "b) GET /api/state (Bearer) -> 200, balance ~= 48.9999, address starts M" 1 \
        "status=$ST balance=$BAL address=$ADDR"
else
  check "b) GET /api/state (Bearer) -> 200, balance ~= 48.9999, address starts M" 0 \
        "status=$ST balance=$BAL address=$ADDR"
fi
echo "$B" > "$WORK/state.json"

# state without any credential must be locked
ST="$(http GET /api/state none)"
if [ "$ST" = "401" ]; then
  check "b2) GET /api/state (no creds) -> 401 locked" 1 "status=$ST"
else
  check "b2) GET /api/state (no creds) -> 401 locked" 0 "status=$ST"
fi

# --- (c) qr.png with Bearer ---------------------------------------------------
ST="$(http GET /api/qr.png bearer)"
CT="$(ct)"
MAGIC="$(od -An -tx1 -N8 "$WORK/body" 2>/dev/null | tr -d ' \n')"
if [ "$ST" = "200" ] && echo "$CT" | grep -qi 'image/png' \
   && [ "$MAGIC" = "89504e470d0a1a0a" ]; then
  check "c) GET /api/qr.png (Bearer) -> 200 image/png + PNG magic" 1 \
        "status=$ST type=$CT magic=$MAGIC bytes=$(stat -c%s "$WORK/body")"
else
  check "c) GET /api/qr.png (Bearer) -> 200 image/png + PNG magic" 0 \
        "status=$ST type=$CT magic=$MAGIC"
fi

# --- (d) query-string auth removed -------------------------------------------
ST="$(http GET /api/state query)"
B="$(cat "$WORK/body" 2>/dev/null)"
if [ "$ST" = "401" ]; then
  check "d) GET /api/state?t=<token> -> 401 (query auth removed)" 1 "status=$ST body=$B"
else
  check "d) GET /api/state?t=<token> -> 401 (query auth removed)" 0 "status=$ST body=$B"
fi

# --- (e) send with invalid address -------------------------------------------
ST="$(http POST /api/send bearer '{"to":"NOT-A-VALID-MAZA-ADDRESS","amount":1}')"
B="$(cat "$WORK/body" 2>/dev/null)"
if [ "$ST" = "400" ] && echo "$B" | jq -e '.error' >/dev/null 2>&1; then
  check "e) POST /api/send invalid address -> 400" 1 "status=$ST body=$B"
else
  check "e) POST /api/send invalid address -> 400" 0 "status=$ST body=$B"
fi

# --- (f) send over the 50 MAZA cap -------------------------------------------
ST="$(http POST /api/send bearer '{"to":"NOT-A-VALID-MAZA-ADDRESS","amount":999}')"
B="$(cat "$WORK/body" 2>/dev/null)"
if [ "$ST" = "400" ] && echo "$B" | grep -qi 'cap'; then
  check "f) POST /api/send amount 999 -> 400 (50 MAZA cap)" 1 "status=$ST body=$B"
else
  check "f) POST /api/send amount 999 -> 400 (50 MAZA cap)" 0 "status=$ST body=$B"
fi

# --- (g) send negative amount ------------------------------------------------
ST="$(http POST /api/send bearer '{"to":"NOT-A-VALID-MAZA-ADDRESS","amount":-1}')"
B="$(cat "$WORK/body" 2>/dev/null)"
if [ "$ST" = "400" ] && echo "$B" | grep -qi 'positive'; then
  check "g) POST /api/send amount -1 -> 400 (amount must be positive)" 1 "status=$ST body=$B"
else
  check "g) POST /api/send amount -1 -> 400 (amount must be positive)" 0 "status=$ST body=$B"
fi

# --- extra: send requires auth ----------------------------------------------
ST="$(http POST /api/send none '{"to":"NOT-A-VALID-MAZA-ADDRESS","amount":1}')"
if [ "$ST" = "401" ]; then
  check "h) POST /api/send (no creds) -> 401" 1 "status=$ST"
else
  check "h) POST /api/send (no creds) -> 401" 0 "status=$ST"
fi

echo
printf '%s\n' "${RESULTS[@]}"
echo
TOTAL=${#RESULTS[@]}
echo "SUMMARY: $((TOTAL - FAILED))/$TOTAL passed, $FAILED failed"
if [ -s "$WORK/state.json" ]; then
  echo "state snapshot: $(jq -c '{balance,address,account,fee,tx_count:(.txs|length)}' "$WORK/state.json" 2>/dev/null)"
fi
[ "$FAILED" -eq 0 ] || exit 1
exit 0
