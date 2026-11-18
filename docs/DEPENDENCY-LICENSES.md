# Dependency & licensing report (S-7)

Item S-7 of `docs/SPEC-AUDIT.md`; discharges the inventory duty of RULE 8 in
`docs/SPEC.md` ("Review all third-party dependencies and their licenses before
incorporation"). Re-runnability, stated per evidence class: **(a) repo-local**
checks (greps/sha256 over this checkout) re-run anywhere with this checkout;
**(b) public-endpoint** checks need network access and cite their endpoint +
captured output; **(c) host-environment** checks read toolchain files whose
paths are given verbatim and are meaningful only on a host that has the JDK /
Android SDK / pinned-electrumx tree installed (the attached battery transcript
was produced on the DNS2 dev host). The dependency-resolution capture input
ships in this commit (`deploy/requirements-deploy.in`), so the section-4
capture command is checkout-contained (requires uv + network).

Layers (the duty applies per layer, not to the repo as one blob):

| Layer | What ships where |
|---|---|
| APK runtime | code + data inside `maza-wallet-bench.apk` — the artifact users install |
| Server runtime | `walletbench/` service deployed on the bench host |
| Operator instruments | `tools/oracle.py`, `tools/txverify.py` — operator host only, never shipped |
| ElectrumX kit | `indexer/` + `deploy/` (M18 community kit; the APK does not depend on it) |
| Build toolchain | produces the APK, not shipped inside it |

## 1. APK runtime — first-party code + ONE vendored library

All first-party Java sources live in `android/src/com/mazawallet/**` (every
`.java` in that tree is `com.mazawallet` code).
Every import in that tree is an Android platform or JDK package, plus
`org.json`, which is part of the Android platform framework (`android.jar`,
provided by the device OS — not bundled by this repo; the AOSP implementation
of that package is Apache-2.0, stated here as platform convention and not
separately verified per-package in this report).

```
grep -rhE '^import ' android/src --include='*.java' | sort -u \
  | grep -vE '^import (java|android|javax|com\.mazawallet)\.'
```

Output (the ONLY imports beyond platform/JDK/first-party):

```
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
```

`android/build-apk.sh` compiles first-party sources with javac and packages
platform resources plus the ONE vendored JAR below.

**Vendored library (adopted 2026-11-17, M8a):** `android/vendor/zxing-core-3.5.3.jar`
— the zxing QR-code DECODING core (`com.google.zxing:core` 3.5.3), pure Java,
**Apache-2.0**. Needed for M8 (QR camera scan): the item's other candidates
are incompatible with this build (CameraX is AndroidX; zxing-embedded
requires AppCompat — this app is platform-APIs only). Provenance and the
content census live in `android/vendor/NOTICE.txt`; the full Apache-2.0
license text is vendored at `android/vendor/LICENSE-zxing.txt` (the jar
itself carries no license file).

```
sha256sum android/vendor/zxing-core-3.5.3.jar
```
```
8d8064c1636fdaef7189dd9055c7d59950a8940a12f2293956446ec3c109fd82
```

Integrity is enforced by the build: `android/build-apk.sh` refuses to run
(fail-loud, before any packaging stage) unless the jar's sha256 matches the
committed pin `android/vendor/zxing-core-3.5.3.jar.sha256`. Upstream provenance:
Maven Central `com/google/zxing/core/3.5.3`, upstream `.sha1`
`ca1349214a356cd7958651b2d5a0e1f3811a9c4b` matched at fetch (2026-11-17);
tests/test_scan_origin_contract.py re-verifies the pin files against the
shipped bytes and the jar content census.

**Adoption honesty (updated M8b, 2026-11-17):** M8b code half one now WIRES
the import — `android/src/com/mazawallet/QrScanner.java` is the only
zxing-consuming class (MultiFormatReader, QR-only hints, PlanarYUVLuminanceSource,
HybridBinarizer; decode in memory, nothing fetched/opened/stored). The M8a
scope shipped the dependency + its supply-chain fence + the scan-origin
policy (`android/src/com/mazawallet/crypto/ScanOrigin.java`:
scanned payload text may only ever become a validated MAZA address; URLs
and foreign schemes are never fetched or opened; since M9 `maza:`
payment-URI parameters parse through `crypto/MazaUri.java` (official
desktop port, DECISIONS D14) with the address re-validated by the same
send-path contract and nothing ever fetched or opened).

**Vendored data (not code):** `android/res/raw/bip39_english.txt` — the BIP39
English wordlist, 2048 words, data-only:

```
sha256sum android/res/raw/bip39_english.txt
```
```
2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda
```

Provenance — byte-identical (same sha256) to both public distribution points:

```
curl -s https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt        | sha256sum
curl -s https://raw.githubusercontent.com/trezor/python-mnemonic/master/src/mnemonic/wordlist/english.txt | sha256sum
```
```
2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda
2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda
```

Upstream revisions of that byte stream (evidence class (b) — GitHub commits
API, a public endpoint — fetched 2026-11-16; the fetch URLs are the moving
master branches and the recorded commit shas are the provenance anchors):

```
curl -s 'https://api.github.com/repos/bitcoin/bips/commits?path=bip-0039/english.txt&per_page=1'
curl -s 'https://api.github.com/repos/trezor/python-mnemonic/commits?path=src/mnemonic/wordlist/english.txt&per_page=1'
```
```
bips:   ce1862ac6bcffa1dd20aad858380e51e66e949ea  2014-02-07 "Added bip39 english wordlist" (origin; unchanged since)
trezor: f5697ffc75547e0f2982b4f43dbd7f8810d09abd  2021-07-27 "chore: reorganize top-level directory" (a move, not a content change)
```

License posture (stated only as far as the evidence goes): the wordlist is
preexisting canonical BIP39 spec data; **this report does not claim the data
is "MIT licensed" in the copyright sense, and no per-file license grant
exists in either distribution repository.** The verified facts are:
(a) byte-identity to both distribution points at the revisions pinned above
(repo-local sha256 + class (b) upstream fetch); (b) repository-level license detection
(`curl -s https://api.github.com/repos/<repo>/license` — bitcoin/bips: no
license file detected, spdx `None`; trezor/python-mnemonic: spdx `MIT`, root
file `LICENSE`), i.e. the reference-implementation repository distributes its
tree — including the wordlist copy — under its repo-wide MIT license;
(c) our copy stays sha-pinned to that byte stream, which is the integrity
mechanism (the file carries no header by design; adding one would break
byte-identity with upstream). If a formal grant determination for the data
itself is wanted, that is an owner decision — recorded as open in the run
log, not decided here. **Correction:** `docs/SPEC-AUDIT.md` previously wrote
"Trezor CC0" — that identifier is not supported by any license file this
inventory could find; it is corrected to the posture above in the same
commit as this report (rows "9 dependency & licensing report" and "RULE 8").

## 2. Server runtime (walletbench) — Python stdlib + one vendored MIT file

Import scan over `walletbench/*.py` (first-party modules `.config`, `.chain`,
`.qr` excluded from the third-party question):

```
grep -rhE '^(import |from )' walletbench/*.py | sed 's/ as .*//' | sort -u
```
```
from . import config
from . import config, qr
from .chain import FLAT_FEE, ChainError, get_chain
from .vendor import qrcodegen
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from typing import Any, Dict, List, Optional, Tuple
from typing import List
import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
```

Everything is Python stdlib except `walletbench/vendor/qrcodegen.py` — the
Nayuki QR Code generator library, vendored WITH its license header in-file:

```
head -4 walletbench/vendor/qrcodegen.py
```
```
#
# QR Code generator library (Python)
#
# Copyright (c) Project Nayuki. (MIT License)
```

The vendored file itself imports only stdlib (`collections`, `itertools`,
`re`, `collections.abc`, `typing` — verified by the same grep on the file).
`requirements-dev.txt` is explicitly marked "Development/test dependencies
(NOT runtime — the repo core is stdlib-only)". The service has **no
pip-installed runtime dependency**.

## 3. Operator instruments (tools/) — python-ecdsa, operator host only

`tools/oracle.py` and `tools/txverify.py` import `ecdsa` (python-ecdsa;
0.19.2 in the dev environment). Upstream license text
(`tlsfuzzer/python-ecdsa`, file `LICENSE`):

> "python-ecdsa" Copyright (c) 2010 Brian Warner
>
> Portions written in 2005 by Peter Pearson and placed in the public domain.
>
> Permission is hereby granted, free of charge, ... (standard MIT grant text)

GitHub SPDX detection: `NOASSERTION` (the file is a custom MIT-style text
with public-domain portions, not the verbatim MIT template). Treat as
MIT-style with the quoted grant. These tools run on the operator host for
verification only — they are not part of the APK and not part of the
walletbench service runtime.

## 4. ElectrumX community kit (indexer/ + deploy/)

Not an APK dependency; relevant because the kit is installed by strangers
following `docs/electrumx/README.md`.

**Scope of this review:** the table covers BOTH (i) the DIRECT declared
dependencies of the pinned tree — read from the pinned checkout's
`pyproject.toml` at the pin (evidence class (c): host-environment; the
local tree `/root/electrumx-src` is at the commit, battery check 16): `dependencies =
["aiorpcx[ws]>=0.25.0,<0.26", "aiohttp>=3.3,<4"]` — plus plyvel/LevelDB from
the `[leveldb]` extra, AND (ii) the FULL RESOLVED CLOSURE captured at report
time (resolution table below; battery check 37 mechanically verifies every
declared/extra dep is covered, and checks 41-43 pin the captured
constraints file). Only the ElectrumX SOURCE COMMIT is pinned by the
installer; its declared dependencies are version RANGES (`aiorpcx
>=0.25,<0.26`, `aiohttp >=3.3,<4`, `websockets >=14.0` via the ws extra) and
plyvel is unbounded UPSTREAM — the captured constraints file pins all of
them (plyvel 1.5.1 included), and the kit installer passes that file to pip
(`-c`), so a deploy built through the documented install path ON THE
CAPTURED TARGET (Python 3.12) repeats the same runtime dependency
resolution, including the leveldb extra. Scope limits, stated plainly: the
capture pins runtime dependency VERSIONS only — it carries no hashes and
does not pin build-isolation/build dependencies — and only the Python 3.12
target is captured. On any OTHER supported interpreter the installer prints
a loud WARNING and installs WITHOUT constraints (their resolution is NOT
the capture — this report does not claim it is). A deploy built WITHOUT
the constraints file resolves the ranges loosely on the target host.

| Component | Version constraint | License | Evidence |
|---|---|---|---|
| electrumx | git `ee28cd8ddcc61019d78880ad59582b9b4ce3cc99` (requirements-dev.txt; the pinned-enforcing installer refuses drift) — the ONLY commit-pinned element | MIT | local tree at that commit: `LICENCE` = "Copyright (c) 2016-2020, Neil Booth / Copyright (c) 2020-2026, The Electrum developers"; pyproject header `license = "MIT"`; GitHub license detection: MIT |
| aiorpcX | `>=0.25.0,<0.26` + `ws` extra (direct declared dep; also imported by `indexer/run_indexer.py`'s wiring check) | MIT | `kyuupichan/aiorpcX` file `LICENCE` = "Copyright (c) 2018 Neil Booth"; GitHub license detection: MIT |
| aiohttp | `>=3.3,<4` (direct declared dep of electrumx) | Apache-2.0 | GitHub license detection: `aio-libs/aiohttp` spdx Apache-2.0, file `LICENSE.txt` |
| websockets | `>=14.0` (pulled by aiorpcX's `ws` extra) | BSD-3-Clause | GitHub license detection: `python-websockets/websockets` spdx BSD-3-Clause, file `LICENSE` |
| plyvel | installed via the `[leveldb]` extra (needs system `libleveldb-dev`); pinned to 1.5.1 by the constraints capture | BSD License | PyPI metadata: `pypi.org/pypi/plyvel/json` → `info.license: "BSD License"` |
| LevelDB | the C++ library behind plyvel | BSD-style | `google/leveldb` `LICENSE`: "Copyright (c) 2011 The LevelDB Authors" + 3-clause-style redistribution grant |
| systemd / Docker / docker-compose / nginx / Caddy | deployment platform | platform terms | environment components, not code dependencies of this repo |

**Captured resolution — the full closure** (evidence classes (a)+(c), fetched
2026-11-16, dev host, Python 3.12 target, resolved WITHOUT installing and
shipped as the constraints file `deploy/requirements-resolved-py312.txt`):

```
uv pip compile deploy/requirements-deploy.in -o resolved-deploy.txt --python-version 3.12
#   (run from the checkout root; the input file ships in this commit)
#   deploy/requirements-deploy.in: e-x[leveldb] @ git+https://github.com/spesmilo/electrumx@ee28cd8d...
#   the committed constraints file = that output MINUS the e-x self-line
#   (electrumx itself is deliberately NOT constrained: the installer's git
#    checkout enforces the commit pin, and a URL constraint would conflict
#    with the -e "<checkout>[leveldb]" install)
```

Every license classification below was recorded from the package's own
license file (GitHub license detection against each project's default
branch on 2026-11-16) or PyPI metadata on the same date. **These
classifications are PROVISIONAL**: they are not yet verified against each
RESOLVED version's immutable release artifact (tag/sdist); confirming them
version-specifically is part of RULE 8's standing re-check duty (see the
note below the table):

| Resolved package | Version | Role | License | Evidence |
|---|---|---|---|---|
| e-x (electrumx) | git `ee28cd8d…` | the kit itself | MIT | local `LICENCE` (row above) |
| aiohttp | 3.14.5 | direct (e-x) | Apache-2.0 | GitHub `aio-libs/aiohttp` `LICENSE.txt` |
| aiorpcx | 0.25.0 | direct (e-x) | MIT | GitHub `kyuupichan/aiorpcX` `LICENCE` |
| websockets | 17.4 | direct via aiorpcx `[ws]` | BSD-3-Clause | GitHub `python-websockets/websockets` `LICENSE` |
| aiohappyeyeballs | 2.7.1 | via aiohttp | PSF-2.0 | LICENSE is the PSF license document; PyPI classifier "Python Software Foundation License" |
| aiosignal | 1.4.0 | via aiohttp | Apache-2.0 | PyPI license field + classifier |
| attrs | 26.1.0 | via aiohttp | MIT | GitHub `python-attrs/attrs` `LICENSE` |
| frozenlist | 1.8.0 | via aiohttp, aiosignal | Apache-2.0 | PyPI license field |
| idna | 3.20 | via yarl | BSD-3-Clause | GitHub `kjd/idna` `LICENSE.md` |
| multidict | 7.2.1 | via aiohttp, yarl | Apache-2.0 | GitHub `aio-libs/multidict` `LICENSE` |
| propcache | 0.5.4 | via aiohttp, yarl | Apache-2.0 | PyPI license field |
| typing-extensions | 4.16.0 | via aiohttp, aiosignal | PSF-2.0 | LICENSE is the PSF license document (GitHub detection NOASSERTION — it is the full PSF text, not a template file) |
| yarl | 1.25.1 | via aiohttp | Apache-2.0 | PyPI license field |
| plyvel | 1.5.1 — pinned by the constraints capture | `[leveldb]` extra | BSD License | PyPI metadata (row above) |

Version numbers are the 2026-11-16 capture; a deploy built WITH the
constraints file repeats them, one built without may resolve newer
in-range versions. Any future deploy re-checks the licenses of newly
resolved versions — that re-check is RULE 8's standing duty, not a one-time
act (the classifications above are provisional until confirmed against each
resolved release artifact).

Note: PyPI `electrumx` 1.20.2 is a stale altcoin-stripped build and is
rejected by the suite — the MIT license statement above applies to the
pinned git tree only.

## 5. Build toolchain (produces the APK; not shipped in it)

| Tool | Version | License | Evidence |
|---|---|---|---|
| OpenJDK (javac) | 21.0.13 (Ubuntu build, `IMPLEMENTOR="Ubuntu"` in `release`) | GPL v2 + Classpath Exception | Ubuntu package copyright file, `/usr/share/doc/openjdk-21-jre-headless/copyright`: "License: GPL2 with Classpath exception" |
| Android SDK build-tools (aapt2, d8, apksigner, zipalign) | 34.0.0 | USE of the SDK binaries is governed by the Android SDK License Agreement (evidence class (c): host-environment — `/opt/android-sdk/licenses/android-sdk-license` accepted on-host, hash `24333f8a63b6825ea9c5514f83c2829b004d1fee`); the upstream source licenses of the SDK's components (AOSP) are Apache-2.0 — stated as platform convention, not verified per-component here |
| Android platform | android-34 | (build-time only) | `/opt/android-sdk/platforms/android-34` |
| CPython | 3.12.3 (`/usr/bin/python3`) / 3.14.9 (dev default) | PSF License 2.0 | interpreter provenance; server floor is Python >= 3.10 (set by the electrumx pin) |

## 6. Repository license

`LICENSE` at the repo root: **MIT, "Copyright (c) 2026 Sami Ahmed"** —
present since the initial scaffold commit `8c66697` (MAZA coin profile for
ElectrumX). This file establishes the licensing TERMS of the repository; it
is not an authorship claim over every line (code was produced with agent
assistance under Sami's direction — the terms are what RULE 8 cares about).

## 7. Komodo independence (RULE 8)

No Komodo component is incorporated at any layer — the comparison section of
`docs/SPEC-AUDIT.md` records the deliberate exclusions. The section-1 import
scan is the mechanical proof for the APK layer; sections 2-4 show nothing
Komodo-related in any other layer either.

## 8. Incorporation review table (RULE 8 — what IS incorporated)

| Incorporated item | Layer | License check | Technically necessary? |
|---|---|---|---|
| BIP39 English wordlist | APK (data) | license/grant at the data level UNRESOLVED (no per-file grant exists); provenance VERIFIED (byte-identity + recorded upstream revisions, §1); trezor repo is MIT | yes — BIP39 mnemonic requires the canonical 2048-word list; hand-rolling it would break interoperability |
| zxing core 3.5.3 jar | APK (code) | Apache-2.0, license text vendored (`android/vendor/LICENSE-zxing.txt`); sha256-pinned + build-enforced (§1) | yes — QR DECODING for M8 (camera scan); hand-rolling a QR decoder is out of scope; CameraX/zxing-embedded rejected (AndroidX/AppCompat build rule) |
| qrcodegen.py (Nayuki) | server runtime | MIT, header vendored in-file | yes — QR rendering for `/api/qr.png`; single-file, stdlib-only, no install surface |
| python-ecdsa | operator instruments only | MIT-style (quoted above) + public-domain portions | yes — independent ECDSA implementation to cross-check the APK's hand-rolled signer (the whole point of the oracle) |
| electrumx pin + aiorpcX + aiohttp + websockets + plyvel + LevelDB | ElectrumX kit | MIT / MIT / Apache-2.0 / BSD-3-Clause / BSD / BSD-style (§4) | yes — the M18 community kit's indexer; ElectrumX source commit-pinned, drift-refusing; dep ranges resolved at deploy time (§4 scope note) |
| — | APK code | every APK import is Android platform or JDK | the zxing jar above is the one non-imported bundled artifact (consumed by M8b's import; packaged + gated since M8a) |

Dependency-surface summary, scoped precisely: the repo itself carries no
package-manager lockfile and no vendored PACKAGE TREES (its pin artifact is
the captured constraints manifest, `deploy/requirements-resolved-py312.txt`;
the vendored CODE artifacts are exactly two, each documented: the server-side
`walletbench/vendor/qrcodegen.py` and the APK-side
`android/vendor/zxing-core-3.5.3.jar` — the BIP39 wordlist is vendored DATA,
§1); the APK build pipeline
(`android/build-apk.sh`) uses raw aapt2/javac/d8/apksigner — no Gradle, so no
plugin/dependency-resolution surface at all (evidence class (a): the script's
own header names the pipeline, and a comment-scan finds no gradle invocation);
the walletbench service runtime installs no pip packages (stdlib + the one
vendored file, §2); the ElectrumX kit pip-installs its dependency set
through the committed constraints file (the installer passes it with `-c`;
ElectrumX itself comes from the commit pin), so the documented install path
ON THE CAPTURED TARGET (Python 3.12) repeats the same runtime dependency
resolution, plyvel included — the capture pins runtime dependency versions
only, with no hashes and no build-dependency pinning (§4 scope limits).
That kit install is the kit's own
deployment action on the operator's host — not a dependency tree stored in
or shipped by this repo.

## How to re-verify

From a checkout: the section 1-2 grep/sha256 commands are checkout-contained;
the section 1 curl commands and the section 4 capture command need network
access (the capture input ships as `deploy/requirements-deploy.in`); the
tables in sections 3-5 cite public endpoints (`pypi.org`,
`api.github.com`, `raw.githubusercontent.com`) and on-host files whose paths
are given verbatim — the latter are evidence-class (c) host-environment
checks, meaningful only where those toolchains are installed (the battery
transcript shipped with this report was produced on the DNS2 dev host).
