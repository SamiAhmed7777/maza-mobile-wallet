"""Hash and encoding primitives for the MAZA indexer. Stdlib only.

HASH BYTE-ORDER CONVENTION (binding across the package):

Bitcoin-family hash fields appear in TWO orders.  double_sha256() returns the
raw digest in INTERNAL byte order.  RPC/block-explorer "hash", "txid" and
"merkleroot" strings are DISPLAY order (the internal digest reversed).
Comparisons against values the daemon reported MUST reverse first:

    double_sha256(header)[::-1].hex() == rpc_block_hash

and never the raw digest hex.  Everything crossing the HTTP API is DISPLAY
order (the daemon's own spelling, never re-reversed).  Same convention as
indexer/maza_coin.py:111-123 (double_sha256 / hash_to_display_hex).

Bitcoin-family facts (do not re-derive): checksums / merkle pairs / xkey
serialization are DOUBLE sha256; hash160 is single sha256 then ripemd160.
MAZA block identity = double-SHA256 of the 80-byte header for every block in
every PoW era (MazaCore primitives/block.cpp:18-21; DECISIONS.md D2).
"""

import hashlib
import struct

# ---------------------------------------------------------------------------
# ripemd160: hashlib when the OpenSSL build allows legacy digests, otherwise
# a PURE-PYTHON fallback (RIPEMD-160 spec, Dobbertin/Bosselaers/Preneel 1996).
# OpenSSL 3 boxes often refuse legacy ripemd160, so the fallback is REQUIRED
# on this project, not optional.
# ---------------------------------------------------------------------------


def _has_hashlib_ripemd160() -> bool:
    try:
        hashlib.new("ripemd160", b"")
        return True
    except Exception:
        return False


def _rol32(x, n):
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _f(j, x, y, z):
    if j < 16:
        return x ^ y ^ z
    if j < 32:
        return (x & y) | (~x & z)
    if j < 48:
        return (x | ~y) ^ z
    if j < 64:
        return (x & z) | (y & ~z)
    return x ^ (y | ~z)


# Message-word permutations: index of the message word fed at step j, left
# line then right line, five 16-step rounds each (RIPEMD-160 spec, Annex).
_RL = (
    tuple(range(16)),
    (7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8),
    (3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12),
    (1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2),
    (4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13),
)
_RR = (
    (5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12),
    (6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2),
    (15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13),
    (8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14),
    (12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11),
)
# Left-rotation amounts per step, left line then right line (spec, Annex).
_SL = (
    (11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8),
    (7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12),
    (11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5),
    (11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12),
    (9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6),
)
_SR = (
    (8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6),
    (9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11),
    (9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5),
    (15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8),
    (8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11),
)
_KL = (0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E)
_KR = (0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000)


def ripemd160_pure(data: bytes) -> bytes:
    """Pure-Python RIPEMD-160 (spec: 'RIPEMD-160: A Strengthened Ripemd for
    Greater Security', basic vectors -- empty string digests to
    9c1185a5c5e9fc54612808977ee8f548b2258d31)."""
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    padded = data + b"\x80" + b"\x00" * ((55 - len(data)) % 64)
    padded += struct.pack("<Q", (len(data) * 8) & 0xFFFFFFFFFFFFFFFF)
    for off in range(0, len(padded), 64):
        x = struct.unpack("<16I", padded[off:off + 64])
        al, bl, cl, dl, el = h
        ar, br, cr, dr, er = h
        for j in range(80):
            rnd = j >> 4
            t = (_rol32((al + _f(j, bl, cl, dl) + x[_RL[rnd][j & 15]]
                         + _KL[rnd]) & 0xFFFFFFFF, _SL[rnd][j & 15]) + el) \
                & 0xFFFFFFFF
            al, el, dl, cl = el, dl, _rol32(cl, 10), bl
            bl = t
            # Right line: the SAME five f-functions in REVERSE order
            # (f(79-j) per the spec pseudocode).
            t = (_rol32((ar + _f(79 - j, br, cr, dr) + x[_RR[rnd][j & 15]]
                         + _KR[rnd]) & 0xFFFFFFFF, _SR[rnd][j & 15]) + er) \
                & 0xFFFFFFFF
            ar, er, dr, cr = er, dr, _rol32(cr, 10), br
            br = t
        # Final mixing stage (RIPEMD-160 spec; mirrored from the public-domain
        # pycryptodome src/RIPEMD160.c, Litzenberger 2008, HAC Algorithm 9.55).
        t = (h[1] + cl + dr) & 0xFFFFFFFF
        h[1] = (h[2] + dl + er) & 0xFFFFFFFF
        h[2] = (h[3] + el + ar) & 0xFFFFFFFF
        h[3] = (h[4] + al + br) & 0xFFFFFFFF
        h[4] = (h[0] + bl + cr) & 0xFFFFFFFF
        h[0] = t
    return struct.pack("<5I", *h)


_HAS_LIB = _has_hashlib_ripemd160()


def ripemd160(data: bytes) -> bytes:
    """hashlib ripemd160 when available, else the pure-Python fallback."""
    if _HAS_LIB:
        return hashlib.new("ripemd160", data).digest()
    return ripemd160_pure(data)


def double_sha256(data: bytes) -> bytes:
    """Raw double SHA-256, INTERNAL byte order.

    Compare against daemon-reported hashes only in DISPLAY order:
    double_sha256(x)[::-1].hex().  See the module docstring.
    """
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hash160(data: bytes) -> bytes:
    """RIPEMD-160(SHA-256(data)) -- single sha256 then ripemd160 (the
    Bitcoin-family address digest; checksums/merkle stay DOUBLE sha256)."""
    return ripemd160(hashlib.sha256(data).digest())


# ---------------------------------------------------------------------------
# base58check (addresses).  Version bytes are fetched from the repo's own
# ElectrumX coin profile, never recalled from memory:
#   P2PKH_VERSION_BYTE = 50  indexer/maza_coin.py:47
#   P2SH_VERSION_BYTE  = 9   indexer/maza_coin.py:48
# ---------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58check_encode(version: int, payload: bytes) -> str:
    """version byte + payload + first 4 bytes of double-SHA256 -> base58 str."""
    raw = bytes([version]) + payload
    raw += double_sha256(raw)[:4]
    n = int.from_bytes(raw, "big")
    out = []
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_B58_ALPHABET[rem])
    pad = 0
    for byte in raw:
        if byte == 0:
            pad += 1
        else:
            break
    return "1" * pad + "".join(reversed(out))


def base58check_decode(s: str):
    """-> (version_byte, payload_bytes).  Raises ValueError on bad checksum or
    characters outside the base58 alphabet."""
    n = 0
    for ch in s:
        idx = _B58_ALPHABET.find(ch)
        if idx < 0:
            raise ValueError("invalid base58 character")
        n = n * 58 + idx
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    pad = 0
    for ch in s:
        if ch == "1":
            pad += 1
        else:
            break
    raw = b"\x00" * pad + raw
    if len(raw) < 5:
        raise ValueError("base58check too short")
    body, checksum = raw[:-4], raw[-4:]
    if double_sha256(body)[:4] != checksum:
        raise ValueError("bad base58check checksum")
    return body[0], body[1:]
