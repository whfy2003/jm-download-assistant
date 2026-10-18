package com.jmcomic.android.service;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

import com.jmcomic.android.R;
import com.jmcomic.android.core.Models;
import com.jmcomic.android.core.Py;
import com.jmcomic.android.ui.MainActivity;

import org.json.JSONObject;

/**
 * 前台下载服务。
 *
 * 一次下载可能要几分钟到十几分钟，必须放在前台服务里，否则切到后台会被系统杀掉。
 * 真正的下载由 Python 线程执行（jmcore.task.start），这个服务负责：
 *  1. 拉起前台通知；
 *  2. 每秒轮询 jmcore.api.state()，把进度/日志刷到通知上；
 *  3. 结束后自动 stopSelf。
 */
public class DownloadService extends Service {

    public static final String EXTRA_ALBUM_ID = "album_id";
    private static final String CHANNEL_ID = "jm_download";
    private static final int NOTIFICATION_ID = 1001;

    private Thread worker;

    public static void start(Context context, String albumId) {
        Intent intent = new Intent(context, DownloadService.class);
        intent.putExtra(EXTRA_ALBUM_ID, albumId);
        ContextCompat.startForegroundService(context, intent);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String albumId = intent == null ? "" : intent.getStringExtra(EXTRA_ALBUM_ID);
        if (albumId == null) {
            albumId = "";
        }
        final String id = albumId;

        startForeground(NOTIFICATION_ID,
                buildNotification("准备下载 " + id, "正在启动 Python 核心…", true, -1));

        if (worker != null && worker.isAlive()) {
            return START_NOT_STICKY;
        }

        worker = new Thread(() -> runDownload(id), "jm-download");
        worker.start();
        return START_NOT_STICKY;
    }

    private void runDownload(String albumId) {
        try {
            JSONObject start = Py.callSync("start_download", albumId);
            if (!start.optBoolean("ok", false)) {
                notifyFinal("下载未开始", start.optString("error", "未知错误"));
                stopSelf();
                return;
            }

            while (true) {
                JSONObject raw = Py.callSync("state", 12);
                Models.TaskState state = Models.TaskState.from(raw);

                String title = state.running
                        ? "正在下载 " + albumId
                        : (state.ok == Models.TaskState.SUCCESS ? "下载完成" : "下载结束");
                String text = state.running
                        ? progressText(state)
                        : (state.title.isEmpty() ? state.message : state.title);

                updateNotification(title, text, state.running,
                        state.progressTotal > 0 ? state.progressPercent : -1);

                if (!state.running) {
                    notifyFinal(state.ok == Models.TaskState.SUCCESS ? "下载完成" : "下载失败",
                            state.title.isEmpty() ? state.message : state.title);
                    break;
                }
                Thread.sleep(1000L);
            }
        } catch (Throwable t) {
            notifyFinal("下载异常", String.valueOf(t.getMessage()));
        } finally {
            stopSelf();
        }
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
        return lastLog(state);
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
        return String.format(java.util.Locale.US,
                index == 0 ? "%.0f %s" : "%.1f %s", value, units[index]);
    }

    private String lastLog(Models.TaskState state) {
        if (state.logs.isEmpty()) {
            return state.message.isEmpty() ? "请求中…" : state.message;
        }
        String last = state.logs.get(state.logs.size() - 1);
        return last.length() > 80 ? last.substring(0, 80) + "…" : last;
    }

    private void updateNotification(String title, String text, boolean ongoing, int percent) {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager != null) {
            manager.notify(NOTIFICATION_ID, buildNotification(title, text, ongoing, percent));
        }
    }

    private void notifyFinal(String title, String text) {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager == null) {
            return;
        }
        Notification notification = buildNotification(title, text, false, -1);
        manager.notify(NOTIFICATION_ID, notification);
        stopForeground(false);
    }

    private Notification buildNotification(String title, String text, boolean ongoing, int percent) {
        PendingIntent contentIntent = PendingIntent.getActivity(
                this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_nav_download)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
                .setOngoing(ongoing)
                .setOnlyAlertOnce(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setContentIntent(contentIntent);

        // percent < 0：不显示进度条（结束时也不留一个“一直转”的不确定进度）
        if (percent >= 0) {
            builder.setProgress(100, Math.min(100, Math.max(0, percent)), false);
        }
        return builder.build();
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return;
        }
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (manager == null) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "下载任务", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("JM 下载助手的下载进度");
        channel.setShowBadge(false);
        manager.createNotificationChannel(channel);
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
