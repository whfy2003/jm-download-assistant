package com.jmcomic.android.ui;

import android.content.Context;
import android.graphics.Bitmap;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;
import android.widget.PopupMenu;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.google.android.material.imageview.ShapeableImageView;
import com.jmcomic.android.R;
import com.jmcomic.android.core.Models;
import com.jmcomic.android.core.PdfThumbnails;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** 下载记录 / 收藏记录共用的列表适配器（带 PDF 首屏缩略图）。 */
public class RecordAdapter extends RecyclerView.Adapter<RecordAdapter.Holder> {

    public interface Listener {
        void onOpen(Models.Record record);

        void onToggleFavorite(Models.Record record);

        void onDelete(Models.Record record);

        void onExport(Models.Record record);
    }

    private final List<Models.Record> items = new ArrayList<>();
    private final Listener listener;
    private final boolean favoritePage;

    /** 记录里存的是文件名，真正的位置由页面告诉适配器 */
    private String baseDir = "";

    public RecordAdapter(Listener listener, boolean favoritePage) {
        this.listener = listener;
        this.favoritePage = favoritePage;
    }

    public void setBaseDir(String dir) {
        String next = dir == null ? "" : dir;
        if (next.equals(baseDir)) {
            return;
        }
        baseDir = next;
        notifyDataSetChanged();
    }

    public void submit(List<Models.Record> records) {
        items.clear();
        if (records != null) {
            items.addAll(records);
        }
        notifyDataSetChanged();
    }

    public int count() {
        return items.size();
    }

    @NonNull
    @Override
    public Holder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_record, parent, false);
        return new Holder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull Holder holder, int position) {
        Models.Record record = items.get(position);
        Context context = holder.itemView.getContext();

        holder.tvId.setText(record.id.isEmpty() ? "-" : record.id);
        holder.tvName.setText(record.name);

        String time = record.time == null || record.time.isEmpty() ? "—" : record.time;
        holder.tvTime.setText(time);

        holder.tvBadge.setVisibility(record.exists ? View.GONE : View.VISIBLE);

        boolean starred = favoritePage || record.fav;
        holder.btnStar.setImageResource(starred ? R.drawable.ic_star : R.drawable.ic_star_outline);
        holder.btnStar.setColorFilter(context.getColor(
                starred ? R.color.brand : R.color.text_secondary));
        holder.btnStar.setContentDescription(starred ? "取消收藏" : "收藏");

        bindThumbnail(holder, context, record);

        holder.itemView.setOnClickListener(v -> listener.onOpen(record));
        holder.itemView.setOnLongClickListener(v -> {
            showMenu(context, holder, record);
            return true;
        });
        holder.btnStar.setOnClickListener(v -> listener.onToggleFavorite(record));
        holder.btnTrash.setOnClickListener(v -> listener.onDelete(record));
    }

    /** 用本地 PDF 首页渲染缩略图，历史记录也能显示，不依赖网络。 */
    private void bindThumbnail(Holder holder, Context context, Models.Record record) {
        holder.ivThumb.setTag(record.file);
        holder.ivThumb.setImageDrawable(null);

        if (!record.exists) {
            return;
        }
        // 收藏记录的文件在下载目录（移动端收藏不复制），优先用后端给的 dir
        String base = record.dir == null || record.dir.isEmpty() ? baseDir : record.dir;
        if (base.isEmpty()) {
            return;
        }
        File pdf = new File(base, record.file);
        if (!pdf.isFile()) {
            return;
        }

        float density = context.getResources().getDisplayMetrics().density;
        int width = Math.round(56 * density);
        int height = Math.round(76 * density);

        PdfThumbnails.load(context, pdf, width, height, bitmap -> {
            // 复用检查：这一格如果已经被别的记录占了，就丢弃迟到的结果
            if (!record.file.equals(holder.ivThumb.getTag())) {
                return;
            }
            if (bitmap != null) {
                holder.ivThumb.setImageBitmap(bitmap);
            }
        });
    }

    /** 长按菜单：打开 / 导出到系统下载目录 / 删除。 */
    private void showMenu(Context context, Holder holder, Models.Record record) {
        PopupMenu menu = new PopupMenu(context, holder.itemView);
        menu.getMenu().add(0, 1, 0, "打开");
        menu.getMenu().add(0, 2, 1, "导出到“下载”");
        menu.getMenu().add(0, 3, 2, favoritePage ? "删除收藏" : "删除文件与记录");

        menu.setOnMenuItemClickListener(item -> {
            switch (item.getItemId()) {
                case 1:
                    listener.onOpen(record);
                    return true;
                case 2:
                    listener.onExport(record);
                    return true;
                case 3:
                    listener.onDelete(record);
                    return true;
                default:
                    return false;
            }
        });
        menu.show();
    }

    @Override
    public int getItemCount() {
        return items.size();
    }

    static final class Holder extends RecyclerView.ViewHolder {
        final ShapeableImageView ivThumb;
        final TextView tvId;
        final TextView tvName;
        final TextView tvTime;
        final TextView tvBadge;
        final ImageButton btnStar;
        final ImageButton btnTrash;

        Holder(@NonNull View itemView) {
            super(itemView);
            ivThumb = itemView.findViewById(R.id.iv_thumb);
            tvId = itemView.findViewById(R.id.tv_id);
            tvName = itemView.findViewById(R.id.tv_name);
            tvTime = itemView.findViewById(R.id.tv_time);
            tvBadge = itemView.findViewById(R.id.tv_badge);
            btnStar = itemView.findViewById(R.id.btn_star);
            btnTrash = itemView.findViewById(R.id.btn_trash);
        }
    }
}
