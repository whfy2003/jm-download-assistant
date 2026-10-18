package com.jmcomic.android.core;

import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.widget.Toast;

import androidx.core.content.FileProvider;

import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;

/**
 * 文件相关操作。
 *
 * os.startfile() 在 Android 上不存在，对应的做法是：
 *  - FileProvider 生成 content:// URI，交给系统 PDF 阅读器（ACTION_VIEW）；
 *  - 想「保存到自己能看见的地方」时导出到系统下载目录（MediaStore）。
 */
public final class FileOps {

    private FileOps() {
    }

    public static void openPdf(Context context, File file) {
        if (file == null || !file.isFile()) {
            Toast.makeText(context, "文件不存在：" + (file == null ? "" : file.getName()),
                    Toast.LENGTH_LONG).show();
            return;
        }
        try {
            Uri uri = FileProvider.getUriForFile(context,
                    context.getPackageName() + ".fileprovider", file);
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, "application/pdf");
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(intent);
        } catch (ActivityNotFoundException e) {
            Toast.makeText(context, "没有找到能打开 PDF 的应用", Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(context, "打开失败：" + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    /** 导出到系统“下载/JM”目录（Android 10+，无需存储权限）。 */
    public static boolean exportToDownloads(Context context, File file) {
        if (file == null || !file.isFile()) {
            return false;
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            Toast.makeText(context, "导出功能需要 Android 10 及以上", Toast.LENGTH_LONG).show();
            return false;
        }
        ContentValues values = new ContentValues();
        values.put(MediaStore.Downloads.DISPLAY_NAME, file.getName());
        values.put(MediaStore.Downloads.MIME_TYPE, "application/pdf");
        values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/JM");
        values.put(MediaStore.Downloads.IS_PENDING, 1);

        Uri uri = context.getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
        if (uri == null) {
            return false;
        }
        try (FileInputStream in = new FileInputStream(file);
             OutputStream out = context.getContentResolver().openOutputStream(uri)) {
            if (out == null) {
                return false;
            }
            byte[] buffer = new byte[64 * 1024];
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            out.flush();

            ContentValues done = new ContentValues();
            done.put(MediaStore.Downloads.IS_PENDING, 0);
            context.getContentResolver().update(uri, done, null, null);
            Toast.makeText(context, "已导出到 下载/JM/" + file.getName(), Toast.LENGTH_LONG).show();
            return true;
        } catch (Exception e) {
            Toast.makeText(context, "导出失败：" + e.getMessage(), Toast.LENGTH_LONG).show();
            return false;
        }
    }

    public static long dirSize(File dir) {
        if (dir == null || !dir.exists()) {
            return 0;
        }
        if (dir.isFile()) {
            return dir.length();
        }
        long total = 0;
        File[] children = dir.listFiles();
        if (children != null) {
            for (File child : children) {
                total += dirSize(child);
            }
        }
        return total;
    }

    public static void deleteRecursively(File file) {
        if (file == null || !file.exists()) {
            return;
        }
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) {
                deleteRecursively(child);
            }
        }
        //noinspection ResultOfMethodCallIgnored
        file.delete();
    }
}
