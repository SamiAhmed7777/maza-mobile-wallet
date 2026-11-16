package com.mazawallet;

import android.app.Activity;
import android.content.ClipboardManager;
import android.content.ClipData;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.Locale;

/**
 * MAZA Wallet (bench edition). Single activity, fully programmatic UI,
 * no external libraries. Auth is stateless: EVERY request (GET and POST)
 * carry "Authorization: Bearer <token>" (the app keeps no cookie jar).
 */
public class MainActivity extends Activity {

    private static final String PREFS = "maza";
    private static final String KEY_URL = "url";
    private static final String DEFAULT_URL = "http://100.121.150.22:18701"; // lane's SSH tunnel on dns2 tailnet IP — verified reachable from BlueStacks
    // NO default token: credentials are never baked into source or APK.
    private static final long POLL_MS = 15000;
    private static final int MAX_ROWS = 30;

    private static final int BG = 0xFF121418;
    private static final int CARD = 0xFF1E222B;
    private static final int TEXT = 0xFFE8EAF0;
    private static final int MUTED = 0xFF9AA0AC;
    private static final int ACCENT = 0xFFF7931A;
    private static final int RED = 0xFFE05555;
    private static final int GREEN = 0xFF4CAF50;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable pollTask = this::refresh;

    private SharedPreferences prefs;
    private String baseUrl;      // server URL, no trailing slash
    private String token;        // null while locked
    private String lastAddress = "";
    private double fee = 0.0001;

    // Connect card widgets.
    private EditText urlEt;
    private EditText tokenEt;
    private Button connectBtn;
    private TextView connectErr;

    // Wallet widgets.
    private TextView balanceTv;
    private TextView accountTv;
    private TextView addressTv;
    private ImageView qrIv;
    private TextView qrErrTv;
    private EditText toEt;
    private EditText amountEt;
    private Button sendBtn;
    private TextView sendResultTv;
    private LinearLayout historyList;
    private TextView statusTv;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        // Always start at the Connect card: the token is entered per session
        // (bench edition keeps it memory-only; no stored credentials, no
        // auto-attempt).
        showConnect("");
    }

    @Override
    protected void onDestroy() {
        ui.removeCallbacks(pollTask);
        super.onDestroy();
    }

    // ------------------------------------------------------------------ UI

    private void showConnect(String message) {
        ui.removeCallbacks(pollTask);
        token = null;

        LinearLayout col = column();
        col.setPadding(dp(20), dp(32), dp(20), dp(20));
        ScrollView root = new ScrollView(this);
        root.setBackgroundColor(BG);
        root.addView(col, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(root);

        col.addView(label("MAZA Wallet", 28, TEXT, Typeface.BOLD));
        col.addView(label("Connect to your bench server", 14, MUTED, Typeface.NORMAL));

        LinearLayout card = card();
        col.addView(card, mp(0, dp(24), 0, 0));

        card.addView(label("Server URL", 13, MUTED, Typeface.BOLD));
        urlEt = input(prefs.getString(KEY_URL, DEFAULT_URL),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        card.addView(urlEt, mp(0, 0, 0, 0));

        card.addView(label("Token", 13, MUTED, Typeface.BOLD), mp(0, dp(12), 0, 0));
        tokenEt = input("", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        tokenEt.setHint("bench token");
        card.addView(tokenEt, mp(0, 0, 0, 0));

        connectErr = label("", 13, RED, Typeface.NORMAL);
        card.addView(connectErr, mp(0, dp(8), 0, 0));
        if (message.length() > 0) connectErr.setText(message);

        connectBtn = new Button(this);
        connectBtn.setText("Connect");
        connectBtn.setOnClickListener(v -> doUnlock());
        card.addView(connectBtn, mp(0, dp(8), 0, 0));
    }

    private void showWallet() {
        LinearLayout col = column();
        col.setPadding(dp(16), dp(28), dp(16), dp(24));
        ScrollView root = new ScrollView(this);
        root.setBackgroundColor(BG);
        root.addView(col, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(root);

        // 1. Header: coin glyph + title + refresh.
        LinearLayout header = row();
        TextView glyph = label("M", 18, 0xFFFFFFFF, Typeface.BOLD);
        glyph.setGravity(Gravity.CENTER);
        GradientDrawable coin = new GradientDrawable();
        coin.setShape(GradientDrawable.OVAL);
        coin.setColor(ACCENT);
        glyph.setBackground(coin);
        header.addView(glyph, new LinearLayout.LayoutParams(dp(36), dp(36)));
        LinearLayout.LayoutParams titleLp =
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        titleLp.leftMargin = dp(10);
        header.addView(label("MAZA Wallet", 22, TEXT, Typeface.BOLD), titleLp);
        Button refreshBtn = new Button(this);
        refreshBtn.setText("Refresh");
        refreshBtn.setOnClickListener(v -> refresh());
        header.addView(refreshBtn);
        col.addView(header);

        // 2. Balance.
        balanceTv = label("...", 34, TEXT, Typeface.BOLD);
        col.addView(balanceTv, mp(0, dp(16), 0, 0));
        accountTv = label("", 13, MUTED, Typeface.NORMAL);
        col.addView(accountTv);

        // 3. Receive card.
        LinearLayout receive = card();
        col.addView(receive, mp(0, dp(16), 0, 0));
        receive.addView(label("RECEIVE", 13, ACCENT, Typeface.BOLD));
        addressTv = mono("...", 14, TEXT);
        receive.addView(addressTv, mp(0, dp(6), 0, 0));
        LinearLayout receiveRow = row();
        Button copyBtn = new Button(this);
        copyBtn.setText("Copy");
        copyBtn.setOnClickListener(v -> copyAddress());
        receiveRow.addView(copyBtn);
        qrErrTv = label("", 12, RED, Typeface.NORMAL);
        receiveRow.addView(qrErrTv, mp(dp(10), 0, 0, 0));
        receive.addView(receiveRow, mp(0, dp(6), 0, 0));
        qrIv = new ImageView(this);
        LinearLayout.LayoutParams qrLp = new LinearLayout.LayoutParams(dp(220), dp(220));
        qrLp.gravity = Gravity.CENTER_HORIZONTAL;
        qrLp.topMargin = dp(6);
        receive.addView(qrIv, qrLp);

        // 4. Send card.
        LinearLayout send = card();
        col.addView(send, mp(0, dp(16), 0, 0));
        send.addView(label("SEND", 13, ACCENT, Typeface.BOLD));
        toEt = input("", InputType.TYPE_CLASS_TEXT);
        toEt.setHint("Recipient address (M...)");
        toEt.setTypeface(Typeface.MONOSPACE);
        send.addView(toEt, mp(0, dp(4), 0, 0));
        amountEt = input("", InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        amountEt.setHint("Amount (MAZA)");
        send.addView(amountEt, mp(0, dp(4), 0, 0));
        sendBtn = new Button(this);
        sendBtn.setText("Send");
        sendBtn.setOnClickListener(v -> doSend());
        send.addView(sendBtn, mp(0, dp(4), 0, 0));
        sendResultTv = label("Fee per send: " + fmtAmount(fee) + " MAZA", 13, MUTED,
                Typeface.NORMAL);
        send.addView(sendResultTv, mp(0, dp(2), 0, 0));

        // 5. History list + status line.
        col.addView(label("HISTORY", 13, ACCENT, Typeface.BOLD), mp(0, dp(18), 0, dp(4)));
        historyList = column();
        col.addView(historyList);
        statusTv = label("", 12, MUTED, Typeface.NORMAL);
        col.addView(statusTv, mp(0, dp(12), 0, 0));

        loadQr();
        schedulePoll();
    }

    // ------------------------------------------------------------- actions

    private void doUnlock() {
        final String url = stripSlash(urlEt.getText().toString().trim());
        final String tok = tokenEt.getText().toString().trim();
        if (url.length() == 0 || tok.length() == 0) {
            connectErr.setText("Enter server URL and token.");
            return;
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            connectErr.setText("URL must start with http:// or https://");
            return;
        }
        connectBtn.setEnabled(false);
        connectErr.setTextColor(MUTED);
        connectErr.setText("Connecting...");
        new Thread(() -> {
            String err = null;
            try {
                baseUrl = url;
                token = tok;
                JSONObject body = new JSONObject().put("token", tok);
                Resp r = http("POST", "/api/unlock", body);
                if (r.code == 200) {
                    prefs.edit().putString(KEY_URL, url).apply();
                    ui.post(() -> {
                        showWallet();
                        refresh();
                    });
                    return;
                }
                err = r.code == 401 ? "Invalid token." : r.errorText();
            } catch (IOException e) {
                err = "Cannot reach server: " + e.getMessage();
            } catch (JSONException e) {
                err = "Bad response: " + e.getMessage();
            }
            final String msg = err;
            ui.post(() -> {
                token = null;
                connectErr.setTextColor(RED);
                connectErr.setText(msg);
                connectBtn.setEnabled(true);
            });
        }, "unlock").start();
    }

    private void doSend() {
        final String to = toEt.getText().toString().trim();
        final String amtStr = amountEt.getText().toString().trim();
        if (to.length() == 0 || amtStr.length() == 0) {
            sendResult("Enter address and amount.", RED);
            return;
        }
        final double amt;
        try {
            amt = Double.parseDouble(amtStr);
        } catch (NumberFormatException e) {
            sendResult("Invalid amount.", RED);
            return;
        }
        if (amt <= 0 || Double.isFinite(amt) == false) {
            sendResult("Amount must be positive.", RED);
            return;
        }
        sendBtn.setEnabled(false);
        sendResult("Sending...", MUTED);
        new Thread(() -> {
            String msg;
            int color;
            try {
                JSONObject body = new JSONObject().put("to", to).put("amount", amt);
                Resp r = http("POST", "/api/send", body);
                if (r.code == 200) {
                    msg = "Sent: tx " + shortTxid(r.json().optString("txid", ""));
                    color = GREEN;
                    ui.post(this::refresh);
                } else if (r.code == 401) {
                    ui.post(this::lockOut);
                    return;
                } else {
                    msg = r.errorText();
                    color = RED;
                }
            } catch (IOException e) {
                msg = "Network error: " + e.getMessage();
                color = RED;
            } catch (JSONException e) {
                msg = "Bad server response.";
                color = RED;
            }
            final String m = msg;
            final int c = color;
            ui.post(() -> {
                sendResult(m, c);
                sendBtn.setEnabled(true);
            });
        }, "send").start();
    }

    private void refresh() {
        if (token == null) return;
        ui.removeCallbacks(pollTask);
        final String t = token;
        new Thread(() -> {
            try {
                Resp r = http("GET", "/api/state", null);  // Bearer header, never the token in URLs
                if (r.code == 401) {
                    ui.post(this::lockOut);
                    return;
                }
                if (r.code != 200) {
                    ui.post(() -> {
                        note("Update failed: " + r.errorText());
                        schedulePoll();
                    });
                    return;
                }
                final WalletState ws = WalletState.parse(r.text());
                ui.post(() -> {
                    applyState(ws);
                    schedulePoll();
                });
            } catch (IOException e) {
                ui.post(() -> {
                    note("Update failed: " + e.getMessage());
                    schedulePoll();
                });
            } catch (JSONException e) {
                ui.post(() -> {
                    note("Bad response from server.");
                    schedulePoll();
                });
            }
        }, "state").start();
    }

    private void applyState(WalletState ws) {
        fee = ws.fee;
        balanceTv.setText(fmtAmount(ws.balance) + " MAZA");
        accountTv.setText("account " + ws.account + " - fee " + fmtAmount(ws.fee) + " MAZA");
        if (ws.address.equals(lastAddress) == false) {
            lastAddress = ws.address;
            addressTv.setText(ws.address);
            loadQr();
        }
        historyList.removeAllViews();
        int n = Math.min(ws.txs.size(), MAX_ROWS);
        if (n == 0) {
            historyList.addView(label("No transactions yet.", 13, MUTED, Typeface.NORMAL));
        }
        for (int i = 0; i < n; i++) {
            historyList.addView(txRow(ws.txs.get(i)));
        }
        note("Updated " + new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date()));
    }

    private View txRow(Tx t) {
        boolean send = "send".equals(t.category);
        String arrow = send ? "->" : "<-";
        String sign = send ? "-" : "+";
        LinearLayout box = column();
        box.addView(label(arrow + " " + sign + fmtAmount(Math.abs(t.amount)) + " MAZA ("
                + t.confs + " confs)", 14, TEXT, Typeface.NORMAL));
        box.addView(label(relTime(t.time), 12, MUTED, Typeface.NORMAL));
        box.setLayoutParams(mp(0, dp(8), 0, 0));
        return box;
    }

    private void copyAddress() {
        String a = addressTv.getText().toString();
        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (cm == null) return;
        cm.setPrimaryClip(ClipData.newPlainText("MAZA address", a));
        Toast.makeText(this, "Address copied", Toast.LENGTH_SHORT).show();
    }

    private void loadQr() {
        if (token == null) return;
        qrErrTv.setText("Loading QR...");
        qrErrTv.setTextColor(MUTED);
        final String t = token;
        new Thread(() -> {
            try {
                Resp r = http("GET", "/api/qr.png", null);  // Bearer header, no token in URL
                if (r.code != 200) {
                    ui.post(() -> qrErr("QR unavailable (HTTP " + r.code + ")"));
                    return;
                }
                final Bitmap bmp = BitmapFactory.decodeByteArray(r.body, 0, r.body.length);
                if (bmp == null) {
                    ui.post(() -> qrErr("Bad QR image"));
                    return;
                }
                ui.post(() -> {
                    qrIv.setImageBitmap(bmp);
                    qrErrTv.setText("");
                });
            } catch (IOException e) {
                ui.post(() -> qrErr("QR load failed"));
            }
        }, "qr").start();
    }

    private void qrErr(String m) {
        qrErrTv.setText(m);
        qrErrTv.setTextColor(RED);
    }

    private void lockOut() {
        token = null;
                showConnect("Session expired - please reconnect.");
    }

    private void sendResult(String msg, int color) {
        sendResultTv.setText(msg);
        sendResultTv.setTextColor(color);
    }

    private void note(String m) {
        if (statusTv != null) statusTv.setText(m);
    }

    private void schedulePoll() {
        ui.removeCallbacks(pollTask);
        ui.postDelayed(pollTask, POLL_MS);
    }

    // ----------------------------------------------------------- network

    /** Minimal stateless HTTP. Body != null means POST with Bearer auth. */
    private Resp http(String method, String path, JSONObject body) throws IOException {
        HttpURLConnection c =
                (HttpURLConnection) new URL(baseUrl + path).openConnection();
        try {
            c.setConnectTimeout(10000);
            c.setReadTimeout(15000);
            c.setRequestMethod(method);
            c.setRequestProperty("Accept", "application/json");
            // Bearer on EVERY request (GETs included) — never the token in URLs.
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

    private static byte[] readAll(InputStream in) throws IOException {
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

    static final class Resp {
        final int code;
        final byte[] body;

        Resp(int code, byte[] body) {
            this.code = code;
            this.body = body;
        }

        String text() {
            return new String(body, StandardCharsets.UTF_8);
        }

        JSONObject json() throws JSONException {
            return new JSONObject(text());
        }

        String errorText() {
            try {
                return new JSONObject(text()).optString("error", "HTTP " + code);
            } catch (JSONException e) {
                return "HTTP " + code;
            }
        }
    }

    static final class WalletState {
        double balance;
        String address = "";
        String account = "";
        double fee = 0.0001;
        final ArrayList<Tx> txs = new ArrayList<>();

        static WalletState parse(String body) throws JSONException {
            JSONObject o = new JSONObject(body);
            WalletState w = new WalletState();
            w.balance = o.optDouble("balance", 0);
            w.address = o.optString("address", "");
            w.account = o.optString("account", "");
            w.fee = o.optDouble("fee", 0.0001);
            JSONArray arr = o.optJSONArray("txs");
            if (arr != null) {
                for (int i = 0; i < arr.length(); i++) {
                    JSONObject t = arr.optJSONObject(i);
                    if (t != null) w.txs.add(Tx.of(t));
                }
            }
            return w;
        }
    }

    static final class Tx {
        String category;
        double amount;
        int confs;
        long time;

        static Tx of(JSONObject o) {
            Tx t = new Tx();
            t.category = o.optString("category", "");
            t.amount = o.optDouble("amount", 0);
            t.confs = o.optInt("confirmations", 0);
            t.time = o.optLong("time", 0);
            return t;
        }
    }

    // ------------------------------------------------------------- helpers

    private int dp(float v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private LinearLayout column() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    private LinearLayout row() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        return l;
    }

    private LinearLayout card() {
        LinearLayout c = column();
        c.setBackground(rounded(CARD));
        int p = dp(16);
        c.setPadding(p, p, p, p);
        return c;
    }

    private GradientDrawable rounded(int color) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(12));
        return g;
    }

    private TextView label(String s, int size, int color, int style) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(size);
        t.setTextColor(color);
        t.setTypeface(Typeface.DEFAULT, style);
        return t;
    }

    private TextView mono(String s, int size, int color) {
        TextView t = label(s, size, color, Typeface.NORMAL);
        t.setTypeface(Typeface.MONOSPACE);
        return t;
    }

    private EditText input(String text, int inputType) {
        EditText e = new EditText(this);
        e.setText(text);
        e.setTextColor(TEXT);
        e.setHintTextColor(MUTED);
        e.setSingleLine(true);
        e.setInputType(inputType);
        return e;
    }

    private LinearLayout.LayoutParams mp(int l, int t, int r, int b) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(l, t, r, b);
        return lp;
    }

    private static String stripSlash(String u) {
        while (u.endsWith("/")) u = u.substring(0, u.length() - 1);
        return u;
    }

    private static String fmtAmount(double v) {
        return BigDecimal.valueOf(v).setScale(8, RoundingMode.HALF_UP)
                .stripTrailingZeros().toPlainString();
    }

    private static String shortTxid(String txid) {
        return txid.length() > 12
                ? txid.substring(0, 6) + ".." + txid.substring(txid.length() - 4)
                : txid;
    }

    private static String relTime(long unix) {
        long diff = Math.max(0, System.currentTimeMillis() / 1000 - unix);
        if (diff < 60) return "just now";
        if (diff < 3600) return (diff / 60) + "m ago";
        if (diff < 86400) return (diff / 3600) + "h ago";
        return (diff / 86400) + "d ago";
    }
}
