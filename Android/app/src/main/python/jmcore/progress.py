# -*- coding: utf-8 -*-
"""
jmcore.progress —— 下载进度与网速

上游没有「可读的实时进度」接口：`download_album()` 是阻塞的，manifest 要等结束才有。
所以这里在传输层打点：

* 每成功取回一张图片，就把字节数累加（`net.request()` 里 is_image=True 的响应）；
* 总页数在开始下载前用 `client.get_album_detail().page_count` 拿到；
* 网速 = 累计字节 / 已用时间（从开始下载算起）。

计数是线程安全的（图片下载是多线程）。
"""
from __future__ import annotations

import threading
import time


class Progress:

    def __init__(self):
        self._lock = threading.RLock()
        self._total = 0
        self._done = 0
        self._bytes = 0
        self._started = 0.0
        self._active = False

    def reset(self):
        with self._lock:
            self._total = 0
            self._done = 0
            self._bytes = 0
            self._started = 0.0
            self._active = False

    def start(self, total: int = 0):
        with self._lock:
            self._total = max(0, int(total or 0))
            self._done = 0
            self._bytes = 0
            self._started = time.time()
            self._active = True

    def add_image(self, nbytes: int):
        with self._lock:
            if not self._active:
                return
            self._done += 1
            if nbytes and nbytes > 0:
                self._bytes += int(nbytes)

    def finish(self):
        with self._lock:
            self._active = False

    def snapshot(self) -> dict:
        with self._lock:
            elapsed = 0.0
            if self._started:
                elapsed = max(0.0, time.time() - self._started)
            speed = (self._bytes / elapsed) if elapsed > 0.05 else 0.0
            percent = 0
            if self._total > 0:
                percent = min(100, int(self._done * 100 / self._total))
            return {
                'active': self._active,
                'done': self._done,
                'total': self._total,
                'bytes': self._bytes,
                'speed': round(speed, 1),
                'percent': percent,
                'elapsed': round(elapsed, 1),
            }


_PROGRESS = Progress()


def instance() -> Progress:
    return _PROGRESS


# --------------------------------------------------------------------------- #
# 打点：挂到 JmImageResp.transfer_to 上
# --------------------------------------------------------------------------- #
_HOOKED = False


def install() -> bool:
    """给上游的图片保存入口挂一个计数器。

    为什么不在传输层按 `is_image=True` 统计：
    `AbstractJmClient.request_with_retry(request, url, ..., is_image=False, **kwargs)`
    把 is_image 当成了**形参**，转发给 postman 时它已经不在 kwargs 里了，
    所以传输层永远看不到这个标记（这是 v1.3 进度不动的根因）。

    真实的每张图片保存都会走 `JmImageResp.transfer_to()`，且只走一次，
    在这里统计最准确。
    """
    global _HOOKED
    if _HOOKED:
        return True
    try:
        from jmcomic.jm_client_interface import JmImageResp
    except Exception:
        return False

    original = JmImageResp.transfer_to

    def transfer_to(self, *args, **kwargs):
        try:
            instance().add_image(len(self.content or b''))
        except Exception:
            pass
        return original(self, *args, **kwargs)

    JmImageResp.transfer_to = transfer_to
    _HOOKED = True
    return True
