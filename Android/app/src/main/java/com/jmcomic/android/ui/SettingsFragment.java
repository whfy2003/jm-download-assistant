package com.jmcomic.android.ui;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.HapticFeedbackConstants;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatDelegate;
import androidx.fragment.app.Fragment;

import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.materialswitch.MaterialSwitch;
import com.google.android.material.slider.Slider;
import com.google.android.material.textfield.TextInputEditText;
import com.jmcomic.android.R;
import com.jmcomic.android.core.FileOps;
import com.jmcomic.android.core.Models;
import com.jmcomic.android.core.Py;
import com.jmcomic.android.core.Ui;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * 设置页：项目主页入口、目录、环形磁盘占用、并发参数、外观（深色 + 全局圆角）、工具、关于。
 *
 * <p>卡片支持长按标题上下拖动重新排序，顺序存在 SharedPreferences 里。
 * 「项目主页」那张卡固定在顶部，不参与排序。
 */
public class SettingsFragment extends Fragment {

    private static final String PREFS = "jm_settings";
    private static final String KEY_DARK = "dark_mode";
    private static final String KEY_ORDER = "card_order";

    private static final String PROJECT_URL =
            "https://github.com/whfy2003/jm-download-assistant";

    private TextView tvPdfDir;
    private TextView tvFavDir;
    private TextView tvWorkDir;
    private TextView tvDiskPdf;
    private TextView tvDiskFav;
    private TextView tvDiskOther;
    private TextView tvDiskFree;
    private TextView tvDiskTotal;
    private TextView tvAbout;
    private TextView tvCornerDesc;

    private DonutChartView donut;

    private TextInputEditText etImageThreads;
    private TextInputEditText etPhotoThreads;
    private TextInputEditText etCookies;
    private TextInputEditText etProxy;
    private TextInputEditText etProxyUser;
    private TextInputEditText etProxyPass;
    private TextInputEditText etProxyOnly;

    private com.google.android.material.button.MaterialButtonToggleGroup toggleProxyType;
    private com.google.android.material.textfield.TextInputLayout tilProxyPass;
    private com.google.android.material.textfield.TextInputLayout tilCookies;

    private MaterialSwitch switchDark;

    private LinearLayout container;
    private ScrollView scrollView;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private boolean dragging;
    private float dragStartRawY;
    private Runnable longPressRunnable;

    // 拖动排序的状态
    private View dragCard;
    private int dragFromIndex;
    private int dragToIndex;
    private int dragHeight;

    // 拖动到屏幕上下边缘时自动滚动
    private float lastRawY;
    private int dragStartScrollY;

    private long lastThemeToggleAt = 0L;
    private boolean loadedOnce = false;

    private Models.SettingsInfo info = new Models.SettingsInfo();

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup parent,
                             @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_settings, parent, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        container = view.findViewById(R.id.settings_container);
        scrollView = view.findViewById(R.id.settings_scroll);

        tvPdfDir = view.findViewById(R.id.tv_pdf_dir);
        tvFavDir = view.findViewById(R.id.tv_fav_dir);
        tvWorkDir = view.findViewById(R.id.tv_work_dir);
        tvDiskPdf = view.findViewById(R.id.tv_disk_pdf);
        tvDiskFav = view.findViewById(R.id.tv_disk_fav);
        tvDiskOther = view.findViewById(R.id.tv_disk_other);
        tvDiskFree = view.findViewById(R.id.tv_disk_free);
        tvDiskTotal = view.findViewById(R.id.tv_disk_total);
        tvAbout = view.findViewById(R.id.tv_about);
        tvCornerDesc = view.findViewById(R.id.tv_corner_desc);
        donut = view.findViewById(R.id.donut_disk);
        etImageThreads = view.findViewById(R.id.et_image_threads);
        etPhotoThreads = view.findViewById(R.id.et_photo_threads);
        etCookies = view.findViewById(R.id.et_cookies);
        etProxy = view.findViewById(R.id.et_proxy);
        etProxyUser = view.findViewById(R.id.et_proxy_user);
        etProxyPass = view.findViewById(R.id.et_proxy_pass);
        etProxyOnly = view.findViewById(R.id.et_proxy_only);
        toggleProxyType = view.findViewById(R.id.toggle_proxy_type);
        tilProxyPass = view.findViewById(R.id.til_proxy_pass);
        tilCookies = view.findViewById(R.id.til_cookies);
        switchDark = view.findViewById(R.id.switch_dark);

        tvAbout.setText("JM 下载助手（Android）V1.02\n"
                + "下载核心：JMComic-Crawler-Python（MIT · hect0x7）\n"
                + "Python 运行时：Chaquopy 17.1 / Python 3.13\n"
                + "本项目仅做界面与流程封装，仅供个人学习与技术研究使用。\n"
                + "所有内容来自第三方站点，请遵守所在地区法律法规。");

        view.findViewById(R.id.card_project).setOnClickListener(v -> openProject());
        view.findViewById(R.id.btn_project).setOnClickListener(v -> openProject());

        setupDarkSwitch();
        setupCornerSlider(view);
        setupCardOrder(view);

        view.findViewById(R.id.btn_save_runtime).setOnClickListener(v -> saveRuntime());
        view.findViewById(R.id.btn_save_proxy).setOnClickListener(v -> saveRuntime());
        view.findViewById(R.id.btn_test_proxy).setOnClickListener(v -> testProxy());
        view.findViewById(R.id.btn_preview).setOnClickListener(v ->
                Py.call("option_preview", json -> {
                    if (json.optBoolean("ok", false)) {
                        showText("option 配置预览", json.optString("yaml", ""));
                    } else {
                        toast(json.optString("error", "读取失败"));
                    }
                }));
        view.findViewById(R.id.btn_clear_work).setOnClickListener(v -> clearWork());
        view.findViewById(R.id.btn_diagnose).setOnClickListener(v ->
                Py.call("diagnose", json -> showText("运行环境自检", pretty(json))));
        view.findViewById(R.id.btn_wipe).setOnClickListener(v -> confirmWipeFirst());

        // 全局圆角
        Ui.apply(view);
    }

    // ------------------------------------------------------------------ //
    // 清除所有下载数据（两次确认）
    // ------------------------------------------------------------------ //
    private void confirmWipeFirst() {
        if (!isAdded()) {
            return;
        }
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle("清除所有下载数据")
                .setMessage("将会删除：\n\n"
                        + "· 下载目录里的全部漫画 PDF\n"
                        + "· 下载记录 jm_log.txt\n"
                        + "· 收藏记录 jm_fav_log.txt\n"
                        + "· 图片工作区里的临时文件\n\n"
                        + "⚠ 删除后无法找回，也不会进回收站。")
                .setNegativeButton("取消", null)
                .setPositiveButton("我已了解，继续", (dialog, which) -> confirmWipeSecond())
                .show();
    }

    private void confirmWipeSecond() {
        if (!isAdded()) {
            return;
        }
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle("再次确认")
                .setMessage("确定删除所有已下载的内容吗？\n\n这一步执行完就再也恢复不了了。")
                .setNegativeButton("取消", null)
                .setPositiveButton("确定删除", (dialog, which) -> doWipe())
                .show();
    }

    private void doWipe() {
        Py.call("wipe_all", json -> {
            if (!isAdded()) {
                return;
            }
            if (json.optBoolean("ok", false)) {
                int files = json.optInt("pdf_files", 0) + json.optInt("fav_files", 0);
                int logs = json.optInt("logs", 0);
                toast("已清除：PDF " + files + " 个、日志 " + logs + " 个");
                load();
            } else {
                toast(json.optString("error", "清除失败"));
            }
        });
    }

    // ------------------------------------------------------------------ //
    // 项目主页
    // ------------------------------------------------------------------ //
    private void openProject() {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(PROJECT_URL)));
        } catch (Exception e) {
            toast("没有可用的浏览器");
        }
    }

    // ------------------------------------------------------------------ //
    // 深色模式
    // ------------------------------------------------------------------ //
    private void setupDarkSwitch() {
        switchDark.setChecked(isDarkPref());
        switchDark.setOnCheckedChangeListener((buttonView, checked) -> {
            long now = android.os.SystemClock.elapsedRealtime();
            if (now - lastThemeToggleAt < 800) {
                return;                     // 防抖：避免快速连点触发多次 recreate
            }
            lastThemeToggleAt = now;

            prefs().edit().putBoolean(KEY_DARK, checked).apply();

            // 先手动把窗口底色刷成目标色，避免重建瞬间白闪
            if (getActivity() != null) {
                getActivity().getWindow().setBackgroundDrawableResource(
                        checked ? R.color.surface_dark : android.R.color.white);
            }

            int target = checked
                    ? AppCompatDelegate.MODE_NIGHT_YES
                    : AppCompatDelegate.MODE_NIGHT_NO;

            if (AppCompatDelegate.getDefaultNightMode() == target) {
                return;
            }
            buttonView.post(() -> AppCompatDelegate.setDefaultNightMode(target));
        });
    }

    // ------------------------------------------------------------------ //
    // 圆角档位
    // ------------------------------------------------------------------ //
    private void setupCornerSlider(View view) {
        Slider slider = view.findViewById(R.id.slider_corner);
        int level = Ui.level(requireContext());
        slider.setValue(level);
        updateCornerDesc(level);

        slider.addOnChangeListener((s, value, fromUser) -> {
            int next = (int) value;
            if (next == Ui.level(requireContext())) {
                return;
            }
            Ui.setLevel(requireContext(), next);
            updateCornerDesc(next);
            Ui.apply(view);            // 当前页立刻生效，当作预览
            promptRestart();
        });
    }

    private void updateCornerDesc(int level) {
        String[] names = {"方框（完全直角）", "小圆角", "中圆角（默认）",
                "大圆角", "胶囊（最大圆角）"};
        tvCornerDesc.setText("当前：" + names[Math.max(0, Math.min(names.length - 1, level))]);
    }

    private void promptRestart() {
        if (!isAdded()) {
            return;
        }
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle("圆角已更改")
                .setMessage("新的圆角需要重新启动应用后才能应用到所有页面。\n\n现在重启吗？")
                .setNegativeButton("稍后", null)
                .setPositiveButton("立即重启", (dialog, which) -> {
                    if (getActivity() != null) {
                        getActivity().recreate();
                    }
                })
                .show();
    }

    // ------------------------------------------------------------------ //
    // 卡片拖动排序
    // ------------------------------------------------------------------ //
    private void setupCardOrder(View root) {
        restoreOrder();

        for (int i = 0; i < container.getChildCount(); i++) {
            View card = container.getChildAt(i);
            if (card.getTag() == null) {
                continue;                     // 项目主页那张不参与排序
            }
            View handle = findHandle(card);
            if (handle != null) {
                bindDrag(handle, card);
            }
        }
    }

    /** 卡片里第一个 TextView（标题）就是拖动把手 */
    private View findHandle(View card) {
        if (card.getId() == R.id.drag_paths || card.getId() == R.id.drag_disk
                || card.getId() == R.id.drag_runtime || card.getId() == R.id.drag_proxy
                || card.getId() == R.id.drag_appearance
                || card.getId() == R.id.drag_tools || card.getId() == R.id.drag_about) {
            return card;
        }
        if (card instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) card;
            for (int i = 0; i < group.getChildCount(); i++) {
                View child = group.getChildAt(i);
                View found = findHandle(child);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    private void bindDrag(View handle, View card) {
        handle.setOnTouchListener((v, event) -> {
            switch (event.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    dragStartRawY = event.getRawY();
                    // 按下就拦住 ScrollView：否则滑动几像素就被判成"滚页面"，
                    // 长按还没生效事件就被 CANCEL 了。标题区不用于滚动，代价可接受。
                    requestParentIntercept(v, true);
                    handler.removeCallbacks(longPressRunnable);
                    longPressRunnable = () -> startDrag(card, v);
                    handler.postDelayed(longPressRunnable, 300);
                    return true;
                case MotionEvent.ACTION_MOVE: {
                    lastRawY = event.getRawY();
                    // 自动滚动时手指不动、内容在滚，所以位移要把 scrollY 的差值算进去
                    float dy = (lastRawY - dragStartRawY)
                            + (scrollView.getScrollY() - dragStartScrollY);
                    if (!dragging) {
                        if (Math.abs(lastRawY - dragStartRawY) > dp(14)) {
                            handler.removeCallbacks(longPressRunnable);
                        }
                        return true;
                    }
                    dragCard.setTranslationY(dy);
                    updateDragTarget(dy);
                    return true;
                }                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    handler.removeCallbacks(longPressRunnable);
                    requestParentIntercept(v, false);
                    if (dragging) {
                        dragging = false;
                        finishDrag();
                    }
                    return true;
                default:
                    return false;
            }
        });
    }

    /** 长按生效：卡片浮到最上层，开始跟手 */
    private void startDrag(View card, View handle) {
        dragging = true;
        dragCard = card;
        dragFromIndex = container.indexOfChild(card);
        dragToIndex = dragFromIndex;
        dragHeight = card.getHeight();

        lastRawY = dragStartRawY;
        dragStartScrollY = scrollView.getScrollY();

        // 抬高 Z 轴：被拖的卡片永远压在所有卡片上面，方便看清落点
        card.setTranslationZ(dp(24));
        card.animate().scaleX(1.02f).scaleY(1.02f).alpha(0.96f).setDuration(120).start();
        handle.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS);

        handler.post(autoScrollRunnable);
    }

    /**
     * 拖到屏幕上下边缘时缓慢滚动页面 —— 手指停在边缘，列表一直滑，
     * 这样就能把卡片拖到当前屏幕之外的位置。
     */
    private final Runnable autoScrollRunnable = new Runnable() {
        @Override
        public void run() {
            if (!dragging || dragCard == null || scrollView == null) {
                return;
            }

            int[] location = new int[2];
            scrollView.getLocationOnScreen(location);
            float top = location[1];
            float bottom = top + scrollView.getHeight();

            int edge = dp(140);
            float speed = 0f;
            if (lastRawY < top + edge) {
                float ratio = 1f - Math.max(0f, lastRawY - top) / edge;   // 越靠边越快
                speed = -dp(3) - dp(13) * ratio;
            } else if (lastRawY > bottom - edge) {
                float ratio = 1f - Math.max(0f, bottom - lastRawY) / edge;
                speed = dp(3) + dp(13) * ratio;
            }

            if (Math.abs(speed) > 0.5f) {
                int before = scrollView.getScrollY();
                scrollView.scrollBy(0, (int) speed);
                if (scrollView.getScrollY() != before) {
                    float dy = (lastRawY - dragStartRawY)
                            + (scrollView.getScrollY() - dragStartScrollY);
                    dragCard.setTranslationY(dy);
                    updateDragTarget(dy);
                }
            }

            handler.postDelayed(this, 16);
        }
    };

    /** 手指移到别处：算出松手后会落在哪个位置 */
    private void updateDragTarget(float dy) {
        if (dragCard == null) {
            return;
        }
        float center = dragCard.getTop() + dy + dragHeight / 2f;

        int target = dragFromIndex;
        for (int i = 0; i < container.getChildCount(); i++) {
            View other = container.getChildAt(i);
            if (other == dragCard || other.getTag() == null) {
                continue;
            }
            float otherCenter = (other.getTop() + other.getBottom()) / 2f;
            if (center > otherCenter && i > dragFromIndex) {
                target = Math.max(target, i);
            } else if (center < otherCenter && i < dragFromIndex) {
                target = Math.min(target, i);
            }
        }
        if (target != dragToIndex) {
            dragToIndex = target;
            applyShift();
        }
    }

    /**
     * 让中间那些卡片给被拖的卡片腾地方 —— 空位高度正好等于被拖卡片，
     * 相当于提前预览松手后的布局。
     */
    private void applyShift() {
        if (dragCard == null) {
            return;
        }
        float shift = dragHeight + dp(12);

        for (int i = 0; i < container.getChildCount(); i++) {
            View other = container.getChildAt(i);
            if (other == dragCard) {
                continue;
            }
            if (other.getTag() == null) {
                continue;
            }
            float target = 0f;
            if (dragToIndex > dragFromIndex && i > dragFromIndex && i <= dragToIndex) {
                target = -shift;      // 往下拖：上面的卡片整体上移，空位出现在下方
            } else if (dragToIndex < dragFromIndex && i >= dragToIndex && i < dragFromIndex) {
                target = shift;       // 往上拖：下面的卡片整体下移
            }
            other.animate().translationY(target).setDuration(130).start();
        }
    }

    private void finishDrag() {
        if (dragCard == null) {
            return;
        }
        View card = dragCard;
        int from = dragFromIndex;
        int to = dragToIndex;

        dragCard = null;
        handler.removeCallbacks(autoScrollRunnable);
        card.setTranslationY(0f);
        card.setTranslationZ(0f);
        card.animate().scaleX(1f).scaleY(1f).alpha(1f).setDuration(140).start();

        for (int i = 0; i < container.getChildCount(); i++) {
            View other = container.getChildAt(i);
            if (other != card) {
                other.animate().translationY(0f).setDuration(160).start();
            }
        }

        if (to != from && to >= 0) {
            container.removeView(card);
            container.addView(card, Math.min(to, container.getChildCount()));
            saveOrder();
            toast("设置顺序已保存");
        }
    }

    private void saveOrder() {
        StringBuilder builder = new StringBuilder();
        for (int i = 0; i < container.getChildCount(); i++) {
            Object tag = container.getChildAt(i).getTag();
            if (tag == null) {
                continue;
            }
            if (builder.length() > 0) {
                builder.append(',');
            }
            builder.append(tag);
        }
        prefs().edit().putString(KEY_ORDER, builder.toString()).apply();
    }

    private void restoreOrder() {
        String order = prefs().getString(KEY_ORDER, "");
        if (order == null || order.isEmpty()) {
            return;
        }

        // 兼容旧版本保存的顺序：新加的「代理」卡片默认排在「下载参数」后面
        if (!order.contains("proxy")) {
            order = order.contains("runtime")
                    ? order.replace("runtime", "runtime,proxy")
                    : order + ",proxy";
        }

        Map<String, View> byTag = new HashMap<>();
        for (int i = 0; i < container.getChildCount(); i++) {
            View card = container.getChildAt(i);
            if (card.getTag() != null) {
                byTag.put(String.valueOf(card.getTag()), card);
            }
        }

        for (String tag : order.split(",")) {
            View card = byTag.remove(tag);
            if (card != null) {
                container.removeView(card);
                container.addView(card);
            }
        }
        // 没出现在保存顺序里的（新加的卡片）接在后面
        for (View card : byTag.values()) {
            container.removeView(card);
            container.addView(card);
        }
    }


    /** 拖动期间禁止外层 ScrollView 抢事件（View 上没有这个方法，要问到 parent） */
    private void requestParentIntercept(View view, boolean disallow) {
        android.view.ViewParent parent = view.getParent();
        if (parent != null) {
            parent.requestDisallowInterceptTouchEvent(disallow);
        }
    }
    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    // ------------------------------------------------------------------ //
    // 数据加载
    // ------------------------------------------------------------------ //
    private String pretty(JSONObject json) {
        try {
            return json.toString(2);
        } catch (Exception e) {
            return String.valueOf(json);
        }
    }

    @Override
    public void onResume() {
        super.onResume();
        load(!loadedOnce);
        loadedOnce = true;
    }

    private void load() {
        load(true);
    }

    /**
     * @param resetSecrets 是否清空「密码 / Cookie」输入框。
     *                     首次加载清空；保存或重进页面时保留用户正在输入的内容。
     */
    private void load(boolean resetSecrets) {
        Py.call("settings", json -> {
            if (!isAdded()) {
                return;
            }
            info = Models.SettingsInfo.from(json.optJSONObject("dirs"));
            tvPdfDir.setText(info.pdfDir);
            tvFavDir.setText(info.favDir);
            tvWorkDir.setText(info.workDir);

            etImageThreads.setText(String.valueOf(info.imageThreads));
            etPhotoThreads.setText(String.valueOf(info.photoThreads));
            etProxy.setText(info.proxy);
            etProxyUser.setText(info.proxyUser);
            etProxyOnly.setText(info.proxyOnly);
            toggleProxyType.check(typeButtonId(info.proxyType));

            if (resetSecrets) {
                etProxyPass.setText("");
                etCookies.setText("");
            }
            // hint 要设在 TextInputLayout 上，设在 EditText 上会和浮动标签重叠
            tilProxyPass.setHint(info.hasProxyPassword
                    ? "密码已保存（留空＝不变）"
                    : "密码（可选）");
            tilCookies.setHint(info.hasCookies
                    ? "Cookie 已保存（留空＝不变）"
                    : "Cookie（AVS=...）");

            JSONObject disk = json.optJSONObject("disk");
            if (disk != null) {
                Models.DiskInfo pdf = Models.DiskInfo.from(disk.optJSONObject("pdf"));
                Models.DiskInfo fav = Models.DiskInfo.from(disk.optJSONObject("fav"));

                donut.setData(pdf.dirSize, fav.dirSize, pdf.otherUsed, pdf.free);
                tvDiskPdf.setText("下载目录 · " + fmtSize(pdf.dirSize));
                tvDiskFav.setText("收藏目录 · " + fmtSize(fav.dirSize));
                tvDiskOther.setText("同盘其它 · " + fmtSize(pdf.otherUsed));
                tvDiskFree.setText("可用 · " + fmtSize(pdf.free));
                tvDiskTotal.setText("已用 " + fmtSize(pdf.used) + " / 共 " + fmtSize(pdf.total));
            }
        });
    }

    private void saveRuntime() {
        saveRuntime(null);
    }

    private void saveRuntime(Runnable afterSaved) {
        int image = parseInt(text(etImageThreads), info.imageThreads);
        int photo = parseInt(text(etPhotoThreads), info.photoThreads);
        String cookies = text(etCookies);
        String proxy = text(etProxy);
        String proxyUser = text(etProxyUser);
        String proxyPass = text(etProxyPass);
        String proxyOnly = text(etProxyOnly);
        String proxyType = selectedProxyType();

        Py.call("update_runtime", json -> {
            if (json.optBoolean("ok", false)) {
                toast("已保存下载参数");
                load(false);
                if (afterSaved != null) {
                    afterSaved.run();
                }
            } else {
                toast(json.optString("error", "保存失败"));
            }
        }, image, photo, cookies, proxy, proxyUser, proxyPass, proxyOnly, proxyType);
    }

    private int typeButtonId(String type) {
        if ("socks".equals(type)) {
            return R.id.btn_type_socks;
        }
        if ("http".equals(type)) {
            return R.id.btn_type_http;
        }
        return R.id.btn_type_auto;
    }

    private String selectedProxyType() {
        int checked = toggleProxyType.getCheckedButtonId();
        if (checked == R.id.btn_type_socks) {
            return "socks";
        }
        if (checked == R.id.btn_type_http) {
            return "http";
        }
        return "auto";
    }

    /** 先用当前输入保存，再验证 TCP 端口 + HTTP / SOCKS5 × HTTP / HTTPS。 */
    private void testProxy() {
        toast("正在通过代理请求…");
        saveRuntime(() -> Py.call("test_proxy", json -> {
            boolean ok = json.optBoolean("ok", false);
            StringBuilder text = new StringBuilder();
            text.append(ok ? "代理可用 ✅" : "代理不可用 ❌").append("\n\n");
            text.append("代理：").append(json.optString("proxy", "—")).append('\n');
            text.append("认证：")
                    .append(json.optBoolean("auth", false) ? "已带上用户名/密码" : "无")
                    .append("\n\n");

            JSONObject tcp = json.optJSONObject("tcp");
            if (tcp != null) {
                text.append("TCP 端口：")
                        .append(tcp.optBoolean("ok", false) ? "✓ 可达" : "✗ 连不上")
                        .append(" (").append(tcp.optInt("elapsed_ms", 0)).append(" ms)");
                String tcpError = tcp.optString("error", "");
                if (!tcpError.isEmpty()) {
                    text.append("\n   ").append(tcpError);
                }
                text.append("\n\n");
            }

            JSONArray results = json.optJSONArray("results");
            if (results != null) {
                for (int i = 0; i < results.length(); i++) {
                    JSONObject item = results.optJSONObject(i);
                    if (item == null) {
                        continue;
                    }
                    boolean itemOk = item.optBoolean("ok", false);
                    text.append(itemOk ? "✓ " : "✗ ")
                            .append(item.optString("label", "?"))
                            .append("：");
                    if (item.has("status")) {
                        text.append("HTTP ").append(item.optInt("status", 0)).append(' ');
                    }
                    text.append('(').append(item.optInt("elapsed_ms", 0)).append(" ms)");
                    String error = item.optString("error", "");
                    if (!error.isEmpty()) {
                        text.append("\n   ").append(error);
                    }
                    text.append('\n');
                }
            }

            if (json.has("direct_status")) {
                text.append("\n直连对照：HTTP ")
                        .append(json.optInt("direct_status", 0)).append('\n');
            }
            String directError = json.optString("direct_error", "");
            if (!directError.isEmpty()) {
                text.append("\n直连也失败：").append(directError).append('\n');
            }

            String recommended = json.optString("recommended", "");
            if (!recommended.isEmpty()) {
                text.append("\n推荐协议：")
                        .append("socks".equals(recommended) ? "SOCKS5" : "HTTP")
                        .append("（可在上面「代理协议」里选中它）\n");
            }

            if (!ok) {
                text.append("\n排查建议：\n")
                        .append("· 代理软件里打开「允许局域网连接 / allow-lan」\n")
                        .append("· 手机和电脑要连同一个 Wi-Fi，电脑防火墙放行该端口\n")
                        .append("· 认证失败一般返回 407，核对用户名/密码\n")
                        .append("· 地址只填「主机:端口」，不要带路径\n")
                        .append("· OpenClash 的认证信息可能只对 SOCKS5 生效，试试「代理协议」选 SOCKS5\n");
            }

            new MaterialAlertDialogBuilder(requireContext())
                    .setTitle("代理测试（TCP + HTTP/SOCKS5）")
                    .setMessage(text.toString())
                    .setPositiveButton("关闭", null)
                    .show();
        }));
    }

    private void clearWork() {
        File work = new File(info.workDir == null ? "" : info.workDir);
        if (!work.exists()) {
            toast("工作区已经是空的");
            return;
        }
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle("清空图片工作区")
                .setMessage("工作区里是下载过程中解出来的图片。\n"
                        + "正常情况下合并成 PDF 后会自动清空，这里只用于手动兜底。\n\n确认清空？")
                .setNegativeButton("取消", null)
                .setPositiveButton("清空", (dialog, which) -> {
                    FileOps.deleteRecursively(work);
                    toast("已清空");
                    load();
                })
                .show();
    }

    private void showText(String title, String content) {
        if (!isAdded()) {
            return;
        }
        TextView textView = new TextView(requireContext());
        textView.setText(content);
        textView.setTextSize(11);
        textView.setTypeface(android.graphics.Typeface.MONOSPACE);
        textView.setTextIsSelectable(true);
        int pad = (int) (getResources().getDisplayMetrics().density * 16);
        textView.setPadding(pad, pad, pad, pad);

        ScrollView scrollView = new ScrollView(requireContext());
        scrollView.addView(textView);

        new MaterialAlertDialogBuilder(requireContext())
                .setTitle(title)
                .setView(scrollView)
                .setPositiveButton("关闭", null)
                .show();
    }

    private void toast(String message) {
        if (isAdded()) {
            Toast.makeText(requireContext(), message, Toast.LENGTH_SHORT).show();
        }
    }

    private boolean isDarkPref() {
        return prefs().getBoolean(KEY_DARK, false);
    }

    private SharedPreferences prefs() {
        return requireContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private String text(TextInputEditText editText) {
        if (editText == null || editText.getText() == null) {
            return "";
        }
        return editText.getText().toString().trim();
    }

    private int parseInt(String raw, int fallback) {
        try {
            return Integer.parseInt(raw);
        } catch (Exception e) {
            return fallback;
        }
    }

    private String fmtSize(long bytes) {
        if (bytes <= 0) {
            return "0 B";
        }
        String[] units = {"B", "KB", "MB", "GB", "TB"};
        double value = bytes;
        int index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index++;
        }
        return (index == 0 ? String.valueOf((long) value) : String.format(Locale.US, "%.1f", value))
                + " " + units[index];
    }
}
