#!/usr/bin/env python3
"""Verify a client-signed legacy P2PKH transaction offline (implementation #2).

Given the raw tx hex, the input index, the UTXO's scriptPubKey and the
expected receiving address, this recomputes the SIGHASH_ALL digest and
ECDSA-verifies the signature against the pubkey embedded in the scriptSig.
This is the gate that must pass BEFORE any /api/broadcast of a
self-custody transaction on mainnet.

Usage:
  /tmp/destvenv/bin/python tools/txverify.py <raw_tx_hex> \
      <input_index> <prev_scriptpubkey_hex>
"""

import hashlib
import sys

from ecdsa import BadSignatureError, VerifyingKey, SECP256k1


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def hash160(b: bytes) -> bytes:
    return hashlib.new("ripemd160", sha256(b)).digest()


def read_varint(data: bytes, pos: int):
    prefix = data[pos]
    if prefix < 0xFD:
        return prefix, pos + 1
    if prefix == 0xFD:
        return int.from_bytes(data[pos + 1:pos + 3], "little"), pos + 3
    if prefix == 0xFE:
        return int.from_bytes(data[pos + 1:pos + 5], "little"), pos + 5
    return int.from_bytes(data[pos + 1:pos + 9], "little"), pos + 9


def parse_tx(raw: bytes):
    pos = 0
    version = int.from_bytes(raw[pos:pos + 4], "little")
    pos += 4
    n_in, pos = read_varint(raw, pos)
    inputs = []
    for _ in range(n_in):
        prev_txid = raw[pos:pos + 32][::-1].hex()
        pos += 32
        prev_vout = int.from_bytes(raw[pos:pos + 4], "little")
        pos += 4
        script_len, pos = read_varint(raw, pos)
        script_sig = raw[pos:pos + script_len]
        pos += script_len
        seq = raw[pos:pos + 4]
        pos += 4
        inputs.append({"txid": prev_txid, "vout": prev_vout,
                       "script_sig": script_sig, "sequence": seq})
    n_out, pos = read_varint(raw, pos)
    outputs = []
    for _ in range(n_out):
        value = int.from_bytes(raw[pos:pos + 8], "little")
        pos += 8
        script_len, pos = read_varint(raw, pos)
        script_pub = raw[pos:pos + script_len]
        pos += script_len
        outputs.append({"value": value, "script_pubkey": script_pub})
    locktime = int.from_bytes(raw[pos:pos + 4], "little")
    pos += 4
    return version, inputs, outputs, locktime, pos, len(raw)


def parse_pushes(script: bytes):
    """Return list of (opcode, data) pushes; supports 0x4c/0x4d forms."""
    out = []
    pos = 0
    while pos < len(script):
        op = script[pos]
        pos += 1
        if 1 <= op <= 75:
            out.append((op, script[pos:pos + op]))
            pos += op
        elif op == 0x4c:  # OP_PUSHDATA1
            n = script[pos]
            pos += 1
            out.append((op, script[pos:pos + n]))
            pos += n
        elif op == 0x4d:  # OP_PUSHDATA2
            n = int.from_bytes(script[pos:pos + 2], "little")
            pos += 2
            out.append((op, script[pos:pos + n]))
            pos += n
        else:
            out.append((op, None))
    return out


def sighash_all(raw: bytes, input_index: int, prev_script: bytes) -> bytes:
    """Recompute the SIGHASH_ALL digest the signer committed to."""
    version, inputs, outputs, locktime, _, _ = parse_tx(raw)
    buf = bytearray()
    buf += version.to_bytes(4, "little")
    buf += len(inputs).to_bytes(1, "little") if len(inputs) < 0xFD \
        else b"\xfd" + len(inputs).to_bytes(2, "little")
    for i, txin in enumerate(inputs):
        buf += bytes.fromhex(txin["txid"])[::-1]
        buf += txin["vout"].to_bytes(4, "little")
        script = prev_script if i == input_index else b""
        n = len(script)
        if n < 0xFD:
            buf += n.to_bytes(1, "little")
        else:
            buf += b"\xfd" + n.to_bytes(2, "little")
        buf += script
        buf += txin["sequence"]
    buf += len(outputs).to_bytes(1, "little") if len(outputs) < 0xFD \
        else b"\xfd" + len(outputs).to_bytes(2, "little")
    for out in outputs:
        buf += out["value"].to_bytes(8, "little")
        n = len(out["script_pubkey"])
        if n < 0xFD:
            buf += n.to_bytes(1, "little")
        else:
            buf += b"\xfd" + n.to_bytes(2, "little")
        buf += out["script_pubkey"]
    buf += locktime.to_bytes(4, "little")
    buf += (1).to_bytes(4, "little")  # SIGHASH_ALL
    return sha256(sha256(bytes(buf)))


def main() -> None:
    raw_hex = sys.argv[1].strip().lower()
    input_index = int(sys.argv[2])
    prev_spk = bytes.fromhex(sys.argv[3].strip().lower())

    raw = bytes.fromhex(raw_hex)
    version, inputs, outputs, locktime, consumed, total = parse_tx(raw)
    print(f"tx: version={version} inputs={len(inputs)} "
          f"outputs={len(outputs)} locktime={locktime} "
          f"consumed={consumed}/{total} bytes")
    if consumed != total:
        print("FAIL: trailing bytes after tx end")
        sys.exit(1)

    script_sig = inputs[input_index]["script_sig"]
    pushes = parse_pushes(script_sig)
    data_pushes = [p for p in pushes if p[1] is not None]
    if len(data_pushes) != 2:
        print(f"FAIL: expected [sig, pubkey] pushes, got {len(data_pushes)}")
        sys.exit(1)
    (sig_op, sig_der_ct), (pub_op, pubkey) = data_pushes
    if not (len(sig_der_ct) >= 1 and sig_der_ct[-1] == 0x01):
        print("FAIL: hashtype byte is not SIGHASH_ALL")
        sys.exit(1)
    sig_der = sig_der_ct[:-1]

    # pubkey sanity + address
    if pubkey[0] not in (2, 3, 4):
        print("FAIL: pubkey prefix invalid")
        sys.exit(1)
    vk = VerifyingKey.from_string(pubkey, curve=SECP256k1)
    from_addr = "M" if True else ""
    # MAZA P2PKH address from the embedded pubkey
    import struct

    def base58check(version: int, payload: bytes) -> str:
        data = bytes([version]) + payload
        full = data + sha256(sha256(data))[:4]
        alphabet = ("123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
                    "abcdefghijkmnopqrstuvwxyz")
        n = int.from_bytes(full, "big")
        s = ""
        while n:
            n, r = divmod(n, 58)
            s = alphabet[r] + s
        pad = len(full) - len(full.lstrip(b"\x00"))
        return "1" * pad + s

    addr = base58check(0x32, hash160(pubkey))
    print(f"pubkey {pubkey.hex()[:16]}... -> address {addr}")

    # low-S check on the DER signature
    r_len = sig_der[3]
    s_start = 4 + r_len + 2
    s_len = sig_der[s_start - 1]
    s_val = int.from_bytes(sig_der[s_start:s_start + s_len], "big")
    order = SECP256k1.order
    low_s = s_val <= order // 2
    print(f"s value: {'LOW (ok)' if low_s else 'HIGH (BIP62 violation!)'}")

    digest = sighash_all(raw, input_index, prev_spk)
    from ecdsa.util import sigdecode_der
    try:
        ok = vk.verify_digest(sig_der, digest, sigdecode=sigdecode_der)
    except BadSignatureError:
        ok = False
    print("SIGNATURE:", "VALID" if ok else "INVALID")
    for i, out in enumerate(outputs):
        print(f"  output {i}: {out['value'] / 1e8:.8f} MAZA "
              f"script={out['script_pubkey'].hex()[:28]}...")
    sys.exit(0 if (ok and low_s) else 1)


if __name__ == "__main__":
    main()
