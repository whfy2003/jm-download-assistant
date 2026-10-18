package com.jmcomic.android.ui;

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
 * 「本机」页：下载完成后的记录都在这里（原来是下载页的下半部分）。
 *
 * <p>数据来自下载目录里的 jm_log.txt，与桌面版同一套格式：
 * 一个本子两行（标题行 + .pdf 行），解析时按 (编号, 时间) 合并，同文件名只留最新一条。
 */
public class LocalFragment extends Fragment implements RecordAdapter.Listener {

    private RecordAdapter adapter;
    private TextInputEditText etSearch;
    private TextView tvCount;
    private TextView tvEmpty;
    private TextView tvPdfDir;

    private String pdfDir = "";
    private String scope = "all";
    private String query = "";

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_local, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        etSearch = view.findViewById(R.id.et_search);
        tvCount = view.findViewById(R.id.tv_count);
        tvEmpty = view.findViewById(R.id.tv_empty);
        tvPdfDir = view.findViewById(R.id.tv_pdf_dir);
        RecyclerView recycler = view.findViewById(R.id.rv_records);

        adapter = new RecordAdapter(this, false);
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
            toast("已刷新下载记录");
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
        Py.call("settings", json -> {
            if (!isAdded()) {
                return;
            }
            Models.SettingsInfo info = Models.SettingsInfo.from(json.optJSONObject("dirs"));
            pdfDir = info.pdfDir;
            tvPdfDir.setText(shorten(pdfDir));
            adapter.setBaseDir(pdfDir);
        });

        Py.call("records", json -> {
            if (!isAdded()) {
                return;
            }
            List<Models.Record> records = Models.Record.list(json);
            adapter.submit(records);
            tvCount.setText("共 " + records.size() + " 条记录");
            tvEmpty.setVisibility(records.isEmpty() ? View.VISIBLE : View.GONE);
        }, scope, query);
    }

    @Override
    public void onOpen(Models.Record record) {
        if (pdfDir.isEmpty()) {
            toast("正在读取目录，请稍后再试");
            return;
        }
        FileOps.openPdf(requireContext(), new File(pdfDir, record.file));
    }

    @Override
    public void onToggleFavorite(Models.Record record) {
        String message = record.fav
                ? "取消收藏？\n\n" + record.file + "\n\n· 只从收藏列表移除\n· 下载目录里的文件保留"
                : "收藏到收藏夹？\n\n" + record.file + "\n\n（收藏只记录文件名，不复制文件，不占额外空间）";
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle(record.fav ? "取消收藏" : "收藏")
                .setMessage(message)
                .setNegativeButton("取消", null)
                .setPositiveButton("确定", (dialog, which) -> {
                    if (record.fav) {
                        Py.call("delete", json -> {
                            toast(json.optBoolean("ok", false) ? "已取消收藏"
                                    : json.optString("error", "操作失败"));
                            load();
                        }, record.file, record.id, "fav");
                    } else {
                        Py.call("favorite", json -> {
                            toast(json.optBoolean("ok", false)
                                    ? (json.optBoolean("already", false) ? "该文件已在收藏中" : "已收藏（仅记录，不复制文件）")
                                    : json.optString("error", "收藏失败"));
                            load();
                        }, record.file, record.id);
                    }
                })
                .show();
    }

    @Override
    public void onDelete(Models.Record record) {
        new MaterialAlertDialogBuilder(requireContext())
                .setTitle("删除文件")
                .setMessage("确定删除这个文件吗？\n\n" + record.file
                        + "\n\n· 文件将从下载目录中删除\n· 对应日志记录也会被抹去\n\n此操作不可撤销。")
                .setNegativeButton("取消", null)
                .setPositiveButton("删除", (dialog, which) ->
                        Py.call("delete", json -> {
                            if (json.optBoolean("ok", false)) {
                                toast("已删除（日志清理 " + json.optInt("lines_removed", 0) + " 行）");
                            } else {
                                toast(json.optString("error", "删除失败"));
                            }
                            load();
                        }, record.file, record.id, "dl"))
                .show();
    }

    @Override
    public void onExport(Models.Record record) {
        if (pdfDir.isEmpty()) {
            toast("正在读取目录，请稍后再试");
            return;
        }
        FileOps.exportToDownloads(requireContext(), new File(pdfDir, record.file));
    }

    /** 长路径只保留 files/ 之后的部分（…/JM/漫画），比截断尾部更好认 */
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
