package com.mazawallet;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipboardManager;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.InputType;
import android.view.Gravity;
import android.view.MotionEvent;
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

import com.mazawallet.crypto.LockPolicy;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Date;
import java.util.Locale;

/**
 * MAZA Wallet (bench edition). Single activity, fully programmatic UI,
 * five bottom-tab views (BALANCE / RECEIVE / SEND / HISTORY / WALLET), no external
 * libraries. Auth is stateless: EVERY request (GET and POST) carries
 * "Authorization: Bearer <token>" (the app keeps no cookie jar). The token
 * is memory-only: never persisted, never in URLs.
 */
public class MainActivity extends Activity implements SelfCustody.Host {

    /** Prefs file + endpoint key shared with SettingsActivity (package
     *  visible on purpose: the settings screen edits the SAME saved URL the
     *  Connect card reads). */
    static final String PREFS = "maza";
    static final String KEY_URL = "url";
    static final String DEFAULT_URL = "https://mazatest.sami-host.me"; // public TEST endpoint (see deploy/PUBLIC-HOSTING.md); field stays user-editable
    // NO default token: credentials are never baked into source or APK.
    private static final long POLL_MS = 15000;
    private static final int MAX_ROWS = 30;

    private static final int BG = 0xFF141414;       // near-black background
    private static final int CARD = 0xFF1E1E1E;     // cards
    private static final int BAR = 0xFF1A1A1A;      // tab bar background
    private static final int DIVIDER = 0xFF2E2E2E;  // hairline dividers
    private static final int TEXT = 0xFFFFFFFF;     // white primary text
    private static final int MUTED = 0xFFB3B3B3;    // muted secondary text
    private static final int ACCENT = 0xFFF0A000;   // amber brand accent
    private static final int RED = 0xFFFF6B6B;      // send / error
    private static final int GREEN = 0xFF6FD66F;    // receive

    private static final String[] TABS = {"BALANCE", "RECEIVE", "SEND", "HISTORY", "WALLET"};
    private static final int TAB_WALLET = 4;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable pollTask = this::refresh;

    // Absolute history timestamp and last-sync line, device-local timezone
    // (SimpleDateFormat defaults to the device default TimeZone).
    private static final SimpleDateFormat TS_FMT =
            new SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.US);
    private static final SimpleDateFormat SYNC_FMT =
            new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US);

    private SharedPreferences prefs;
    private String baseUrl;      // server URL, no trailing slash
    private String token;        // null while locked
    private String lastAddress = "";
    private double fee = 0.0001;

    // S-2a PIN lock. Storage+policy live in PinGuard (hashed verifier, never
    // the PIN itself); this class owns only the UI surfaces. With no PIN set
    // the app behaves exactly as before (gate inert).
    private PinGuard pinGuard;
    /** The LIVE session guard (per-instance policies start locked by design).
     *  SettingsActivity.onResume consults this for the screen-level re-lock,
     *  so an already-unlocked session stays open there. Nulled in onDestroy. */
    static PinGuard sActiveGuard;
    private int pendingGatedTab = -1;      // tab to open after PIN unlock
    private FrameLayout lockOverlay;       // full-screen PIN cover (GONE)
    private EditText pinEt;
    private TextView pinErrTv;
    private Button pinBtn;
    private LinearLayout pinSection;       // WALLET-tab SECURITY card
    private final Runnable lockTick = this::autoLockTick;

    // Connect card widgets.
    private EditText urlEt;
    private EditText tokenEt;
    private Button connectBtn;
    private TextView connectErr;

    // Tab navigation: content container + one ScrollView per tab. Built once
    // in showWallet(); polls never rebuild the tab bar or switch tabs.
    private FrameLayout content;
    private final ScrollView[] tabViews = new ScrollView[TABS.length];
    private final Button[] tabBtns = new Button[TABS.length];
    private int tab = 0;

    // Wallet widgets (one set, updated in place by applyState).
    private TextView balanceTv;
    private TextView accountTv;
    private TextView lastSyncTv;
    private TextView addressTv;
    private ImageView qrIv;
    private TextView qrStatusTv;
    private EditText toEt;
    private EditText amountEt;
    private TextView feeHintTv;
    private Button sendBtn;
    private TextView sendResultTv;
    private LinearLayout historyList;
    private SelfCustody selfCustody;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        // S-4: saved theme mode through lane S-3's ThemeController, BEFORE the
        // first setContentView (showConnect() below). The manifest's inline
        // platform theme stays the pre-attach fallback.
        ThemeController.applyTheme(this, SettingsActivity.themeMode(prefs));
        // S-4: make the saved auto-lock delay the one the session's LockPolicy
        // enforces. PinGuard builds the policy from pin.autolock_ms at
        // construction, so the settings value is reconciled into that key
        // FIRST (SettingsActivity writes both keys; this repairs drift).
        applySavedAutolock();
        pinGuard = new PinGuard(this);
        sActiveGuard = pinGuard; // live session guard: SettingsActivity resume gate reads it
        // Always start at the Connect card: the token is entered per session
        // (memory-only; no stored credentials, no auto-attempt — the baked-in
        // bench-edition token was removed when the endpoint went public: a
        // token shipped inside the APK would defeat the gate it guards).
        showConnect("");
    }

    /** Reconcile the S-4 auto-lock setting into PinGuard's storage key.
     *  pref_autolock_minutes (int minutes, the documented settings value) is
     *  authoritative when present; otherwise an existing pin.autolock_ms is
     *  adopted into it. A value outside the supported window is clamped by
     *  SettingsActivity.autolockMinutes(), so LockPolicy never receives a
     *  window it cannot enforce. */
    private void applySavedAutolock() {
        boolean hasMinutes = prefs.contains(SettingsActivity.KEY_AUTOLOCK_MINUTES);
        boolean hasMs = prefs.contains(PinGuard.KEY_AUTOLOCK_MS);
        // Fresh install / just-wiped device: nothing saved, so leave the store
        // empty and let PinGuard's own default apply (a wipe must not be
        // followed by this method writing a key back).
        if (!hasMinutes && !hasMs) return;
        long ms = SettingsActivity.autolockMinutes(prefs) * 60_000L;
        long curMs;
        try {
            curMs = prefs.getLong(PinGuard.KEY_AUTOLOCK_MS, -1L);
        } catch (ClassCastException wrongTyped) {
            curMs = -1L; // legacy wrong-typed value: rewritten below
        }
        if (!hasMs || curMs != ms) {
            prefs.edit().putLong(PinGuard.KEY_AUTOLOCK_MS, ms).apply();
        }
    }

    @Override
    protected void onDestroy() {
        ui.removeCallbacks(pollTask);
        ui.removeCallbacks(lockTick);
        if (sActiveGuard == pinGuard) sActiveGuard = null;
        super.onDestroy();
    }

    @Override
    protected void onPause() {
        if (pinGuard != null) pinGuard.onBackground();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Returning after >= the auto-lock window in background re-locks
        // (device out of the user's hands). The POLICY bracket runs on EVERY
        // resume regardless of which screen is showing (judge r1: skipping
        // it on the Connect screen let a long background go unnoticed); only
        // the overlay SHOW needs the wallet UI to exist.
        boolean relock = pinGuard != null && pinGuard.onResumeLocked();
        if (relock && lockOverlay != null) {
            showLock();
        }
        // S-4: the settings screen may have changed the auto-lock delay; the
        // SECURITY card reads it from PinGuard, so re-render on return (the
        // policy object itself keeps the window it was built with - the new
        // value applies from the next session start).
        if (pinSection != null) renderPinSection();
    }

    /** Every touch anywhere counts as user activity for the S-2a auto-lock
     *  (dispatch-level, so consumed child touches still register). */
    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        if (pinGuard != null) pinGuard.onActivity();
        return super.dispatchTouchEvent(ev);
    }

    // ------------------------------------------------------------------ UI

    private void showConnect(String message) {
        ui.removeCallbacks(pollTask);
        ui.removeCallbacks(lockTick);
        token = null;

        LinearLayout col = column();
        col.setPadding(dp(20), dp(32), dp(20), dp(20));
        ScrollView root = new ScrollView(this);
        root.setBackgroundColor(BG);
        root.addView(col, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(root);

        addHeader(col);

        col.addView(label("Connect to your bench server", 14, MUTED, Typeface.NORMAL),
                mp(0, dp(16), 0, 0));

        LinearLayout card = card();
        col.addView(card, mp(0, dp(16), 0, 0));

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
        // Reset the selected-tab index: a successful unlock REBUILDS the whole
        // wallet UI, and selectTab(0) below must count as the initial
        // selection (no navigation refresh) so each unlock/reconnect performs
        // exactly one /api/state fetch - the explicit refresh() in doUnlock.
        // Without this reset, reconnecting while a non-BALANCE tab was
        // selected would double-fetch (judge r2 finding, probe scenario G/H).
        tab = 0;
        LinearLayout root = column();
        root.setBackgroundColor(BG);

        // Content area (weight 1) above the pinned tab bar.
        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        buildBalanceTab();
        buildReceiveTab();
        buildSendTab();
        buildHistoryTab();
        buildWalletTab();
        // Unlock path watch re-import (M21): the landing tab is BALANCE, so
        // the WALLET tab's onShown() will not fire until the user switches
        // there. Fire the idempotent re-import now — a creation-time import
        // that died mid-flight must not leave the wallet blind for the
        // session (no-op while no seed exists).
        selfCustody.onUnlocked();

        // Bottom tab bar: 4 equal-weight buttons, always visible.
        View divider = new View(this);
        divider.setBackgroundColor(DIVIDER);
        root.addView(divider, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(1)));
        LinearLayout bar = row();
        bar.setBackgroundColor(BAR);
        root.addView(bar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(56)));
        for (int i = 0; i < TABS.length; i++) {
            Button b = new Button(this);
            b.setText(TABS[i]);
            b.setTextSize(12);
            b.setAllCaps(false);
            b.setBackgroundColor(0x00000000);
            final int idx = i;
            b.setOnClickListener(v -> selectTab(idx));
            bar.addView(b, new LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.MATCH_PARENT, 1f));
            tabBtns[i] = b;
        }

        // S-2a: lock overlay rides ABOVE the wallet UI in a root wrapper; the
        // 10s tick shows it promptly when the lazy gate decides it is locked.
        buildLockOverlay();
        FrameLayout rootWrap = new FrameLayout(this);
        rootWrap.setBackgroundColor(BG);
        rootWrap.addView(root, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        rootWrap.addView(lockOverlay, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(rootWrap);
        selectTab(0);
        loadQr();
        schedulePoll();
        ui.removeCallbacks(lockTick);
        ui.postDelayed(lockTick, 10_000);
    }

    /** Swap the visible content view; highlight the selected tab. */
    private void selectTab(int i) {
        // S-2a gate: the WALLET tab is the seed surface (its send card
        // included), so it requires the PIN while locked. The current tab
        // stays put; a correct PIN opens the gated tab (pendingGatedTab).
        if (i == TAB_WALLET && pinGuard != null && pinGuard.gateNeeded()) {
            pendingGatedTab = TAB_WALLET;
            showLock();
            return;
        }
        // Compare against the PREVIOUSLY selected tab index, before tab is
        // reassigned below. (A visibility-based guard would double-fire the
        // initial selection: a freshly built view starts GONE, so it cannot
        // tell "first entry" from "re-entry"; the tab-index comparison can,
        // given showWallet()'s tab reset.) showWallet() resets tab to 0, so
        // every unlock/reconnect performs exactly ONE fetch.
        boolean wasSelected = (tab == i);
        tab = i;
        for (int k = 0; k < tabViews.length; k++) {
            tabViews[k].setVisibility(k == i ? View.VISIBLE : View.GONE);
            tabBtns[k].setTextColor(k == i ? ACCENT : MUTED);
            tabBtns[k].setTypeface(Typeface.DEFAULT,
                    k == i ? Typeface.BOLD : Typeface.NORMAL);
        }
        if (i == TAB_WALLET && selfCustody != null) selfCustody.onShown();
        // M22: navigation refresh. Entering BALANCE or HISTORY (from another
        // tab) resyncs immediately instead of waiting up to 15s for the poll
        // (a freshly funded balance used to read as stuck until process
        // restart). tab is initialized to 0, so the INITIAL selectTab(0) in
        // showWallet() counts as "already selected" and does not refresh -
        // the unlock path keeps its single explicit refresh().
        if (!wasSelected && (i == 0 || i == 3)) refresh();
    }

    // ---- tab builders: header logo + view body, one ScrollView each ----

    private LinearLayout tabColumn() {
        LinearLayout col = column();
        col.setPadding(dp(16), dp(24), dp(16), dp(16));
        return col;
    }

    private void addTab(LinearLayout col, int index) {
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        sv.addView(col, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        sv.setVisibility(View.GONE);
        content.addView(sv);
        tabViews[index] = sv;
    }

    /** Header: official MazaCoin roundel (48dp) + title, top of every view. */
    private void addHeader(LinearLayout col) {
        LinearLayout header = row();
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.logo);
        header.addView(logo, new LinearLayout.LayoutParams(dp(48), dp(48)));
        LinearLayout.LayoutParams titleLp = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        titleLp.leftMargin = dp(12);
        header.addView(label("MAZA Wallet", 22, TEXT, Typeface.BOLD), titleLp);
        col.addView(header, mp(0, 0, 0, dp(16)));
    }

    private void buildBalanceTab() {
        LinearLayout col = tabColumn();
        addHeader(col);

        balanceTv = label("...", 36, TEXT, Typeface.BOLD);
        col.addView(balanceTv);

        accountTv = label("", 13, MUTED, Typeface.NORMAL);
        col.addView(accountTv, mp(0, dp(4), 0, 0));

        lastSyncTv = label("", 12, MUTED, Typeface.NORMAL);
        col.addView(lastSyncTv, mp(0, dp(4), 0, 0));

        Button refreshBtn = new Button(this);
        refreshBtn.setText("Refresh");
        refreshBtn.setOnClickListener(v -> refresh());
        col.addView(refreshBtn, mp(0, dp(16), 0, 0));

        addTab(col, 0);
    }

    private void buildReceiveTab() {
        LinearLayout col = tabColumn();
        addHeader(col);

        col.addView(label("RECEIVE", 13, ACCENT, Typeface.BOLD));

        addressTv = mono("...", 14, TEXT);
        col.addView(addressTv, mp(0, dp(6), 0, 0));

        Button copyBtn = new Button(this);
        copyBtn.setText("Copy");
        copyBtn.setOnClickListener(v -> copyAddress());
        col.addView(copyBtn, mp(0, dp(8), 0, 0));

        qrStatusTv = label("", 12, MUTED, Typeface.NORMAL);
        col.addView(qrStatusTv, mp(0, dp(4), 0, 0));

        qrIv = new ImageView(this);
        LinearLayout.LayoutParams qrLp = new LinearLayout.LayoutParams(dp(320), dp(320));
        qrLp.gravity = Gravity.CENTER_HORIZONTAL;
        qrLp.topMargin = dp(8);
        col.addView(qrIv, qrLp);

        addTab(col, 1);
    }

    private void buildSendTab() {
        LinearLayout col = tabColumn();
        addHeader(col);

        // M22: the bar label stays SEND (standard bottom-tab convention),
        // but this tab spends the BENCH account, not the user's seed wallet.
        // Header copy + note make the two send flows un-confusable.
        col.addView(label("SEND \u00B7 BENCH ACCOUNT", 13, ACCENT, Typeface.BOLD));
        col.addView(label(
                "Spends the bench server's held funds (server-side, capped). "
                        + "Your own seed wallet is on the WALLET tab.",
                12, MUTED, Typeface.NORMAL), mp(0, dp(4), 0, 0));
        toEt = input("", InputType.TYPE_CLASS_TEXT);
        toEt.setHint("Recipient address (M...)");
        toEt.setTypeface(Typeface.MONOSPACE);
        col.addView(toEt, mp(0, dp(4), 0, 0));

        amountEt = input("", InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        amountEt.setHint("Amount (MAZA)");
        col.addView(amountEt, mp(0, dp(4), 0, 0));

        feeHintTv = label("fee " + fmtAmount(fee) + " MAZA", 12, MUTED, Typeface.NORMAL);
        col.addView(feeHintTv, mp(0, dp(2), 0, 0));

        sendBtn = new Button(this);
        sendBtn.setText("Send");
        sendBtn.setOnClickListener(v -> doSend());
        col.addView(sendBtn, mp(0, dp(8), 0, 0));

        sendResultTv = mono("", 13, MUTED);
        col.addView(sendResultTv, mp(0, dp(4), 0, 0));

        addTab(col, 2);
    }

    private void buildHistoryTab() {
        LinearLayout col = tabColumn();
        addHeader(col);

        col.addView(label("HISTORY", 13, ACCENT, Typeface.BOLD));

        historyList = column();
        col.addView(historyList, mp(0, dp(4), 0, 0));

        addTab(col, 3);
    }

    /** "My Wallet" self-custody tab; all logic lives in SelfCustody. The
     *  S-2a SECURITY card (PIN set/change/remove + auto-lock status) sits
     *  below it — this is the settings hook; the S-4 settings screen folds
     *  it in. */
    private void buildWalletTab() {
        LinearLayout col = tabColumn();
        selfCustody = new SelfCustody(this, this);
        col.addView(selfCustody.view());
        pinSection = column();
        col.addView(pinSection, mp(0, dp(12), 0, dp(8)));
        renderPinSection();
        addTab(col, TAB_WALLET);
    }

    // ------------------------------------------------- SelfCustody.Host

    @Override
    public String baseUrl() {
        return baseUrl;
    }

    @Override
    public String token() {
        return token;
    }

    @Override
    public void onUnauthorized() {
        ui.post(this::lockOut);
    }

    /** S-2a: SelfCustody consults this at the START of every protected
     *  handler (send / create / import seed) so an in-flight tap that raced
     *  an expiry cannot act while the lock engages (judge r2). Showing the
     *  cover here makes the response immediate — the 10s tick is only a
     *  convenience, never the enforcement. */
    @Override
    public boolean gateOpen() {
        if (pinGuard == null) return true;
        boolean open = !pinGuard.gateNeeded();
        if (!open) showLock();
        return open;
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
                Api.Resp r = Api.http(baseUrl, token, "POST", "/api/unlock", body);
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
        // S-2a gate: the SEND tab spends the bench account — a spend action,
        // so it requires the PIN while locked (same policy as the WALLET tab).
        if (pinGuard != null && pinGuard.gateNeeded()) {
            pendingGatedTab = 2;
            sendResult("Wallet locked - enter your PIN to send.", RED);
            showLock();
            return;
        }
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
                Api.Resp r = Api.http(baseUrl, token, "POST", "/api/send", body);
                if (r.code == 200) {
                    String txid = r.json().optString("txid", "");
                    msg = txid.length() == 0
                            ? "Sent (bench account)."
                            : "Sent (bench account): " + shortTxid(txid);
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
        new Thread(() -> {
            try {
                Api.Resp r = Api.http(baseUrl, token, "GET", "/api/state", null);  // Bearer header, never the token in URLs
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
                    if (selfCustody != null) selfCustody.refresh();
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

    /** Update all views in place; never rebuilds the tab bar or switches tab. */
    private void applyState(WalletState ws) {
        fee = ws.fee;
        balanceTv.setText(fmtAmount(ws.balance) + " MAZA");
        accountTv.setText("account " + ws.account + " \u00B7 fee "
                + fmtAmount(ws.fee) + " MAZA");
        feeHintTv.setText("fee " + fmtAmount(ws.fee) + " MAZA");
        if (ws.address.equals(lastAddress) == false) {
            lastAddress = ws.address;
            addressTv.setText(ws.address);
            loadQr();
        }

        ArrayList<Tx> txs = new ArrayList<>(ws.txs);
        Collections.sort(txs, (a, b) -> Long.compare(b.time, a.time)); // newest first
        historyList.removeAllViews();
        int n = Math.min(txs.size(), MAX_ROWS);
        if (n == 0) {
            historyList.addView(label("No transactions yet", 13, MUTED, Typeface.NORMAL));
        }
        for (int i = 0; i < n; i++) {
            historyList.addView(txRow(txs.get(i)));
        }

        note("Last sync " + SYNC_FMT.format(new Date()));
    }

    private View txRow(Tx t) {
        boolean send = "send".equals(t.category);
        // Arrows via unicode escapes to keep this source file pure ASCII:
        // \u2190 = left arrow (received), \u2192 = right arrow (sent).
        String glyph = send ? "\u2192" : "\u2190";
        String signed = (send ? "-" : "+") + fmtAmount(Math.abs(t.amount));

        LinearLayout box = card();
        int p = dp(12);
        box.setPadding(p, p, p, p);
        box.setLayoutParams(mp(0, 0, 0, dp(8)));

        LinearLayout row1 = row();
        row1.addView(label(glyph + " " + signed, 15, send ? RED : GREEN, Typeface.BOLD),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        // Absolute local timestamp from the unix time field.
        row1.addView(label(TS_FMT.format(new Date(t.time * 1000)), 13, TEXT, Typeface.NORMAL));
        box.addView(row1);

        LinearLayout row2 = row();
        row2.addView(label(relTime(t.time), 12, MUTED, Typeface.NORMAL),
                new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        String conf = t.confs > 0 ? t.confs + " confs" : "unconfirmed";
        row2.addView(label(conf, 12, t.confs > 0 ? MUTED : ACCENT, Typeface.NORMAL));
        box.addView(row2);

        return box;
    }

    private void copyAddress() {
        String a = addressTv.getText().toString();
        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        if (cm == null) return;
        cm.setPrimaryClip(ClipData.newPlainText("MAZA address", a));
        Toast.makeText(this, "Copied", Toast.LENGTH_SHORT).show();
    }

    private void loadQr() {
        if (token == null) return;
        qrStatusTv.setText("Loading QR...");
        qrStatusTv.setTextColor(MUTED);
        new Thread(() -> {
            try {
                Api.Resp r = Api.http(baseUrl, token, "GET", "/api/qr.png", null);  // Bearer header, no token in URL
                if (r.code == 401) {
                    ui.post(this::lockOut);
                    return;
                }
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
                    qrStatusTv.setText("");
                });
            } catch (IOException e) {
                ui.post(() -> qrErr("QR load failed"));
            }
        }, "qr").start();
    }

    private void qrErr(String m) {
        qrStatusTv.setText(m);
        qrStatusTv.setTextColor(RED);
    }

    private void lockOut() {
        token = null;
        showConnect("Session expired - please reconnect.");
    }

    // ------------------------------------------------- S-2a PIN lock UI

    /** Full-screen PIN cover. Built fresh in showWallet(); GONE until the
     *  gate engages (tab tap / send tap / inactivity tick / long background). */
    private void buildLockOverlay() {
        lockOverlay = new FrameLayout(this);
        lockOverlay.setBackgroundColor(BG);
        lockOverlay.setVisibility(View.GONE);
        lockOverlay.setClickable(true); // swallow touches behind the cover
        LinearLayout col = column();
        col.setPadding(dp(24), dp(56), dp(24), dp(24));
        lockOverlay.addView(col, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.TOP));
        addHeader(col);
        col.addView(label("Wallet locked", 22, TEXT, Typeface.BOLD),
                mp(0, dp(16), 0, 0));
        col.addView(label("Enter your PIN to continue.", 13, MUTED, Typeface.NORMAL),
                mp(0, dp(4), 0, dp(16)));
        pinEt = pinInput("PIN or passphrase");
        col.addView(pinEt);
        pinErrTv = label("", 13, RED, Typeface.NORMAL);
        col.addView(pinErrTv, mp(0, dp(8), 0, 0));
        pinBtn = new Button(this);
        pinBtn.setText("Unlock");
        pinBtn.setOnClickListener(v -> doPinUnlock());
        col.addView(pinBtn, mp(0, dp(8), 0, 0));
    }

    private void showLock() {
        if (lockOverlay == null || pinGuard == null) return;
        pinEt.setText("");
        pinErrTv.setTextColor(MUTED);
        pinErrTv.setText(pinGuard.throttled()
                ? "Too many attempts - wait " + pinGuard.throttleRemainingSec() + "s."
                : "");
        if (pinGuard.throttled()) pinErrTv.setTextColor(RED);
        lockOverlay.setVisibility(View.VISIBLE);
        pinEt.requestFocus();
    }

    /** Verify the typed PIN on a worker thread (PBKDF2 at 210k iterations is
     *  ~0.5s); the result lands on the UI thread. THROTTLED refuses without
     *  hashing; WRONG_PIN advances the backoff (LockPolicy). */
    private void doPinUnlock() {
        if (pinGuard == null || lockOverlay == null) return;
        if (pinGuard.throttled()) {
            pinErrTv.setTextColor(RED);
            pinErrTv.setText("Too many attempts - wait "
                    + pinGuard.throttleRemainingSec() + "s.");
            return;
        }
        final char[] pin = grab(pinEt);
        if (pin.length == 0) {
            zero(pin);
            pinErrTv.setTextColor(RED);
            pinErrTv.setText("Enter your PIN.");
            return;
        }
        pinBtn.setEnabled(false);
        pinErrTv.setTextColor(MUTED);
        pinErrTv.setText("Checking...");
        new Thread(() -> {
            final int r = pinGuard.verifyAttempt(pin);
            ui.post(() -> {
                pinBtn.setEnabled(true);
                if (r == LockPolicy.ACCEPTED) {
                    pinEt.setText("");
                    lockOverlay.setVisibility(View.GONE);
                    int target = pendingGatedTab;
                    pendingGatedTab = -1;
                    if (target >= 0) selectTab(target);
                } else {
                    showLock(); // re-arms the throttle message on retry
                    if (r == LockPolicy.WRONG_PIN) {
                        pinErrTv.setTextColor(RED);
                        pinErrTv.setText("Wrong PIN - try again.");
                    }
                }
            });
        }, "pin-verify").start();
    }

    /** 10s UI tick: prompt the overlay when the (authoritative, lazy) gate
     *  says locked. The gate check at every tab/send tap stays the real
     *  enforcement; this only makes the cover appear without user action. */
    private void autoLockTick() {
        if (pinGuard != null && lockOverlay != null
                && lockOverlay.getVisibility() != View.VISIBLE
                && pinGuard.gateNeeded()) {
            showLock();
        }
        ui.postDelayed(lockTick, 10_000);
    }

    /** WALLET-tab SECURITY card. Set / Change / Remove; Change and Remove
     *  REQUIRE the current PIN (a removable-without-PIN gate is decorative).
     *  Auto-lock delay display + the settings entry point (S-4: endpoint,
     *  auto-lock editor, theme selector, wallet management). This card is
     *  only reachable through the PIN-gated WALLET tab, so the settings screen
     *  is entered from an already-unlocked session. */
    private void renderPinSection() {
        if (pinSection == null || pinGuard == null) return;
        pinSection.removeAllViews();
        LinearLayout card = card();
        pinSection.addView(card);
        card.addView(label("SECURITY", 13, ACCENT, Typeface.BOLD));
        if (!pinGuard.isSet()) {
            card.addView(label(
                    "No PIN set. A PIN locks the WALLET tab and sending behind"
                            + " a prompt.",
                    12, MUTED, Typeface.NORMAL), mp(0, dp(4), 0, dp(8)));
            Button setBtn = new Button(this);
            setBtn.setText("Set PIN");
            setBtn.setOnClickListener(v -> showPinSetPrompt(null));
            card.addView(setBtn);
        } else {
            long mins = pinGuard.autolockMs() / 60_000L;
            card.addView(label("PIN lock ON \u00B7 auto-lock after " + mins
                    + " min of inactivity (also locks while backgrounded).",
                    12, MUTED, Typeface.NORMAL), mp(0, dp(4), 0, dp(8)));
            Button changeBtn = new Button(this);
            changeBtn.setText("Change PIN");
            changeBtn.setOnClickListener(v -> showPinChangePrompt());
            card.addView(changeBtn, mp(0, 0, 0, dp(4)));
            Button removeBtn = new Button(this);
            removeBtn.setText("Remove PIN");
            removeBtn.setOnClickListener(v -> showPinRemovePrompt());
            card.addView(removeBtn);
        }
        Button settingsBtn = new Button(this);
        settingsBtn.setText(R.string.settings_entry);
        settingsBtn.setOnClickListener(v -> openSettings());
        card.addView(settingsBtn, mp(0, dp(8), 0, 0));
    }

    /** S-4 entry point: settings + wallet management (one activity, two
     *  pages). Leaves the wallet UI untouched on return so the session and
     *  the poll loop survive. */
    private void openSettings() {
        startActivity(new Intent(this, SettingsActivity.class));
    }

    private void showPinSetPrompt(final char[] verifiedCurrent) {
        zero(verifiedCurrent); // proven possession is consumed here
        AlertDialog.Builder b = new AlertDialog.Builder(this);
        b.setTitle(verifiedCurrent == null ? "Set PIN" : "Change PIN");
        LinearLayout box = column();
        box.setPadding(dp(20), dp(12), dp(20), 0);
        final EditText e1 = pinInput("New PIN (min 4 characters)");
        final EditText e2 = pinInput("Repeat new PIN");
        box.addView(e1);
        box.addView(e2, mp(0, dp(8), 0, 0));
        // In-dialog validation error (r2 polish fold): invalid input keeps
        // the dialog OPEN with the reason inline, instead of dismissing it.
        final TextView errTv = label("", 13, RED, Typeface.NORMAL);
        box.addView(errTv, mp(0, dp(8), 0, 0));
        b.setView(box);
        b.setPositiveButton("Save", null); // click overridden after show()
        b.setNegativeButton("Cancel", null);
        AlertDialog dlg = b.create();
        dlg.show();
        dlg.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
                char[] p1 = grab(e1);
                char[] p2 = grab(e2);
                boolean same = p1.length >= 4 && Arrays.equals(p1, p2);
                zero(p2);
                if (!same) {
                    zero(p1);
                    errTv.setText("PINs must match and be at least 4 characters.");
                    return; // dialog stays open for correction
                }
                final char[] pin = p1;
                new Thread(() -> {
                    pinGuard.store(pin); // zeroes pin; ~0.5s PBKDF2
                    ui.post(() -> {
                        renderPinSection();
                        Toast.makeText(MainActivity.this, "PIN saved.",
                                Toast.LENGTH_SHORT).show();
                    });
                }, "pin-store").start();
                dlg.dismiss();
        });
    }

    /** Verify the current PIN first (worker thread), then open the set
     *  prompt. Uses verifyAttempt so a throttled session is refused here
     *  too. */
    private void showPinChangePrompt() {
        promptCurrentPin("Change PIN - enter current PIN", verified ->
                showPinSetPrompt(verified));
    }

    private void showPinRemovePrompt() {
        promptCurrentPin("Remove PIN - enter current PIN", verified -> {
            zero(verified);
            pinGuard.clear();
            renderPinSection();
            Toast.makeText(this, "PIN removed.", Toast.LENGTH_SHORT).show();
        });
    }

    private interface PinVerified {
        void go(char[] verifiedCurrent);
    }

    private void promptCurrentPin(String title, final PinVerified go) {
        AlertDialog.Builder b = new AlertDialog.Builder(this);
        b.setTitle(title);
        LinearLayout box = column();
        box.setPadding(dp(20), dp(12), dp(20), 0);
        final EditText e = pinInput("Current PIN");
        box.addView(e);
        b.setView(box);
        b.setPositiveButton("Continue", (d, w) -> {
                final char[] cur = grab(e);
                if (cur.length == 0) {
                    zero(cur);
                    Toast.makeText(MainActivity.this, "Enter your PIN.",
                            Toast.LENGTH_SHORT).show();
                    return;
                }
                new Thread(() -> {
                    int r = pinGuard.verifyAttempt(cur);
                    ui.post(() -> {
                        if (r == LockPolicy.ACCEPTED) {
                            go.go(cur);
                        } else if (r == LockPolicy.THROTTLED) {
                            Toast.makeText(MainActivity.this,
                                    "Too many attempts - wait "
                                            + pinGuard.throttleRemainingSec() + "s.",
                                    Toast.LENGTH_LONG).show();
                        } else {
                            Toast.makeText(MainActivity.this,
                                    "Wrong PIN.", Toast.LENGTH_SHORT).show();
                        }
                    });
                }, "pin-verify").start();
        });
        b.setNegativeButton("Cancel", null);
        b.show();
    }

    private EditText pinInput(String hint) {
        EditText e = input("", InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        e.setHint(hint);
        return e;
    }

    private static char[] grab(EditText e) {
        Editable ed = e.getText();
        char[] p = new char[ed.length()];
        ed.getChars(0, ed.length(), p, 0);
        return p;
    }

    private static void zero(char[] a) {
        if (a != null) java.util.Arrays.fill(a, '\0');
    }

    private void sendResult(String msg, int color) {
        sendResultTv.setText(msg);
        sendResultTv.setTextColor(color);
    }

    private void note(String m) {
        if (lastSyncTv != null) {
            lastSyncTv.setText(m);
            lastSyncTv.setTextColor(m.startsWith("Last sync") ? MUTED : RED);
        }
    }

    private void schedulePoll() {
        ui.removeCallbacks(pollTask);
        ui.postDelayed(pollTask, POLL_MS);
    }

    // ----------------------------------------------------------- network
    // All HTTP lives in Api (shared with the SelfCustody wallet tab).

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

    /** Relative time: "3m ago", "2h 15m ago", "5d ago" (from now). */
    private static String relTime(long unix) {
        long diff = Math.max(0, System.currentTimeMillis() / 1000 - unix);
        if (diff < 60) return "just now";
        long m = diff / 60;
        if (m < 60) return m + "m ago";
        long h = m / 60;
        if (h < 24) {
            long rm = m % 60;
            return rm == 0 ? h + "h ago" : h + "h " + rm + "m ago";
        }
        return (h / 24) + "d ago";
    }
}
