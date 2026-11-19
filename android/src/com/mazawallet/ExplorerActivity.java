package com.mazawallet;

import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.mazawallet.crypto.Base58Check;

import java.io.IOException;
import java.util.List;

/** Read-only address, transaction, and block explorer. */
public final class ExplorerActivity extends Activity {
    private UiTheme.Palette pal;
    private EditText query;
    private Button search;
    private LinearLayout results;
    private IndexerClient client;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        SharedPreferences prefs = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE);
        ThemeController.applyTheme(this, SettingsActivity.themeMode(prefs));
        pal = UiTheme.palette(this);
        String base = IndexerClient.configuredBase(prefs);
        client = base == null ? null : new IndexerClient(base);
        buildScreen();
        if (client == null) showNote(getString(R.string.explorer_no_indexer), true);
        else showNote(getString(R.string.explorer_ready), false);
    }

    private void buildScreen() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(16), dp(20), dp(16), dp(20));
        root.setBackgroundColor(pal.background());

        TextView title = text(getString(R.string.explorer_title), 22, pal.textPrimary());
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        root.addView(title);
        root.addView(text(getString(R.string.explorer_subtitle), 12, pal.textSecondary()),
                margins(0, dp(4), 0, dp(14)));

        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setOrientation(LinearLayout.HORIZONTAL);
        searchRow.setGravity(Gravity.CENTER_VERTICAL);
        query = new EditText(this);
        query.setSingleLine(true);
        query.setInputType(InputType.TYPE_CLASS_TEXT);
        query.setHint(getString(R.string.explorer_hint));
        query.setTextColor(pal.textPrimary());
        query.setHintTextColor(pal.textSecondary());
        searchRow.addView(query, new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        search = new Button(this);
        search.setText(getString(R.string.explorer_search));
        search.setTextColor(pal.background());
        search.setBackgroundColor(pal.accent());
        search.setOnClickListener(v -> startSearch());
        LinearLayout.LayoutParams buttonLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        buttonLp.leftMargin = dp(8);
        searchRow.addView(search, buttonLp);
        root.addView(searchRow);

        results = new LinearLayout(this);
        results.setOrientation(LinearLayout.VERTICAL);
        root.addView(results, margins(0, dp(14), 0, 0));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(root);
        setContentView(scroll);
    }

    private void startSearch() {
        if (client == null) {
            showNote(getString(R.string.explorer_no_indexer), true);
            return;
        }
        final String value = query.getText().toString().trim();
        final int kind = queryKind(value);
        if (kind < 0) {
            showNote(getString(R.string.explorer_unknown), true);
            return;
        }
        search.setEnabled(false);
        showNote(getString(R.string.explorer_loading), false);
        new Thread(() -> fetch(value, kind)).start();
    }

    private void fetch(String value, int kind) {
        ExplorerParse.Result parsed;
        try {
            Api.Resp response = kind == 0 ? client.address(value)
                    : kind == 1 ? client.transaction(value) : client.block(value);
            if (response.code < 200 || response.code >= 300) {
                parsed = ExplorerParse.error(response.errorText());
            } else if (kind == 0) {
                parsed = ExplorerParse.address(response.text());
            } else if (kind == 1) {
                parsed = ExplorerParse.transaction(response.text());
            } else {
                parsed = ExplorerParse.block(response.text());
            }
        } catch (IOException e) {
            parsed = ExplorerParse.error(networkMessage(e));
        } catch (RuntimeException e) {
            parsed = ExplorerParse.error(getString(R.string.explorer_bad_response));
        }
        final ExplorerParse.Result result = parsed;
        runOnUiThread(() -> {
            search.setEnabled(true);
            render(result);
        });
    }

    private void render(ExplorerParse.Result result) {
        results.removeAllViews();
        TextView heading = text(result.heading, 16,
                result.error ? pal.danger() : pal.accent());
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        results.addView(heading);
        List<String> rows = result.rows;
        for (int i = 0; i < rows.size(); i++) {
            TextView row = text(rows.get(i), 13,
                    result.error ? pal.danger() : pal.textPrimary());
            row.setTextIsSelectable(true);
            row.setPadding(dp(10), dp(10), dp(10), dp(10));
            row.setBackgroundColor(pal.surface());
            results.addView(row, margins(0, dp(6), 0, 0));
        }
    }

    private void showNote(String message, boolean error) {
        ExplorerParse.Result result = ExplorerParse.error(message);
        if (!error) result = new ExplorerParse.Result(getString(R.string.explorer_title),
                result.rows, false);
        render(result);
    }

    private String networkMessage(IOException e) {
        int type = Net.classify(e);
        if (type == Net.FAIL_OFFLINE) return getString(R.string.net_error_offline);
        if (type == Net.FAIL_TIMEOUT) return getString(R.string.net_error_timeout);
        if (type == Net.FAIL_UNREACHABLE) return getString(R.string.net_error_unreachable);
        return getString(R.string.net_error_generic);
    }

    static int queryKind(String value) {
        if (isAddress(value)) return 0;
        if (value != null && value.matches("[0-9a-fA-F]{64}")) return 1;
        if (value != null && value.matches("[0-9]+")) return 2;
        return -1;
    }

    private static boolean isAddress(String value) {
        if (value == null || value.length() < 26 || value.length() > 35) return false;
        try {
            return Base58Check.decode(value).length == 21;
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    private TextView text(String value, int sp, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sp);
        view.setTextColor(color);
        return view;
    }

    private LinearLayout.LayoutParams margins(int left, int top, int right, int bottom) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(left, top, right, bottom);
        return lp;
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
