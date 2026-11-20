package com.mazawallet;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import com.mazawallet.crypto.LogRing;

/**
 * M24: in-app console - the AppLog ring (newest last) with copy-to-clipboard.
 * Reached only from Settings (itself behind the PIN-gated WALLET tab), so
 * the entry is not exported in the manifest. Lines are status-only by
 * contract; LogRing.scrub truncates anything secret-shaped as defense.
 */
public final class DiagnosticsActivity extends Activity {

    private SharedPreferences prefs;
    private int bg, cardBg, text, muted, accent;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE);
        // Contract (lane S-3): apply the saved mode BEFORE any view is built.
        String mode = SettingsActivity.themeMode(prefs);
        ThemeController.applyTheme(this, mode);
        UiTheme.Palette pal = UiTheme.palette(this);
        bg = pal.background();
        cardBg = pal.surface();
        text = pal.textPrimary();
        muted = pal.textSecondary();
        accent = pal.accent();

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(bg);
        root.setPadding(dp(16), dp(24), dp(16), dp(16));
        setContentView(root);

        TextView title = new TextView(this);
        title.setText(getString(R.string.diag_title));
        title.setTextSize(16);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(accent);
        root.addView(title, margins(0, 0, dp(8)));

        TextView note = new TextView(this);
        note.setText(getString(R.string.diag_note));
        note.setTextSize(12);
        note.setTextColor(muted);
        root.addView(note, margins(0, 0, dp(8)));

        TextView console = new TextView(this);
        console.setTypeface(Typeface.MONOSPACE);
        console.setTextSize(11);
        console.setTextColor(text);
        // ScrollView is the single scroll mechanism (judge r1 polish: no
        // ScrollingMovementMethod nesting).
        String dump = AppLog.dump();
        console.setText(dump.length() == 0
                ? getString(R.string.diag_empty) : dump);
        ScrollView scroller = new ScrollView(this);
        scroller.addView(console);
        LinearLayout.LayoutParams scrollLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f);
        root.addView(scroller, scrollLp);

        TextView count = new TextView(this);
        count.setText(getString(R.string.diag_count, AppLog.size(), LogRing.DEFAULT_CAPACITY));
        count.setTextSize(12);
        count.setTextColor(muted);
        root.addView(count, margins(0, dp(8), dp(8)));

        Button copy = new Button(this);
        copy.setText(getString(R.string.diag_copy));
        copy.setBackgroundColor(cardBg);
        copy.setTextColor(text);
        copy.setOnClickListener(v -> copyConsole());
        root.addView(copy, margins(ViewGroup.LayoutParams.MATCH_PARENT, 0, 0));
    }

    private void copyConsole() {
        ClipboardManager cm =
                (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        String payload = AppLog.dump();
        cm.setPrimaryClip(ClipData.newPlainText(
                "maza-console", payload.length() == 0
                        ? getString(R.string.diag_empty) : payload));
        Toast.makeText(this, R.string.diag_copied, Toast.LENGTH_SHORT).show();
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private LinearLayout.LayoutParams margins(int width, int top, int bottom) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                width, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = top;
        lp.bottomMargin = bottom;
        return lp;
    }
}
