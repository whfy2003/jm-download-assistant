# -*- coding: utf-8 -*-
"""
jmcore —— JM 下载助手的 Python 核心（Android 版）

与 Flask 版的对应关系：

    webui/app.py            →  jmcore/api.py + paths.py + store.py + task.py
    webui/templates+static  →  Android 原生界面（Java）
    option.yml              →  jmcore/task.build_option_yaml()
    curl_cffi               →  jmcore/net.py（Android 原生 HTTP）

上游 jmcomic 与 commonx 以源码形式随包分发，逻辑不改，只打了两处 Android 补丁。
"""

__version__ = '1.0.0-android'

from . import api  # noqa: F401
