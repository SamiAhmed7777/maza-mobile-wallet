package com.mazawallet;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Stateless Bearer-authed JSON HTTP shared by MainActivity (custodial bench
 * views) and SelfCustody (self-custody wallet). Every request carries
 * "Authorization: Bearer <token>"; the token never appears in URLs.
 */
public final class Api {

    private Api() {}

    /** Minimal HTTP response wrapper. */
    public static final class Resp {
        public final int code;
        public final byte[] body;

        Resp(int code, byte[] body) {
            this.code = code;
            this.body = body;
        }

        public String text() {
            return new String(body, StandardCharsets.UTF_8);
        }

        public JSONObject json() throws JSONException {
            return new JSONObject(text());
        }

        public String errorText() {
            try {
                return new JSONObject(text()).optString("error", "HTTP " + code);
            } catch (JSONException e) {
                return "HTTP " + code;
            }
        }
    }

    /** Body != null means POST (UTF-8 JSON). token may be null (no auth). */
    public static Resp http(String baseUrl, String token, String method,
            String path, JSONObject body) throws IOException {
        HttpURLConnection c =
                (HttpURLConnection) new URL(baseUrl + path).openConnection();
        try {
            c.setConnectTimeout(10000);
            c.setReadTimeout(15000);
            c.setRequestMethod(method);
            c.setRequestProperty("Accept", "application/json");
            if (token != null) {
                c.setRequestProperty("Authorization", "Bearer " + token);
            }
            if (body != null) {
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                c.getOutputStream().write(body.toString().getBytes("UTF-8"));
            }
            int code = c.getResponseCode();
            InputStream in = code >= HttpURLConnection.HTTP_BAD_REQUEST
                    ? c.getErrorStream() : c.getInputStream();
            return new Resp(code, readAll(in));
        } finally {
            c.disconnect();
        }
    }

    static byte[] readAll(InputStream in) throws IOException {
        if (in == null) return new byte[0];
        try {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] tmp = new byte[4096];
            int n;
            while ((n = in.read(tmp)) != -1) buf.write(tmp, 0, n);
            return buf.toByteArray();
        } finally {
            in.close();
        }
    }
}
