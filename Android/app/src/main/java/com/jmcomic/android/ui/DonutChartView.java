package com.jmcomic.android.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.util.AttributeSet;
import android.view.View;

import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;

import com.jmcomic.android.R;

import java.util.Locale;

/**
 * 环形磁盘占用图。
 *
 * <p>四段：下载目录（橙）/ 收藏目录（橙亮）/ 同盘其它（紫）/ 可用（灰）。
 * 中心只显示「下载目录 + 收藏目录」占整块磁盘总容量的百分比 ——
 * 具体的已用 / 总量文字放在左侧图例下方。
 */
public class DonutChartView extends View {

    private final Paint arcPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint captionPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF oval = new RectF();

    private long pdfBytes;
    private long favBytes;
    private long otherBytes;
    private long freeBytes;

    private int colorPdf;
    private int colorFav;
    private int colorOther;
    private int colorFree;

    public DonutChartView(Context context) {
        this(context, null);
    }

    public DonutChartView(Context context, @Nullable AttributeSet attrs) {
        this(context, attrs, 0);
    }

    public DonutChartView(Context context, @Nullable AttributeSet attrs, int defStyleAttr) {
        super(context, attrs, defStyleAttr);

        colorPdf = ContextCompat.getColor(context, R.color.seg_dir);
        colorFav = ContextCompat.getColor(context, R.color.seg_fav);
        colorOther = ContextCompat.getColor(context, R.color.seg_other);
        colorFree = ContextCompat.getColor(context, R.color.seg_free);

        arcPaint.setStyle(Paint.Style.STROKE);

        textPaint.setColor(ContextCompat.getColor(context, R.color.text_primary));
        textPaint.setTextAlign(Paint.Align.CENTER);

        captionPaint.setColor(ContextCompat.getColor(context, R.color.text_secondary));
        captionPaint.setTextAlign(Paint.Align.CENTER);
    }

    public void setData(long pdfBytes, long favBytes, long otherBytes, long freeBytes) {
        this.pdfBytes = Math.max(0, pdfBytes);
        this.favBytes = Math.max(0, favBytes);
        this.otherBytes = Math.max(0, otherBytes);
        this.freeBytes = Math.max(0, freeBytes);
        invalidate();
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        int size = (int) dp(150);
        int width = resolveSize(size, widthMeasureSpec);
        int height = resolveSize(size, heightMeasureSpec);
        int side = Math.max(Math.min(width, height), size);
        setMeasuredDimension(side, side);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);

        float size = Math.min(getWidth(), getHeight());
        float stroke = size * 0.15f;
        arcPaint.setStrokeWidth(stroke);

        float inset = stroke / 2f + dp(2);
        oval.set(inset, inset, size - inset, size - inset);

        long total = pdfBytes + favBytes + otherBytes + freeBytes;
        if (total <= 0) {
            total = 1;
        }

        // 底圈：可用空间
        arcPaint.setColor(colorFree);
        canvas.drawArc(oval, 0, 360, false, arcPaint);

        float start = -90f;
        float pdfSweep = pdfBytes * 360f / total;
        float favSweep = favBytes * 360f / total;
        float otherSweep = otherBytes * 360f / total;

        if (pdfSweep > 0.2f) {
            arcPaint.setColor(colorPdf);
            canvas.drawArc(oval, start, pdfSweep, false, arcPaint);
            start += pdfSweep;
        }
        if (favSweep > 0.2f) {
            arcPaint.setColor(colorFav);
            canvas.drawArc(oval, start, favSweep, false, arcPaint);
            start += favSweep;
        }
        if (otherSweep > 0.2f) {
            arcPaint.setColor(colorOther);
            canvas.drawArc(oval, start, otherSweep, false, arcPaint);
        }

        // 中心：只放「本应用占用 / 磁盘总量」的百分比
        float percent = (pdfBytes + favBytes) * 100f / total;
        String percentText = percent < 1 ? String.format(Locale.US, "%.1f%%", percent)
                : String.format(Locale.US, "%.0f%%", percent);

        textPaint.setTextSize(size * 0.20f);
        textPaint.setFakeBoldText(true);
        canvas.drawText(percentText, size / 2f, size / 2f + size * 0.03f, textPaint);
        textPaint.setFakeBoldText(false);

        captionPaint.setTextSize(size * 0.078f);
        canvas.drawText("占本机存储", size / 2f, size / 2f + size * 0.185f, captionPaint);
    }

    private float dp(float value) {
        return value * getResources().getDisplayMetrics().density;
    }

    /** 人类可读容量 */
    public static String fmt(long bytes) {
        if (bytes <= 0) {
            return "0 B";
        }
        String[] units = {"B", "KB", "MB", "GB", "TB", "PB"};
        double value = bytes;
        int index = 0;
        while (value >= 1024 && index < units.length - 1) {
            value /= 1024;
            index++;
        }
        return index == 0
                ? String.format(Locale.US, "%.0f %s", value, units[index])
                : String.format(Locale.US, "%.1f %s", value, units[index]);
    }
}
