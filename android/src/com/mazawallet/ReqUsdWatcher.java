package com.mazawallet;

import android.text.Editable;
import android.text.TextWatcher;

/**
 * M29: repaints the receive figure as the amount is typed.
 *
 * Deliberately a TOP-LEVEL class, holding the activity explicitly. A
 * NESTED class that captures its outer instance crashes the dexer on this
 * toolchain (d8 8.2.2-dev: "Cannot invoke String.length() because
 * <parameter1> is null") - anonymous or named alike - and this watcher has
 * to call back into the activity. Measured on the build's own flags, with
 * sources compiled by this toolchain's javac; the two matrices are recorded
 * in DECISIONS.md D20. Same rule PromptCb follows.
 *
 * The watcher is dumb plumbing: it forwards to MainActivity's
 * package-private handler, which owns what a keystroke repaints (the
 * figure, from the quote the gate already remembers - never a request).
 * It lives as long as the amount input it is attached to, and both die
 * with the activity.
 */
final class ReqUsdWatcher implements TextWatcher {

    private final MainActivity act;

    ReqUsdWatcher(MainActivity act) {
        this.act = act;
    }

    @Override
    public void beforeTextChanged(CharSequence s, int start,
            int count, int after) {
    }

    @Override
    public void onTextChanged(CharSequence s, int start,
            int before, int count) {
    }

    @Override
    public void afterTextChanged(Editable s) {
        act.onReceiveAmountEdited();
    }
}
