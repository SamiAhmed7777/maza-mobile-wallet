package com.mazawallet;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import com.mazawallet.crypto.SettingsResumePolicy;
import android.text.Editable;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.mazawallet.crypto.Bip32;
import com.mazawallet.crypto.Bip39;
import com.mazawallet.crypto.Bip44Maza;
import com.mazawallet.crypto.LockPolicy;

import java.io.File;
import java.util.ArrayList;
import java.util.Arrays;

/**
 * S-4 settings + wallet management.
 *
 * <p>Two pages in one activity (the manifest carries exactly one extra
 * &lt;activity&gt; registration for this lane):
 * <ol>
 *   <li>SETTINGS - endpoint URL (the SAME pref the Connect card writes),
 *       auto-lock delay (5/10/30 min), theme mode (system/light/dark);</li>
 *   <li>WALLET MANAGEMENT - receive addresses, seed re-display behind the
 *       PIN, wipe wallet (double confirm + typed WIPE + current-PIN
 *       verification immediately before destruction).</li>
 * </ol>
 *
 * <p>Settings storage contract (prefs file "maza", shared with MainActivity
 * and PinGuard):
 * <ul>
 *   <li>{@code url} - endpoint, owned by MainActivity's Connect card too;</li>
 *   <li>{@code pref_autolock_minutes} - int minutes, default 5, the settings
 *       AUTHORITY. {@code pin.autolock_ms} is PinGuard's storage hook (the
 *       window it builds the LockPolicy with), so the selector writes BOTH
 *       keys in one commit and then retunes the RUNNING session through
 *       {@link PinGuard#retuneAutolockMs(long)} - no restart needed.
 *       MainActivity reconciles the two keys at every launch (authority
 *       wins, no policy change);</li>
 *   <li>{@code pref_theme_mode} - "system" | "light" | "dark".</li>
 * </ul>
 *
 * <p>Theme: {@link ThemeController#applyTheme(Activity, String)} is called
 * BEFORE setContentView (lane S-3's contract). This screen additionally
 * resolves the mode itself for its own palette, so it is legible under
 * either theme even before/without S-3's resource restyle.
 *
 * <p>Secrets: the seed is never logged, never put in an Intent, never shown
 * outside the FLAG_SECURE dialog, and is displayed only after a successful
 * PinGuard verify.
 */
public final class SettingsActivity extends Activity {

    /** Prefs file shared with MainActivity/PinGuard (they own the name). */
    static final String KEY_THEME = "pref_theme_mode";
    static final String KEY_AUTOLOCK_MINUTES = "pref_autolock_minutes";

    static final String MODE_SYSTEM = "system";
    static final String MODE_LIGHT = "light";
    static final String MODE_DARK = "dark";

    /** Auto-lock selector options in minutes, in display order. */
    static final int[] AUTOLOCK_CHOICES = {5, 10, 30};

    /** Owned by SelfCustody (not editable by this lane) - keep in sync with
     *  SelfCustody.SEED_FILE / SelfCustody.PREFS / KEY_RECV_IDX. */
    static final String SEED_FILE = "selfcustody.seed";
    static final String WALLET_PREFS = "selfcustody";
    static final String KEY_RECV_IDX = "recv_idx";

    private static final int ADDRESS_COUNT = 10;
    private static final int PAGE_SETTINGS = 0;
    private static final int PAGE_WALLET = 1;
    private static final String WIPE_WORD = "WIPE";
    /** Default auto-lock window, inherited from the S-2a shell default. */
    static final int DEFAULT_MINUTES = (int) (PinGuard.DEFAULT_AUTOLOCK_MS / 60_000L);

    // Palette (per resolved mode). SelfTest pins these EXACT ARGB values in
    // its WCAG contrast table - change both places together.
    private int bg;
    private int cardBg;
    private int text;
    private int muted;
    private int accent;
    private int danger;

    private SharedPreferences prefs;
    private PinGuard pinGuard;
    private int page = PAGE_SETTINGS;
    private final Handler ui = new Handler(Looper.getMainLooper());

    /** 10s authoritative gate tick while resumed (r3): auto-lock is enforced
     *  for the whole foreground lifetime of this screen, not only at entry.
     *  Stopped in onPause. Method-reference form: the build's d8 (8.2.2-dev)
     *  NPEs on some anonymous-class field shapes, and a lambda may not
     *  textually self-reference its own field; a non-capturing method
     *  reference avoids both. */
    private final Runnable lockTick = this::lockTickRun;

    private void lockTickRun() {
        if (enforceResumeGate()) {
            return; // finished; no further ticks
        }
        ui.postDelayed(lockTick, 10_000L);
    }

    // Settings-page widgets.
    private EditText urlEt;
    private TextView urlErrTv;
    private Button[] autolockBtns;
    private TextView autolockNoteTv;
    private Button[] themeBtns;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE);
        pinGuard = new PinGuard(this);
        String mode = themeMode(prefs);
        // Contract (lane S-3): apply the saved mode BEFORE setContentView.
        ThemeController.applyTheme(this, mode);
        applyPalette(isDark(mode));
        showSettingsPage();
    }

    @Override
    public void onBackPressed() {
        if (page == PAGE_WALLET) {
            showSettingsPage();
            return;
        }
        super.onBackPressed();
    }

    // ------------------------------------------------------------ settings

    private void showSettingsPage() {
        page = PAGE_SETTINGS;
        setContentView(R.layout.activity_settings);
        LinearLayout root = findViewById(R.id.settings_root);
        root.setBackgroundColor(bg);
        root.setPadding(dp(16), dp(24), dp(16), dp(24));
        addHeader(root, getString(R.string.settings_subtitle));

        // ---- endpoint ----
        LinearLayout server = card();
        root.addView(server, mp(0, dp(16), 0, dp(12)));
        server.addView(label(getString(R.string.settings_server), 13, accent, Typeface.BOLD));
        server.addView(label(getString(R.string.settings_server_label), 12, muted,
                Typeface.NORMAL), mp(0, dp(6), 0, 0));
        urlEt = input(prefs.getString(MainActivity.KEY_URL, MainActivity.DEFAULT_URL),
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        urlEt.setHint(MainActivity.DEFAULT_URL);
        urlEt.setTypeface(Typeface.MONOSPACE);
        server.addView(urlEt, mp(0, dp(4), 0, 0));
        urlErrTv = label("", 12, danger, Typeface.NORMAL);
        server.addView(urlErrTv, mp(0, dp(6), 0, 0));
        server.addView(button(getString(R.string.settings_server_save), accent, bg,
                v -> saveEndpoint()), mp(0, dp(6), 0, 0));
        server.addView(label(getString(R.string.settings_server_note), 11, muted,
                Typeface.NORMAL), mp(0, dp(6), 0, 0));

        // ---- auto-lock ----
        LinearLayout lock = card();
        root.addView(lock, mp(0, 0, 0, dp(12)));
        lock.addView(label(getString(R.string.settings_autolock), 13, accent, Typeface.BOLD));
        autolockNoteTv = label("", 12, muted, Typeface.NORMAL);
        lock.addView(autolockNoteTv, mp(0, dp(6), 0, dp(6)));
        LinearLayout lockRow = row();
        lock.addView(lockRow);
        autolockBtns = new Button[AUTOLOCK_CHOICES.length];
        for (int i = 0; i < AUTOLOCK_CHOICES.length; i++) {
            final int minutes = AUTOLOCK_CHOICES[i];
            Button b = button(getString(R.string.autolock_minutes, minutes), cardBg, text, null);
            b.setOnClickListener(v -> selectAutolock(minutes));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            lp.rightMargin = i == AUTOLOCK_CHOICES.length - 1 ? 0 : dp(6);
            lockRow.addView(b, lp);
            autolockBtns[i] = b;
        }
        lock.addView(label(getString(R.string.settings_autolock_note), 11, muted,
                Typeface.NORMAL), mp(0, dp(8), 0, 0));
        renderAutolock();

        // ---- theme ----
        LinearLayout theme = card();
        root.addView(theme, mp(0, 0, 0, dp(12)));
        theme.addView(label(getString(R.string.settings_theme), 13, accent, Typeface.BOLD));
        LinearLayout themeRow = row();
        theme.addView(themeRow, mp(0, dp(8), 0, 0));
        String[] modes = {MODE_SYSTEM, MODE_LIGHT, MODE_DARK};
        int[] names = {R.string.theme_system, R.string.theme_light, R.string.theme_dark};
        themeBtns = new Button[modes.length];
        for (int i = 0; i < modes.length; i++) {
            final String mode = modes[i];
            Button b = button(getString(names[i]), cardBg, text, null);
            b.setOnClickListener(v -> selectTheme(mode));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
            lp.rightMargin = i == modes.length - 1 ? 0 : dp(6);
            themeRow.addView(b, lp);
            themeBtns[i] = b;
        }
        theme.addView(label(getString(R.string.settings_theme_note), 11, muted,
                Typeface.NORMAL), mp(0, dp(8), 0, 0));
        renderTheme();

        // ---- wallet management entry ----
        LinearLayout wallet = card();
        root.addView(wallet, mp(0, 0, 0, dp(12)));
        wallet.addView(label(getString(R.string.settings_wallet), 13, accent, Typeface.BOLD));
        wallet.addView(label(getString(R.string.settings_wallet_note), 12, muted,
                Typeface.NORMAL), mp(0, dp(6), 0, dp(6)));
        wallet.addView(button(getString(R.string.settings_wallet_open), accent, bg,
                v -> showWalletPage()));
    }

    private void saveEndpoint() {
        String raw = urlEt.getText().toString().trim();
        if (raw.length() == 0) {
            urlErrTv.setText(getString(R.string.err_url_empty));
            return;
        }
        if (!raw.startsWith("http://") && !raw.startsWith("https://")) {
            urlErrTv.setText(getString(R.string.err_url_scheme));
            return;
        }
        String url = stripSlash(raw);
        // SAME key the Connect card reads (pref persistence across updates is
        // intended: a saved endpoint survives reinstalls of the app data).
        prefs.edit().putString(MainActivity.KEY_URL, url).apply();
        urlEt.setText(url);
        urlErrTv.setText("");
        toast(getString(R.string.toast_endpoint_saved));
    }

    private void selectAutolock(int minutes) {
        long ms = minutes * 60_000L;
        // Two keys, one SYNCHRONOUS commit: pref_autolock_minutes is the
        // documented settings value (int minutes) and the authority;
        // pin.autolock_ms is what PinGuard reads when it builds the
        // LockPolicy at session start. commit() (not apply()) so the store
        // and the live policy can never disagree: the durable write lands
        // BEFORE the retune, and a failed commit aborts the retune instead
        // of retuning a session whose persisted value never happened.
        boolean persisted = prefs.edit()
                .putInt(KEY_AUTOLOCK_MINUTES, minutes)
                .putLong(PinGuard.KEY_AUTOLOCK_MS, ms)
                .commit();
        if (!persisted) {
            toast(getString(R.string.autolock_save_failed));
            return;
        }
        // S-4 follow-up: the new delay applies to the RUNNING session, not
        // only at the next launch. MainActivity.sActiveGuard is the live
        // session policy (the same guard the resume gate consults); the
        // retune changes the window only - never the lock state, never the
        // wrong-PIN streak.
        // With no live session (restoration window) the persisted value is
        // picked up by the next PinGuard construction at launch.
        PinGuard session = MainActivity.sActiveGuard;
        if (session != null) {
            session.retuneAutolockMs(ms);
        }
        renderAutolock();
    }

    private void renderAutolock() {
        int current = autolockMinutes(prefs);
        if (autolockNoteTv != null) {
            autolockNoteTv.setText(getString(R.string.settings_autolock_current, current));
        }
        if (autolockBtns == null) return;
        for (int i = 0; i < AUTOLOCK_CHOICES.length; i++) {
            boolean on = AUTOLOCK_CHOICES[i] == current;
            autolockBtns[i].setBackground(rounded(on ? accent : cardBg));
            autolockBtns[i].setTextColor(on ? bg : text);
        }
    }

    private void selectTheme(String mode) {
        prefs.edit().putString(KEY_THEME, mode).apply();
        // Contract: apply through ThemeController, then recreate so every
        // view is rebuilt under the new theme (platform widgets included).
        ThemeController.applyTheme(this, mode);
        recreate();
    }

    private void renderTheme() {
        if (themeBtns == null) return;
        String current = themeMode(prefs);
        String[] modes = {MODE_SYSTEM, MODE_LIGHT, MODE_DARK};
        for (int i = 0; i < modes.length; i++) {
            boolean on = modes[i].equals(current);
            themeBtns[i].setBackground(rounded(on ? accent : cardBg));
            themeBtns[i].setTextColor(on ? bg : text);
        }
    }

    // ---------------------------------------------------- wallet management

    private void showWalletPage() {
        page = PAGE_WALLET;
        setContentView(R.layout.view_wallet_manage);
        LinearLayout root = findViewById(R.id.wm_root);
        root.setBackgroundColor(bg);
        root.setPadding(dp(16), dp(24), dp(16), dp(24));
        addHeader(root, getString(R.string.wm_title));
        root.addView(button(getString(R.string.wm_back), cardBg, text,
                v -> showSettingsPage()), mp(0, 0, 0, dp(12)));

        boolean hasSeed = hasSeed();
        if (!hasSeed) {
            LinearLayout none = card();
            root.addView(none, mp(0, 0, 0, dp(12)));
            none.addView(label(getString(R.string.wm_no_seed), 13, muted, Typeface.NORMAL));
            return;
        }

        // ---- receive addresses ----
        LinearLayout addrCard = card();
        root.addView(addrCard, mp(0, 0, 0, dp(12)));
        addrCard.addView(label(getString(R.string.wm_receive), 13, accent, Typeface.BOLD));
        final LinearLayout addrList = column();
        addrCard.addView(addrList, mp(0, dp(6), 0, 0));
        loadAddresses(addrList);

        // ---- seed phrase (PIN gated) ----
        LinearLayout seedCard = card();
        root.addView(seedCard, mp(0, 0, 0, dp(12)));
        seedCard.addView(label(getString(R.string.wm_seed), 13, danger, Typeface.BOLD));
        seedCard.addView(label(pinGuard.isSet()
                        ? getString(R.string.wm_seed_note)
                        : getString(R.string.seed_requires_pin),
                12, muted, Typeface.NORMAL), mp(0, dp(6), 0, dp(6)));
        seedCard.addView(button(getString(R.string.wm_seed_button), accent, bg,
                v -> onRevealSeed()));

        // ---- wipe ----
        LinearLayout wipeCard = card();
        root.addView(wipeCard, mp(0, 0, 0, dp(12)));
        wipeCard.addView(label(getString(R.string.wm_wipe), 13, danger, Typeface.BOLD));
        wipeCard.addView(label(getString(R.string.wm_wipe_note), 12, muted,
                Typeface.NORMAL), mp(0, dp(6), 0, dp(6)));
        wipeCard.addView(button(getString(R.string.wm_wipe_button), danger, bg,
                v -> confirmWipe()));
    }

    private void loadAddresses(final LinearLayout holder) {
        holder.addView(label(getString(R.string.wm_receive_note), 11, muted,
                Typeface.NORMAL));
        holder.addView(label(getString(R.string.wm_deriving), 12, muted,
                Typeface.NORMAL), mp(0, dp(4), 0, 0));
        final int current = getSharedPreferences(WALLET_PREFS, MODE_PRIVATE)
                .getInt(KEY_RECV_IDX, 0);
        new Thread(() -> {
            final ArrayList<String> rows = new ArrayList<>();
            try {
                String seed = SeedVault.loadOrMigrate(SettingsActivity.this, SEED_FILE);
                if (seed != null && seed.length() > 0) {
                    Bip32.Node account = Bip44Maza.accountNode(
                            Bip39.mnemonicToSeed(seed, ""));
                    for (int i = 0; i < ADDRESS_COUNT; i++) {
                        rows.add(Bip44Maza.address(
                                Bip44Maza.keyAt(account, Bip44Maza.RECEIVE_CHAIN, i)));
                    }
                }
            } catch (RuntimeException e) {
                rows.clear();
            }
            ui.post(() -> fillAddresses(holder, rows, current));
        }, "settings-addresses").start();
    }

    private void fillAddresses(LinearLayout holder, ArrayList<String> rows, int current) {
        holder.removeAllViews();
        holder.addView(label(getString(R.string.wm_receive_note), 11, muted,
                Typeface.NORMAL));
        if (rows.isEmpty()) {
            holder.addView(label(getString(R.string.addresses_unavailable), 12, danger,
                    Typeface.NORMAL), mp(0, dp(4), 0, 0));
            return;
        }
        for (int i = 0; i < rows.size(); i++) {
            boolean isCurrent = i == current;
            LinearLayout line = row();
            line.addView(label(String.valueOf(i), 12, isCurrent ? accent : muted,
                            Typeface.BOLD),
                    new LinearLayout.LayoutParams(dp(24), ViewGroup.LayoutParams.WRAP_CONTENT));
            TextView a = mono(rows.get(i), 12, isCurrent ? text : muted);
            a.setTextIsSelectable(true);
            line.addView(a, new LinearLayout.LayoutParams(0,
                    ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            if (isCurrent) {
                line.addView(label(getString(R.string.wm_current), 11, accent,
                        Typeface.NORMAL));
            }
            holder.addView(line, mp(0, dp(4), 0, 0));
        }
    }

    /** Seed re-display gate: REQUIRES a VALID PinGuard (a stored, parseable
     *  verifier) plus a successful verify. With no PIN set the seed is NOT
     *  shown - protection against a briefly-borrowed phone beating a
     *  PIN-less wallet. */
    private void onRevealSeed() {
        if (!pinGuard.isSet()) {
            toast(getString(R.string.seed_requires_pin));
            return;
        }
        promptPin(() -> showSeedDialog());
    }

    private void showSeedDialog() {
        final String seed = SeedVault.loadOrMigrate(this, SEED_FILE);
        if (seed == null || seed.length() == 0) {
            toast(getString(R.string.addresses_unavailable));
            return;
        }
        // FLAG_SECURE for the lifetime of the window: no screenshots, no
        // recents thumbnail, no screen recording of the seed.
        setSecure(true);
        LinearLayout box = column();
        box.setPadding(dp(20), dp(12), dp(20), 0);
        box.addView(label(getString(R.string.seed_dialog_note), 12, danger, Typeface.BOLD));
        LinearLayout list = column();
        list.setBackground(rounded(cardBg));
        int p = dp(12);
        list.setPadding(p, p, p, p);
        box.addView(list, mp(0, dp(10), 0, 0));
        String[] words = seed.split("\\s+");
        for (int i = 0; i < words.length; i++) {
            LinearLayout line = row();
            line.addView(label(String.format(java.util.Locale.US, "%2d.", i + 1), 14,
                            muted, Typeface.NORMAL),
                    new LinearLayout.LayoutParams(dp(36),
                            ViewGroup.LayoutParams.WRAP_CONTENT));
            line.addView(mono(words[i], 15, text),
                    new LinearLayout.LayoutParams(0,
                            ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            list.addView(line, mp(0, i == 0 ? 0 : dp(6), 0, 0));
        }
        AlertDialog dlg = new AlertDialog.Builder(this)
                .setTitle(R.string.seed_dialog_title)
                .setView(box)
                .setPositiveButton(R.string.dlg_close, null)
                .create();
        dlg.setOnDismissListener(d -> {
            // Best-effort scrub: drop the word views, then lift FLAG_SECURE.
            list.removeAllViews();
            setSecure(false);
        });
        dlg.show();
        // Never log the mnemonic; nothing here writes it to disk.
    }

    private void setSecure(boolean on) {
        if (on) {
            getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE,
                    WindowManager.LayoutParams.FLAG_SECURE);
        } else {
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
        }
    }

    /** True when the screen must close. The decision itself lives in the
     *  pure SettingsResumePolicy (behaviorally tested in crypto/SelfTest
     *  settingsResumeGateChecks); this method only gathers the inputs:
     *  the verifier-store state and MainActivity's LIVE session guard
     *  (sActiveGuard - a PinGuard constructed fresh here would start LOCKED
     *  by design, which would wrongly close Settings after an
     *  already-unlocked entry; the local pinGuard stays scoped to the
     *  seed-reveal/wipe PIN verifications). */
    private boolean enforceResumeGate() {
        PinGuard session = MainActivity.sActiveGuard;
        boolean close = SettingsResumePolicy.evaluate(
                pinGuard.isSet(), session != null,
                session != null && session.gateNeeded())
                == SettingsResumePolicy.CLOSE;
        if (close) {
            finish(); // MainActivity underneath re-renders its lock cover
        }
        return close;
    }

    /** Foreground-lifetime enforcement entry (r3/r4). Order matters:
     *  1. Apply the engaged device-out-of-sight bracket FIRST (set by
     *     MainActivity.onPause when this screen launched, or by our own
     *     onPause after a HOME press from this screen): backgrounded for
     *     >= the window locks, exactly like any other return.
     *  2. THEN clear the bracket: the app is foreground again via THIS
     *     screen, so returning to MainActivity later must not apply a
     *     duration lock spanning long ACTIVE settings use (r4 judge).
     *  The bracket re-engages in onPause. The 10s tick then covers
     *  inactivity expiry while the user sits on this screen (r3). */
    @Override
    protected void onResume() {
        super.onResume();
        PinGuard session = MainActivity.sActiveGuard;
        if (session != null) {
            session.onResumeLocked();
            session.onForegroundChildResumed();
        }
        if (enforceResumeGate()) {
            return;
        }
        ui.postDelayed(lockTick, 10_000L);
    }

    @Override
    protected void onPause() {
        ui.removeCallbacks(lockTick);
        PinGuard session = MainActivity.sActiveGuard;
        if (session != null) {
            session.onBackground(); // re-engage the device-out-of-sight bracket
        }
        super.onPause();
    }

    /** Settings touches are session touches: forward them to the LIVE
     *  session policy so active use of this screen pushes the inactivity
     *  deadline (r3). The gate stays authoritative - gateNeeded() is still
     *  evaluated on every tick and at every gate check. */
    @Override
    public void onUserInteraction() {
        super.onUserInteraction();
        PinGuard session = MainActivity.sActiveGuard;
        if (session != null) {
            session.onActivity();
        }
    }

    // ---------------------------------------------------------------- wipe

    private void confirmWipe() {
        new AlertDialog.Builder(this)
                .setTitle(R.string.wipe_step1_title)
                .setMessage(R.string.wipe_step1_msg)
                .setNegativeButton(R.string.dlg_cancel, null)
                .setPositiveButton(R.string.dlg_continue, (d, w) -> confirmWipeTyped())
                .show();
    }

    private void confirmWipeTyped() {
        final AlertDialog.Builder b = new AlertDialog.Builder(this);
        b.setTitle(R.string.wipe_step2_title);
        b.setMessage(R.string.wipe_step2_msg);
        LinearLayout box = column();
        box.setPadding(dp(20), dp(12), dp(20), 0);
        final EditText ack = input("", InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS);
        ack.setHint(getString(R.string.wipe_type_hint));
        box.addView(ack);
        final TextView err = label("", 12, danger, Typeface.NORMAL);
        box.addView(err, mp(0, dp(6), 0, 0));
        b.setView(box);
        b.setNegativeButton(R.string.dlg_cancel, null);
        b.setPositiveButton(R.string.wipe_confirm_button, null); // overridden below
        final AlertDialog dlg = b.create();
        dlg.show();
        dlg.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String typed = ack.getText().toString().trim();
            if (!WIPE_WORD.equals(typed)) {
                err.setText(getString(R.string.wipe_type_error));
                return; // stay open: typing the word is the whole point
            }
            dlg.dismiss();
            proceedToDestructiveWipe();
        });
    }

    /** Last gate before destruction: re-verify the CURRENT PIN (fail-closed;
     *  THROTTLED refuses here too) when one is set, so the typed
     *  acknowledgement is never the only thing between an open settings
     *  screen and a wipe. A PIN-less wallet has no verifier to check and
     *  wipes directly. */
    private void proceedToDestructiveWipe() {
        if (pinGuard.isSet()) {
            promptPin(this::doWipe);
        } else {
            doWipe();
        }
    }

    /** Destroys the on-device wallet: seed file (plus crash leftovers), the
     *  AndroidKeyStore wrap-key alias, every pref this app owns (endpoint,
     *  PIN verifier, auto-lock, theme), the address counters, then restarts
     *  the app so the user lands on the fresh Connect card. There is no undo
     *  and nothing is kept in memory.
     *
     *  <p>Fail-loud: the seed file deletion is verified before anything else
     *  is reported as wiped, and the pref clears use commit() (synchronous)
     *  because the next step restarts the process. A wipe that cannot remove
     *  the seed says so and touches nothing else. The Keystore alias removal
     *  is best-effort: the wrap key without the seed file is inert, and an
     *  app-data reset clears the Keystore entry regardless. */
    private void doWipe() {
        File seedFile = getFileStreamPath(SEED_FILE);
        seedFile.delete();
        if (seedFile.exists()) {
            toast(getString(R.string.wm_wipe_failed));
            return;
        }
        File dir = getFilesDir();
        File[] left = dir == null ? null : dir.listFiles();
        if (left != null) {
            for (File f : left) {
                String n = f.getName();
                if (n.startsWith(SEED_FILE + ".") && n.endsWith(".tmp")) {
                    f.delete(); // SeedVault crash leftovers
                }
            }
        }
        try {
            java.security.KeyStore ks =
                    java.security.KeyStore.getInstance("AndroidKeyStore");
            ks.load(null);
            ks.deleteEntry(SeedVault.KEY_ALIAS);
        } catch (Exception keystoreCleanup) {
            // deliberate swallow: alias without the seed file is inert
        }
        boolean cleared = prefs.edit().clear().commit();
        cleared &= getSharedPreferences(WALLET_PREFS, MODE_PRIVATE)
                .edit().clear().commit();
        // The seed (the funds) is already gone at this point: a pref-clear
        // failure leaves only cosmetic leftovers, so report it distinctly
        // instead of claiming the wipe failed. App-data reset clears them.
        // In-memory state: a fresh guard re-reads the (now empty) store, so
        // the PIN gate is inert until a new PIN is set.
        pinGuard = new PinGuard(this);
        toast(getString(cleared ? R.string.toast_wiped : R.string.wm_wipe_partial));
        Intent fresh = new Intent(this, MainActivity.class);
        fresh.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        startActivity(fresh);
        finish();
    }

    // ------------------------------------------------------------- PIN flow

    private interface PinVerified {
        void go();
    }

    /** Verify a PIN with the S-2a guard (worker thread: PBKDF2 at 210k
     *  iterations is ~0.5s). THROTTLED refuses here too. */
    private void promptPin(final PinVerified go) {
        final AlertDialog.Builder b = new AlertDialog.Builder(this);
        b.setTitle(R.string.pin_prompt_title);
        LinearLayout box = column();
        box.setPadding(dp(20), dp(12), dp(20), 0);
        final EditText e = input("", InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        e.setHint(getString(R.string.pin_prompt_title));
        box.addView(e);
        b.setView(box);
        b.setNegativeButton(R.string.dlg_cancel, null);
        b.setPositiveButton(R.string.dlg_continue, (d, w) -> {
            final char[] pin = grab(e);
            if (pin.length == 0) {
                zero(pin);
                toast(getString(R.string.pin_needed));
                return;
            }
            new Thread(() -> {
                final int r = pinGuard.verifyAttempt(pin);
                ui.post(() -> {
                    if (r == LockPolicy.ACCEPTED) {
                        go.go();
                    } else if (r == LockPolicy.THROTTLED) {
                        toast(getString(R.string.pin_throttled,
                                (int) pinGuard.throttleRemainingSec()));
                    } else {
                        toast(getString(R.string.pin_wrong));
                    }
                });
            }, "settings-pin-verify").start();
        });
        b.show();
    }

    // ------------------------------------------------------------ helpers

    /** Saved theme mode, normalized to the contract set. */
    static String themeMode(SharedPreferences p) {
        String m = p.getString(KEY_THEME, MODE_SYSTEM);
        if (MODE_LIGHT.equals(m) || MODE_DARK.equals(m)) return m;
        return MODE_SYSTEM;
    }

    /** Selector value: clamps an unexpected stored value to the default 5.
     *  pref_autolock_minutes (int minutes) wins; an S-2a-era install that only
     *  has pin.autolock_ms is mapped back onto the selector when it matches a
     *  choice, so no saved delay is silently discarded. */
    static int autolockMinutes(SharedPreferences p) {
        if (p.contains(KEY_AUTOLOCK_MINUTES)) {
            int v;
            try {
                v = p.getInt(KEY_AUTOLOCK_MINUTES, DEFAULT_MINUTES);
            } catch (ClassCastException e) {
                v = DEFAULT_MINUTES; // wrong type: fall back, never crash
            }
            for (int choice : AUTOLOCK_CHOICES) {
                if (choice == v) return choice;
            }
            return AUTOLOCK_CHOICES[0];
        }
        long savedMs = -1L;
        if (p.contains(PinGuard.KEY_AUTOLOCK_MS)) {
            try {
                savedMs = p.getLong(PinGuard.KEY_AUTOLOCK_MS, -1L);
            } catch (ClassCastException e) {
                savedMs = -1L;
            }
        }
        if (savedMs > 0) {
            long rounded = (savedMs + 30_000L) / 60_000L; // nearest minute
            for (int choice : AUTOLOCK_CHOICES) {
                if (choice == rounded) return choice;
            }
        }
        return DEFAULT_MINUTES;
    }

    private boolean isDark(String mode) {
        if (MODE_LIGHT.equals(mode)) return false;
        if (MODE_DARK.equals(mode)) return true;
        int uiMode = getResources().getConfiguration().uiMode
                & Configuration.UI_MODE_NIGHT_MASK;
        return uiMode == Configuration.UI_MODE_NIGHT_YES;
    }

    private void applyPalette(boolean dark) {
        // Single source of truth: the same UiTheme palette the wallet screens
        // resolve from colors.xml via the live theme (wave-2 alignment — the
        // duplicated literals are gone, so settings and wallet cannot drift).
        UiTheme.Palette pal = UiTheme.paletteOf(this, !dark);
        bg = pal.background();
        cardBg = pal.surface();
        text = pal.textPrimary();
        muted = pal.textSecondary();
        accent = pal.accent();
        danger = pal.danger();
    }

    private boolean hasSeed() {
        return getFileStreamPath(SEED_FILE).exists();
    }

    private void addHeader(LinearLayout col, String subtitle) {
        LinearLayout header = row();
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.drawable.logo);
        header.addView(logo, new LinearLayout.LayoutParams(dp(48), dp(48)));
        LinearLayout titles = column();
        titles.addView(label("MAZA Wallet", 22, text, Typeface.BOLD));
        titles.addView(label(subtitle, 12, muted, Typeface.NORMAL));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        lp.leftMargin = dp(12);
        header.addView(titles, lp);
        col.addView(header, mp(0, 0, 0, dp(12)));
    }

    private void toast(String msg) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show();
    }

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
        c.setBackground(rounded(cardBg));
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

    /** All buttons carry an explicit background + text colour so every
     *  text/background pair on this screen is one of the WCAG-table pairs
     *  pinned in SelfTest (no reliance on platform button colours). */
    private Button button(String labelText, int bgColor, int fgColor,
                          View.OnClickListener onClick) {
        Button b = new Button(this);
        b.setText(labelText);
        b.setAllCaps(false);
        b.setBackground(rounded(bgColor));
        b.setTextColor(fgColor);
        if (onClick != null) b.setOnClickListener(onClick);
        return b;
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

    /** Inputs get an explicit background too: platform EditText colours are
     *  theme-derived and could land light-on-light under a mismatched theme. */
    private EditText input(String value, int inputType) {
        EditText e = new EditText(this);
        e.setText(value);
        e.setTextColor(text);
        e.setHintTextColor(muted);
        e.setBackground(rounded(cardBg));
        int p = dp(12);
        e.setPadding(p, p, p, p); // explicit background drops the theme padding
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

    private static char[] grab(EditText e) {
        Editable ed = e.getText();
        char[] p = new char[ed.length()];
        ed.getChars(0, ed.length(), p, 0);
        return p;
    }

    private static void zero(char[] a) {
        if (a != null) Arrays.fill(a, '\0');
    }
}
