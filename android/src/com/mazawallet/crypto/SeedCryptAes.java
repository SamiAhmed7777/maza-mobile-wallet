package com.mazawallet.crypto;

import java.security.SecureRandom;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * At-rest encryption envelope for wallet secrets (seed phrases).
 *
 * AES-256-GCM with a random 12-byte IV per encryption and a 128-bit
 * authentication tag. Wire format: [IV (12 bytes)][ciphertext+tag].
 *
 * The key is passed as a javax.crypto.SecretKey so callers can use a
 * NON-EXPORTABLE AndroidKeyStore key (SeedVault) — its raw bytes never
 * exist in memory outside the keystore. For desktop testing, keyFor(raw)
 * wraps plain bytes in a SecretKeySpec (that is what SelfTest uses).
 *
 * First-party, no dependencies; pure javax.crypto (JDK).
 */
public final class SeedCryptAes {

    public static final int IV_LEN = 12;
    public static final int TAG_BITS = 128;
    public static final int KEY_LEN = 32;

    private static final String TRANSFORM = "AES/GCM/NoPadding";
    private static final String ALG = "AES";
    private static final SecureRandom RNG = new SecureRandom();

    private SeedCryptAes() {
    }

    /** Wrap raw key bytes into a SecretKey (desktop/test path). */
    public static SecretKey keyFor(byte[] raw32) {
        if (raw32 == null || raw32.length != KEY_LEN) {
            throw new IllegalArgumentException("key must be " + KEY_LEN + " bytes");
        }
        return new SecretKeySpec(raw32, ALG);
    }

    /** Encrypt plaintext -> [IV][ciphertext+tag]. Fresh random IV each call. */
    public static byte[] encrypt(SecretKey key, byte[] plaintext) {
        requireAes(key);
        try {
            byte[] iv = new byte[IV_LEN];
            RNG.nextBytes(iv);
            Cipher c = Cipher.getInstance(TRANSFORM);
            c.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            byte[] ct = c.doFinal(plaintext == null ? new byte[0] : plaintext);
            byte[] out = new byte[IV_LEN + ct.length];
            System.arraycopy(iv, 0, out, 0, IV_LEN);
            System.arraycopy(ct, 0, out, IV_LEN, ct.length);
            return out;
        } catch (java.security.GeneralSecurityException e) {
            throw new IllegalStateException("seed encryption failed", e);
        }
    }

    /** Decrypt [IV][ciphertext+tag] -> plaintext. Throws on tamper/wrong key. */
    public static byte[] decrypt(SecretKey key, byte[] blob) {
        requireAes(key);
        if (blob == null || blob.length <= IV_LEN + 16) {
            throw new IllegalArgumentException("blob too short");
        }
        try {
            byte[] iv = new byte[IV_LEN];
            System.arraycopy(blob, 0, iv, 0, IV_LEN);
            Cipher c = Cipher.getInstance(TRANSFORM);
            c.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            return c.doFinal(blob, IV_LEN, blob.length - IV_LEN);
        } catch (java.security.GeneralSecurityException e) {
            throw new IllegalStateException("seed decryption failed (wrong key or tampered data)", e);
        }
    }

    /** True if [IV][ciphertext+tag] decrypts cleanly with this key. Never logs. */
    public static boolean canDecrypt(SecretKey key, byte[] blob) {
        try {
            decrypt(key, blob);
            return true;
        } catch (RuntimeException e) {
            return false;
        }
    }

    private static void requireAes(SecretKey key) {
        if (key == null || !ALG.equals(key.getAlgorithm())) {
            throw new IllegalArgumentException("expected an AES SecretKey");
        }
    }
}
