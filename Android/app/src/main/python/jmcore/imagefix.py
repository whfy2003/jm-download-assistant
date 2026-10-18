# -*- coding: utf-8 -*-
"""
jmcore.imagefix —— Android 上的 WebP 兼容补丁

问题：Chaquopy 的 Pillow 轮子只带了 `WebPImagePlugin`，没有 `PIL/_webp.so`，
所以 `Image.open(webp_bytes)` 会抛 `cannot identify image file`；
而 JM 的图片大量是 `.webp`，上游后续又会按 `.webp` 后缀调 `image.save()`，
缺编码器同样会失败。

做法（不改上游源码，只在初始化时打两个补丁）：

1. `JmImageTool.open_image`
   先让 Pillow 自己试；失败时把原始字节交给 Android 的 `BitmapFactory`
   解码成 PNG 再交回 Pillow。BitmapFactory 从 API 14 起就支持 WebP。
2. `JmImageTool.save_image`
   目标后缀是 `.webp` 时改存为同名 `.jpg`（质量 95），
   因为 Pillow 没有 WebP 编码器。合并 PDF 时 img2pdf 按目录遍历文件，
   后缀变化不影响结果；工作区在合并后本来就会被清空。

补丁是幂等的，重复调用无副作用。
"""
from __future__ import annotations

from io import BytesIO

_INSTALLED = False
_INFO = {'open_patched': False, 'save_patched': False, 'android_decoder': False}


def _android_decode(data):
    """用 Android BitmapFactory 把图片解码成 PNG 字节；桌面环境返回 None。"""
    if not isinstance(data, (bytes, bytearray)):
        return None
    try:
        from java import jclass
        bridge = jclass('com.jmcomic.android.core.ImageBridge')
        png = bridge.decodeToPng(bytes(data))
        if png is None:
            return None
        _INFO['android_decoder'] = True
        return bytes(png)
    except Exception:
        return None


def install() -> bool:
    global _INSTALLED
    if _INSTALLED:
        return True

    try:
        from PIL import Image
        from jmcomic.jm_toolkit import JmImageTool
    except Exception:
        return False

    orig_open = JmImageTool.open_image      # 绑定过的 classmethod
    orig_save = JmImageTool.save_image

    def open_image(fp):
        try:
            return orig_open(fp)
        except Exception:
            png = _android_decode(fp)
            if not png:
                raise
            return Image.open(BytesIO(png))

    def save_image(image, filepath, **kwargs):
        if isinstance(filepath, str) and filepath.lower().endswith('.webp'):
            target = filepath[:-5] + '.jpg'
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            image.save(target, quality=95)
            return
        orig_save(image, filepath, **kwargs)

    JmImageTool.open_image = staticmethod(open_image)
    JmImageTool.save_image = staticmethod(save_image)

    _INFO['open_patched'] = True
    _INFO['save_patched'] = True
    _INSTALLED = True
    return True


def info() -> dict:
    return dict(_INFO, installed=_INSTALLED)
