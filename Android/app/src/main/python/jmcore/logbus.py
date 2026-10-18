# -*- coding: utf-8 -*-
"""
jmcore.logbus —— 运行日志总线

Flask 版是把 stdout / jmcomic 的 logging 一起重定向到网页的状态区。
Android 上没有「前端 socket」，所以这里做两件事：

* 一个固定长度的环形缓冲（供界面轮询）；
* 一个 logging.Handler，把 jmcomic 的日志搬进缓冲。
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

DEFAULT_LIMIT = 200


class LogBus:

    def __init__(self, limit: int = DEFAULT_LIMIT):
        self._limit = limit
        self._lines = deque(maxlen=limit)
        self._lock = threading.RLock()
        self._seq = 0

    def push(self, line: str, with_time: bool = True) -> None:
        line = (line or '').rstrip()
        if not line:
            return
        if with_time:
            line = '[%s] %s' % (time.strftime('%H:%M:%S'), line)
        with self._lock:
            self._lines.append(line)
            self._seq += 1

    def tail(self, n: int = 60) -> list:
        with self._lock:
            if n is None or n <= 0:
                return list(self._lines)
            return list(self._lines)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    def seq(self) -> int:
        with self._lock:
            return self._seq


class _BusHandler(logging.Handler):

    def __init__(self, bus: LogBus):
        super().__init__()
        self.bus = bus

    def emit(self, record):
        try:
            self.bus.push(self.format(record), with_time=False)
        except Exception:
            pass


_INSTALLED = False


def install(bus: LogBus) -> LogBus:
    """把 bus 接到 jmcomic 的 logger 上（只装一次，避免重复刷屏）。"""
    global _INSTALLED
    if _INSTALLED:
        return bus

    logger = logging.getLogger('jmcomic')
    logger.setLevel(logging.INFO)
    handler = _BusHandler(bus)
    handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(handler)
    _INSTALLED = True
    return bus
