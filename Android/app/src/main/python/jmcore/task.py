# -*- coding: utf-8 -*-
"""
jmcore.task —— 下载任务编排

对应 Flask 版的 `_run_download()`：

1. 记录下载前的 PDF 集合（用来反推本次生成的文件名）；
2. 把 settings 里的目录 / 并发 / cookies 组装成 option；
3. 调 `jmcomic.download_album()`（上游负责：域名、接口加解密、拆图、并发、
   img2pdf 合并 PDF、删除原图）；
4. 成功后写两条记录（标题行 + .pdf 行，同一时间戳）；
5. 清理工作区空目录。

单任务串行：同一时刻只允许一个下载，与网页版行为一致。
"""
from __future__ import annotations

import threading
import traceback

import jmcore.paths as paths
import jmcore.store as store
from jmcore import progress
from jmcore.logbus import LogBus

_bus = LogBus(200)
_lock = threading.RLock()
_thread = None

_state = {
    'running': False,
    'album_id': '',
    'title': '',
    'message': '空闲',
    'ok': None,          # None=未跑过 / True=成功 / False=失败
    'started_at': '',
    'finished_at': '',
    'progress': '',      # 最近一条日志，给通知栏用
}


def bus() -> LogBus:
    return _bus


def snapshot(include_logs: bool = True, log_limit: int = 60) -> dict:
    with _lock:
        data = dict(_state)
    data['pdf_dir'] = paths.pdf_dir() if paths.is_ready() else ''
    data['progress'] = progress.instance().snapshot()
    if include_logs:
        data['logs'] = _bus.tail(log_limit)
    return data


def is_running() -> bool:
    with _lock:
        return bool(_state['running'])


def _set(**kwargs):
    with _lock:
        _state.update(kwargs)


def cancel_placeholder():
    """上游不支持中断下载，这里保留接口给界面做提示。"""
    return {'ok': False, 'error': '正在下载的任务无法中断，请等待其完成'}


def _log_proxy():
    """把当前网络方式写进运行日志，便于确认「到底走没走代理」。"""
    try:
        from jmcore import net
        config = net._proxy_config()
        if not config:
            _bus.push('网络：直连（未配置代理）')
            return

        only = (paths.proxy_only() or '').strip()
        if only:
            count = len([line for line in only.splitlines() if line.strip()])
            scope = '仅白名单 %d 项' % count
        else:
            scope = '全部请求'

        _bus.push('网络：代理 %s:%s（认证：%s，范围：%s）' % (
            config['host'], config['port'],
            '是' if config.get('user') else '否', scope))
    except Exception as e:
        _bus.push('网络：读取代理配置失败：%s' % e)


# --------------------------------------------------------------------------- #
# option 组装
# --------------------------------------------------------------------------- #
def _cookie_dict():
    raw = (paths.cookies() or '').strip()
    if not raw:
        return None
    cookies = {}
    for part in raw.split(';'):
        part = part.strip()
        if not part:
            continue
        if '=' in part:
            key, value = part.split('=', 1)
            cookies[key.strip()] = value.strip()
    return cookies or None


def _proxy_value():
    proxy = (paths.proxy() or '').strip()
    if not proxy:
        return None
    return proxy


def build_option_yaml() -> str:
    """生成 option 配置（与原 option.yml 等价，只是路径/并发换成运行时设置）。"""
    import yaml

    conf = {
        'log': True,
        'client': {
            'impl': 'api',
            'retry_times': 5,
            'postman': {
                # 由 jmcore.net 顶替成 Android 传输实现
                'type': 'curl_cffi',
                'meta_data': {
                    'headers': None,
                    'proxies': _proxy_value(),
                    'cookies': _cookie_dict(),
                },
            },
        },
        'download': {
            'cache': True,
            'image': {'decode': True},
            'threading': {
                'image': paths.image_threads(),
                'photo': paths.photo_threads(),
            },
        },
        'dir_rule': {
            'base_dir': paths.work_dir(),
            'rule': 'Bd / Ptitle',
        },
        'plugins': {
            # 缺少可选依赖时只记录日志，不抛异常（Android 上没有 pikepdf / rich 等）
            'dependencies_strategy': 'ignore-only-log',
            'after_album': [
                {
                    'plugin': 'img2pdf',
                    'kwargs': {
                        'pdf_dir': paths.pdf_dir(),
                        'filename_rule': 'Atitle',
                        'delete_original_file': True,
                    },
                },
            ],
        },
    }
    return yaml.safe_dump(conf, allow_unicode=True, sort_keys=False)


def build_option():
    import jmcomic
    return jmcomic.create_option_by_str(build_option_yaml())


# --------------------------------------------------------------------------- #
# 下载
# --------------------------------------------------------------------------- #
def start(album_id) -> dict:
    """启动下载线程；参数校验与网页版一致。"""
    global _thread

    album_id = str(album_id or '').strip()
    if not album_id:
        return {'ok': False, 'error': '请输入本子编号'}
    if not album_id.isdigit():
        return {'ok': False, 'error': '编号必须是纯数字'}

    with _lock:
        if _state['running']:
            return {'ok': False, 'error': '已有下载任务在运行中，请稍候'}
        _state.update({
            'running': True,
            'album_id': album_id,
            'title': '',
            'message': '程序运行中',
            'ok': None,
            'started_at': store.now(),
            'finished_at': '',
            'progress': '',
        })

    _bus.clear()
    _bus.push('开始下载：%s' % album_id)

    _thread = threading.Thread(target=_run, args=(album_id,), daemon=True)
    _thread.start()
    return {'ok': True, 'message': '已开始下载 %s' % album_id}


def _run(album_id: str) -> None:
    before = store.snapshot_pdfs()
    title = ''
    ok, message = False, ''

    try:
        import jmcomic

        from jmcore import imagefix
        imagefix.install()
        progress.install()

        option = build_option()
        _log_proxy()

        # 先拿总页数，让进度条是确定的；失败不影响下载，只是退回不确定进度
        total = 0
        try:
            client = option.build_jm_client()
            detail = client.get_album_detail(album_id)
            total = int(getattr(detail, 'page_count', 0) or 0)
        except Exception as e:
            _bus.push('预取本子信息失败（进度条将显示为不确定）：%s' % e)

        progress.instance().start(total)
        _bus.push('总页数：%s' % (total if total else '未知'))

        result = jmcomic.download_album(album_id, option)

        album = getattr(result, 'detail', None)
        if album is None:
            try:
                album = result[0]
            except Exception:
                album = None

        newest = store.newest_pdf_stem(before)
        album_name = getattr(album, 'name', '') or ''

        if not newest and not album_name:
            raise RuntimeError('下载结束但没有生成 PDF，请查看运行日志')

        title = newest or album_name or album_id

        store.append_record_pair(paths.pdf_log(), album_id, title)
        store.cleanup_empty_dirs(paths.work_dir())
        ok, message = True, '下载完成'
        _bus.push('下载完成：%s' % title)

    except Exception as e:
        message = '%s: %s' % (type(e).__name__, e)
        _bus.push('[下载失败] ' + message)
        _bus.push(traceback.format_exc()[-1500:])

    finally:
        progress.instance().finish()
        with _lock:
            _state.update({
                'running': False,
                'title': title,
                'message': message,
                'ok': ok,
                'finished_at': store.now(),
            })
