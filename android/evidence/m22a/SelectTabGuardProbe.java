import java.nio.file.*;
import java.util.*;

/**
 * M22a regression probe: MainActivity's tab-selection + navigation refresh
 * guard (selectTab + showWallet reset).
 *
 * Two layers:
 *  1. STATIC - reads the real MainActivity.java and asserts
 *       (a) the wasSelected capture sits BEFORE "tab = i" (comparing against
 *           the previous tab index is only correct before reassignment), and
 *       (b) showWallet() resets "tab = 0;" BEFORE its selectTab(0) call.
 *  2. DYNAMIC - a lifecycle-aware replica (selected-index + reset, not just a
 *     fresh object) run against navigation AND lockout/reconnect sequences.
 *
 * Defect history this probe pins (each named scenario fails on that defect):
 *   - r1 (judge): capture placed after the setVisibility loop read always
 *     VISIBLE -> initial selectTab(0) double-fetched with doUnlock's explicit
 *     refresh(). Scenario A fails on that code.
 *   - r2-prep (probe's own scenarios): first rework used a visibility guard
 *     with the wrong polarity (refresh when already-visible = self-tap only).
 *     B2/C1/C2 fail on that code. NOTE: a !visible-polarity visibility guard
 *     CAN express re-entry (a returning target reads GONE before the loop);
 *     its real defect is that a freshly built view ALSO reads GONE, so it
 *     cannot tell first-entry from re-entry and would double-fire the initial
 *     selection.
 *   - r2 (judge): the tab index was not reset on reconnect - lockout while a
 *     non-BALANCE tab was selected left selected=2, so the reconnect's
 *     selectTab(0) saw wasSelected=false and double-fetched with doUnlock's
 *     explicit refresh(). Scenarios G/H fail on that code.
 *
 * Guard semantics under test:
 *   - each unlock/reconnect performs exactly ONE /api/state fetch (showWallet
 *     resets the index to 0; selectTab(0) counts as initial; doUnlock
 *     refreshes once)
 *   - navigating INTO BALANCE (0) or HISTORY (3) from another tab -> refresh
 *   - tapping the already-selected tab -> NO refresh
 *   - RECEIVE (1) / SEND (2) / WALLET (4) -> never balance-refresh
 *
 * Run from the repo root:  bash android/evidence/m22a/run-probe.sh
 * Exit 0 = all assertions PASS; exit 1 = any FAIL.
 */
public class SelectTabGuardProbe {

    static int fails = 0;

    static void check(String name, boolean cond) {
        System.out.println((cond ? "PASS " : "FAIL ") + name);
        if (!cond) fails++;
    }

    // ---- dynamic replica (mirrors MainActivity showWallet/selectTab) ----
    static final int TAB_COUNT = 5;
    static final int TAB_WALLET = 4;

    static class TabBar {
        int selected = 0;        // mirrors "private int tab = 0;"
        int refreshCount = 0;
        int walletShownCount = 0;
        final boolean resetEnabled;  // false = models the r2 defect (no reset)

        TabBar(boolean resetEnabled) { this.resetEnabled = resetEnabled; }
        TabBar() { this(true); }

        void refresh() { refreshCount++; }          // the real refresh() re-syncs /api/state
        void onShown() { walletShownCount++; }      // SelfCustody.onShown()

        void resetSelection() {                     // mirrors showWallet()'s "tab = 0;"
            if (resetEnabled) selected = 0;
        }

        void selectTab(int i) {
            boolean wasSelected = (selected == i);  // <-- captured BEFORE reassignment
            selected = i;
            if (i == TAB_WALLET) onShown();
            if (!wasSelected && (i == 0 || i == 3)) refresh();
        }

        /** One full unlock: showWallet() [reset + selectTab(0)] + doUnlock's explicit refresh. */
        void unlock() {
            resetSelection();
            selectTab(0);
            refresh();
        }
    }

    public static void main(String[] args) throws Exception {
        // ---- layer 1: static order checks on the REAL source ----
        Path src;
        if (args.length > 0) src = Paths.get(args[0]);
        else src = Paths.get("android/src/com/mazawallet/MainActivity.java");
        List<String> lines = Files.readAllLines(src);
        int captureIdx = -1, assignIdx = -1, refreshIdx = -1, resetIdx = -1, initSelIdx = -1;
        for (int i = 0; i < lines.size(); i++) {
            String l = lines.get(i);
            if (captureIdx < 0 && l.contains("boolean wasSelected = (tab == i);")) captureIdx = i;
            if (assignIdx < 0 && l.trim().equals("tab = i;")) assignIdx = i;
            if (refreshIdx < 0 && l.contains("if (!wasSelected && (i == 0 || i == 3)) refresh();")) refreshIdx = i;
            if (resetIdx < 0 && l.trim().equals("tab = 0;")) resetIdx = i;
            if (initSelIdx < 0 && l.trim().equals("selectTab(0);")) initSelIdx = i;
        }
        check("static: wasSelected capture exists", captureIdx >= 0);
        check("static: tab reassignment exists", assignIdx >= 0);
        check("static: navigation refresh guard exists", refreshIdx >= 0);
        check("static: showWallet tab reset exists", resetIdx >= 0);
        check("static: capture is BEFORE the tab reassignment", captureIdx >= 0 && assignIdx >= 0 && captureIdx < assignIdx);
        check("static: reset is BEFORE the initial selectTab(0)", resetIdx >= 0 && initSelIdx >= 0 && resetIdx < initSelIdx);
        check("static: no visibility-based guard remains", lines.stream().noneMatch(l ->
                l.contains("wasVisible") || l.contains("wasVisible &&")));

        // ---- layer 2: dynamic truth table ----
        TabBar t = new TabBar();

        // Scenario A: unlock path = exactly ONE /api/state fetch.
        t.unlock();
        check("A: unlock performs exactly 1 fetch", t.refreshCount == 1);

        // Scenario B: navigation refresh polarity.
        t.selectTab(2); // SEND
        check("B1: switching to SEND does not refresh", t.refreshCount == 1);
        t.selectTab(0); // BALANCE from another tab
        check("B2: navigating to BALANCE refreshes", t.refreshCount == 2);

        // Scenario C: navigation into HISTORY refreshes (first and later).
        t.selectTab(1); // RECEIVE
        t.selectTab(3); // HISTORY
        check("C1: navigating to HISTORY refreshes", t.refreshCount == 3);
        t.selectTab(1); // RECEIVE
        t.selectTab(3); // HISTORY again
        check("C2: returning to HISTORY refreshes again", t.refreshCount == 4);

        // Scenario D: WALLET tab never balance-refreshes; onShown per entry.
        t.selectTab(4);
        t.selectTab(4);
        check("D: WALLET navigation does not balance-refresh", t.refreshCount == 4);
        check("D: WALLET onShown fired per entry", t.walletShownCount == 2);

        // Scenario E: each navigation into BALANCE refreshes.
        t.selectTab(0);
        t.selectTab(1);
        t.selectTab(0);
        check("E: each BALANCE navigation refreshes", t.refreshCount == 6);

        // Scenario F: tapping the already-selected tab does not refresh.
        t.selectTab(3);
        t.selectTab(3);
        check("F: self-tap of the selected tab does not refresh", t.refreshCount == 7);

        // Scenario G (r2 blocker): lockout while on SEND (selected=2), then
        // reconnect. showWallet() resets the selection first, so the
        // reconnect is exactly ONE fetch - total 8.
        t.unlock(); // reset -> selectTab(0) is initial -> no nav refresh
        check("G: reconnect from non-BALANCE tab = exactly 1 fetch", t.refreshCount == 8);

        // Scenario H (discriminator): the SAME unlock-lockout-reconnect
        // sequence WITHOUT the reset (models the r2 defect) MUST produce the
        // double fetch, proving scenario G's assertion actually kills the
        // defect class instead of passing vacuously.
        TabBar broken = new TabBar(false);
        broken.unlock();      // first unlock: selected starts 0 -> initial -> explicit only = 1
        broken.selectTab(2);  // user is on SEND when lockout hits
        broken.unlock();      // no reset: selectTab(0) sees wasSelected=false -> nav refresh + explicit = 2
        check("H: without the reset the reconnect double-fetches (discriminator)",
                broken.refreshCount == 3);

        System.out.println(fails == 0 ? "ALL CHECKS PASSED" : fails + " CHECK(S) FAILED");
        System.exit(fails == 0 ? 0 : 1);
    }
}
