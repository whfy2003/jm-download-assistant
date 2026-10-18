package com.jmcomic.android.core;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/** Python 返回 JSON 的强类型映射（字段与 jmcore.api 保持一致）。 */
public final class Models {

    private Models() {
    }

    /**
     * 读字符串字段。
     *
     * <p>Android 自带的 org.json 在遇到 JSON {@code null} 时会返回字符串 "null"
     * （{@code JSONObject.NULL.toString()}），界面上就会莫名显示一个 "null"。
     * 这里统一把它折成空串。
     */
    private static String str(JSONObject o, String key, String fallback) {
        String value = o.optString(key, fallback);
        if (value == null) {
            return fallback;
        }
        value = value.trim();
        return value.isEmpty() || "null".equals(value) ? fallback : value;
    }

    public static final class Record {
        public String id = "";
        public String name = "";
        public String file = "";
        public String time = "";
        /** 该记录文件真正所在的目录（收藏记录在下载目录，旧版副本在收藏目录） */
        public String dir = "";
        public boolean exists;
        public boolean fav;
        public boolean inDownload;

        public static Record from(JSONObject o) {
            Record r = new Record();
            r.id = str(o, "id", "");
            r.name = str(o, "name", "");
            r.file = str(o, "file", "");
            r.time = str(o, "time", "");
            r.dir = str(o, "dir", "");
            r.exists = o.optBoolean("exists", false);
            r.fav = o.optBoolean("fav", false);
            r.inDownload = o.optBoolean("in_download", false);
            return r;
        }

        public static List<Record> list(JSONObject root) {
            List<Record> list = new ArrayList<>();
            JSONArray array = root.optJSONArray("records");
            if (array == null) {
                return list;
            }
            for (int i = 0; i < array.length(); i++) {
                JSONObject item = array.optJSONObject(i);
                if (item != null) {
                    list.add(from(item));
                }
            }
            return list;
        }
    }

    public static final class TaskState {
        public static final int UNKNOWN = -1;
        public static final int FAILED = 0;
        public static final int SUCCESS = 1;

        public boolean running;
        public String albumId = "";
        public String title = "";
        public String message = "";
        public int ok = UNKNOWN;
        public String startedAt = "";
        public String finishedAt = "";
        public List<String> logs = new ArrayList<>();

        // 下载进度（jmcore.progress）
        public int progressDone;
        public int progressTotal;
        public int progressPercent;
        public long progressBytes;
        public double progressSpeed;
        public double progressElapsed;

        public static TaskState from(JSONObject o) {
            TaskState s = new TaskState();
            s.running = o.optBoolean("running", false);
            s.albumId = str(o, "album_id", "");
            s.title = str(o, "title", "");
            s.message = str(o, "message", "");
            s.startedAt = str(o, "started_at", "");
            s.finishedAt = str(o, "finished_at", "");
            if (!o.isNull("ok")) {
                s.ok = o.optBoolean("ok", false) ? SUCCESS : FAILED;
            }
            JSONArray array = o.optJSONArray("logs");
            if (array != null) {
                for (int i = 0; i < array.length(); i++) {
                    s.logs.add(array.optString(i, ""));
                }
            }
            JSONObject progress = o.optJSONObject("progress");
            if (progress != null) {
                s.progressDone = progress.optInt("done", 0);
                s.progressTotal = progress.optInt("total", 0);
                s.progressPercent = progress.optInt("percent", 0);
                s.progressBytes = progress.optLong("bytes", 0);
                s.progressSpeed = progress.optDouble("speed", 0);
                s.progressElapsed = progress.optDouble("elapsed", 0);
            }
            return s;
        }
    }

    public static final class DiskInfo {
        public String path = "";
        public String drive = "";
        public long dirSize;
        public long total;
        public long used;
        public long free;
        public long otherUsed;

        public static DiskInfo from(JSONObject o) {
            DiskInfo d = new DiskInfo();
            if (o == null) {
                return d;
            }
            d.path = str(o, "path", "");
            d.drive = str(o, "drive", "");
            d.dirSize = o.optLong("dir_size", 0);
            d.total = o.optLong("total", 0);
            d.used = o.optLong("used", 0);
            d.free = o.optLong("free", 0);
            d.otherUsed = o.optLong("other_used", 0);
            return d;
        }
    }

    public static final class SettingsInfo {
        public String pdfDir = "";
        public String favDir = "";
        public String workDir = "";
        public String proxy = "";
        public String proxyUser = "";
        public String proxyOnly = "";
        public String proxyType = "auto";
        public boolean hasProxyPassword;
        public int imageThreads = 16;
        public int photoThreads = 4;
        public boolean hasCookies;

        public static SettingsInfo from(JSONObject dirs) {
            SettingsInfo s = new SettingsInfo();
            if (dirs == null) {
                return s;
            }
            s.pdfDir = str(dirs, "pdf_dir", "");
            s.favDir = str(dirs, "fav_dir", "");
            s.workDir = str(dirs, "work_dir", "");
            s.proxy = str(dirs, "proxy", "");
            s.proxyUser = str(dirs, "proxy_user", "");
            s.proxyOnly = str(dirs, "proxy_only", "");
            s.proxyType = str(dirs, "proxy_type", "auto");
            s.hasProxyPassword = dirs.optBoolean("has_proxy_password", false);
            s.imageThreads = dirs.optInt("image_threads", 16);
            s.photoThreads = dirs.optInt("photo_threads", 4);
            s.hasCookies = dirs.optBoolean("has_cookies", false);
            return s;
        }
    }
}
