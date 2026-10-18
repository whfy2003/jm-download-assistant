package com.jmcomic.android;

import android.content.Context;
import android.content.SharedPreferences;

import androidx.appcompat.app.AppCompatDelegate;

import com.chaquo.python.android.PyApplication;

/**
 * 应用入口。
 *
 * 继承 Chaquopy 的 PyApplication，它会在 onCreate 里完成 Python.start()；
 * 我们随后在后台线程里 import jmcore.api 并做初始化（导入 jmcomic 需要一点时间，
 * 不能放在主线程，否则会 ANR）。
 */
public class JmApp extends PyApplication {

    private static Context appContext;

    @Override
    public void onCreate() {
        super.onCreate();
        appContext = getApplicationContext();

        SharedPreferences prefs = getSharedPreferences("jm_settings", MODE_PRIVATE);
        boolean dark = prefs.getBoolean("dark_mode", false);
        AppCompatDelegate.setDefaultNightMode(dark
                ? AppCompatDelegate.MODE_NIGHT_YES
                : AppCompatDelegate.MODE_NIGHT_NO);

        com.jmcomic.android.core.Py.start(this);
    }

    public static Context ctx() {
        return appContext;
    }
}
