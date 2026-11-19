package com.mazawallet;

import android.content.SharedPreferences;

import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;

/** Read-only HTTP client for the lean chain indexer. */
public final class IndexerClient {
    public static final String KEY_INDEXER_URL = "indexer_url";

    private final String baseUrl;

    public IndexerClient(String baseUrl) {
        this.baseUrl = stripSlash(baseUrl);
    }

    /** Override wins; otherwise use the saved wallet endpoint's origin. */
    public static String configuredBase(SharedPreferences prefs) {
        String override = clean(prefs.getString(KEY_INDEXER_URL, ""));
        if (override.length() != 0) return validHttpBase(override);
        if (!prefs.contains(MainActivity.KEY_URL)) return null;
        String saved = clean(prefs.getString(MainActivity.KEY_URL, ""));
        if (saved.length() == 0) return null;
        try {
            URI uri = new URI(saved);
            String scheme = uri.getScheme();
            String host = uri.getHost();
            if (host == null || !("http".equalsIgnoreCase(scheme)
                    || "https".equalsIgnoreCase(scheme))) return null;
            URI origin = new URI(scheme.toLowerCase(), null, host, uri.getPort(),
                    null, null, null);
            return origin.toASCIIString() + "/indexer";
        } catch (URISyntaxException e) {
            return null;
        }
    }

    private static String validHttpBase(String value) {
        try {
            URI uri = new URI(value);
            if (uri.getHost() == null || !("http".equalsIgnoreCase(uri.getScheme())
                    || "https".equalsIgnoreCase(uri.getScheme()))) return null;
            return stripSlash(uri.toASCIIString());
        } catch (URISyntaxException e) {
            return null;
        }
    }

    public Api.Resp address(String address) throws IOException {
        return get("/api/v0/address", "/api/v0/address/" + address);
    }

    public Api.Resp transaction(String txid) throws IOException {
        return get("/api/v0/tx", "/api/v0/tx/" + txid);
    }

    public Api.Resp block(String height) throws IOException {
        return get("/api/v0/block", "/api/v0/block/" + height);
    }

    private Api.Resp get(String retryPath, String requestPath) throws IOException {
        return Net.withRetry("GET", retryPath,
                () -> Api.http(baseUrl, null, "GET", requestPath, null));
    }

    private static String clean(String value) {
        return value == null ? "" : value.trim();
    }

    private static String stripSlash(String value) {
        String out = clean(value);
        while (out.endsWith("/")) out = out.substring(0, out.length() - 1);
        return out;
    }
}
