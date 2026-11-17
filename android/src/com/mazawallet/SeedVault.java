package com.mazawallet;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Log;
import com.mazawallet.crypto.SeedCryptAes;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.security.KeyStore;
import javax.crypto.SecretKey;

/**
 * Seed-at-rest vault: AndroidKeyStore AES-256-GCM key (NON-exportable —
 * the raw key never exists outside the keystore) + SeedCryptAes envelope.
 *
 * File format (app-private file): "MZAE1" magic + SeedCryptAes envelope.
 * Migration: a legacy PLAINTEXT seed file is validated, then encrypted in
 * place on first read (atomic: temp file + fsync + rename; the plaintext
 * bytes are gone after the rename). A failed migration is DEFERRED, not
 * fatal: the seed keeps working from memory and every later read retries;
 * a count-only Log.w records the deferral (never the seed itself), so
 * plaintext-at-rest never continues silently.
 *
 * Failure contract:
 * - save(): throws checked IOException ONLY (keystore/encryption problems
 *   are normalized, messages are content-free). The existing destination
 *   file is never removed before the new blob is atomically in place, so
 *   a failed write can never destroy the last valid seed.
 * - loadOrMigrate(): returns "" for "no seed available" (absent file,
 *   tampered/wrong-key/truncated envelope, garbage legacy content) —
 *   never a fabricated seed, never seed content in a message or log.
 */
public final class SeedVault {

    private static final String TAG = "SeedVault";
    public static final byte[] MAGIC = {'M', 'Z', 'A', 'E', '1'};
    static final String KEY_ALIAS = "maza_seed_wrap"; // package-visible: SettingsActivity wipe deletes the entry
    private static final String TMP_SUFFIX = ".tmp";
    private static final int[] MNEMONIC_LENGTHS = {12, 15, 18, 21, 24};
    /** Serializes seed writes process-wide: unique staging names + this
     *  lock make every publish atomic and crash-leftover sweeps safe. */
    private static final Object WRITE_LOCK = new Object();

    private SeedVault() {
    }

    /** Load the seed from file, migrating a legacy plaintext file in place. */
    public static String loadOrMigrate(Context act, String fileName) {
        File f = new File(act.getFilesDir(), fileName);
        byte[] blob;
        try {
            blob = readAll(f);
        } catch (IOException e) {
            return ""; // no seed yet
        }
        if (startsWith(blob, MAGIC)) {
            byte[] plain;
            try {
                plain = SeedCryptAes.decrypt(getKey(), trimMagic(blob));
            } catch (RuntimeException e) {
                // Wrong key / tampered / truncated envelope: never fabricate.
                return "";
            }
            String seed = new String(plain, java.nio.charset.StandardCharsets.UTF_8).trim();
            // Defense in depth: even a decrypting envelope must hold a
            // structurally valid mnemonic to be served.
            return isPlausibleMnemonic(seed) ? seed : "";
        }
        // Legacy plaintext file: validate its shape, then encrypt in place.
        String seed = new String(blob, java.nio.charset.StandardCharsets.UTF_8).trim();
        if (!isPlausibleMnemonic(seed)) {
            // Half-written / corrupted legacy file: serve nothing, migrate
            // nothing — the wallet shows unavailable rather than deriving
            // addresses from garbage.
            return "";
        }
        try {
            save(act, fileName, seed);
        } catch (IOException e) {
            // Keystore / encryption / disk failure: keep serving the seed
            // from memory this session and RETRY the migration on every
            // future read. Count-only log; never the seed itself.
            Log.w(TAG, "seed migration deferred; will retry on next read");
        }
        return seed;
    }

    /** Encrypt and atomically write the seed (magic + envelope).
     *  Failure contract: checked IOException only — keystore/encryption
     *  problems are normalized here so every caller (creation note,
     *  migration deferral) handles one checked type. The existing seed
     *  file survives ANY failed write.
     *  Concurrency: all writes serialize on a process-wide lock and stage
     *  through a UNIQUELY named temp file, so two concurrent writers can
     *  never share an inode and the rename always publishes one whole
     *  written-and-fsynced blob. The descriptor is closed before the
     *  rename (try-with-resources), so nothing retains an open fd on the
     *  staged inode after it becomes the destination. */
    public static void save(Context act, String fileName, String seed) throws IOException {
        if (!isPlausibleMnemonic(seed)) {
            // The vault must not persist what its own load path refuses.
            throw new IOException("seed rejected: not a plausible BIP39 mnemonic");
        }
        synchronized (WRITE_LOCK) {
            try {
                saveEncrypted(act, fileName, seed);
            } catch (IllegalStateException e) {
                // AndroidKeyStore unavailable / cipher failure — checked and
                // content-free; creation surfaces a note, migration defers.
                throw new IOException("seed encryption unavailable", e);
            }
        }
    }

    private static void saveEncrypted(Context act, String fileName, String seed)
            throws IOException {
        byte[] env = SeedCryptAes.encrypt(getKey(),
                seed.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        byte[] blob = new byte[MAGIC.length];
        System.arraycopy(MAGIC, 0, blob, 0, MAGIC.length);
        File dir = act.getFilesDir();
        File dst = new File(dir, fileName);
        File tmp = new File(dir, fileName + "." + java.util.UUID.randomUUID() + TMP_SUFFIX);
        // Sweep crash leftovers of PREVIOUS writers (safe under the lock:
        // every writer serializes here, so any matching tmp is stale).
        File[] stale = dir.listFiles();
        if (stale != null) {
            for (File s : stale) {
                String n = s.getName();
                if (n.startsWith(fileName + ".") && n.endsWith(TMP_SUFFIX)) {
                    s.delete();
                }
            }
        }
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            out.write(blob);
            out.write(env);
            out.flush();
            out.getFD().sync();
        } catch (IOException e) {
            tmp.delete(); // never leave a partial staging file behind
            throw e;
        }
        if (!tmp.renameTo(dst)) {
            // POSIX rename over an existing file is atomic and effectively
            // always succeeds within one directory; on the rare failure,
            // keep the OLD seed and clean the staging file — deleting dst
            // here would risk destroying the only copy of the seed.
            tmp.delete();
            throw new IOException("seed write failed; existing seed untouched");
        }
        fsyncDir(dir);
    }

    /** Best-effort directory fsync so the rename survives sudden power loss. */
    private static void fsyncDir(File dir) {
        try (java.io.FileInputStream in = new java.io.FileInputStream(dir)) {
            in.getFD().sync();
        } catch (IOException e) {
            // Best-effort: the file data is already fsynced and in place.
        }
    }

    /** Structural BIP39-English check: exactly 12/15/18/21/24 words, each
     *  lowercase a-z. Guards load and migration against serving garbage
     *  from a half-written legacy file. (Wordlist membership is enforced
     *  by the import UI; this structural gate needs no resources.) */
    static boolean isPlausibleMnemonic(String seed) {
        if (seed == null || seed.isEmpty()) {
            return false;
        }
        String[] words = seed.split("\\s+");
        boolean lenOk = false;
        for (int n : MNEMONIC_LENGTHS) {
            if (words.length == n) {
                lenOk = true;
            }
        }
        if (!lenOk) {
            return false;
        }
        for (String w : words) {
            if (!w.matches("[a-z]+")) {
                return false;
            }
        }
        return true;
    }

    private static SecretKey getKey() {
        try {
            KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
            ks.load(null);
            if (ks.containsAlias(KEY_ALIAS)) {
                return (SecretKey) ks.getKey(KEY_ALIAS, null);
            }
            KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build();
            javax.crypto.KeyGenerator kg = javax.crypto.KeyGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            kg.init(spec);
            return kg.generateKey();
        } catch (Exception e) {
            throw new IllegalStateException("AndroidKeyStore unavailable", e);
        }
    }

    private static boolean startsWith(byte[] data, byte[] prefix) {
        if (data == null || data.length < prefix.length) return false;
        for (int i = 0; i < prefix.length; i++) {
            if (data[i] != prefix[i]) return false;
        }
        return true;
    }

    private static byte[] trimMagic(byte[] blob) {
        byte[] out = new byte[blob.length - MAGIC.length];
        System.arraycopy(blob, 0, out, 0, out.length);
        return out;
    }

    private static byte[] readAll(File f) throws IOException {
        FileInputStream in = new FileInputStream(f);
        try {
            java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            int n;
            while ((n = in.read(chunk)) > 0) {
                buf.write(chunk, 0, n);
            }
            return buf.toByteArray();
        } finally {
            in.close();
        }
    }
}
