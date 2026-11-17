package com.mazawallet.crypto;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.security.GeneralSecurityException;

/**
 * PBKDF2-HMAC-SHA512 key derivation (RFC 2898/8018). Thin wrapper over the
 * platform SecretKeyFactory ("PBKDF2WithHmacSHA512") — the exact primitive
 * Bip39.toSeed already uses, which is proven on-device (every seed-creation
 * device proof — M1/M2/M21/M22 — exercised it). Used by the S-2a PIN lock to
 * derive the PIN verifier; pure Java (no android.* imports) so the desktop
 * selftest vector-pins it.
 *
 * Anchors (SelfTest):
 *  - the official BIP39 TREZOR seed vector IS PBKDF2-HMAC-SHA512(mnemonic,
 *    "mnemonic"+passphrase, 2048, 64) — deriving it through this class must
 *    reproduce the already-pinned official seed byte for byte;
 *  - direct anchors cross-derived with Python 3 hashlib.pbkdf2_hmac
 *    (OpenSSL) — the same independent-oracle pattern as tools/oracle.py.
 * If a fetched/computed anchor "mismatches" this implementation, suspect the
 * implementation, never the vector (standing repo rule).
 */
public final class Pbkdf2 {

    private Pbkdf2() {}

    /**
     * Derives dkLen bytes from password + salt with the given iteration
     * count. The password char[] is cleared by PBEKeySpec before return.
     */
    public static byte[] derive(char[] password, byte[] salt, int iterations, int dkLen) {
        if (password == null || password.length == 0) {
            throw new IllegalArgumentException("empty password");
        }
        if (salt == null || salt.length < 8) {
            throw new IllegalArgumentException("salt must be at least 8 bytes");
        }
        if (iterations < 1) {
            throw new IllegalArgumentException("iterations must be >= 1");
        }
        if (dkLen < 1) {
            throw new IllegalArgumentException("dkLen must be >= 1");
        }
        PBEKeySpec spec = new PBEKeySpec(password, salt, iterations, dkLen * 8);
        try {
            SecretKeyFactory skf =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA512");
            return skf.generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            // Same platform-primitive caveat Bip39 carries: if the runtime
            // lacks PBKDF2WithHmacSHA512 the caller must surface a clear
            // error, never a silent fallback to a weaker hash.
            throw new IllegalStateException("PBKDF2-HMAC-SHA512 unavailable", e);
        } finally {
            spec.clearPassword();
        }
    }
}
