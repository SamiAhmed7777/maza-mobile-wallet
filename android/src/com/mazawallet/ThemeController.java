package com.mazawallet;

import java.util.Locale;

/**
 * Dark/light palette switch for the MAZA wallet (S-3).
 *
 * <p>Cross-lane contract (the S-4 settings screen compiles against exactly
 * this):
 * <pre>
 *   ThemeController.applyTheme(Activity activity, String mode)  // "system" | "light" | "dark"
 *   ThemeController.normalize(String mode)                      // -> one of the three
 * </pre>
 *
 * <p>USAGE: call {@code ThemeController.applyTheme(this, mode)} as the first
 * statement of {@code onCreate}, BEFORE {@code setContentView}. Applying a
 * theme after the content view is attached has no visible effect until the
 * activity is recreated, so this class never calls {@code recreate()} on its
 * own: the caller decides when a change should rebuild the UI.
 *
 * <p>Palettes live in {@code res/values/colors.xml} (maza_dark_* /
 * maza_light_*) and are wired up by {@code res/values/styles.xml}
 * ({@code Theme.MazaWallet} / {@code Theme.MazaWallet_Light}). The manifest
 * keeps its platform fallback theme, so this is the only entry point.
 *
 * <p>"system" resolution reads the ACTIVITY's configuration:
 * {@code getResources().getConfiguration().uiMode} masked with
 * {@code Configuration.UI_MODE_NIGHT_MASK}. That is deliberate: the device
 * configuration already accounts for a user's system-wide dark theme choice,
 * while {@code UiModeManager.getCurrentModeType()} reports the device mode
 * type (car / desk / television ...), not day/night, and would answer the
 * wrong question.
 *
 * <p>Platform APIs only: no AppCompat, no androidx (this is a raw
 * aapt2/javac/d8 build).
 */
public final class ThemeController {

    /** Follow the device day/night setting. Default for every unknown input. */
    public static final String MODE_SYSTEM = "system";
    /** Force the light palette regardless of the device setting. */
    public static final String MODE_LIGHT = "light";
    /** Force the dark palette regardless of the device setting. */
    public static final String MODE_DARK = "dark";

    private ThemeController() {
        // static helper only
    }

    /**
     * Normalizes a stored/typed mode string. Never throws and never returns
     * anything outside the three modes: null, empty and garbage all map to
     * {@link #MODE_SYSTEM}.
     */
    public static String normalize(String mode) {
        if (mode == null) return MODE_SYSTEM;
        String m = mode.trim().toLowerCase(Locale.US);
        if (MODE_LIGHT.equals(m)) return MODE_LIGHT;
        if (MODE_DARK.equals(m)) return MODE_DARK;
        return MODE_SYSTEM;
    }

    /** True when the configuration asks for night mode. */
    public static boolean isNightUiMode(int uiMode) {
        return (uiMode & android.content.res.Configuration.UI_MODE_NIGHT_MASK)
                == android.content.res.Configuration.UI_MODE_NIGHT_YES;
    }

    /**
     * Resolves a mode string to the palette that will actually be drawn:
     * {@link #MODE_LIGHT} or {@link #MODE_DARK}. "system" (and anything
     * unrecognized) resolves through {@code uiMode}.
     */
    public static String resolve(String mode, int uiMode) {
        String m = normalize(mode);
        if (MODE_LIGHT.equals(m)) return MODE_LIGHT;
        if (MODE_DARK.equals(m)) return MODE_DARK;
        return isNightUiMode(uiMode) ? MODE_DARK : MODE_LIGHT;
    }

    /** Style resource for an already-resolved mode ("light" or "dark"). */
    public static int styleFor(String resolvedMode) {
        return MODE_DARK.equals(resolvedMode)
                ? R.style.Theme_MazaWallet
                : R.style.Theme_MazaWallet_Light;
    }

    /**
     * Applies the palette to an activity. Safe to call before the content
     * view is set (that is the intended place); a no-op for a null activity.
     */
    public static void applyTheme(android.app.Activity activity, String mode) {
        if (activity == null) return;
        int uiMode = activity.getResources().getConfiguration().uiMode;
        int styleRes = styleFor(resolve(mode, uiMode));
        activity.setTheme(styleRes);
    }
}
