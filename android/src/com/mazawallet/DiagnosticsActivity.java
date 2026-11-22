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

import java.util.List;

/**
 * M24: in-app console - the AppLog ring (newest last) with copy-to-clipboard.
 * Reached only through the app's own Settings screen (manifest
 * exported=false); the protection is that flag plus the status-only
 * logging contract (AppLog/LogRing scrub as defense-in-depth) - Settings'
 * main page itself has no PIN gate, so no richer content may ever live in
 * the ring. Re-created freely on day/night flips (no configChanges):
 * onCreate re-themes; onResume re-reads the ring.
 */
public final class DiagnosticsActivity extends Activity {

    private TextView console;
    private TextView count;
    private String rendered = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        SharedPreferences prefs =
                getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE);
        // Contract (lane S-3): apply the saved mode BEFORE any view is built.
        ThemeController.applyTheme(this, SettingsActivity.themeMode(prefs));
        UiTheme.Palette pal = UiTheme.palette(this);
        int bg = pal.background();
        int cardBg = pal.surface();
        int text = pal.textPrimary();
        int muted = pal.textSecondary();
        int accent = pal.accent();

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

        console = new TextView(this);
        console.setTypeface(Typeface.MONOSPACE);
        console.setTextSize(11);
        console.setTextColor(text);
        // ScrollView is the single scroll mechanism (judge r1 polish: no
        // ScrollingMovementMethod nesting).
        ScrollView scroller = new ScrollView(this);
        scroller.addView(console);
        LinearLayout.LayoutParams scrollLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f);
        root.addView(scroller, scrollLp);

        count = new TextView(this);
        count.setTextSize(12);
        count.setTextColor(muted);
        root.addView(count, margins(0, dp(8), dp(8)));

        Button copy = new Button(this);
        copy.setText(getString(R.string.diag_copy));
        copy.setBackgroundColor(cardBg);
        copy.setTextColor(text);
        copy.setOnClickListener(v -> copyConsole());
        root.addView(copy, margins(ViewGroup.LayoutParams.MATCH_PARENT, 0, 0));

        renderConsole();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // The ring keeps filling while this screen is open (the 15s poll
        // keeps running) - re-render so the body, the count line and the
        // clipboard payload can never disagree (M25 simplify pass).
        renderConsole();
    }

    /** One locked read of the ring feeds the body AND the count line. */
    private void renderConsole() {
        List<String> lines = AppLog.snapshot();
        StringBuilder sb = new StringBuilder();
        for (String line : lines) {
            if (sb.length() > 0) {
                sb.append('\n');
            }
            sb.append(line);
        }
        rendered = sb.toString();
        console.setText(rendered.isEmpty()
                ? getString(R.string.diag_empty) : rendered);
        count.setText(getString(R.string.diag_count, lines.size(),
                AppLog.capacity()));
    }

    private void copyConsole() {
        ClipboardManager cm =
                (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        cm.setPrimaryClip(ClipData.newPlainText("maza-console",
                rendered.isEmpty() ? getString(R.string.diag_empty) : rendered));
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
