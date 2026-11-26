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
            long t0 = System.nanoTime();
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
            byte[] payload = readAll(in);
            // M24: one status line per request through this single choke
            // point. Route identity via Net.normalizePath (the same rule
            // the retry table keys on); headers/bodies never logged (the
            // token rides the Authorization header).
            AppLog.i(method + " " + Net.normalizePath(path) + " -> " + code
                    + " (" + (System.nanoTime() - t0) / 1_000_000L + "ms)");
            return new Resp(code, payload);
        } catch (IOException e) {
            // M25 (simplify pass): transport failures used to produce NO
            // console line - the most common failure mode was invisible.
            // Exception class name only; never e.getMessage().
            AppLog.w(method + " " + Net.normalizePath(path) + " -> FAIL "
                    + e.getClass().getSimpleName());
            throw e;
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

    /**
     * M26: outcome of one price read.
     *
     * {@code keep} is true when the read produced no new information (the
     * request failed, or the answer belongs to a session that has already
     * ended): the caller leaves the line untouched. Otherwise {@code quote}
     * is the quote to show, or null for "no source right now", which hides
     * the line.
     */
    public static final class Price {
        public static final Price KEEP = new Price(null, true, PricePoll.NOT_DUE);
        public final PriceLine.Quote quote;
        public final boolean keep;
        /** The session ticket the answer was recorded under. The paint
         *  repeats the check (PricePoll.isCurrent): a session can end
         *  between the read and the paint. KEEP carries no ticket. */
        public final long ticket;

        private Price(PriceLine.Quote quote, boolean keep, long ticket) {
            this.quote = quote;
            this.keep = keep;
            this.ticket = ticket;
        }
    }

    /**
     * M26: one price read. {@code ticket} is what PricePoll.due handed the
     * caller; the answer is remembered only while that is still the current
     * session, so a reply that arrives after an unlock never lands on the
     * new endpoint's screen. Runs on the caller's worker thread and never
     * throws: a display extra must not fail anything it rides on. A plain
     * GET, retried by Net like every other read.
     */
    public static Price readPrice(PricePoll poll, long ticket, String baseUrl,
            String token) {
        try {
            Resp r = Net.withRetry("GET", "/api/price",
                    () -> http(baseUrl, token, "GET", "/api/price", null));
            if (r.code == HttpURLConnection.HTTP_NOT_FOUND) {
                // An older bench has no such route: stop asking, show nothing.
                poll.retire(ticket);
                return poll.record(ticket, null) ? new Price(null, false, ticket)
                        : Price.KEEP;
            }
            if (r.code != HttpURLConnection.HTTP_OK) {
                throw new IOException("price HTTP " + r.code);
            }
            PriceLine.Quote quote = quoteOf(r.json());
            return poll.record(ticket, quote) ? new Price(quote, false, ticket)
                    : Price.KEEP;
        } catch (IOException | JSONException e) {
            // Class name only, never the message.
            AppLog.w("price unavailable " + e.getClass().getSimpleName());
            return Price.KEEP;
        }
    }

    /** The bench's answer, or null when it has no source right now. */
    private static PriceLine.Quote quoteOf(JSONObject body) {
        JSONObject p = body == null ? null : body.optJSONObject("price");
        if (p == null) return null;
        return new PriceLine.Quote(str(p, "usd"), str(p, "source"),
                str(p, "pair"), str(p, "last"), str(p, "quote"),
                p.optLong("age_s", 0), p.optBoolean("stale", false));
    }

    /** A JSON null or a missing key both read as Java null (never "null"). */
    private static String str(JSONObject o, String key) {
        return o.isNull(key) ? null : o.optString(key, null);
    }

    /** M25: route identity for log lines comes from Net (the retry table's
     *  own normalizer) - this class no longer keeps a second copy. */
}
