package com.mazawallet;

import android.content.Context;
import android.util.TypedValue;

/**
 * Resolves the ACTIVE theme's palette into one immutable Palette object.
 *
 * WHY THIS EXISTS
 * ---------------
 * MainActivity and SelfCustody used to pin nine ARGB ints (BG / CARD / BAR /
 * DIVIDER / TEXT / MUTED / ACCENT / RED / GREEN). Those constants ignore the
 * theme, so switching to the light theme turned the app's surfaces light while
 * the ink stayed dark-theme white (the integration blocker tracked by
 * tests/test_theme_contrast.py). Every color they draw now comes from here.
 *
 * HOW THE PALETTE IS CHOSEN
 * -------------------------
 * The two palettes are namespaced resources (values/colors.xml:
 * maza_dark_* / maza_light_*) and each theme in styles.xml points at exactly
 * one of them. So the canvas color the theme reports IS the selector:
 *
 *   1. resolve android:colorBackground (falling back to windowBackground)
 *      from the context's theme -- this is the theme that is live after
 *      ThemeController.applyTheme() and therefore follows an explicit user
 *      choice (light) even on a night-mode device, and vice versa;
 *   2. exact-match it against the two palette backgrounds;
 *   3. only for a theme we do not own (the manifest fallback before
 *      applyTheme runs) fall back to a luminance split.
 *
 * Dark mode is byte-identical to the constants this replaced: the dark slot
 * values in colors.xml are the same hexes, asserted by the frozen baseline in
 * tests/test_theme_contrast.py.
 *
 * LIFETIME
 * --------
 * One Palette per activity, resolved in onCreate() AFTER applyTheme() and
 * before the first view is built. A theme change is picked up WITHOUT an
 * activity restart: MainActivity.repaintForThemeChange() re-resolves on
 * resume (and on uiMode configuration changes) and repaints in place, so
 * the memory-only session survives both the Settings-driven switch and an
 * OS day/night flip. Palette is immutable, so worker threads may read it.
 */
public final class UiTheme {

    /** Relative-luminance split between "light canvas" and "dark canvas" used
     *  only for themes we do not own. The palettes sit far from 0.5
     *  (#141414 -> 0.006, #FAFAFA -> 0.96), so the split is unambiguous. */
    private static final double LIGHT_CANVAS_LUMINANCE = 0.5;

    private UiTheme() {
    }

    /** The palette for the context's CURRENT theme. */
    public static Palette palette(Context context) {
        Palette light = paletteOf(context, true);
        Palette dark = paletteOf(context, false);
        int canvas = canvasColor(context);
        if (canvas == light.background()) return light;
        if (canvas == dark.background()) return dark;
        return isLightCanvas(canvas) ? light : dark;
    }

    /** The nine slots one palette mode defines, resolved to opaque ARGB ints. */
    public static Palette paletteOf(Context context, boolean light) {
        return new Palette(
                light,
                color(context, light ? R.color.maza_light_background : R.color.maza_dark_background),
                color(context, light ? R.color.maza_light_surface : R.color.maza_dark_surface),
                color(context, light ? R.color.maza_light_bar : R.color.maza_dark_bar),
                color(context, light ? R.color.maza_light_divider : R.color.maza_dark_divider),
                color(context, light ? R.color.maza_light_text_primary : R.color.maza_dark_text_primary),
                color(context, light ? R.color.maza_light_text_secondary : R.color.maza_dark_text_secondary),
                color(context, light ? R.color.maza_light_accent : R.color.maza_dark_accent),
                color(context, light ? R.color.maza_light_danger : R.color.maza_dark_danger),
                color(context, light ? R.color.maza_light_success : R.color.maza_dark_success));
    }

    /** The theme's page color: android:colorBackground, else windowBackground.
     *  Returns 0 when neither resolves (the caller then falls back to dark,
     *  which is the pre-theming look). */
    private static int canvasColor(Context context) {
        int value = themeColor(context, android.R.attr.colorBackground);
        if (value != 0) return value;
        return themeColor(context, android.R.attr.windowBackground);
    }

    private static int themeColor(Context context, int attribute) {
        TypedValue typed = new TypedValue();
        if (!context.getTheme().resolveAttribute(attribute, typed, true)) return 0;
        if (typed.type >= TypedValue.TYPE_FIRST_COLOR_INT
                && typed.type <= TypedValue.TYPE_LAST_COLOR_INT) {
            return typed.data;
        }
        if (typed.resourceId != 0) return context.getColor(typed.resourceId);
        return 0;
    }

    private static int color(Context context, int resourceId) {
        return context.getColor(resourceId);
    }

    /** True when an opaque ARGB canvas color reads as a light surface.
     *  Pure math (WCAG 2.1 relative luminance), no Android API calls, so the
     *  desktop JVM probe in tests/test_theme_contrast.py can exercise it. */
    public static boolean isLightCanvas(int argb) {
        return relativeLuminance(argb) >= LIGHT_CANVAS_LUMINANCE;
    }

    /** WCAG 2.1 relative luminance of an opaque ARGB int, 0.0 .. 1.0. */
    public static double relativeLuminance(int argb) {
        return 0.2126 * channel(argb >> 16 & 0xFF)
                + 0.7152 * channel(argb >> 8 & 0xFF)
                + 0.0722 * channel(argb & 0xFF);
    }

    private static double channel(int value) {
        double c = value / 255.0;
        return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    }

    /** Immutable resolved palette. Accessors are named after the colors.xml
     *  slot suffixes (maza_&lt;mode&gt;_&lt;slot&gt;) so a call site reads like
     *  the resource it came from. */
    public static final class Palette {

        private final boolean light;
        private final int background;
        private final int surface;
        private final int bar;
        private final int divider;
        private final int textPrimary;
        private final int textSecondary;
        private final int accent;
        private final int danger;
        private final int success;

        Palette(boolean light, int background, int surface, int bar, int divider,
                int textPrimary, int textSecondary, int accent, int danger, int success) {
            this.light = light;
            this.background = background;
            this.surface = surface;
            this.bar = bar;
            this.divider = divider;
            this.textPrimary = textPrimary;
            this.textSecondary = textSecondary;
            this.accent = accent;
            this.danger = danger;
            this.success = success;
        }

        /** True for the light palette (maza_light_*). */
        public boolean isLight() {
            return light;
        }

        public int background() {
            return background;
        }

        public int surface() {
            return surface;
        }

        public int bar() {
            return bar;
        }

        public int divider() {
            return divider;
        }

        public int textPrimary() {
            return textPrimary;
        }

        public int textSecondary() {
            return textSecondary;
        }

        public int accent() {
            return accent;
        }

        public int danger() {
            return danger;
        }

        public int success() {
            return success;
        }
    }
}
