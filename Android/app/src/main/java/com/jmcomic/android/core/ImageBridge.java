package com.jmcomic.android.core;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import java.io.ByteArrayOutputStream;

/**
 * 给 Python 用的图片解码兜底。
 *
 * Chaquopy 的 Pillow 轮子没有 `PIL/_webp.so`，JM 的图片又是 webp，
 * 所以 Python 侧 `Image.open()` 会失败。Android 的 BitmapFactory 自带 WebP 解码，
 * 这里把它转成 PNG 交给 Pillow（PNG 解码器是有的）。
 *
 * 只在 Python 侧调用，运行在后台线程，不需要主线程保护。
 */
public final class ImageBridge {

    private ImageBridge() {
    }

    /** 任意常见格式（webp/jpeg/png/gif）→ PNG 字节；失败返回 null。 */
    public static byte[] decodeToPng(byte[] data) {
        if (data == null || data.length == 0) {
            return null;
        }
        Bitmap bitmap = null;
        try {
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inPreferredConfig = Bitmap.Config.ARGB_8888;
            bitmap = BitmapFactory.decodeByteArray(data, 0, data.length, options);
            if (bitmap == null) {
                return null;
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream(
                    Math.max(1024, data.length / 2));
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)) {
                return null;
            }
            return out.toByteArray();
        } catch (Throwable t) {
            return null;
        } finally {
            if (bitmap != null && !bitmap.isRecycled()) {
                bitmap.recycle();
            }
        }
    }
}
