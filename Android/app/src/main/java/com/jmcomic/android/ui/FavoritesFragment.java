package com.jmcomic.android.ui;

import android.app.AlertDialog;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.google.android.material.dialog.MaterialAlertDialogBuilder;
import com.google.android.material.textfield.TextInputEditText;
import com.jmcomic.android.R;
import com.jmcomic.android.core.FileOps;
import com.jmcomic.android.core.Models;
import com.jmcomic.android.core.Py;
import com.jmcomic.android.core.Ui;

import java.io.File;
import java.util.List;

/**
 * 收藏页。
 *
 * <p>移动端收藏**不复制 PDF**：点星标只往收藏目录的 {@code jm_fav_log.txt} 里记一行文件名，
 * 省一半空间。这一页读那份日志，再回下载目录把文件找出来展示；文件被删掉时显示「文件缺失」。
 * 取消收藏也只是抹掉日志那一行，不会动下载目录里的原文件。
 */
public class FavoritesFragment extends Fragment implements RecordAdapter.Listener {

    private RecordAdapter adapter;
    private TextInputEditText etSearch;
    private TextView tvWarning;
    private TextView tvCount;
    private TextView tvFavDir;
    private TextView tvEmpty;

    private String fallbackDir = "";
    private String scope = "all";
    private String query = "";

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_favorites, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        etSearch = view.findViewById(R.id.et_search);
        tvWarning = view.findViewById(R.id.tv_warning);
        tvCount = view.findViewById(R.id.tv_count);
        tvFavDir = view.findViewById(R.id.tv_fav_dir);
        tvEmpty = view.findViewById(R.id.tv_empty);
        RecyclerView recycler = view.findViewById(R.id.rv_records);

        adapter = new RecordAdapter(this, true);
        recycler.setLayoutManager(new LinearLayoutManager(requireContext()));
        recycler.setAdapter(adapter);

        view.findViewById(R.id.btn_recent).setOnClickListener(v -> {
            query = text(etSearch);
            scope = "recent";
            load();
        });
        view.findViewById(R.id.btn_all).setOnClickListener(v -> {
            query = text(etSearch);
            scope = "all";
            load();
        });
        view.findViewById(R.id.btn_refresh).setOnClickListener(v -> {
            load();
            toast("已刷新收藏记录");
        });
        etSearch.setOnEditorActionListener((v, actionId, event) -> {
            query = text(etSearch);
            scope = "recent";
            load();
            return true;
        });

        Ui.apply(view);
    }

    @Override
    public void onResume() {
        super.onResume();
        load();
    }

    private void load() {
        Py.call("favorites", json -> {
            if (!isAdded()) {
                return;
            }
            List<Models.Record> records = Models.Record.list(json);
            adapter.submit(records);
            tvCount.setText("共 " + records.size() + " 条收藏");
            tvEmpty.setVisibility(records.isEmpty() ? View.VISIBLE : View.GONE);

            fallbackDir = json.optString("fav_dir", fallbackDir);
            tvFavDir.setText(shorten(fallbackDir));
            adapter.setBaseDir(fallbackDir);

            String warning = json.optString("warning", "");
            if (warning == null || warning.isEmpty() || "null".equals(warning.trim())) {
                tvWarning.setVisibility(View.GONE);
            } else {
                tvWarning.setText(warning);
                tvWarning.setVisibility(View.VISIBLE);
            }
        }, scope, query);
    }

    private String dirOf(Models.Record record) {
        return record.dir == null || record.dir.isEmpty() ? fallbackDir : record.dir;
    }

    @Override
    public void onOpen(Models.Record record) {
        String dir = dirOf(record);
        if (dir.isEmpty()) {
            toast("正在读取目录，请稍后再试");
            return;
        }
        FileOps.openPdf(requireContext(), new File(dir, record.file));
    }

    @Override
    public void onToggleFavorite(Models.Record record) {
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle("取消收藏")
                .setMessage("将从收藏列表移除：\n\n" + record.file
                        + "\n\n收藏只记录了文件名，没有复制文件；"
                        + "取消后下载目录里的原文件仍然保留。")
                .setNegativeButton("取消", null)
                .setPositiveButton("确定", (dialog, which) ->
                        Py.call("delete", json -> {
                            toast(json.optBoolean("ok", false) ? "已取消收藏"
                                    : json.optString("error", "操作失败"));
                            load();
                        }, record.file, record.id, "fav"))
                .show();
    }

    @Override
    public void onDelete(Models.Record record) {
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle("从收藏移除")
                .setMessage("确定把这条从收藏里移除吗？\n\n" + record.file
                        + "\n\n只会删掉收藏记录，下载目录里的 PDF 不受影响。")
                .setNegativeButton("取消", null)
                .setPositiveButton("移除", (dialog, which) ->
                        Py.call("delete", json -> {
                            toast(json.optBoolean("ok", false) ? "已移除" : json.optString("error", "操作失败"));
                            load();
                        }, record.file, record.id, "fav"))
                .show();
    }

    @Override
    public void onExport(Models.Record record) {
        String dir = dirOf(record);
        if (dir.isEmpty()) {
            toast("正在读取目录，请稍后再试");
            return;
        }
        FileOps.exportToDownloads(requireContext(), new File(dir, record.file));
    }

    /** 长路径只保留 files/ 之后的部分（…/JM/收藏），比截断尾部更好认 */
    private String shorten(String path) {
        if (path == null || path.isEmpty()) {
            return "";
        }
        int index = path.indexOf("/files/");
        if (index >= 0) {
            return "…" + path.substring(index + "/files".length());
        }
        return path.length() <= 28 ? path : "…" + path.substring(path.length() - 26);
    }

    private String text(TextInputEditText editText) {
        if (editText == null || editText.getText() == null) {
            return "";
        }
        return editText.getText().toString().trim();
    }

    private void toast(String message) {
        if (isAdded()) {
            Toast.makeText(requireContext(), message, Toast.LENGTH_SHORT).show();
        }
    }
}
