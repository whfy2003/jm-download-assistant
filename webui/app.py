# -*- coding: utf-8 -*-
"""
JM 下载助手 —— 本地网页端（Flask）

功能：
  1. 输入本子编号 → 后台下载 → 自动合并为 PDF 保存到下载目录
  2. 下载记录：读取同目录的 jm_log.txt（同一个本子只显示一条）
  3. 单条记录可：用系统默认程序打开 / 收藏到收藏夹 / 删除文件并抹去日志
  4. 收藏页：收藏夹同样支持查看、搜索、打开、取消收藏、删除
  5. 设置页：可修改下载目录与收藏目录，修改后自动把原目录内容迁移过去
  6. 侧栏显示两个目录所在磁盘的占用条
  7. 下载过程实时进度：已下载张数 / 总张数、第几章、合并 PDF 阶段
  8. 设置页可填 AVS（登录 cookies），用于访问登录后才可见的内容
  9. 设置页可检查更新：读取项目主页最新 Release 版本

日志格式（两个目录一致）：编号 | 文件名 | 时间
配置持久化：E:\\JM web\\settings.json

启动：见同目录上一级的 start-jm-web.cmd
"""
import io
import json
import logging
import os
import shutil
import sys
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request

# ----------------------------------------------------------------------------
# 路径与运行参数
#   源码运行：数据放在 E:\JM web
#   打包运行：数据放在 exe 同级目录，静态资源取自解包目录
# ----------------------------------------------------------------------------
IS_FROZEN = getattr(sys, 'frozen', False)

if IS_FROZEN:
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = os.path.join(getattr(sys, '_MEIPASS', APP_DIR), 'webui')
else:
    RES_DIR = os.path.dirname(os.path.abspath(__file__))     # E:\JM web\webui
    APP_DIR = os.path.dirname(RES_DIR)                        # E:\JM web

OPTION_FILE = os.path.join(APP_DIR, 'option.yml')        # jmcomic 配置
WORK_DIR = os.path.join(APP_DIR, 'downloads')            # 图片工作区
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')   # 目录设置

if IS_FROZEN:
    DEFAULT_PDF_DIR = os.path.join(APP_DIR, '漫画')
    DEFAULT_FAV_DIR = os.path.join(APP_DIR, '收藏')
else:
    DEFAULT_PDF_DIR = r'E:\漫画\JM'                        # 默认下载目录
    DEFAULT_FAV_DIR = r'E:\([AAAAA])'                     # 默认收藏夹

HOST = '127.0.0.1'
PORT = 8080
RECENT_LIMIT = 500          # “搜索”只在这最近 500 条记录里找
MAX_RUNTIME_LOGS = 200      # 状态区保留的最近运行日志行数
DISK_CACHE_SECONDS = 20     # 磁盘占用统计缓存

# ----------------------------------------------------------------------------
# 版本与项目信息（「检查更新」用）
# 发新版本时只要同步改 APP_VERSION，与 GitHub Release 的 tag 比较即可。
# ----------------------------------------------------------------------------
APP_VERSION = '1.1'
PROJECT_URL = 'https://github.com/whfy2003/jm-download-assistant'
RELEASES_URL = PROJECT_URL + '/releases/latest'
LATEST_RELEASE_API = ('https://api.github.com/repos/whfy2003/'
                      'jm-download-assistant/releases/latest')

app = Flask(__name__,
            template_folder=os.path.join(RES_DIR, 'templates'),
            static_folder=os.path.join(RES_DIR, 'static'))

# ----------------------------------------------------------------------------
# 目录设置（可在设置页修改，持久化到 settings.json）
# ----------------------------------------------------------------------------
_settings_lock = threading.Lock()
_settings = {'pdf_dir': DEFAULT_PDF_DIR, 'fav_dir': DEFAULT_FAV_DIR, 'avs': ''}


def _load_settings():
    if not os.path.exists(SETTINGS_FILE):
        _save_settings()      # 首次运行落盘一份，便于查看与备份
        return
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data.get('pdf_dir'), str) and data['pdf_dir'].strip():
            _settings['pdf_dir'] = data['pdf_dir'].strip()
        if isinstance(data.get('fav_dir'), str) and data['fav_dir'].strip():
            _settings['fav_dir'] = data['fav_dir'].strip()
        if isinstance(data.get('avs'), str):
            _settings['avs'] = data['avs'].strip()
    except Exception as e:
        print('读取 settings.json 失败：%s' % e)


def _save_settings():
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('写入 settings.json 失败：%s' % e)


def get_pdf_dir():
    return _settings['pdf_dir']


def get_fav_dir():
    return _settings['fav_dir']


def get_avs():
    """登录 cookies 里的 AVS 值（可空）。用于访问登录后才可见的内容。"""
    return (_settings.get('avs') or '').strip()


def get_log_file():
    return os.path.join(get_pdf_dir(), 'jm_log.txt')


def get_fav_log():
    return os.path.join(get_fav_dir(), 'jm_fav_log.txt')


def _dir_for_scope(scope):
    if scope == 'fav':
        return get_fav_dir(), get_fav_log()
    return get_pdf_dir(), get_log_file()


# ----------------------------------------------------------------------------
# 运行状态（单任务：同一时刻只跑一个下载）
# ----------------------------------------------------------------------------
_state_lock = threading.Lock()
_state = {
    'running': False,
    'album_id': '',
    'title': '',
    'message': '空闲',
    'ok': None,             # None=未跑过 / True=成功 / False=失败
    'started_at': '',
    'finished_at': '',
    'logs': [],
    # 下载进度：phase = idle / meta / download / pdf / done / error
    'progress': {
        'phase': 'idle',
        'done': 0,          # 已处理的图片数（含缓存命中）
        'total': 0,         # 总图片数（拿到本子详情后才知道）
        'percent': 0,
        'photo_done': 0,
        'photo_total': 0,
        'photo_index': 0,
        'current': '',      # 当前章节标题
        'title': '',        # 本子标题
        'note': '',         # 阶段说明文字
        'failed': 0,
    },
}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _progress_reset(note=''):
    with _state_lock:
        _state['progress'] = {
            'phase': 'meta', 'done': 0, 'total': 0, 'percent': 0,
            'photo_done': 0, 'photo_total': 0, 'photo_index': 0,
            'current': '', 'title': '', 'note': note, 'failed': 0,
        }


def _progress_update(**fields):
    with _state_lock:
        p = _state['progress']
        p.update(fields)
        total = int(p.get('total') or 0)
        if total > 0:
            p['percent'] = max(0, min(100, int(int(p.get('done') or 0) * 100 / total)))


def _progress_bump(images=0, photos=0, failed=0):
    with _state_lock:
        p = _state['progress']
        if images:
            p['done'] = int(p.get('done') or 0) + images
        if photos:
            p['photo_done'] = int(p.get('photo_done') or 0) + photos
        if failed:
            p['failed'] = int(p.get('failed') or 0) + failed
        total = int(p.get('total') or 0)
        if total > 0:
            p['percent'] = max(0, min(100, int(int(p.get('done') or 0) * 100 / total)))


def _push_log(line):
    line = (line or '').rstrip()
    if not line:
        return
    with _state_lock:
        logs = _state['logs']
        logs.append(line)
        if len(logs) > MAX_RUNTIME_LOGS:
            del logs[:len(logs) - MAX_RUNTIME_LOGS]


class _TeeStream(io.TextIOBase):
    """把写到 stdout/stderr 的内容同时转发到界面状态区。"""

    def __init__(self, original):
        self._original = original
        self._buf = ''

    def write(self, s):
        try:
            self._original.write(s)
        except Exception:
            pass
        if not isinstance(s, str):
            return 0
        self._buf += s
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            _push_log(line)
        return len(s)

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass


class _UiLogHandler(logging.Handler):
    """jmcomic 用 logging.getLogger('jmcomic') 输出，这里把它接到界面上。"""

    def emit(self, record):
        try:
            _push_log(self.format(record))
        except Exception:
            pass


class _JmLoggerCapture(object):
    def __init__(self):
        self.logger = logging.getLogger('jmcomic')
        self.handler = _UiLogHandler()
        self.handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(message)s', datefmt='%H:%M:%S'))

    def __enter__(self):
        self.logger.addHandler(self.handler)
        return self

    def __exit__(self, exc_type, exc, tb):
        self.logger.removeHandler(self.handler)
        return False


# ----------------------------------------------------------------------------
# 磁盘占用
# ----------------------------------------------------------------------------
_disk_cache = {'ts': 0.0, 'data': None}


def _dir_size(path):
    """递归统计目录大小（只读元数据，很快）。"""
    total = 0
    if not os.path.isdir(path):
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _disk_info(path):
    info = {'path': path, 'exists': os.path.isdir(path), 'dir_size': 0,
            'total': 0, 'used': 0, 'free': 0}
    try:
        probe = path if os.path.isdir(path) else (os.path.splitdrive(os.path.abspath(path))[0] + os.sep)
        usage = shutil.disk_usage(probe)
        info.update(total=usage.total, used=usage.used, free=usage.free)
        info['drive'] = os.path.splitdrive(os.path.abspath(path))[0] or '/'
    except Exception as e:
        info['error'] = str(e)

    info['dir_size'] = _dir_size(path) if info['exists'] else 0
    # 该目录之外已被占用的空间
    info['other_used'] = max(0, info['used'] - info['dir_size'])
    return info


def _disk_snapshot(force=False):
    now = time.time()
    if not force and _disk_cache['data'] and now - _disk_cache['ts'] < DISK_CACHE_SECONDS:
        return _disk_cache['data']
    data = {'pdf': _disk_info(get_pdf_dir()), 'fav': _disk_info(get_fav_dir())}
    _disk_cache['ts'] = now
    _disk_cache['data'] = data
    return data


# ----------------------------------------------------------------------------
# 目录迁移（设置页用）
# ----------------------------------------------------------------------------
def _relocate(old_dir, new_dir):
    """把 old_dir 下的所有内容移动到 new_dir；旧目录空掉后会被删除。"""
    old_dir = os.path.abspath(old_dir)
    new_dir = os.path.abspath(new_dir)

    if old_dir == new_dir:
        return {'moved': 0, 'skipped': 0, 'errors': [], 'same': True}

    # 防止把新目录设在旧目录里（或反过来），否则会自我递归
    if new_dir.startswith(old_dir + os.sep) or old_dir.startswith(new_dir + os.sep):
        return {'moved': 0, 'skipped': 0,
                'errors': ['新旧目录不能互相包含'], 'fatal': True}

    try:
        os.makedirs(new_dir, exist_ok=True)
    except Exception as e:
        return {'moved': 0, 'skipped': 0, 'errors': ['无法创建新目录：%s' % e], 'fatal': True}

    if not os.path.isdir(old_dir):
        return {'moved': 0, 'skipped': 0, 'errors': [], 'note': '旧目录不存在，已直接切换'}

    moved = skipped = 0
    errors = []
    for name in os.listdir(old_dir):
        src = os.path.join(old_dir, name)
        dst = os.path.join(new_dir, name)
        if os.path.exists(dst):
            skipped += 1
            continue
        try:
            shutil.move(src, dst)
            moved += 1
        except Exception as e:
            errors.append('%s：%s' % (name, e))

    old_removed = False
    try:
        if not os.listdir(old_dir):
            os.rmdir(old_dir)
            old_removed = True
    except OSError:
        pass

    return {'moved': moved, 'skipped': skipped, 'errors': errors[:10],
            'old_removed': old_removed, 'same': False}


# ----------------------------------------------------------------------------
# 日志读取 / 解析 / 写入
# ----------------------------------------------------------------------------
def _read_lines(log_path, scope='all'):
    if not os.path.exists(log_path):
        return []
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    if scope == 'recent':
        return lines[-RECENT_LIMIT:]
    return lines


def _parse_records(lines):
    """
    解析并合并记录：
      · 同一个 (编号, 时间) 的多行视为一个本子（标题行 + .pdf 行）
      · 优先使用 .pdf 行作为真实文件名
      · 同一个文件名多次出现时，只保留时间最新的一条
    返回按时间倒序（最新在最上面）的列表。
    """
    groups, order = {}, []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) < 3:
            continue
        jm_id = parts[0].strip()
        name = '|'.join(parts[1:-1]).strip()
        ts = parts[-1].strip()
        if not jm_id or not name:
            continue
        key = (jm_id, ts)
        if key not in groups:
            groups[key] = {'id': jm_id, 'time': ts, 'names': []}
            order.append(key)
        groups[key]['names'].append(name)

    by_file = {}
    for key in order:
        g = groups[key]
        pdfs = [n for n in g['names'] if n.lower().endswith('.pdf')]
        if pdfs:
            filename = pdfs[0]
            display = filename[:-4]
        else:
            display = g['names'][0]
            filename = display + '.pdf'

        record = {'id': g['id'], 'name': display, 'file': filename, 'time': g['time']}
        prev = by_file.get(filename)
        if prev is None or record['time'] > prev['time']:
            by_file[filename] = record

    return sorted(by_file.values(), key=lambda r: r['time'], reverse=True)


def _append_log_line(log_path, jm_id, filename):
    ts = _now()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write('%s | %s | %s\n' % (jm_id, filename, ts))


def _append_record_pair(log_path, jm_id, stem):
    """按既有格式写入两行（标题行 + .pdf 行），共用同一时间戳。"""
    ts = _now()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write('%s | %s | %s\n' % (jm_id, stem, ts))
        f.write('%s | %s.pdf | %s\n' % (jm_id, stem, ts))


def _remove_log_entries(log_path, jm_id, filename):
    """抹去该文件对应的日志行（文件名行 + 去掉 .pdf 的标题行）。返回删除行数。"""
    if not os.path.exists(log_path):
        return 0
    stem = os.path.splitext(filename)[0]
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()

    kept, removed = [], 0
    for line in lines:
        parts = line.split('|')
        if len(parts) >= 3:
            pid = parts[0].strip()
            pname = '|'.join(parts[1:-1]).strip()
            if pid == str(jm_id) and pname in (filename, stem):
                removed += 1
                continue
        kept.append(line)

    with open(log_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(kept))
        if kept:
            f.write('\n')
    return removed


def _enrich(records, base_dir, fav_files=None):
    out = []
    for r in records:
        item = dict(r)
        item['exists'] = os.path.isfile(os.path.join(base_dir, r['file']))
        if fav_files is not None:
            item['fav'] = r['file'] in fav_files
        out.append(item)
    return out


def _list_pdf_names(directory):
    try:
        return {n for n in os.listdir(directory) if n.lower().endswith('.pdf')}
    except OSError:
        return set()


def _fav_file_set():
    return _list_pdf_names(get_fav_dir())


def _dir_writable(path):
    probe = os.path.join(path, '.jm_write_probe')
    try:
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('x')
        os.remove(probe)
        return True
    except OSError:
        return False


def _sync_fav_directory():
    """把收藏夹里「有文件但没日志」的内容纳管（编号记为 -）。"""
    fav_dir, fav_log = get_fav_dir(), get_fav_log()
    if not os.path.isdir(fav_dir):
        return 0, None

    files = _list_pdf_names(fav_dir)
    logged = {r['file'] for r in _parse_records(_read_lines(fav_log, 'all'))}
    missing = sorted(files - logged)
    if not missing:
        return 0, None

    try:
        with open(fav_log, 'a', encoding='utf-8') as f:
            for name in missing:
                path = os.path.join(fav_dir, name)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
                except OSError:
                    mtime = _now()
                f.write('- | %s | %s\n' % (name, mtime))
        return len(missing), None
    except PermissionError:
        return 0, '收藏夹目录没有写入权限，日志暂时无法登记'
    except Exception as e:
        return 0, str(e)


def _fav_records(scope='all'):
    """收藏页数据 = 收藏日志 + 目录里实际存在但尚未登记的文件。"""
    fav_dir, fav_log = get_fav_dir(), get_fav_log()
    records = _parse_records(_read_lines(fav_log, scope))
    logged = {r['file'] for r in records}

    for name in sorted(_list_pdf_names(fav_dir) - logged):
        path = os.path.join(fav_dir, name)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
        except OSError:
            mtime = ''
        records.append({
            'id': '-', 'name': os.path.splitext(name)[0],
            'file': name, 'time': mtime,
        })

    records.sort(key=lambda r: r['time'], reverse=True)
    return records


def _safe_name(raw):
    name = os.path.basename(str(raw or '').strip())
    if not name or name in ('.', '..') or '/' in name or '\\' in name:
        return None
    return name


# ----------------------------------------------------------------------------
# 下载任务
# ----------------------------------------------------------------------------
def _snapshot_pdfs():
    return _list_pdf_names(get_pdf_dir())


def _newest_pdf_name(before):
    pdf_dir = get_pdf_dir()
    added = _list_pdf_names(pdf_dir) - before
    if not added:
        return None
    newest, newest_mtime = None, -1
    for name in added:
        try:
            mtime = os.path.getmtime(os.path.join(pdf_dir, name))
        except OSError:
            continue
        if mtime > newest_mtime:
            newest, newest_mtime = name, mtime
    return os.path.splitext(newest)[0] if newest else None


def _cleanup_empty_dirs(root):
    if not os.path.isdir(root):
        return
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        if os.path.abspath(dirpath) == os.path.abspath(root):
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError:
            pass


def _build_option():
    """
    载入 option.yml，并把两项路径对齐到本机实际位置：
      · img2pdf 的输出目录 pdf_dir → 当前设置的下载目录
      · 图片工作区 base_dir      → 程序目录下的 downloads\\
    以字符串方式改写，不改动磁盘上的 option.yml 文件。
    若设置里填了 AVS，则把它作为登录 cookies 注入，用于访问登录后才可见的内容。
    """
    import re

    import jmcomic

    with open(OPTION_FILE, 'r', encoding='utf-8') as f:
        text = f.read()

    def as_yaml_str(path):
        return '"' + path.replace('\\', '/').replace('"', '\\"') + '"'

    # PDF 成品输出目录
    new_text, count = re.subn(r'pdf_dir\s*:\s*.*', 'pdf_dir: ' + as_yaml_str(get_pdf_dir()),
                              text, count=1)
    if count == 0:
        # 配置里没有 pdf_dir 时，退回原始配置，避免意外
        new_text = text

    # 图片工作区：必须跟程序目录走，否则绿色版/安装版会写到打包机器的路径
    new_text, count = re.subn(r'base_dir\s*:\s*.*', 'base_dir: ' + as_yaml_str(WORK_DIR),
                              new_text, count=1)

    option = jmcomic.create_option_by_str(new_text)

    avs = get_avs()
    if avs:
        try:
            option.update_cookies({'AVS': avs})
        except Exception as e:
            _push_log('[提示] AVS 注入失败（将按未登录状态下载）：%s' % e)

    return option


def _run_download(jm_id):
    before = _snapshot_pdfs()

    with _state_lock:
        _state.update({
            'running': True, 'album_id': jm_id, 'title': '',
            'message': '程序运行中', 'ok': None,
            'started_at': _now(), 'finished_at': '', 'logs': [],
        })
    _progress_reset('正在获取本子信息…')

    original_stdout, original_stderr = sys.stdout, sys.stderr
    tee_out, tee_err = _TeeStream(original_stdout), _TeeStream(original_stderr)

    ok, message, title = False, '', ''
    try:
        import jmcomic

        # 用自定义 downloader 挂在 jmcomic 的下载回调上统计进度。
        # 这些回调由 jmcomic 自己在多线程里调用，_progress_* 内部已加锁。
        class _ProgressDownloader(jmcomic.JmDownloader):
            def before_album(self, album):
                try:
                    total = int(getattr(album, 'page_count', 0) or 0)
                except Exception:
                    total = 0
                try:
                    photo_total = len(album)
                except Exception:
                    photo_total = 0
                _progress_update(phase='download', total=total,
                                 photo_total=photo_total,
                                 title=getattr(album, 'name', '') or '',
                                 note='')
                super().before_album(album)

            def before_photo(self, photo):
                # jmcomic 的 photo.index 从 1 开始（形如 album[1/12]）
                try:
                    index = int(getattr(photo, 'index', 0) or 0)
                except Exception:
                    index = 0
                _progress_update(photo_index=index,
                                 current=getattr(photo, 'name', '') or '')
                super().before_photo(photo)

            def after_image(self, image, img_save_path):
                super().after_image(image, img_save_path)
                _progress_bump(images=1)

            def after_photo(self, photo):
                super().after_photo(photo)
                _progress_bump(photos=1)

            def after_album(self, album):
                # 配置里 img2pdf 挂在 after_album，这一步耗时最长，单独显示
                _progress_update(phase='pdf', note='正在合并为 PDF…')
                super().after_album(album)
                _progress_update(phase='done', note='')

        option = _build_option()
        with _JmLoggerCapture():
            sys.stdout, sys.stderr = tee_out, tee_err
            try:
                album, _downloader = jmcomic.download_album(
                    jm_id, option, downloader=_ProgressDownloader)
            finally:
                sys.stdout, sys.stderr = original_stdout, original_stderr

        title = _newest_pdf_name(before) or getattr(album, 'name', '') or jm_id
        _append_record_pair(get_log_file(), jm_id, title)
        _cleanup_empty_dirs(WORK_DIR)
        ok, message = True, '下载完成'
        _progress_update(phase='done', percent=100, note='')
    except Exception as e:
        message = '%s: %s' % (type(e).__name__, e)
        _push_log('[下载失败] ' + message)
        _progress_update(phase='error', note='下载失败')
    finally:
        with _state_lock:
            _state.update({
                'running': False, 'title': title,
                'message': message, 'ok': ok, 'finished_at': _now(),
            })


# ----------------------------------------------------------------------------
# 路由 · 页面
# ----------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template(
        'index.html',
        pdf_dir=get_pdf_dir(), log_file=get_log_file(),
        fav_dir=get_fav_dir(), fav_log=get_fav_log(),
        default_pdf=DEFAULT_PDF_DIR, default_fav=DEFAULT_FAV_DIR,
        addr='127.0.0.1:%d' % PORT,
        version=APP_VERSION, project_url=PROJECT_URL,
        releases_url=RELEASES_URL,
    )


@app.route('/api/state')
def api_state():
    with _state_lock:
        payload = dict(_state)
        payload['logs'] = list(_state['logs'])
        payload['progress'] = dict(_state['progress'])
    payload['pdf_dir'] = get_pdf_dir()
    return jsonify(payload)


@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json(silent=True) or {}
    jm_id = str(data.get('id', '')).strip()

    if not jm_id:
        return jsonify(ok=False, error='请输入本子编号'), 400
    if not jm_id.isdigit():
        return jsonify(ok=False, error='编号必须是纯数字'), 400

    with _state_lock:
        if _state['running']:
            return jsonify(ok=False, error='已有下载任务在运行中，请稍候'), 409

    _progress_reset('正在启动…')
    threading.Thread(target=_run_download, args=(jm_id,), daemon=True).start()
    return jsonify(ok=True, message='已开始下载 %s' % jm_id)


# ----------------------------------------------------------------------------
# 路由 · 记录
# ----------------------------------------------------------------------------
@app.route('/api/records')
def api_records():
    q = (request.args.get('q') or '').strip()
    scope = 'recent' if request.args.get('scope') == 'recent' else 'all'

    records = _parse_records(_read_lines(get_log_file(), scope))
    if q:
        records = [r for r in records if q in r['id']]
    records = _enrich(records, get_pdf_dir(), fav_files=_fav_file_set())

    return jsonify(ok=True, records=records, total=len(records), scope=scope, q=q)


@app.route('/api/favorites')
def api_favorites():
    q = (request.args.get('q') or '').strip()
    scope = 'recent' if request.args.get('scope') == 'recent' else 'all'

    _added, warning = _sync_fav_directory()
    records = _fav_records(scope)
    if q:
        records = [r for r in records if q in r['id']]
    records = _enrich(records, get_fav_dir())

    writable = _dir_writable(get_fav_dir())
    if not writable:
        warning = warning or '收藏夹目录没有写入权限：可以查看，但收藏/删除会失败'

    return jsonify(ok=True, records=records, total=len(records),
                   scope=scope, q=q, fav_dir=get_fav_dir(),
                   writable=writable, warning=warning)


# ----------------------------------------------------------------------------
# 路由 · 设置与磁盘
# ----------------------------------------------------------------------------
@app.route('/api/disk')
def api_disk():
    return jsonify(ok=True, disk=_disk_snapshot(force=request.args.get('force') == '1'))


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify(ok=True, pdf_dir=get_pdf_dir(), fav_dir=get_fav_dir(),
                       avs=get_avs(), version=APP_VERSION,
                       disk=_disk_snapshot())

    data = request.get_json(silent=True) or {}
    new_pdf = (data.get('pdf_dir') or '').strip().rstrip('\\/')
    new_fav = (data.get('fav_dir') or '').strip().rstrip('\\/')

    moves = {}
    changed = False

    if new_pdf and os.path.abspath(new_pdf) != os.path.abspath(get_pdf_dir()):
        if not os.path.splitdrive(new_pdf)[0]:
            return jsonify(ok=False, error='下载目录必须是绝对路径（例如 E:\\漫画\\JM）'), 400
        result = _relocate(get_pdf_dir(), new_pdf)
        if result.get('fatal'):
            return jsonify(ok=False, error='下载目录迁移失败：%s' % '；'.join(result['errors'])), 400
        moves['pdf'] = result
        with _settings_lock:
            _settings['pdf_dir'] = os.path.abspath(new_pdf)
        changed = True

    if new_fav and os.path.abspath(new_fav) != os.path.abspath(get_fav_dir()):
        if not os.path.splitdrive(new_fav)[0]:
            return jsonify(ok=False, error='收藏目录必须是绝对路径（例如 E:\\([AAAAA])）'), 400
        result = _relocate(get_fav_dir(), new_fav)
        if result.get('fatal'):
            return jsonify(ok=False, error='收藏目录迁移失败：%s' % '；'.join(result['errors'])), 400
        moves['fav'] = result
        with _settings_lock:
            _settings['fav_dir'] = os.path.abspath(new_fav)
        changed = True

    # AVS：只有请求里明确带了 avs 字段才改，避免「只保存目录」时被清空
    if 'avs' in data:
        avs = str(data.get('avs') or '').strip()
        avs = avs.replace('\r', '').replace('\n', '').replace('"', '').replace("'", '')
        if len(avs) > 200:
            return jsonify(ok=False, error='AVS 长度异常（正常不超过几十个字符）'), 400
        with _settings_lock:
            if _settings.get('avs', '') != avs:
                _settings['avs'] = avs
                changed = True

    if changed:
        _save_settings()
        _disk_cache['data'] = None

    return jsonify(ok=True, changed=changed, moves=moves,
                   pdf_dir=get_pdf_dir(), fav_dir=get_fav_dir(), avs=get_avs(),
                   disk=_disk_snapshot(force=True))


# ----------------------------------------------------------------------------
# 路由 · 关于与更新
# ----------------------------------------------------------------------------
def _version_tuple(text):
    """把 'V1.0' / 'v1.2.3' 之类解析成可比较的元组；解析不出返回 ()。"""
    import re
    nums = re.findall(r'\d+', str(text or ''))
    return tuple(int(n) for n in nums[:4])


def _fetch_latest_release():
    """
    读 GitHub 的最新 Release。返回 (info, error)。
    只用 Python 标准库，避免额外依赖；超时较短，失败时返回友好提示。
    """
    import urllib.request

    req = urllib.request.Request(
        LATEST_RELEASE_API,
        headers={
            'User-Agent': 'JM-Download-Assistant/%s' % APP_VERSION,
            'Accept': 'application/vnd.github+json',
        })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception as e:
        return None, ('无法连接 GitHub（%s）。可以点「打开项目主页」手动查看。'
                      % type(e).__name__)

    assets = []
    for a in data.get('assets') or []:
        assets.append({
            'name': a.get('name') or '',
            'size': a.get('size') or 0,
            'url': a.get('browser_download_url') or '',
        })

    return {
        'tag': data.get('tag_name') or '',
        'name': data.get('name') or '',
        'url': data.get('html_url') or RELEASES_URL,
        'notes': (data.get('body') or '')[:4000],
        'published_at': data.get('published_at') or '',
        'assets': assets,
    }, None


@app.route('/api/about')
def api_about():
    return jsonify(ok=True, version=APP_VERSION, project_url=PROJECT_URL,
                   releases_url=RELEASES_URL)


@app.route('/api/check-update')
def api_check_update():
    info, error = _fetch_latest_release()
    if error:
        return jsonify(ok=False, error=error, current=APP_VERSION,
                       project_url=PROJECT_URL, releases_url=RELEASES_URL)

    latest = info['tag']
    has_update = _version_tuple(latest) > _version_tuple(APP_VERSION)
    return jsonify(ok=True, current=APP_VERSION, latest=latest,
                   latest_name=info['name'], has_update=has_update,
                   url=info['url'], notes=info['notes'],
                   published_at=info['published_at'],
                   assets=info['assets'],
                   project_url=PROJECT_URL, releases_url=RELEASES_URL)


@app.route('/api/open-url', methods=['POST'])
def api_open_url():
    """只允许打开本项目的 GitHub 页面，避免被当成任意 URL 跳板。"""
    import webbrowser

    data = request.get_json(silent=True) or {}
    url = str(data.get('url') or '').strip()
    allowed_prefix = ('https://github.com/whfy2003/jm-download-assistant',
                      'https://api.github.com/repos/whfy2003/jm-download-assistant',
                      'https://objects.githubusercontent.com/',
                      'https://github.com/whfy2003/')
    if not url.startswith(allowed_prefix):
        return jsonify(ok=False, error='地址不在允许范围内'), 400
    try:
        webbrowser.open(url)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


# ----------------------------------------------------------------------------
# 路由 · 文件操作
# ----------------------------------------------------------------------------
@app.route('/api/open-file', methods=['POST'])
def api_open_file():
    data = request.get_json(silent=True) or {}
    filename = _safe_name(data.get('file'))
    if not filename:
        return jsonify(ok=False, error='文件名无效'), 400

    base_dir, _log = _dir_for_scope(data.get('scope'))
    path = os.path.join(base_dir, filename)
    if not os.path.isfile(path):
        return jsonify(ok=False, error='文件不存在：%s' % filename), 404
    try:
        os.startfile(path)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.route('/api/open-folder', methods=['POST'])
def api_open_folder():
    data = request.get_json(silent=True) or {}
    base_dir, _log = _dir_for_scope(data.get('scope'))
    try:
        os.makedirs(base_dir, exist_ok=True)
        os.startfile(base_dir)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.route('/api/delete', methods=['POST'])
def api_delete():
    """删除 PDF 文件，并从对应日志里抹去该文件的记录。"""
    data = request.get_json(silent=True) or {}
    filename = _safe_name(data.get('file'))
    jm_id = str(data.get('id', '')).strip()
    if not filename:
        return jsonify(ok=False, error='文件名无效'), 400

    base_dir, log_path = _dir_for_scope(data.get('scope'))
    path = os.path.join(base_dir, filename)

    file_removed = False
    if os.path.isfile(path):
        try:
            os.remove(path)
            file_removed = True
        except PermissionError:
            return jsonify(ok=False, error='没有删除权限，删除失败。'), 500
        except Exception as e:
            return jsonify(ok=False, error='删除文件失败：%s' % e), 500

    try:
        lines_removed = _remove_log_entries(log_path, jm_id, filename)
    except PermissionError:
        return jsonify(ok=False, error='文件已删除，但日志不可写，记录未能抹去'), 500

    return jsonify(ok=True, file_removed=file_removed, lines_removed=lines_removed)


@app.route('/api/favorite', methods=['POST'])
def api_favorite():
    """把下载目录里的 PDF 复制到收藏夹，并写收藏日志。"""
    data = request.get_json(silent=True) or {}
    filename = _safe_name(data.get('file'))
    jm_id = str(data.get('id', '')).strip() or '-'
    if not filename:
        return jsonify(ok=False, error='文件名无效'), 400

    pdf_dir, fav_dir, fav_log = get_pdf_dir(), get_fav_dir(), get_fav_log()
    src = os.path.join(pdf_dir, filename)
    if not os.path.isfile(src):
        return jsonify(ok=False, error='源文件不存在：%s' % filename), 404

    os.makedirs(fav_dir, exist_ok=True)
    dst = os.path.join(fav_dir, filename)
    if os.path.exists(dst):
        return jsonify(ok=True, already=True, message='该文件已在收藏夹中')

    try:
        shutil.copy2(src, dst)
    except PermissionError:
        return jsonify(ok=False, error='收藏夹目录没有写入权限，收藏失败。'), 500
    except Exception as e:
        return jsonify(ok=False, error='收藏失败：%s' % e), 500

    warning = None
    try:
        _append_log_line(fav_log, jm_id, filename)
    except PermissionError:
        warning = '文件已复制，但收藏日志登记失败（目录不可写）'

    return jsonify(ok=True, already=False, message='已收藏', warning=warning)


def main():
    _load_settings()

    # 打包运行时，option.yml 会先随程序分发，这里补一份到数据目录
    if not os.path.exists(OPTION_FILE):
        src = os.path.join(RES_DIR, 'option.yml')
        if os.path.exists(src):
            try:
                shutil.copy2(src, OPTION_FILE)
            except Exception as e:
                print('释放 option.yml 失败：%s' % e)

    for d in (get_pdf_dir(), get_fav_dir(), WORK_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            print('创建目录失败 %s：%s' % (d, e))

    print('=' * 60)
    print('JM 下载助手 已启动  v%s' % APP_VERSION)
    print('  访问地址 : http://%s:%d' % (HOST, PORT))
    print('  数据目录 : %s' % APP_DIR)
    print('  PDF 目录 : %s' % get_pdf_dir())
    print('  下载日志 : %s' % get_log_file())
    print('  收藏目录 : %s' % get_fav_dir())
    print('  收藏日志 : %s' % get_fav_log())
    print('  AVS 登录 : %s' % ('已配置' if get_avs() else '未配置（只能下载公开内容）'))
    print('  设置文件 : %s' % SETTINGS_FILE)
    print('  关闭本窗口即停止服务')
    print('=' * 60)
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == '__main__':
    main()
