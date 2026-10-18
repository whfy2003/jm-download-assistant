package com.jmcomic.android.ui;

import android.content.res.ColorStateList;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.util.Base64;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.PathInterpolator;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.widget.ImageView;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.appcompat.app.AlertDialog;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.imageview.ShapeableImageView;
import com.google.android.material.progressindicator.LinearProgressIndicator;
import com.google.android.material.textfield.TextInputEditText;
import com.jmcomic.android.R;
import com.jmcomic.android.core.FileOps;
import com.jmcomic.android.core.LogExporter;
import com.jmcomic.android.core.Models;
import com.jmcomic.android.core.PdfThumbnails;
import com.jmcomic.android.core.Py;
import com.jmcomic.android.core.Ui;
import com.jmcomic.android.service.DownloadService;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.io.File;
import java.util.List;
import java.util.Locale;

/**
 * 下载页（主页）：只有「编号输入 + 预览封面 / 开始下载 + 进度 + 日志」。
 *
 * <p>下载记录已经挪到「本机」页，这里不再显示列表。
 *
 * <p>布局要点：主内容用 {@code layout_gravity="center"} 垂直居中；日志面板是
 * 铺满整页的浮层，平时整体沉到屏幕外、只露出 56dp 的头部（就是底部那条「运行日志」），
 * 展开时升起覆盖下半屏。因为日志面板不参与主内容的布局，所以无论日志是折叠还是展开，
 * 输入框和按钮的位置都不会动。
 */
public class DownloadFragment extends Fragment {

    private static final long POLL_MS = 1500L;

    /** 日志面板头部高度（56dp 标题条 + 1dp 分隔线） */
    private static final float LOG_HEADER_DP = 57f;

    /** 展开后露出屏幕的百分比（留够空间，展开时不会盖住输入框与按钮） */
    private static final float LOG_SHEET_RATIO = 0.45f;

    // 跨 Fragment 重建保留，避免重复弹「完成」提示
    private static String sLastFinishedAt = "";
    private static int sLastLogCount = -1;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable poller = new Runnable() {
        @Override
        public void run() {
            pollState();
            if (isResumed()) {
                handler.postDelayed(this, POLL_MS);
            }
        }
    };

    private TextInputEditText etAlbum;
    private MaterialButton btnDownload;
    private MaterialButton btnPreview;
    private TextView tvStatus;
    private TextView tvTask;
    private TextView tvLogs;
    private TextView tvLogCount;
    private LinearProgressIndicator progress;
    private ScrollView svLogs;
    private View logSheet;
    private ImageView ivLogArrow;

    private boolean logExpanded = false;

    /** 输入框里这个编号如果已经下载过，就存这里 */
    private Models.Record matched;
    private String lastLookupId = "";
    private Runnable lookupRunnable;

    private View albumCard;
    private ShapeableImageView albumThumb;
    private TextView albumId;
    private TextView albumName;
    private TextView albumTime;

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_download, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        etAlbum = view.findViewById(R.id.et_album_id);
        btnDownload = view.findViewById(R.id.btn_download);
        btnPreview = view.findViewById(R.id.btn_preview);
        tvStatus = view.findViewById(R.id.tv_status);
        tvTask = view.findViewById(R.id.tv_task);
        tvLogs = view.findViewById(R.id.tv_logs);
        tvLogCount = view.findViewById(R.id.tv_log_count);
        progress = view.findViewById(R.id.progress);
        svLogs = view.findViewById(R.id.sv_logs);
        logSheet = view.findViewById(R.id.log_sheet);
        ivLogArrow = view.findViewById(R.id.iv_log_arrow);

        albumCard = view.findViewById(R.id.album_card);
        albumThumb = view.findViewById(R.id.iv_album_thumb);
        albumId = view.findViewById(R.id.tv_album_id);
        albumName = view.findViewById(R.id.tv_album_name);
        albumTime = view.findViewById(R.id.tv_album_time);
        albumCard.setOnClickListener(v -> openMatched());

        etAlbum.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
            }

            @Override
            public void afterTextChanged(Editable s) {
                scheduleLookup(s.toString().trim());
            }
        });

        view.findViewById(R.id.log_header).setOnClickListener(v -> setLogExpanded(!logExpanded, true));
        view.findViewById(R.id.btn_export_log).setOnClickListener(v -> exportLog());



        btnDownload.setOnClickListener(v -> doDownload());
        btnPreview.setOnClickListener(v -> previewAlbum());

        etAlbum.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                doDownload();
                return true;
            }
            return false;
        });

        // 全局圆角（设置页可调）
        Ui.apply(view);

        // 布局完成后再定位日志面板，否则拿不到高度
        logSheet.post(() -> applyLogState(false));
    }

    @Override
    public void onResume() {
        super.onResume();
        handler.removeCallbacks(poller);
        handler.post(poller);
    }

    @Override
    public void onPause() {
        super.onPause();
        handler.removeCallbacks(poller);
    }

    // ------------------------------------------------------------------ //
    // 日志面板
    // ------------------------------------------------------------------ //
    private void setLogExpanded(boolean expanded, boolean animate) {
        logExpanded = expanded;
        applyLogState(animate);
    }

    private void applyLogState(boolean animate) {
        if (logSheet == null) {
            return;
        }
        int height = logSheet.getHeight();
        if (height <= 0) {
            logSheet.post(() -> applyLogState(animate));
            return;
        }

        float headerPx = LOG_HEADER_DP * getResources().getDisplayMetrics().density;
        float collapsedY = height - headerPx;
        float expandedY = height - height * LOG_SHEET_RATIO;
        float target = logExpanded ? expandedY : collapsedY;

        if (animate) {
            logSheet.animate()
                    .translationY(target)
                    .setDuration(220L)
                    .setInterpolator(new PathInterpolator(0.32f, 0.72f, 0f, 1f))
                    .start();
        } else {
            logSheet.setTranslationY(target);
        }

        // 箭头：展开时朝下（提示收起），折叠时朝上（提示展开）
        if (ivLogArrow != null) {
            ivLogArrow.animate()
                    .rotation(logExpanded ? 180f : 0f)
                    .setDuration(animate ? 200L : 0L)
                    .start();
        }
    }

    // ------------------------------------------------------------------ //
    // 下载
    // ------------------------------------------------------------------ //
    private void doDownload() {
        String id = validateAlbumId();
        if (id == null) {
            return;
        }
        if (matched != null && id.equals(matched.id)) {
            new MaterialAlertDialogBuilder(requireContext())
                    .setTitle("该本子已下载过")
                    .setMessage("「" + matched.name + "」已经在本机了。\n\n"
                            + "重新下载会覆盖同名 PDF，确定吗？")
                    .setNegativeButton("取消", null)
                    .setPositiveButton("重新下载", (d, which) -> startDownload(id))
                    .show();
            return;
        }
        startDownload(id);
    }

    /** 校验输入框里的编号，合法返回去空格后的编号，否则返回 null 并提示。 */
    private String validateAlbumId() {
        String id = text(etAlbum);
        if (id.isEmpty()) {
            toast("请输入本子编号");
            return null;
        }
        if (!id.matches("\\d+")) {
            toast("编号必须是纯数字");
            return null;
        }
        return id;
    }

    private void startDownload(String id) {
        hideKeyboard();
        btnDownload.setEnabled(false);
        DownloadService.start(requireContext(), id);
        toast("已开始下载 " + id);
        handler.postDelayed(this::pollState, 400);
    }

    // ------------------------------------------------------------------ //
    // 已下载检测：输入编号时去下载日志里比对
    // ------------------------------------------------------------------ //
    private void scheduleLookup(String id) {
        handler.removeCallbacks(lookupRunnable);
        if (id.isEmpty() || !id.matches("\\d+")) {
            showAlbumCard(null);
            return;
        }
        lookupRunnable = () -> lookupAlbum(id);
        handler.postDelayed(lookupRunnable, 350);
    }

    private void lookupAlbum(String id) {
        lastLookupId = id;
        Py.call("records", json -> {
            if (!isAdded()) {
                return;
            }
            // 用户在请求返回前又改了输入，这次结果作废
            if (!id.equals(text(etAlbum))) {
                return;
            }
            Models.Record hit = null;
            List<Models.Record> records = Models.Record.list(json);
            for (Models.Record record : records) {
                // 后端是模糊匹配，这里再精确比一次
                if (id.equals(record.id)) {
                    hit = record;
                    break;
                }
            }
            showAlbumCard(hit);
        }, "all", id);
    }

    private void showAlbumCard(Models.Record record) {
        if (albumCard == null) {
            return;
        }
        matched = record;
        if (record == null) {
            albumCard.setVisibility(View.GONE);
            return;
        }

        albumId.setText(record.id);
        albumName.setText(record.name);
        albumTime.setText(record.time == null || record.time.isEmpty() ? "—" : record.time);
        albumCard.setVisibility(View.VISIBLE);

        albumThumb.setTag(record.file);
        albumThumb.setImageDrawable(null);
        String dir = record.dir == null || record.dir.isEmpty() ? "" : record.dir;
        if (record.exists && !dir.isEmpty()) {
            File pdf = new File(dir, record.file);
            float density = getResources().getDisplayMetrics().density;
            PdfThumbnails.load(requireContext(), pdf,
                    Math.round(56 * density), Math.round(76 * density), bitmap -> {
                        if (bitmap != null && record.file.equals(albumThumb.getTag())) {
                            albumThumb.setImageBitmap(bitmap);
                        }
                    });
        }

        if (!isRunning()) {
            setStatusText(getString(R.string.status_downloaded), R.color.ok);
        }
    }

    private boolean isRunning() {
        return btnDownload != null && !btnDownload.isEnabled();
    }

    private void openMatched() {
        if (matched == null) {
            return;
        }
        String dir = matched.dir == null || matched.dir.isEmpty() ? "" : matched.dir;
        if (!matched.exists || dir.isEmpty()) {
            toast("文件已不在本机");
            return;
        }
        FileOps.openPdf(requireContext(), new File(dir, matched.file));
    }

    // ------------------------------------------------------------------ //
    // 预览封面
    // ------------------------------------------------------------------ //
    private void previewAlbum() {
        final String id = validateAlbumId();
        if (id == null) {
            return;
        }
        hideKeyboard();
        toast("正在获取封面…");

        Py.call("preview_album", json -> {
            if (!isAdded()) {
                return;
            }
            if (!json.optBoolean("ok", false)) {
                toast(json.optString("error", "获取失败"));
                return;
            }
            showPreviewDialog(id, json.optJSONObject("album"));
        }, id);
    }

    private void showPreviewDialog(String albumId, JSONObject album) {
        if (album == null || !isAdded()) {
            return;
        }
        View view = LayoutInflater.from(requireContext())
                .inflate(R.layout.dialog_preview, null, false);

        ImageView cover = view.findViewById(R.id.iv_cover);
        String base64 = album.optString("cover_base64", "");
        if (!base64.isEmpty()) {
            try {
                byte[] bytes = Base64.decode(base64, Base64.DEFAULT);
                Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
                if (bitmap != null) {
                    cover.setImageBitmap(bitmap);
                }
            } catch (Exception ignored) {
                // 解不出来就保留占位底色
            }
        }

        ((TextView) view.findViewById(R.id.tv_title))
                .setText(album.optString("title", albumId));

        String meta = "作者：" + emptyDash(album.optString("author", ""))
                + " · " + album.optInt("page_count", 0) + " 页"
                + " · " + album.optInt("episodes", 0) + " 章";
        String likes = album.optString("likes", "");
        String views = album.optString("views", "");
        if (!likes.isEmpty() || !views.isEmpty()) {
            meta += " · 赞 " + emptyDash(likes) + " · 看 " + emptyDash(views);
        }
        ((TextView) view.findViewById(R.id.tv_meta)).setText(meta);

        JSONArray tags = album.optJSONArray("tags");
        StringBuilder tagText = new StringBuilder();
        if (tags != null) {
            for (int i = 0; i < tags.length(); i++) {
                if (tagText.length() > 0) {
                    tagText.append(" · ");
                }
                tagText.append(tags.optString(i));
            }
        }
        TextView tvTags = view.findViewById(R.id.tv_tags);
        tvTags.setText(tagText.toString());
        tvTags.setVisibility(tagText.length() == 0 ? View.GONE : View.VISIBLE);

        TextView tvDescription = view.findViewById(R.id.tv_description);
        String description = album.optString("description", "");
        String coverError = album.optString("cover_error", "");
        if (!coverError.isEmpty()) {
            tvDescription.setText("封面获取失败：" + coverError);
            tvDescription.setVisibility(View.VISIBLE);
        } else {
            tvDescription.setText(description);
            tvDescription.setVisibility(description.isEmpty() ? View.GONE : View.VISIBLE);
        }

        AlertDialog dialog = new MaterialAlertDialogBuilder(requireContext())
                .setTitle("确认下载 " + albumId)
                .setView(view)
                .setNegativeButton("取消", null)
                .setPositiveButton("开始下载", (d, which) -> startDownload(albumId))
                .create();
        dialog.show();
        Ui.roundDialog(dialog);
    }

    private String emptyDash(String value) {
        return value == null || value.isEmpty() ? "—" : value;
    }

    // ------------------------------------------------------------------ //
    // 导出运行日志
    // ------------------------------------------------------------------ //
    private void exportLog() {
        Py.call("state", json -> {
            if (!isAdded()) {
                return;
            }
            Models.TaskState state = Models.TaskState.from(json);
            String stamp = new SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US)
                    .format(new Date());

            StringBuilder builder = new StringBuilder();
            builder.append("JM 下载助手 · 运行日志\n");
            builder.append("导出时间：")
                    .append(new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)
                            .format(new Date()))
                    .append('\n');
            builder.append("任务编号：")
                    .append(state.albumId.isEmpty() ? "-" : state.albumId)
                    .append('\n');
            builder.append("状态：");
            if (state.running) {
                builder.append("运行中");
            } else if (state.ok == Models.TaskState.SUCCESS) {
                builder.append("成功");
            } else if (state.ok == Models.TaskState.FAILED) {
                builder.append("失败");
            } else {
                builder.append("空闲");
            }
            builder.append('\n');
            builder.append("消息：").append(state.message).append("\n\n");

            if (state.logs.isEmpty()) {
                builder.append("（暂无运行日志）\n");
            } else {
                for (String line : state.logs) {
                    builder.append(line).append('\n');
                }
            }

            LogExporter.export(requireContext(), builder.toString(),
                    "jm-log-" + stamp + ".txt");
        }, 200);
    }

    // ------------------------------------------------------------------ //
    // 状态轮询
    // ------------------------------------------------------------------ //
    private void pollState() {
        Py.call("state", this::applyState, 60);
    }

    private void applyState(JSONObject json) {
        if (!isAdded() || getView() == null) {
            return;
        }
        if (!json.optBoolean("api_ok", true)) {
            setStatusText("服务未连接", R.color.danger);
            return;
        }

        Models.TaskState state = Models.TaskState.from(json);

        btnDownload.setEnabled(!state.running);
        btnPreview.setEnabled(!state.running);
        etAlbum.setEnabled(!state.running);

        // 进度条常驻显示：空闲时是一条灰色轨道，下载时填充品牌色
        progress.setVisibility(View.VISIBLE);
        if (state.running) {
            if (state.progressTotal > 0) {
                progress.setIndeterminate(false);
                progress.setProgressCompat(
                        Math.max(0, Math.min(100, state.progressPercent)), true);
            } else {
                progress.setIndeterminate(true);
            }
        } else {
            progress.setIndeterminate(false);
            progress.setProgressCompat(
                    state.ok == Models.TaskState.SUCCESS ? 100 : 0, false);
        }

        if (state.running) {
            setStatusText(getString(R.string.status_running), R.color.brand);
        } else if (state.ok == Models.TaskState.FAILED) {
            setStatusText(getString(R.string.status_failed), R.color.danger);
        } else if (matched != null) {
            setStatusText(getString(R.string.status_downloaded), R.color.ok);
        } else if (state.ok == Models.TaskState.SUCCESS) {
            setStatusText(getString(R.string.status_ok), R.color.ok);
        } else {
            setStatusText(getString(R.string.status_idle), R.color.text_secondary);
        }

        if (state.running) {
            tvTask.setText(progressText(state));
        } else if (state.ok == Models.TaskState.FAILED) {
            tvTask.setText(state.message);
        } else {
            // 空闲/成功时不重复显示 message（"空闲"已经由徽标表达）
            tvTask.setText(state.title.isEmpty() ? "" : state.title);
        }

        if (state.logs.size() != sLastLogCount) {
            sLastLogCount = state.logs.size();
            int from = Math.max(0, state.logs.size() - 60);
            StringBuilder builder = new StringBuilder();
            for (int i = from; i < state.logs.size(); i++) {
                builder.append(state.logs.get(i)).append('\n');
            }
            String text = builder.length() == 0 ? getString(R.string.log_empty) : builder.toString();
            tvLogs.setText(text);
            tvLogCount.setText(lastLine(state.logs));
            svLogs.post(() -> svLogs.fullScroll(View.FOCUS_DOWN));
        }

        if (!state.finishedAt.isEmpty() && !state.finishedAt.equals(sLastFinishedAt)) {
            sLastFinishedAt = state.finishedAt;
            // 结束时把日志面板收起来，让「已完成 / 标题」重新露出来
            if (logExpanded) {
                setLogExpanded(false, true);
            }
            // 刚下完这一本就不再显示「已下载」卡片，改显示「已完成 + 标题」
            if (matched != null && matched.id.equals(state.albumId)) {
                matched = null;
                albumCard.setVisibility(View.GONE);
            }
            if (state.ok == Models.TaskState.SUCCESS) {
                toast("下载完成：" + (state.title.isEmpty() ? state.albumId : state.title));
            } else if (state.ok == Models.TaskState.FAILED) {
                toast("下载失败：" + state.message);
            }
        }
    }

    /** 状态徽标：文字色随状态变，背景统一用品牌浅色 */
    private void setStatusText(String text, int colorRes) {
        tvStatus.setText(text);
        tvStatus.setTextColor(ContextCompat.getColor(requireContext(), colorRes));
        tvStatus.setBackgroundTintList(ColorStateList.valueOf(
                ContextCompat.getColor(requireContext(), R.color.brand_light)));
    }

    private String lastLine(java.util.List<String> logs) {
        if (logs == null || logs.isEmpty()) {
            return "";
        }
        String line = logs.get(logs.size() - 1);
        if (line == null) {
            return "";
        }
        line = line.trim();
        return line.length() <= 60 ? line : "…" + line.substring(line.length() - 58);
    }

    private String progressText(Models.TaskState state) {
        if (state.progressTotal > 0) {
            return state.progressDone + "/" + state.progressTotal + " 页 · "
                    + formatSpeed(state.progressSpeed)
                    + " · " + state.progressPercent + "%";
        }
        if (state.progressSpeed > 0.5) {
            return formatSpeed(state.progressSpeed);
        }
        return state.message;
    }

    private String formatSpeed(double bytesPerSecond) {
        if (bytesPerSecond <= 0.5) {
            return "0 B/s";
        }
        String[] units = {"B/s", "KB/s", "MB/s", "GB/s"};
        double value = bytesPerSecond;
        int index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index++;
        }
        return String.format(Locale.US,
                index == 0 ? "%.0f %s" : "%.1f %s", value, units[index]);
    }

    private String text(TextInputEditText editText) {
        if (editText == null || editText.getText() == null) {
            return "";
        }
        return editText.getText().toString().trim();
    }

    private void hideKeyboard() {
        InputMethodManager imm = requireContext().getSystemService(InputMethodManager.class);
        if (imm != null && getView() != null) {
            imm.hideSoftInputFromWindow(getView().getWindowToken(), 0);
        }
    }

    private void toast(String message) {
        if (isAdded()) {
            Toast.makeText(requireContext(), message, Toast.LENGTH_SHORT).show();
        }
    }
}
