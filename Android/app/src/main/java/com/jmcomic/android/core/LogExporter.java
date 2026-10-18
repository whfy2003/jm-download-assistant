package com.jmcomic.android.core;

import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * 日志导出。
 *
 * Android 10+ 直接写进系统「下载/JM」，不需要存储权限；
 * 更老的系统（本项目 minSdk 24）只能写到应用自己的外部目录，并在 Toast 里给出路径。
 */
public final class LogExporter {

    private LogExporter() {
    }

    public static boolean export(Context context, String text, String fileName) {
        byte[] bytes = (text == null ? "" : text).getBytes(StandardCharsets.UTF_8);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentValues values = new ContentValues();
            values.put(MediaStore.Downloads.DISPLAY_NAME, fileName);
            values.put(MediaStore.Downloads.MIME_TYPE, "text/plain");
            values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/JM");
            values.put(MediaStore.Downloads.IS_PENDING, 1);

            Uri uri = context.getContentResolver()
                    .insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (uri == null) {
                Toast.makeText(context, "导出失败：无法创建文件", Toast.LENGTH_LONG).show();
                return false;
            }
            try (OutputStream out = context.getContentResolver().openOutputStream(uri)) {
                if (out == null) {
                    return false;
                }
                out.write(bytes);
                out.flush();

                ContentValues done = new ContentValues();
                done.put(MediaStore.Downloads.IS_PENDING, 0);
                context.getContentResolver().update(uri, done, null, null);
                Toast.makeText(context, "日志已导出到 下载/JM/" + fileName,
                        Toast.LENGTH_LONG).show();
                return true;
            } catch (Exception e) {
                Toast.makeText(context, "导出失败：" + e.getMessage(), Toast.LENGTH_LONG).show();
                return false;
            }
        }

        File dir = context.getExternalFilesDir("logs");
        if (dir == null) {
            Toast.makeText(context, "导出失败：没有可写目录", Toast.LENGTH_LONG).show();
            return false;
        }
        if (!dir.isDirectory() && !dir.mkdirs()) {
            Toast.makeText(context, "导出失败：无法创建目录", Toast.LENGTH_LONG).show();
            return false;
        }
        File file = new File(dir, fileName);
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(bytes);
            Toast.makeText(context, "日志已导出到 " + file.getAbsolutePath(),
                    Toast.LENGTH_LONG).show();
            return true;
        } catch (Exception e) {
            Toast.makeText(context, "导出失败：" + e.getMessage(), Toast.LENGTH_LONG).show();
            return false;
        }
    }
}
