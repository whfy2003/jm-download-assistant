package com.jmcomic.android.ui;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;

import androidx.annotation.NonNull;
import androidx.activity.OnBackPressedCallback;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.Fragment;
import androidx.fragment.app.FragmentManager;
import androidx.fragment.app.FragmentTransaction;

import com.google.android.material.bottomnavigation.BottomNavigationView;
import com.jmcomic.android.R;

/**
 * 单 Activity + 四个 Fragment：下载 / 本机 / 收藏 / 设置。
 *
 * <p>下载页是主页，只有输入框、两个按钮、进度与日志；
 * 下载完成后的记录统一放在「本机」页。
 *
 * <p>注意：深色模式切换会让 Activity recreate，此时 FragmentManager 会恢复之前
 * add 过的 Fragment。如果不把它们的引用取回来，show() 又会 add 一个新实例，
 * 结果就是「设置页和下载页叠在一起」。所以这里必须在 onCreate 里按 tag 恢复。
 */
public class MainActivity extends AppCompatActivity {

    private static final String[] TAGS = {"download", "local", "favorites", "settings"};
    private static final int[] ITEMS = {
            R.id.nav_download, R.id.nav_local, R.id.nav_favorites, R.id.nav_settings};

    private static final String KEY_CURRENT = "current_tab";
    private static final int REQ_NOTIFICATION = 100;

    private final Fragment[] fragments = new Fragment[TAGS.length];
    private int current = 0;
    private boolean restoring = false;


    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        BottomNavigationView nav = findViewById(R.id.bottom_nav);
        nav.setOnItemSelectedListener(item -> {
            if (restoring) {
                return true;
            }
            int index = indexOfItem(item.getItemId());
            if (index >= 0) {
                show(index);
            }
            return true;
        });

        FragmentManager manager = getSupportFragmentManager();
        if (savedInstanceState != null) {
            // recreate 后：把已恢复的 Fragment 引用接回来，避免重复 add 造成叠加
            for (int i = 0; i < TAGS.length; i++) {
                fragments[i] = manager.findFragmentByTag(TAGS[i]);
            }
            current = savedInstanceState.getInt(KEY_CURRENT, 0);
            if (current < 0 || current >= TAGS.length) {
                current = 0;
            }
            restoring = true;
            nav.setSelectedItemId(ITEMS[current]);
            restoring = false;
        }

        show(current);
        requestNotificationPermission();

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (current != 0) {
                    BottomNavigationView nav = findViewById(R.id.bottom_nav);
                    nav.setSelectedItemId(R.id.nav_download);
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });
    }

    @Override
    protected void onSaveInstanceState(@NonNull Bundle outState) {
        super.onSaveInstanceState(outState);
        outState.putInt(KEY_CURRENT, current);
    }

    private int indexOfItem(int itemId) {
        for (int i = 0; i < ITEMS.length; i++) {
            if (ITEMS[i] == itemId) {
                return i;
            }
        }
        return -1;
    }

    private void show(int index) {
        if (index < 0 || index >= TAGS.length) {
            return;
        }
        FragmentManager manager = getSupportFragmentManager();
        FragmentTransaction tx = manager.beginTransaction().setReorderingAllowed(true);

        for (int i = 0; i < TAGS.length; i++) {
            Fragment fragment = fragments[i];
            if (i == index) {
                if (fragment == null) {
                    fragment = create(i);
                    fragments[i] = fragment;
                    tx.add(R.id.fragment_container, fragment, TAGS[i]);
                } else if (!fragment.isAdded()) {
                    tx.add(R.id.fragment_container, fragment, TAGS[i]);
                } else if (fragment.isHidden()) {
                    tx.show(fragment);
                }
            } else if (fragment != null && fragment.isAdded() && !fragment.isHidden()) {
                tx.hide(fragment);
            }
        }

        // recreate 期间也可能走到这里，用 AllowingStateLoss 更稳
        tx.commitAllowingStateLoss();
        current = index;
    }

    private Fragment create(int index) {
        switch (index) {
            case 1:
                return new LocalFragment();
            case 2:
                return new FavoritesFragment();
            case 3:
                return new SettingsFragment();
            default:
                return new DownloadFragment();
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions,
                                           @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
    }

    /** Android 13+ 发通知需要运行时权限，否则前台服务的进度条看不到。 */
    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) {
            return;
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
            return;
        }
        ActivityCompat.requestPermissions(this,
                new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATION);
    }
}
