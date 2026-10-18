package com.jmcomic.android.core;

import android.app.Dialog;
import android.content.Context;
import android.graphics.drawable.ColorDrawable;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;

import androidx.core.content.ContextCompat;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;
import com.google.android.material.progressindicator.LinearProgressIndicator;
import com.google.android.material.textfield.TextInputLayout;

/**
 * 全局外观：圆角档位。
 *
 * <p>设置页有一根 5 档滑杆（0=方框 … 4=胶囊），改完提示重启；这里负责把档位
 * 换算成 px 并递归套用到所有卡片 / 按钮 / 输入框 / 进度条 / 对话框上，
 * 保证全应用圆角一致。
 */
public final class Ui {

    public static final int LEVELS = 5;

    /** 卡片类（大块）的圆角 dp */
    private static final int[] CARD_CORNER = {0, 6, 10, 16, 26};

    /** 胶囊档时按钮 / 输入框用「高度的一半」，这里给一个大到足够的值让系统自己夹紧 */
    private static final int CAPSULE_DP = 999;

    private static final String PREF = "jm_ui";
    private static final String KEY_LEVEL = "corner_level";

    private Ui() {
    }

    public static int level(Context context) {
        return clamp(context.getSharedPreferences(PREF, Context.MODE_PRIVATE)
                .getInt(KEY_LEVEL, 2));
    }

    public static void setLevel(Context context, int level) {
        context.getSharedPreferences(PREF, Context.MODE_PRIVATE)
                .edit().putInt(KEY_LEVEL, clamp(level)).apply();
    }

    private static int clamp(int level) {
        return Math.max(0, Math.min(LEVELS - 1, level));
    }

    /** 卡片圆角（px） */
    public static int cardPx(Context context) {
        return dp(context, CARD_CORNER[level(context)]);
    }

    /** 按钮 / 输入框圆角（px），最高档为胶囊 */
    public static int pillPx(Context context) {
        int level = level(context);
        return dp(context, level >= LEVELS - 1 ? CAPSULE_DP : CARD_CORNER[level]);
    }

    public static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    /** 把当前档位套用到整棵视图树 */
    public static void apply(View root) {
        if (root == null) {
            return;
        }
        Context context = root.getContext();
        int level = level(context);
        int cardPx = dp(context, CARD_CORNER[level]);
        int pillPx = dp(context, level >= LEVELS - 1 ? CAPSULE_DP : CARD_CORNER[level]);
        walk(root, cardPx, pillPx);
    }

    private static void walk(View view, int cardPx, int pillPx) {
        if (view instanceof MaterialCardView) {
            ((MaterialCardView) view).setRadius(cardPx);
        } else if (view instanceof MaterialButton) {
            ((MaterialButton) view).setCornerRadius(pillPx);
        } else if (view instanceof TextInputLayout) {
            ((TextInputLayout) view).setBoxCornerRadii(pillPx, pillPx, pillPx, pillPx);
        } else if (view instanceof LinearProgressIndicator) {
            ((LinearProgressIndicator) view).setTrackCornerRadius(pillPx);
        }

        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                walk(group.getChildAt(i), cardPx, pillPx);
            }
        }
    }

    /** 对话框也要跟着圆：MaterialAlertDialog 默认是 28dp 固定值 */
    public static void roundDialog(Dialog dialog) {
        if (dialog == null || dialog.getWindow() == null) {
            return;
        }
        Context context = dialog.getContext();
        GradientDrawable background = new GradientDrawable();
        background.setColor(surfaceColor(context));
        background.setCornerRadius(cardPx(context));
        Window window = dialog.getWindow();
        window.setBackgroundDrawable(background);
        // 圆角外的四个角要透明，否则会露出方形阴影底
        window.setBackgroundDrawable(background);
    }

    private static int surfaceColor(Context context) {
        TypedValue value = new TypedValue();
        if (context.getTheme().resolveAttribute(
                com.google.android.material.R.attr.colorSurface, value, true)) {
            return value.data;
        }
        return ContextCompat.getColor(context, android.R.color.white);
    }

    /** 透明底（给需要自定义背景的对话框用） */
    public static void clearWindowBackground(Dialog dialog) {
        if (dialog == null || dialog.getWindow() == null) {
            return;
        }
        dialog.getWindow().setBackgroundDrawable(new ColorDrawable(android.graphics.Color.TRANSPARENT));
    }
}
