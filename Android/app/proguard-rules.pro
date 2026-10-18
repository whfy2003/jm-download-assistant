# 默认不混淆。Chaquopy 的 Python 代码在 APK 里是数据，不参与 R8，
# 但 Java <-> Python 的桥接类名（HttpBridge / jmcore.api）必须保留，
# 所以即使开启混淆，也要保留下面两类。
-keep class com.jmcomic.android.core.HttpBridge { *; }
-keep class com.chaquo.python.** { *; }
