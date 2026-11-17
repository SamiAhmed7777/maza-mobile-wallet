#!/usr/bin/env bash
# Install electrumx at the PINNED commit into a venv (dist name: e-x).
#
# Usage:  bash deploy/install-electrumx-dev.sh [dest-dir] [venv-python]
#   dest-dir   checkout location (default: third_party/electrumx, gitignored)
#   venv-python interpreter to install with (default: python3)
#
# The pin is enforced: after checkout, HEAD must equal the pin or the script
# refuses. PyPI `electrumx` (1.20.2, altcoin-stripped) is NOT acceptable.
# The pinned tree (pyproject.toml at the pin) declares requires-python
# = ">=3.10" and ships NO database backend — serving with DB_ENGINE=leveldb
# needs the `leveldb` extra (plyvel), which this script installs and then
# verifies by import before reporting success.
set -euo pipefail

PIN="ee28cd8ddcc61019d78880ad59582b9b4ce3cc99"
DEST="${1:-third_party/electrumx}"
PYBIN="${2:-python3}"

# Distinguish a MISSING interpreter from an OLD one (a missing python3 must
# not be reported as "too old").
if ! command -v "$PYBIN" >/dev/null 2>&1; then
  echo "FATAL: interpreter '$PYBIN' not found — pass the venv python as the" >&2
  echo "2nd argument: bash deploy/install-electrumx-dev.sh <dest-dir> <venv-python>" >&2
  exit 1
fi

# Python floor of the pinned tree: pyproject.toml at the pin declares
# requires-python = ">=3.10". Fail clearly BEFORE any checkout/install.
if ! "$PYBIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "REFUSING to install: $PYBIN is older than Python 3.10 — the pinned" >&2
  echo "electrumx tree declares requires-python = \">=3.10\" (pyproject.toml" >&2
  echo "at the pin). Point venv-python at a >=3.10 interpreter and retry." >&2
  exit 1
fi

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

# The pinned tree ships NO database backend (pyproject.toml at the pin:
# base dependencies are aiorpcx + aiohttp only; `leveldb = ["plyvel"]` is
# an optional extra and the upstream comment says the user MUST install at
# least one). We serve DB_ENGINE=leveldb, so install the leveldb extra.
# plyvel BUILDS against the LevelDB C library — if this pip step fails,
# install the system build prerequisites first (same list as the guide's
# Step 3), then re-run:
#   Debian/Ubuntu: apt-get install -y libleveldb-dev build-essential python3-dev python3-venv
#   Fedora:        dnf install -y leveldb-devel gcc-c++ python3-devel
#   Alpine:        apk add leveldb-dev g++ python3-dev
#   macOS:         brew install leveldb
"$PYBIN" -m pip install -e "$DEST[leveldb]"

# Post-install fingerprint check (must match tests' expectations).
"$PYBIN" - <<'EOF'
from importlib.metadata import PackageNotFoundError, version
import electrumx.lib.tx as lib_tx
import electrumx.lib.coins as coins
import electrumx.lib.util as util
try:
    dist = version("e-x")
except PackageNotFoundError:
    raise SystemExit(
        "unexpected e-x dist: an electrumx IS importable but NOT installed "
        "under the name 'e-x' — this is the stale PyPI build, not the "
        "pinned git tree. Reinstall via deploy/install-electrumx-dev.sh."
    )
assert dist == "2.0.1", f"unexpected e-x dist: {dist}"
assert hasattr(lib_tx, "DeserializerSegWit"), "DeserializerSegWit missing"
n = len(util.subclasses(coins.Coin))
assert n > 100, f"coin registry too small ({n}) — stale/PyPI build?"
try:
    import plyvel  # noqa: F401 — the leveldb extra; DB_ENGINE=leveldb needs it
except ImportError as exc:
    raise SystemExit(
        "plyvel is not importable — the leveldb DB backend is missing. "
        "Install the LevelDB C headers (see the comment above the pip step "
        "in deploy/install-electrumx-dev.sh) and re-run the installer."
    ) from exc
print(f"electrumx pinned tree OK: e-x {dist}, {n} coin classes, "
      f"plyvel importable")
EOF
