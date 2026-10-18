# -*- coding: utf-8 -*-
"""
jmcore.api —— 暴露给 Java 层的 JSON 接口

Java 侧统一这样调用（Chaquopy）：

    Python.getInstance().getModule("jmcore.api").callAttr("records", "all", "")

所有函数都返回 JSON 字符串，避免跨语言对象转换带来的坑。
"""
from __future__ import annotations

import functools
import json
import os
import platform
import sys
import traceback

import jmcore.paths as paths
import jmcore.store as store
from jmcore import net, task
from jmcore.logbus import install as install_logbus

VERSION = '1.0.0-android'

_init_info = {}


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _dumps(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _safe(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return _dumps(func(*args, **kwargs))
        except Exception as e:
            return _dumps({
                'ok': False,
                'error': '%s: %s' % (type(e).__name__, e),
                'traceback': traceback.format_exc()[-1200:],
            })

    return wrapper


# --------------------------------------------------------------------------- #
# 初始化
# --------------------------------------------------------------------------- #
@_safe
def init(home: str, pdf_dir: str = '', fav_dir: str = '', work_dir: str = '') -> dict:
    """启动时调用一次（幂等）。"""
    install_logbus(task.bus())
    # 运行日志只保留本次启动的内容：进程每次启动都会走到这里
    task.bus().clear()

    info = paths.init(home, pdf_dir or None, fav_dir or None, work_dir or None)

    transport = {}
    try:
        transport['registered'] = net.install()
        transport['backend'] = net.backend_name()
        transport['ok'] = True
    except Exception as e:
        transport['ok'] = False
        transport['error'] = '%s: %s' % (type(e).__name__, e)

    _init_info.update({'dirs': info, 'transport': transport})
    return {'ok': True, 'version': VERSION, 'dirs': info, 'transport': transport}


@_safe
def diagnose() -> dict:
    """首屏自检：Python 版本、依赖、目录、传输后端。"""
    modules = {}
    for name in ('jmcomic', 'common', 'Crypto', 'PIL', 'yaml', 'img2pdf', 'requests'):
        try:
            __import__(name)
            modules[name] = 'ok'
        except Exception as e:
            modules[name] = '%s: %s' % (type(e).__name__, e)

    from jmcore import imagefix as _imagefix
    from jmcore import progress as _progress

    return {
        'ok': True,
        'version': VERSION,
        'python': sys.version.split()[0],
        'implementation': platform.python_implementation(),
        'dirs': paths.snapshot() if paths.is_ready() else {},
        'init': _init_info,
        'modules': modules,
        'transport': net.backend_name(),
        'image': {
            'pillow_webp': _webp_supported(),
            'imagefix': _imagefix.info(),
        },
        'progress': {
            # 挂上了才能按图片计数（JmImageResp.transfer_to）
            'hooked': _progress.install(),
            'counter': _progress.instance().snapshot(),
        },
        'writable': {
            'pdf': paths.is_writable(paths.pdf_dir()) if paths.is_ready() else False,
            'fav': paths.is_writable(paths.fav_dir()) if paths.is_ready() else False,
        },
    }


def _webp_supported() -> str:
    """Pillow 自身能不能解 WebP（Android 上通常是 no，由 imagefix 兜底）。"""
    try:
        from PIL import features
        return 'yes' if features.check('webp') else 'no (imagefix 兜底)'
    except Exception as e:
        return 'unknown: %s' % e


# --------------------------------------------------------------------------- #
# 下载
# --------------------------------------------------------------------------- #
@_safe
def start_download(album_id) -> dict:
    return task.start(album_id)


@_safe
def preview_album(album_id) -> dict:
    """下载前预览：标题 / 作者 / 页数 / 章节 / 标签 / 封面。

    封面由上游的 get_album_cover_url() 拼出图片地址，再走同一个 client 下载，
    这样能复用域名重试与 cookie；返回 base64 交给 Java 解码显示。
    """
    import base64

    album_id = str(album_id or '').strip()
    if not album_id:
        return {'ok': False, 'error': '请输入本子编号'}
    if not album_id.isdigit():
        return {'ok': False, 'error': '编号必须是纯数字'}

    import jmcomic

    from jmcore import imagefix
    imagefix.install()

    option = task.build_option()
    client = option.build_jm_client()

    album = client.get_album_detail(album_id)

    cover_b64 = ''
    cover_url = ''
    cover_error = ''
    try:
        cover_url = jmcomic.JmcomicText.get_album_cover_url(album_id)
        resp = client.get_jm_image(cover_url)
        if resp.is_success:
            cover_b64 = base64.b64encode(resp.content).decode('ascii')
        else:
            cover_error = '封面请求失败：HTTP %s' % resp.http_code
    except Exception as e:
        cover_error = '%s: %s' % (type(e).__name__, e)

    authors = getattr(album, 'authors', None) or []
    tags = getattr(album, 'tags', None) or []

    return {
        'ok': True,
        'album': {
            'id': str(album.album_id),
            'title': album.name,
            'author': '、'.join(authors) if authors else getattr(album, 'author', ''),
            'page_count': int(getattr(album, 'page_count', 0) or 0),
            'episodes': len(album.episode_list or []),
            'tags': [str(t) for t in tags][:12],
            'description': (getattr(album, 'description', '') or '').strip()[:600],
            'pub_date': getattr(album, 'pub_date', ''),
            'likes': getattr(album, 'likes', ''),
            'views': getattr(album, 'views', ''),
            'cover_url': cover_url,
            'cover_base64': cover_b64,
            'cover_error': cover_error,
        },
    }


@_safe
def state(log_limit: int = 60) -> dict:
    payload = task.snapshot(include_logs=True, log_limit=int(log_limit or 60))
    # 注意：payload 里的 'ok' 是「任务结果」（None/True/False），
    # 不能被接口成功标志覆盖，否则界面永远显示"已完成"。
    payload['api_ok'] = True
    return payload


@_safe
def log_tail(n: int = 60) -> dict:
    return {'ok': True, 'logs': task.bus().tail(int(n or 60))}


# --------------------------------------------------------------------------- #
# 记录
# --------------------------------------------------------------------------- #
@_safe
def records(scope: str = 'all', q: str = '') -> dict:
    scope = 'recent' if scope == 'recent' else 'all'
    items = store.download_records(scope, q or '')
    return {'ok': True, 'records': items, 'total': len(items), 'scope': scope, 'q': q or ''}


@_safe
def favorites(scope: str = 'all', q: str = '') -> dict:
    scope = 'recent' if scope == 'recent' else 'all'
    _added, warning = store.sync_fav_directory()
    items = store.fav_records(scope, q or '')
    writable = paths.is_writable(paths.fav_dir())
    if not writable:
        warning = warning or '收藏目录没有写入权限：可以查看，但收藏/删除会失败'
    return {'ok': True, 'records': items, 'total': len(items), 'scope': scope,
            'q': q or '', 'fav_dir': paths.fav_dir(),
            'writable': writable, 'warning': warning}


@_safe
def favorite(file, album_id='') -> dict:
    result = store.add_favorite(file, album_id or '-')
    result.setdefault('ok', True)
    return result



@_safe
def wipe_all() -> dict:
    """清除所有下载数据：下载目录与收藏目录里的全部文件（PDF + 日志）、图片工作区。"""
    import shutil

    detail = {'pdf_files': 0, 'fav_files': 0, 'logs': 0, 'errors': []}

    for key, directory in (('pdf', paths.pdf_dir()), ('fav', paths.fav_dir())):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                lower = name.lower()
                if lower.endswith('.pdf'):
                    detail[key + '_files'] += 1
                elif lower.endswith('.txt'):
                    detail['logs'] += 1
            except Exception as e:
                detail['errors'].append('%s：%s' % (name, e))

    work = paths.work_dir()
    if work and os.path.isdir(work):
        for name in os.listdir(work):
            try:
                path = os.path.join(work, name)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception:
                pass

    task.bus().clear()
    return {'ok': True, **detail}
@_safe
def delete(file, album_id='', scope='dl') -> dict:
    return store.delete_file(scope or 'dl', file, album_id or '')


# --------------------------------------------------------------------------- #
# 设置 / 磁盘
# --------------------------------------------------------------------------- #
@_safe
def settings() -> dict:
    return {'ok': True, 'dirs': paths.snapshot(), 'disk': paths.disk_snapshot()}


@_safe
def update_settings(pdf_dir='', fav_dir='') -> dict:
    result = paths.set_dirs(pdf_dir or '', fav_dir or '')
    result['disk'] = paths.disk_snapshot()
    return result


@_safe
def update_runtime(image_threads=None, photo_threads=None, cookies=None, proxy=None,
                   proxy_user=None, proxy_pass=None, proxy_only=None,
                   proxy_type=None) -> dict:
    kwargs = {}
    if image_threads not in (None, ''):
        kwargs['image_threads'] = image_threads
    if photo_threads not in (None, ''):
        kwargs['photo_threads'] = photo_threads
    if cookies is not None and cookies != '':
        kwargs['cookies'] = cookies
    if proxy is not None:
        kwargs['proxy'] = proxy
    if proxy_user is not None:
        kwargs['proxy_user'] = proxy_user
    if proxy_pass is not None and proxy_pass != '':
        kwargs['proxy_pass'] = proxy_pass
    if proxy_only is not None:
        kwargs['proxy_only'] = proxy_only
    if proxy_type in ('auto', 'http', 'socks'):
        kwargs['proxy_type'] = proxy_type
    return {'ok': True, 'dirs': paths.set_runtime(**kwargs)}


@_safe
def test_proxy() -> dict:
    """设置页的「测试代理」。

    两种协议 × 两个目标，共 4 项（全部强制走代理，不受白名单影响）：

      * HTTP 代理   —— 普通转发 + 407 认证；
      * SOCKS5 代理 —— 用户名/密码握手（OpenClash 的 mixed 端口通常都能用）；
      * 目标分别是 HTTP 与 HTTPS（图片下载走 HTTPS 隧道）。

    目标用 `www.baidu.com`（只验证代理链路，不依赖能否翻墙）。
    全部失败时再直连一次做对照，区分「代理没开 allow-lan」与「手机连不上外网」。
    """
    import socket
    import time

    proxy = net._proxy_config()
    if not proxy:
        return {'ok': False,
                'error': '没有配置代理：请填写「代理」地址，例如 localhost:8080'}

    # 第一步：TCP 端口能否连上。
    # 这一步不经过任何代理协议，用来区分「手机根本连不上代理」
    # 和「连上了但 HTTP/SOCKS 认证失败」。
    tcp = {'ok': False, 'elapsed_ms': 0}
    started = time.time()
    try:
        sock = socket.create_connection((proxy['host'], proxy['port']), timeout=6)
        sock.close()
        tcp = {'ok': True, 'elapsed_ms': int((time.time() - started) * 1000)}
    except Exception as e:
        tcp = {'ok': False,
               'elapsed_ms': int((time.time() - started) * 1000),
               'error': '%s: %s' % (type(e).__name__, e)}

    protocols = [('HTTP 代理', 'http'), ('SOCKS5', 'socks')]
    targets = [('HTTP', 'http://www.baidu.com/'), ('HTTPS', 'https://www.baidu.com/')]

    results = []
    for protocol_label, protocol in protocols:
        for target_label, url in targets:
            started = time.time()
            item = {'label': '%s → %s' % (protocol_label, target_label),
                    'protocol': protocol, 'target': target_label, 'url': url}
            try:
                resp = net.request('GET', url, timeout=12,
                                   _force_proxy=True, _proxy_type=protocol)
                item.update(status=resp.status_code,
                            ok=resp.status_code < 400,
                            elapsed_ms=int((time.time() - started) * 1000))
            except Exception as e:
                item.update(ok=False,
                            elapsed_ms=int((time.time() - started) * 1000),
                            error='%s: %s' % (type(e).__name__, e))
            results.append(item)

    # 推荐协议：HTTPS 目标能通的那一个（图片下载走 HTTPS）
    recommended = None
    for item in results:
        if item.get('ok') and item.get('target') == 'HTTPS':
            recommended = item['protocol']
            break

    result = {
        'ok': any(item.get('ok') and item.get('target') == 'HTTPS' for item in results),
        'proxy': '%s:%s' % (proxy['host'], proxy['port']),
        'auth': bool(proxy.get('user')),
        'tcp': tcp,
        'results': results,
        'recommended': recommended,
    }

    if not result['ok']:
        try:
            direct = net.request('GET', 'http://www.baidu.com/', timeout=8,
                                 _no_proxy=True)
            result['direct_status'] = direct.status_code
        except Exception as e:
            result['direct_error'] = '%s: %s' % (type(e).__name__, e)

    return result


@_safe
def disk(force: bool = False) -> dict:
    return {'ok': True, 'disk': paths.disk_snapshot()}


@_safe
def option_preview() -> dict:
    """把实际使用的 option 打出来，方便排查（设置页「配置预览」用）。"""
    return {'ok': True, 'yaml': task.build_option_yaml()}


@_safe
def version() -> dict:
    return {'ok': True, 'version': VERSION, 'python': sys.version.split()[0]}
