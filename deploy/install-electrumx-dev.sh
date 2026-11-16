#!/usr/bin/env bash
# Install electrumx at the PINNED commit into a venv (dist name: e-x).
#
# Usage:  bash deploy/install-electrumx-dev.sh [dest-dir] [venv-python]
#   dest-dir   checkout location (default: third_party/electrumx, gitignored)
#   venv-python interpreter to install with (default: python3)
#
# The pin is enforced: after checkout, HEAD must equal the pin or the script
# refuses. PyPI `electrumx` (1.20.2, altcoin-stripped) is NOT acceptable.
set -euo pipefail

PIN="ee28cd8ddcc61019d78880ad59582b9b4ce3cc99"
DEST="${1:-third_party/electrumx}"
PYBIN="${2:-python3}"

if [ ! -d "$DEST/.git" ]; then
  mkdir -p "$(dirname "$DEST")"
  git clone https://github.com/spesmilo/electrumx "$DEST"
fi

git -C "$DEST" fetch origin master --quiet
git -C "$DEST" checkout --quiet "$PIN"

ACTUAL="$(git -C "$DEST" rev-parse HEAD)"
if [ "$ACTUAL" != "$PIN" ]; then
  echo "REFUSING to install: checkout HEAD $ACTUAL != pin $PIN" >&2
  exit 1
fi

"$PYBIN" -m pip install -e "$DEST"

# Post-install fingerprint check (must match tests' expectations).
"$PYBIN" - <<'EOF'
from importlib.metadata import version
import electrumx.lib.tx as lib_tx
import electrumx.lib.coins as coins
import electrumx.lib.util as util
assert version("e-x") == "2.0.1", f"unexpected e-x dist: {version('e-x')}"
assert hasattr(lib_tx, "DeserializerSegWit"), "DeserializerSegWit missing"
n = len(util.subclasses(coins.Coin))
assert n > 100, f"coin registry too small ({n}) — stale/PyPI build?"
print(f"electrumx pinned tree OK: e-x {version('e-x')}, {n} coin classes")
EOF
