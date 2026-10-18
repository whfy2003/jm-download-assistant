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
import com.jmcomic.android.core.Models;

/**
 * 三段式占用条：橙色＝本目录、紫色＝同盘其它、灰色＝可用。
 * 对应网页版侧栏的那条指示条。
 */
public class DiskBarView extends View {

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final RectF rect = new RectF();
    private final float radius;

    private long dirSize;
    private long otherUsed;
    private long free;

    public DiskBarView(Context context) {
        this(context, null);
    }

    public DiskBarView(Context context, @Nullable AttributeSet attrs) {
        super(context, attrs);
        radius = getResources().getDisplayMetrics().density * 5f;
    }

    public void setInfo(Models.DiskInfo info) {
        if (info == null) {
            dirSize = otherUsed = free = 0;
        } else {
            dirSize = Math.max(0, info.dirSize);
            otherUsed = Math.max(0, info.otherUsed);
            free = Math.max(0, info.free);
        }
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);

        float width = getWidth();
        float height = getHeight();
        if (width <= 0 || height <= 0) {
            return;
        }
        rect.set(0, 0, width, height);

        // 底：可用空间
        paint.setColor(ContextCompat.getColor(getContext(), R.color.seg_free));
        canvas.drawRoundRect(rect, radius, radius, paint);

        long total = dirSize + otherUsed + free;
        if (total <= 0) {
            return;
        }

        // 用底条做圆角裁剪，保证两端是圆的
        canvas.save();
        canvas.clipRect(rect);
        float x = 0f;

        paint.setColor(ContextCompat.getColor(getContext(), R.color.seg_dir));
        float dirWidth = width * (dirSize / (float) total);
        if (dirWidth > 0) {
            canvas.drawRect(x, 0, x + dirWidth, height, paint);
            x += dirWidth;
        }

        paint.setColor(ContextCompat.getColor(getContext(), R.color.seg_other));
        float otherWidth = width * (otherUsed / (float) total);
        if (otherWidth > 0) {
            canvas.drawRect(x, 0, x + otherWidth, height, paint);
        }
        canvas.restore();

        // 重新描一次圆角边框，遮住裁剪造成的直角
        paint.setColor(ContextCompat.getColor(getContext(), R.color.seg_free));
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(getResources().getDisplayMetrics().density);
        canvas.drawRoundRect(rect, radius, radius, paint);
        paint.setStyle(Paint.Style.FILL);
    }
}
