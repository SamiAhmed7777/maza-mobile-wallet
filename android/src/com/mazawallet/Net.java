package com.mazawallet;

import java.io.IOException;
import java.io.InterruptedIOException;
import java.net.ConnectException;
import java.net.NoRouteToHostException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.util.Locale;

/**
 * S-5 network hardening: ONE retry policy table for the whole walletbench API
 * surface, one uniform exponential backoff, and one transport-failure
 * classifier for the user-facing copy.
 *
 * <p>WHY A TABLE
 * -------------
 * Every call site used to decide retries on its own (the WALLET import retried
 * three times inside SelfCustody, everything else failed on the first throw).
 * That is how an interrupted network became an empty balance with no message.
 * Here the decision is data: {@link #routeFor(String, String)} answers
 * "how many attempts does this path get?" and {@link #withRetry} is the only
 * place a request is looped.
 *
 * <p>SPEND POSTS ARE NEVER RETRIED
 * -------------------------------
 * A retried {@code POST /api/send} or {@code POST /api/broadcast} can submit
 * the SAME signed transaction twice: the first attempt may well have reached
 * the node and only the response was lost. Those routes are registered with
 * exactly one attempt, and the caller reports "not confirmed - check HISTORY"
 * instead of trying again. Retrying is only ever safe for requests that do not
 * move funds: reads (GET) and the idempotent POSTs (unlock validates a token,
 * watch/import dedupes by address and returns 200 on re-import).
 *
 * <p>WHAT IS RETRIED
 * -----------------
 * Transport failures only - {@link IOException} from connect/read (offline,
 * unreachable, timeout, connection reset). HTTP status codes are NOT retried
 * here: a 401 means the session is gone (the caller returns to Connect), and a
 * 5xx is surfaced with copy while the 15s poll re-tries on its own schedule.
 * Hammering a failing server in a tight backoff loop is worse than showing the
 * user what happened.
 *
 * <p>UNKNOWN PATHS FAIL SAFE: an unregistered path gets ONE attempt. A new call
 * site that forgets the table can never double-submit anything.
 *
 * <p>PLATFORM ONLY: this class imports nothing from Android (java.io/java.net
 * exactly), so tests/test_w3_network_repaint.py compiles it standalone on the
 * desktop JVM and drives the real retry loop.
 */
public final class Net {

    private Net() {
    }

    /** First backoff gap. Attempt 1 -> 300ms, 2 -> 600ms, 3 -> 1200ms ... */
    public static final long BASE_BACKOFF_MS = 300L;
    /** Backoff ceiling, so a long retry chain cannot stall a worker for long. */
    public static final long MAX_BACKOFF_MS = 5000L;
    /** Attempts for a path that is not in the table: no retry, by design. */
    public static final int DEFAULT_ATTEMPTS = 1;

    /** No network at all (DNS resolution failed). */
    public static final int FAIL_OFFLINE = 1;
    /** Connected, but the server did not answer inside the read timeout. */
    public static final int FAIL_TIMEOUT = 2;
    /** Host resolved but nothing accepted the connection (refused / no route). */
    public static final int FAIL_UNREACHABLE = 3;
    /** Any other transport failure (reset, TLS, unknown). */
    public static final int FAIL_OTHER = 4;

    /** One registered API path and its retry policy. */
    public static final class Route {
        public final String method;
        public final String path;
        public final int attempts;
        /** True when the request moves funds: attempts must stay 1. */
        public final boolean spend;

        Route(String method, String path, int attempts, boolean spend) {
            this.method = method;
            this.path = path;
            this.attempts = attempts;
            this.spend = spend;
        }
    }

    /**
     * THE retry table. The WHOLE walletbench surface is wired through
     * {@link #withRetry}: MainActivity paths since the S-5 lane, and the
     * SelfCustody rows since the wave-3 integration fold (all six call sites
     * routed; see tests/test_w3_network_repaint.py SelfCustodyRoutesThroughNet).
     */
    private static final Route[] ROUTES = {
            // method, path, attempts, spend
            new Route("POST", "/api/unlock", 3, false),        // validates a token; side-effect free
            new Route("GET", "/api/state", 3, false),          // balance + history read
            new Route("GET", "/api/qr.png", 3, false),         // QR image (also ?addr= form)
            new Route("POST", "/api/send", 1, true),           // SPEND: never retried
            new Route("POST", "/api/broadcast", 1, true),      // SPEND: never retried (SelfCustody)
            new Route("POST", "/api/watch/import", 3, false),  // idempotent: dedupes addresses
            new Route("GET", "/api/watch/utxos", 3, false),    // read (SelfCustody)
            new Route("GET", "/api/watch/history", 3, false),  // read (SelfCustody)
            new Route("GET", "/api/price", 3, false),         // price for display (M26): a read
            new Route("GET", "/api/v0/address", 3, false),    // indexer address read
            new Route("GET", "/api/v0/tx", 3, false),         // indexer transaction read
            new Route("GET", "/api/v0/block", 3, false),      // indexer block read
            new Route("GET", "/api/v0/proof", 3, false),      // indexer merkle proof read (IDX-8)
    };

    /** A copy of the table, in order (tests and probes enumerate it). */
    public static Route[] routes() {
        Route[] copy = new Route[ROUTES.length];
        System.arraycopy(ROUTES, 0, copy, 0, ROUTES.length);
        return copy;
    }

    /**
     * Policy for one request. Unregistered paths get {@link #DEFAULT_ATTEMPTS}
     * and are never treated as spend (they simply do not get a second try).
     */
    public static Route routeFor(String method, String path) {
        String m = method == null ? "GET" : method.trim().toUpperCase(Locale.US);
        String p = normalizePath(path);
        for (int i = 0; i < ROUTES.length; i++) {
            if (ROUTES[i].method.equals(m) && ROUTES[i].path.equals(p)) return ROUTES[i];
        }
        return new Route(m, p, DEFAULT_ATTEMPTS, false);
    }

    /** Strips the query string and normalizes to a leading slash. */
    static String normalizePath(String path) {
        if (path == null) return "";
        int q = path.indexOf('?');
        String p = q >= 0 ? path.substring(0, q) : path;
        if (p.length() == 0 || p.charAt(0) != '/') p = "/" + p;
        return p;
    }

    /** One transport attempt, returning whatever the caller's client yields. */
    public interface Call<T> {
        T run() throws IOException;
    }

    /**
     * Runs {@code call} under the registered policy: attempts at most
     * {@code routeFor(method, path).attempts} times, sleeping the exponential
     * backoff between attempts, and rethrowing the LAST {@link IOException}
     * when the budget is gone. Spend routes therefore run exactly once.
     */
    public static <T> T withRetry(String method, String path, Call<T> call)
            throws IOException {
        return withRetry(method, path, call, BASE_BACKOFF_MS);
    }

    /** Test seam: same contract with a caller-supplied base backoff. */
    public static <T> T withRetry(String method, String path, Call<T> call,
            long baseBackoffMs) throws IOException {
        if (call == null) throw new IOException("no request supplied");
        int attempts = Math.max(1, routeFor(method, path).attempts);
        IOException last = null;
        for (int attempt = 1; attempt <= attempts; attempt++) {
            try {
                return call.run();
            } catch (IOException e) {
                last = e;
                if (attempt >= attempts) break;
                pause(backoffMs(attempt, baseBackoffMs));
            }
        }
        throw last; // always non-null: the loop only exits via return or catch
    }

    /** Backoff after a FAILED attempt N (1-based): base * 2^(N-1), capped. */
    public static long backoffMs(int attempt) {
        return backoffMs(attempt, BASE_BACKOFF_MS);
    }

    static long backoffMs(int attempt, long baseMs) {
        if (attempt < 1) return 0L;
        long delay = Math.max(1L, baseMs);
        for (int i = 1; i < attempt; i++) {
            if (delay >= MAX_BACKOFF_MS) break;
            delay *= 2L;
        }
        return Math.min(delay, MAX_BACKOFF_MS);
    }

    private static void pause(long ms) throws InterruptedIOException {
        if (ms <= 0) return;
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new InterruptedIOException("interrupted during retry backoff");
        }
    }

    /** Which user-facing copy a transport failure deserves. */
    public static int classify(IOException e) {
        if (e instanceof UnknownHostException) return FAIL_OFFLINE;
        if (e instanceof SocketTimeoutException) return FAIL_TIMEOUT;
        if (e instanceof ConnectException) return FAIL_UNREACHABLE;
        if (e instanceof NoRouteToHostException) return FAIL_UNREACHABLE;
        return FAIL_OTHER;
    }
}
