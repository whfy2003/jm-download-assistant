package com.jmcomic.android.core;

import android.content.Context;
import android.os.Handler;
import android.os.Looper;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONObject;

import java.io.File;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * Java → Python 的唯一入口。
 *
 * 约定：Python 侧所有函数都返回 JSON 字符串（见 jmcore/api.py），
 * 这样跨语言只传字符串，避免 Chaquopy 对象转换的坑，也便于日志排查。
 *
 * 线程模型：
 *  - 所有 Python 调用都丢到 POOL 里执行，绝不占用主线程（下载/统计目录都可能很慢）；
 *  - 回调统一 post 回主线程，界面代码可以直接改 View。
 */
public final class Py {

    private static final ExecutorService POOL = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final CountDownLatch READY = new CountDownLatch(1);

    private static volatile PyObject api;
    private static volatile String initError;
    private static volatile JSONObject initResult;

    public interface Callback {
        void onJson(JSONObject json);
    }

    private Py() {
    }

    /** 在 Application.onCreate 里调用一次。 */
    public static void start(Context context) {
        final Context app = context.getApplicationContext();
        POOL.execute(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new com.chaquo.python.android.AndroidPlatform(app));
                }
                PyObject module = Python.getInstance().getModule("jmcore.api");

                File root = app.getExternalFilesDir(null);
                if (root == null) {
                    root = app.getFilesDir();
                }
                File home = new File(root, "JM");
                File pdfDir = new File(home, "漫画");
                File favDir = new File(home, "收藏");
                File workDir = new File(home, "work");

                String raw = module.callAttr("init",
                        home.getAbsolutePath(),
                        pdfDir.getAbsolutePath(),
                        favDir.getAbsolutePath(),
                        workDir.getAbsolutePath()).toString();

                initResult = new JSONObject(raw);
                api = module;
            } catch (Throwable t) {
                initError = t.getClass().getSimpleName() + ": " + t.getMessage();
            } finally {
                READY.countDown();
            }
        });
    }

    public static boolean isReady() {
        return READY.getCount() == 0 && api != null;
    }

    public static String initError() {
        return initError;
    }

    public static JSONObject initResult() {
        return initResult;
    }

    /** 异步调用，回调在主线程。 */
    public static void call(String function, Callback callback, Object... args) {
        POOL.execute(() -> {
            JSONObject result;
            try {
                result = callSync(function, args);
            } catch (Throwable t) {
                result = error(t);
            }
            final JSONObject out = result;
            MAIN.post(() -> callback.onJson(out));
        });
    }

    /** 同步调用；只能在后台线程使用（Service / POOL 内部）。 */
    public static JSONObject callSync(String function, Object... args) throws Exception {
        if (!READY.await(60, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Python 初始化超时");
        }
        if (api == null) {
            throw new IllegalStateException("Python 初始化失败：" + initError);
        }
        String raw = api.callAttr(function, args).toString();
        return new JSONObject(raw);
    }

    public static JSONObject error(Throwable t) {
        JSONObject json = new JSONObject();
        try {
            json.put("ok", false);
            json.put("error", t.getClass().getSimpleName() + ": " + t.getMessage());
        } catch (Exception ignored) {
        }
        return json;
    }
}
