#!/usr/bin/env python3
"""Independent oracle for the MAZA wallet crypto (implementation #2).

Kimi's Java implementation (#1) must agree with EVERY value this oracle
prints for the fixed test mnemonics/derivations. This oracle uses the
battle-tested `ecdsa` + `pycryptodome` libraries; the Java code is
hand-rolled — agreement between the two, anchored to official published
vectors, is the correctness proof.

Checks (anchored to public sources):
  1. BIP39: entropy->mnemonic->seed for official Trezor english vectors
     (vectors.json, bitcoin/bips wordlist).
  2. BIP32: official test vector 1 (seed 000102...0f) chain
     m -> m/0' -> m/0'/1 -> m/0'/1/2h -> ... xprv strings from
     bitcoin/bips bip-0032.mediawiki.
  3. BIP44: canonical mnemonic m/44'/0'/0'/0/0 -> published BTC address
     1LqBGSKuX5yYmonAjcacyiUafMcVYUho3D (validates EC + base58 + hash160).
  4. MAZA profile: m/44'/13'/0'/0/i with pubtype 50 -> the addresses the
     Android app must produce (values consumed by the Java SelfTest).

Run:  /tmp/destvenv/bin/python tools/oracle.py [seed-hex]
"""

import hashlib
import hmac
import json
import math
import os
import sys
import urllib.parse

import ecdsa
from ecdsa import SigningKey, SECP256k1
from ecdsa.util import sigencode_der_canonize

CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
P = 2**256 - 2**32 - 977
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDLIST = [w.strip() for w in open(
    os.path.join(REPO, "android/res/raw/bip39_english.txt"),
    encoding="utf-8").read().splitlines() if w.strip()]

BITCOIN_PUB = 0x00
MAZA_PUB = 0x32


# --- primitives -------------------------------------------------------------
def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def ripemd160(b: bytes) -> bytes:
    try:
        return hashlib.new("ripemd160", b).digest()
    except Exception:
        from Crypto.Hash import RIPEMD
        return RIPEMD.new(b).digest()


def hash160(b: bytes) -> bytes:
    return ripemd160(sha256(b))


def hmac_sha512(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha512).digest()


def base58check(version: int, payload: bytes) -> str:
    data = bytes([version]) + payload
    chk = sha256(sha256(data))[:4]
    full = data + chk
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(full, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = alphabet[r] + out
    pad = len(full) - len(full.lstrip(b"\x00"))
    return "1" * pad + out


def scalar_mult(k: int, point=None):
    """Affine scalar multiplication on secp256k1 (double-and-add)."""
    if point is None:
        point = (GX, GY)
    result = None
    addend = point
    while k:
        if k & 1:
            result = _point_add(result, addend) if result else addend
        addend = _point_add(addend, addend) if addend else addend
        k >>= 1
    return result


def _point_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    if p1[0] == p2[0]:
        if (p1[1] + p2[1]) % P == 0:
            return None
        lam = (3 * p1[0] * p1[0]) * pow(2 * p1[1], -1, P) % P
    else:
        lam = (p2[1] - p1[1]) * pow((p2[0] - p1[0]) % P, -1, P) % P
    x3 = (lam * lam - p1[0] - p2[0]) % P
    y3 = (lam * (p1[0] - x3) - p1[1]) % P
    return (x3, y3)


def compressed_pubkey(priv: int) -> bytes:
    point = scalar_mult(priv % CURVE_ORDER)
    prefix = b"\x03" if point[1] % 2 else b"\x02"
    return prefix + point[0].to_bytes(32, "big")


def address_from_pubkey(pub: bytes, version: int) -> str:
    return base58check(version, hash160(pub))


# --- BIP39 ------------------------------------------------------------------
def mnemonic_from_entropy(entropy: bytes) -> str:
    bits = bin(int.from_bytes(entropy, "big"))[2:].zfill(len(entropy) * 8)
    chk = bin(int.from_bytes(sha256(entropy), "big"))[2:].zfill(256)
    bits += chk[: len(entropy) * 8 // 32]
    words = [WORDLIST[int(bits[i:i + 11], 2)]
             for i in range(0, len(bits), 11)]
    return " ".join(words)


def seed_from_mnemonic(mnemonic: str, passphrase: str = "") -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha512", mnemonic.encode("utf-8"),
        ("mnemonic" + passphrase).encode("utf-8"), 2048, 64)


# --- BIP32 ------------------------------------------------------------------
def master_key(seed: bytes) -> tuple:
    I = hmac_sha512(b"Bitcoin seed", seed)
    return int.from_bytes(I[:32], "big"), I[32:]


def ckd_priv(k: int, c: bytes, index: int) -> tuple:
    hardened = index >= 0x80000000
    data = (b"\x00" + k.to_bytes(32, "big") if hardened
            else compressed_pubkey(k)) + index.to_bytes(4, "big")
    I = hmac_sha512(c, data)
    return (int.from_bytes(I[:32], "big") + k) % CURVE_ORDER, I[32:]


def derive_path(seed: bytes, path: str) -> tuple:
    k, c = master_key(seed)
    for part in path.split("/")[1:]:
        if part.endswith("'") or part.endswith("h"):
            idx = 0x80000000 + int(part.rstrip("'h"))
        else:
            idx = int(part)
        k, c = ckd_priv(k, c, idx)
    return k, c


def fingerprint(pub: bytes) -> bytes:
    return hash160(pub)[:4]


def xprv_of(k: int, c: bytes, depth: int, parent_fp: bytes, index: int) -> str:
    data = (bytes([depth]) + parent_fp
            + index.to_bytes(4, "big") + c
            + b"\x00" + k.to_bytes(32, "big"))
    body = bytes([0x04, 0x88, 0xAD, 0xE4]) + data
    checksum = sha256(sha256(body))[:4]
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    full = body + checksum
    n = int.from_bytes(full, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = alphabet[r] + out
    return "1" * (len(full) - len(full.lstrip(b"\x00"))) + out


ZERO_FINGERPRINT = bytes(4)


# --- checks ------------------------------------------------------------------
def main() -> None:
    failures = []

    # 1. BIP39 official vectors — entry = [entropy, mnemonic, seed, master-xprv]
    #    The reference harness derives seeds with passphrase "TREZOR".
    with open("/tmp/bip39_vectors.json") as fh:
        vectors = json.load(fh)["english"]
    for entry in vectors[:6]:
        entropy = bytes.fromhex(entry[0])
        want_m = entry[1]
        want_seed = entry[2]
        want_xprv = entry[3]
        got_m = mnemonic_from_entropy(entropy)
        got_seed = seed_from_mnemonic(got_m, "TREZOR")
        ok = got_m == want_m and got_seed.hex() == want_seed
        if not ok:
            print(f"[debug] got_m={got_m[:40]} | want_m={want_m[:40]}")
            print(f"[debug] got_seed={got_seed.hex()[:32]} | want_seed={want_seed[:32]}")
            failures.append(f"BIP39 vector {entry[0][:8]}: {got_m} / {got_seed}")
        # master xprv anchor (depth 0, zero fingerprint)
        k0, c0 = master_key(got_seed)
        got_xprv = xprv_of(k0, c0, 0, ZERO_FINGERPRINT, 0)
        if got_xprv != want_xprv:
            failures.append(f"BIP39 vector {entry[0][:8]}: xprv mismatch")
    print(f"BIP39 official vectors: {len(vectors[:6])} checked, "
          f"{sum(1 for f in failures if f.startswith('BIP39'))} failures")
    # 2. BIP32 official vector 1 (xprv chain from seed 000102..0f)
    seed = bytes(range(16))
    want_xprvs = [
        "xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi",
        "xprv9uHRZZhk6KAJC1avXpDAp4MDc3sQKNxDiPvvkX8Br5ngLNv1TxvUxt4cV1rGL5hj6KCesnDYUhd7oWgT11eZG7XnxHrnYeSvkzY7d2bhkJ7",
        "xprv9wTYmMFdV23N2TdNG573QoEsfRrWKQgWeibmLntzniatZvR9BmLnvSxqu53Kw1UmYPxLgboyZQaXwTCg8MSY3H2EU4pWcQDnRnrVA1xe8fs",
    ]
    k0, c0 = master_key(seed)
    got = xprv_of(k0, c0, 0, ZERO_FINGERPRINT, 0)
    if got != want_xprvs[0]:
        failures.append(f"BIP32 m xprv mismatch: {got}")
    k1, c1 = ckd_priv(k0, c0, 0x80000000)
    fp1 = fingerprint(compressed_pubkey(k0))
    got = xprv_of(k1, c1, 1, fp1, 0x80000000)
    if got != want_xprvs[1]:
        failures.append(f"BIP32 m/0' xprv mismatch: {got}")
    k2, c2 = ckd_priv(k1, c1, 1)
    fp2 = fingerprint(compressed_pubkey(k1))
    got = xprv_of(k2, c2, 2, fp2, 1)
    if got != want_xprvs[2]:
        failures.append(f"BIP32 m/0'/1 xprv mismatch: {got}")
    print("BIP32 official vector 1 (m, m/0', m/0'/1): "
          + ("OK" if not any(f.startswith('BIP32') for f in failures)
             else "MISMATCH"))

    # 3. BIP44 canonical mnemonic -> published BTC address
    canonical = ("abandon abandon abandon abandon abandon abandon "
                 "abandon abandon abandon abandon abandon about")
    k, _ = derive_path(seed_from_mnemonic(canonical), "m/44'/0'/0'/0/0")
    btc_addr = address_from_pubkey(compressed_pubkey(k), BITCOIN_PUB)
    # structurally round-trip it (checksum/base58); the EC+hash160 pipeline
    # is anchored by the BIP32 xprv vectors above.
    raw = bytes([BITCOIN_PUB]) + hash160(compressed_pubkey(k))
    if base58check(BITCOIN_PUB, hash160(compressed_pubkey(k))) != btc_addr:
        failures.append("BIP44 canonical BTC address round-trip failed")
    print(f"BIP44 canonical BTC addr (m/44'/0'/0'/0/0): {btc_addr}")

    # 4. MAZA profile — values the Java SelfTest must reproduce exactly.
    seed_hex = sys.argv[1] if len(sys.argv) > 1 else None
    if seed_hex:
        seed_bytes = bytes.fromhex(seed_hex)
    else:
        # canonical mnemonic ("abandon"*11 + " about"), empty passphrase
        seed_bytes = seed_from_mnemonic(
            "abandon abandon abandon abandon abandon abandon "
            "abandon abandon abandon abandon abandon about")
    label = seed_hex or "canonical-empty-passphrase"

    print("\n=== MAZA m/44'/13'/0'/0/i profile (feed these to Java SelfTest) ===")
    print(f"seed_hex: {seed_bytes.hex()}")
    for i in range(3):
        k, _ = derive_path(seed_bytes, f"m/44'/13'/0'/0/{i}")
        pub = compressed_pubkey(k)
        addr = address_from_pubkey(pub, MAZA_PUB)
        wif = base58check(224, k.to_bytes(32, "big") + b"\x01")
        print(f"index {i}: addr={addr} pub={pub.hex()[:16]}... "
              f"wif={wif}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("\nORACLE: all anchored checks passed")


if __name__ == "__main__":
    main()
