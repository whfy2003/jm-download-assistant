package com.jmcomic.android.core;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.graphics.pdf.PdfRenderer;

import java.io.File;
import java.io.FileOutputStream;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * 用系统 PDF 渲染器给本地 PDF 生成首屏缩略图。
 *
 * 为什么不用网络封面：
 *  - 历史记录、收藏、甚至别人拷进来的 PDF 都能显示；
 *  - 不依赖域名可用性，也不额外消耗对方流量；
 *  - 结果按「路径 + 修改时间 + 宽度」缓存在 cacheDir，文件改动会自动失效。
 *
 * 渲染只在后台线程做，内存里再放一层 LruCache，列表滚动时不会反复解码。
 */
public final class PdfThumbnails {

    private static final ExecutorService POOL = Executors.newFixedThreadPool(2);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private static final android.util.LruCache<String, Bitmap> MEMORY =
            new android.util.LruCache<String, Bitmap>(12 * 1024 * 1024) {
                @Override
                protected int sizeOf(String key, Bitmap value) {
                    return value.getByteCount();
                }
            };

    public interface Callback {
        void onResult(Bitmap bitmap);
    }

    private PdfThumbnails() {
    }

    public static void load(Context context, File pdf, int widthPx, int heightPx, Callback callback) {
        if (pdf == null || !pdf.isFile()) {
            callback.onResult(null);
            return;
        }

        final String key = pdf.getAbsolutePath() + '|' + pdf.lastModified() + '|' + widthPx;
        Bitmap cached = MEMORY.get(key);
        if (cached != null) {
            MAIN.post(() -> callback.onResult(cached));
            return;
        }

        final Context app = context.getApplicationContext();
        POOL.execute(() -> {
            Bitmap bitmap = null;
            try {
                bitmap = loadFromDisk(app, pdf, key, widthPx, heightPx);
            } catch (Throwable ignored) {
                // 损坏 / 加密 / 非 PDF：交给界面显示占位
            }
            if (bitmap != null) {
                MEMORY.put(key, bitmap);
            }
            final Bitmap result = bitmap;
            MAIN.post(() -> callback.onResult(result));
        });
    }

    private static Bitmap loadFromDisk(Context context, File pdf, String key,
                                       int widthPx, int heightPx) throws Exception {
        File cacheFile = new File(new File(context.getCacheDir(), "pdf_thumbs"), sha1(key) + ".png");
        if (cacheFile.isFile()) {
            Bitmap bitmap = BitmapFactory.decodeFile(cacheFile.getAbsolutePath());
            if (bitmap != null) {
                return bitmap;
            }
        }

        Bitmap bitmap = renderFirstPage(pdf, widthPx, heightPx);
        if (bitmap == null) {
            return null;
        }

        File parent = cacheFile.getParentFile();
        if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
            return bitmap;
        }
        try (FileOutputStream out = new FileOutputStream(cacheFile)) {
            bitmap.compress(Bitmap.CompressFormat.PNG, 100, out);
        } catch (Exception ignored) {
        }
        return bitmap;
    }

    private static Bitmap renderFirstPage(File pdf, int widthPx, int heightPx) throws Exception {
        ParcelFileDescriptor descriptor =
                ParcelFileDescriptor.open(pdf, ParcelFileDescriptor.MODE_READ_ONLY);
        PdfRenderer renderer = new PdfRenderer(descriptor);
        try {
            if (renderer.getPageCount() <= 0) {
                return null;
            }
            PdfRenderer.Page page = renderer.openPage(0);
            try {
                int pageWidth = Math.max(1, page.getWidth());
                int pageHeight = Math.max(1, page.getHeight());

                float scale = Math.min(widthPx / (float) pageWidth, heightPx / (float) pageHeight);
                scale = Math.min(scale, 4f);            // 避免超大页面吃内存
                int width = Math.max(1, Math.round(pageWidth * scale));
                int height = Math.max(1, Math.round(pageHeight * scale));

                Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
                bitmap.eraseColor(Color.WHITE);          // PDF 页面默认透明，先铺白
                page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                return bitmap;
            } finally {
                page.close();
            }
        } finally {
            renderer.close();
            descriptor.close();
        }
    }

    private static String sha1(String text) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-1");
            byte[] bytes = digest.digest(text.getBytes("UTF-8"));
            StringBuilder builder = new StringBuilder(bytes.length * 2);
            for (byte b : bytes) {
                builder.append(String.format("%02x", b));
            }
            return builder.toString();
        } catch (Exception e) {
            return String.valueOf(Math.abs(text.hashCode()));
        }
    }
}
