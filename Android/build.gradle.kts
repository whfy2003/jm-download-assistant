// 顶层构建脚本
// AGP 9.4.x：与 Android Studio 2026.2.1 自带的 SDK（android-37 / build-tools 36）配套
// Chaquopy 17.1.0：支持 AGP 7.3 ~ 9.4，Python 3.10 ~ 3.15
plugins {
    id("com.android.application") version "9.4.1" apply false
    id("com.chaquo.python") version "17.1.0" apply false
}
