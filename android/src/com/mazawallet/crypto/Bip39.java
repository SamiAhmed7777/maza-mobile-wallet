package com.mazawallet.crypto;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

/**
 * BIP39: entropy <-> mnemonic (2048-word list), mnemonic -> 64-byte seed via
 * PBKDF2-HMAC-SHA512(2048). No android deps; the wordlist arrives as an
 * InputStream (Android: getResources().openRawResource(R.raw.bip39_english);
 * desktop SelfTest: FileInputStream).
 */
public final class Bip39 {

    public static final int WORDLIST_SIZE = 2048;

    private Bip39() {}

    /** Load the 2048-word list, one word per line, blank lines ignored. */
    public static String[] loadWordlist(InputStream in) throws IOException {
        List<String> words = new ArrayList<>();
        BufferedReader br = new BufferedReader(
                new InputStreamReader(in, StandardCharsets.UTF_8));
        String line;
        while ((line = br.readLine()) != null) {
            line = line.trim();
            if (!line.isEmpty()) words.add(line);
        }
        br.close();
        if (words.size() != WORDLIST_SIZE) {
            throw new IllegalArgumentException(
                    "wordlist must have 2048 words, got " + words.size());
        }
        return words.toArray(new String[0]);
    }

    /** entropy (16/20/24/28/32 bytes) -> space-joined mnemonic sentence. */
    public static String entropyToMnemonic(byte[] entropy, String[] wordlist) {
        if (entropy.length % 4 != 0 || entropy.length < 16 || entropy.length > 32) {
            throw new IllegalArgumentException("bad entropy length " + entropy.length);
        }
        int csBits = entropy.length * 8 / 32; // checksum length = ENT/32
        byte[] hash = sha256(entropy);
        // bits = entropy || first-csBits-of-hash, as one integer.
        java.math.BigInteger ent = new java.math.BigInteger(1, entropy);
        java.math.BigInteger cs = new java.math.BigInteger(1, hash)
                .shiftRight(256 - csBits);
        java.math.BigInteger bits = ent.shiftLeft(csBits).or(cs);
        int totalBits = entropy.length * 8 + csBits;
        int groups = totalBits / 11;
        StringBuilder sb = new StringBuilder();
        for (int i = groups - 1; i >= 0; i--) {
            int idx = bits.shiftRight(i * 11).and(java.math.BigInteger.valueOf(0x7FF))
                    .intValue();
            if (sb.length() > 0) sb.append(' ');
            sb.append(wordlist[idx]);
        }
        return sb.toString();
    }

    /** Split a mnemonic into lowercase words (any whitespace run). */
    public static String[] splitWords(String mnemonic) {
        return mnemonic.trim().toLowerCase(Locale.ROOT).split("\\s+");
    }

    /** True when every word is in the wordlist. */
    public static boolean isValidWords(String mnemonic, String[] wordlist) {
        Set<String> set = new HashSet<>(Arrays.asList(wordlist));
        String[] words = splitWords(mnemonic);
        if (words.length == 0) return false;
        for (String w : words) {
            if (!set.contains(w)) return false;
        }
        return true;
    }

    /** True when words are all valid AND the embedded checksum matches. */
    public static boolean isValidChecksum(String mnemonic, String[] wordlist) {
        String[] words = splitWords(mnemonic);
        if (words.length % 3 != 0 || !isValidWords(mnemonic, wordlist)) return false;
        // Rebuild the index bit stream.
        java.math.BigInteger bits = java.math.BigInteger.ZERO;
        for (String w : words) {
            int idx = Arrays.binarySearch(wordlist, w);
            if (idx < 0) return false;
            bits = bits.shiftLeft(11).or(java.math.BigInteger.valueOf(idx));
        }
        int csBits = words.length / 3; // 12 words -> 4 checksum bits
        int entBits = words.length * 11 - csBits;
        java.math.BigInteger cs = bits.and(java.math.BigInteger.ONE.shiftLeft(csBits)
                .subtract(java.math.BigInteger.ONE));
        byte[] entropy = bits.shiftRight(csBits)
                .toByteArray();
        // toByteArray may have a leading zero sign byte; take the low entBits/8.
        int entLen = entBits / 8;
        byte[] ent = new byte[entLen];
        System.arraycopy(entropy, Math.max(0, entropy.length - entLen), ent,
                Math.max(0, entLen - entropy.length), Math.min(entLen, entropy.length));
        byte[] hash = sha256(ent);
        java.math.BigInteger expectedCs = new java.math.BigInteger(1, hash)
                .shiftRight(256 - csBits);
        return cs.equals(expectedCs);
    }

    /**
     * mnemonic + passphrase -> 64-byte seed.
     * NFKD normalization per BIP39; salt = "mnemonic" + passphrase.
     */
    public static byte[] mnemonicToSeed(String mnemonic, String passphrase) {
        String normM = Normalizer.normalize(mnemonic, Normalizer.Form.NFKD);
        String normS = Normalizer.normalize("mnemonic" + passphrase,
                Normalizer.Form.NFKD);
        PBEKeySpec spec = new PBEKeySpec(normM.toCharArray(),
                normS.getBytes(StandardCharsets.UTF_8), 2048, 512);
        try {
            SecretKeyFactory skf =
                    SecretKeyFactory.getInstance("PBKDF2WithHmacSHA512");
            return skf.generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        } finally {
            spec.clearPassword();
        }
    }

    static byte[] sha256(byte[] data) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(data);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
