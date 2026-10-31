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
import random
import shutil
import sys
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request

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
APP_VERSION = '1.0.3'
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
_settings = {'pdf_dir': DEFAULT_PDF_DIR, 'fav_dir': DEFAULT_FAV_DIR, 'avs': '',
             'app_version': '', 'domains': []}


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
        if isinstance(data.get('app_version'), str):
            _settings['app_version'] = data['app_version'].strip()
        if isinstance(data.get('domains'), list):
            _settings['domains'] = [str(x).strip() for x in data['domains'] if str(x).strip()]
    except Exception as e:
        print('读取 settings.json 失败：%s' % e)


def _save_settings():
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print('写入 settings.json 失败：%s' % e)


# ----------------------------------------------------------------------------
# 上游版本标识 / API 域名缓存
# ----------------------------------------------------------------------------
def _apply_cached_app_version() -> str:
    """
    把上次协商到的 APP_VERSION 注入 jmcomic 内存常量。

    jmcomic 的 APP_VERSION 只是请求头 tokenparam 里的一个字段，
    检测到更高版本时只改内存，进程退出就没了。这里启动时先填回去，
    服务端返回相同版本时就不会再走一遍 change APP_VERSION。
    """
    cached = (_settings.get('app_version') or '').strip()
    if not cached:
        return ''
    try:
        import jmcomic
        current = jmcomic.JmMagicConstants.APP_VERSION
        if current and jmcomic.JmcomicText.compare_versions(cached, current) <= 0:
            return current
        jmcomic.JmMagicConstants.APP_VERSION = cached
        return cached
    except Exception:
        return ''


def _sync_app_version() -> str:
    """jmcomic 在内存里换过版本后写回 settings.json。"""
    try:
        import jmcomic
        current = jmcomic.JmMagicConstants.APP_VERSION
        if current and current != (_settings.get('app_version') or ''):
            _settings['app_version'] = current
            _save_settings()
        return current or ''
    except Exception:
        return ''


def _apply_cached_domains() -> list:
    """把上次缓存的域名列表注入 jmcomic，跳过阻塞式的域名探测。"""
    cached = _settings.get('domains') or []
    if not cached:
        return []
    try:
        from jmcomic import JmModuleConfig
        JmModuleConfig.DOMAIN_API_LIST = list(cached)
        JmModuleConfig.DOMAIN_API_UPDATED_LIST = list(cached)
        return list(cached)
    except Exception:
        return []


def _sync_domains() -> list:
    """jmcomic 探测到新域名后写回 settings.json（无变化不写盘）。"""
    try:
        from jmcomic import JmModuleConfig
        updated = [str(x) for x in (JmModuleConfig.DOMAIN_API_UPDATED_LIST or [])]
        if updated and sorted(updated) != sorted(_settings.get('domains') or []):
            _settings['domains'] = updated
            _save_settings()
        return updated
    except Exception:
        return []

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

# PDF 首页封面缓存（文件名 → base64 PNG），避免每次轮询都重新渲染
_cover_cache = {}


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


# ----------------------------------------------------------------------------
# 漫画详情（下载目录/日志/<编号>.txt）
# ----------------------------------------------------------------------------
DETAIL_SUBDIR = '日志'
_detail_cache = {}


def _detail_dir():
    return os.path.join(get_pdf_dir(), DETAIL_SUBDIR)


def _detail_path(jm_id):
    jm_id = str(jm_id or '').strip()
    if not jm_id or jm_id == '-':
        return None
    safe = ''.join(c for c in jm_id if c.isdigit()) or jm_id
    return os.path.join(_detail_dir(), safe + '.txt')


def _save_detail(detail):
    """把一部漫画的详情写成 日志/<编号>.txt。"""
    jm_id = str(detail.get('id') or '').strip()
    path = _detail_path(jm_id)
    if not path:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        lines = [
            '编号: %s' % jm_id,
            '标题: %s' % (detail.get('title') or ''),
            '作者: %s' % (detail.get('author') or ''),
            '点赞: %s' % (detail.get('likes') or ''),
            '浏览: %s' % (detail.get('views') or ''),
            '页数: %s' % (detail.get('pages') or ''),
            '标签: %s' % '、'.join(detail.get('tags') or []),
            '更新: %s' % _now(),
        ]
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        _detail_cache[jm_id] = {
            'id': jm_id,
            'title': detail.get('title') or '',
            'author': detail.get('author') or '',
            'likes': detail.get('likes') or '',
            'views': detail.get('views') or '',
            'pages': detail.get('pages') or '',
            'tags': list(detail.get('tags') or []),
            'updated': _now(),
        }
        return True
    except Exception as e:
        print('写入详情失败 %s：%s' % (jm_id, e))
        return False


def _read_detail(jm_id):
    """读取 日志/<编号>.txt；没有就返回 None（带内存缓存）。"""
    jm_id = str(jm_id or '').strip()
    if jm_id in _detail_cache:
        return _detail_cache[jm_id]

    path = _detail_path(jm_id)
    result = None
    if path and os.path.isfile(path):
        try:
            data = {}
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or ':' not in line:
                        continue
                    key, value = line.split(':', 1)
                    data[key.strip()] = value.strip()
            result = {
                'id': data.get('编号', jm_id),
                'title': data.get('标题', ''),
                'author': data.get('作者', ''),
                'likes': data.get('点赞', ''),
                'views': data.get('浏览', ''),
                'pages': data.get('页数', ''),
                'tags': [x for x in (data.get('标签') or '').split('、') if x],
                'updated': data.get('更新', ''),
            }
        except Exception:
            result = None

    _detail_cache[jm_id] = result
    return result


def _attach_detail(item):
    """把详情字段并进一条记录。"""
    detail = _read_detail(item.get('id'))
    if detail:
        item['author'] = detail.get('author', '')
        item['tags'] = detail.get('tags', [])
        item['likes'] = detail.get('likes', '')
        item['views'] = detail.get('views', '')
        item['pages'] = detail.get('pages', '')
        item['has_detail'] = True
    else:
        item.setdefault('author', '')
        item.setdefault('tags', [])
        item.setdefault('likes', '')
        item.setdefault('views', '')
        item.setdefault('pages', '')
        item['has_detail'] = False
    return item


def _match_query(item, q):
    """中文/编号/标题/作者/标签 任意子串匹配。"""
    if not q:
        return True
    q = q.lower()
    if q in str(item.get('id', '')).lower():
        return True
    if q in str(item.get('name', '')).lower():
        return True
    if q in str(item.get('author', '')).lower():
        return True
    for tag in item.get('tags') or []:
        if q in str(tag).lower():
            return True
    return False


def _sort_records(records, sort):
    """sort=likes 按点赞数倒序；否则按时间倒序。"""
    if sort == 'likes':
        def likes_key(item):
            try:
                return int(str(item.get('likes') or '0').replace(',', '').strip() or 0)
            except Exception:
                return 0
        return sorted(records, key=likes_key, reverse=True)
    return sorted(records, key=lambda x: x.get('time', ''), reverse=True)

def _enrich(records, base_dir, fav_files=None):
    out = []
    for r in records:
        item = dict(r)
        item['exists'] = os.path.isfile(os.path.join(base_dir, r['file']))
        item['dir'] = base_dir
        if fav_files is not None:
            item['fav'] = r['file'] in fav_files
        _attach_detail(item)
        out.append(item)
    return out


def _enrich_fav(records):
    """
    收藏记录的文件位置：优先下载目录（新版只记名字），
    其次收藏目录（旧版本复制过去的副本）。
    """
    pdf_dir, fav_dir = get_pdf_dir(), get_fav_dir()
    out = []
    for r in records:
        item = dict(r)
        in_pdf = os.path.isfile(os.path.join(pdf_dir, r['file']))
        in_fav = os.path.isfile(os.path.join(fav_dir, r['file']))
        item['exists'] = in_pdf or in_fav
        item['dir'] = pdf_dir if in_pdf else (fav_dir if in_fav else pdf_dir)
        item['in_download'] = in_pdf
        item['fav'] = True
        _attach_detail(item)
        out.append(item)
    return out


def _list_pdf_names(directory):
    try:
        return {n for n in os.listdir(directory) if n.lower().endswith('.pdf')}
    except OSError:
        return set()


def _fav_file_set():
    """
    收藏过的文件名集合。

    v1.2 起收藏不再复制 PDF，只在 jm_fav_log.txt 里记一行文件名，
    所以不能只看「收藏目录里有什么文件」——那样永远是空集，
    下载列表里的星标就永远不会变成实心。

    这里以收藏日志为准，并兼容旧版本复制到收藏目录里的副本。
    """
    names = set()
    try:
        for record in _parse_records(_read_lines(get_fav_log(), 'all')):
            if record.get('file'):
                names.add(record['file'])
    except Exception:
        pass
    names |= _list_pdf_names(get_fav_dir())
    return names


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
    """
    收藏页数据 = 收藏日志（只记文件名）+ 收藏目录里老版本遗留的副本。

    新版收藏不复制 PDF，文件本体在下载目录，展示时由 _enrich_fav 去找。
    """
    fav_dir, fav_log = get_fav_dir(), get_fav_log()
    records = _parse_records(_read_lines(fav_log, scope))
    logged = {r['file'] for r in records}

    # 老版本复制到收藏目录、日志里却没有登记的副本，补上
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


def _find_downloaded(jm_id):
    """在下载日志里精确找这个编号的记录；找不到返回 None。"""
    jm_id = str(jm_id or '').strip()
    if not jm_id:
        return None
    records = _parse_records(_read_lines(get_log_file(), 'all'))
    for r in records:
        if r['id'] == jm_id:
            return r
    return None


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
    # 顺手把协商出来的版本标识 / 域名写回 settings.json
    payload['app_version'] = _sync_app_version()
    payload['domains'] = _sync_domains()
    payload['detail_refresh'] = dict(_detail_refresh)
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

    # 已经下过就要求前端再确认一次（前端点「重新下载」时带 force=true）
    if not data.get('force'):
        existed = _find_downloaded(jm_id)
        if existed is not None:
            item = _enrich([existed], get_pdf_dir(), fav_files=_fav_file_set())[0]
            return jsonify(ok=False, need_confirm=True, record=item,
                           error='该本子已经下载过')

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
    sort = request.args.get('sort', 'time')

    records = _parse_records(_read_lines(get_log_file(), scope))
    records = _enrich(records, get_pdf_dir(), fav_files=_fav_file_set())
    if q:
        records = [r for r in records if _match_query(r, q)]
    records = _sort_records(records, sort)

    return jsonify(ok=True, records=records, total=len(records),
                   scope=scope, q=q, sort=sort)


@app.route('/api/favorites')
def api_favorites():
    q = (request.args.get('q') or '').strip()
    scope = 'recent' if request.args.get('scope') == 'recent' else 'all'
    sort = request.args.get('sort', 'time')

    _added, warning = _sync_fav_directory()
    records = _fav_records(scope)
    records = _enrich_fav(records)
    if q:
        records = [r for r in records if _match_query(r, q)]
    records = _sort_records(records, sort)

    writable = _dir_writable(get_fav_dir())
    if not writable:
        warning = warning or '收藏夹目录没有写入权限：可以查看，但收藏/删除会失败'

    return jsonify(ok=True, records=records, total=len(records),
                   scope=scope, q=q, sort=sort, fav_dir=get_fav_dir(),
                   writable=writable, warning=warning)


# ----------------------------------------------------------------------------
# 详情刷新：给还没有 日志/<编号>.txt 的漫画补抓详情
# ----------------------------------------------------------------------------
_detail_refresh = {'running': False, 'done': 0, 'total': 0, 'current': '', 'error': ''}


def _refresh_details_worker():
    try:
        ids = []
        for log_path in (get_log_file(), get_fav_log()):
            for r in _parse_records(_read_lines(log_path, 'all')):
                jm_id = str(r.get('id') or '').strip()
                if jm_id and jm_id != '-' and jm_id not in ids:
                    ids.append(jm_id)

        todo = [i for i in ids if _read_detail(i) is None]
        _detail_refresh.update({'total': len(todo), 'done': 0, 'error': ''})

        if not todo:
            return

        option = _build_option()
        client = option.build_jm_client()

        for index, jm_id in enumerate(todo):
            _detail_refresh['current'] = jm_id
            try:
                album = client.get_album_detail(jm_id)
                authors = getattr(album, 'authors', None) or []
                tags = getattr(album, 'tags', None) or []
                _save_detail({
                    'id': str(album.album_id),
                    'title': album.name,
                    'author': '、'.join(authors) if authors else getattr(album, 'author', ''),
                    'likes': getattr(album, 'likes', ''),
                    'views': getattr(album, 'views', ''),
                    'pages': int(getattr(album, 'page_count', 0) or 0),
                    'tags': [str(x) for x in tags],
                })
            except Exception as e:
                _detail_refresh['error'] = '%s: %s' % (jm_id, e)
            _detail_refresh['done'] = index + 1

            # 上游对高并发不友好，每部之间随机停 0.1~2 秒
            time.sleep(random.uniform(0.1, 2.0))
    finally:
        _detail_refresh['running'] = False
        _detail_refresh['current'] = ''


@app.route('/api/refresh-details', methods=['POST'])
def api_refresh_details():
    with _state_lock:
        if _detail_refresh['running']:
            return jsonify(ok=False, error='详情刷新已经在进行中'), 409
        _detail_refresh.update({'running': True, 'done': 0, 'total': 0,
                                'current': '', 'error': ''})

    threading.Thread(target=_refresh_details_worker, daemon=True).start()
    return jsonify(ok=True, message='开始刷新详情')


@app.route('/api/refresh-details/status')
def api_refresh_details_status():
    return jsonify(ok=True, **(dict(_detail_refresh)))


@app.route('/api/preview')
def api_preview():
    """预览本子：标题 / 作者 / 页数 / 章节 / 标签 / 封面（base64）。"""
    import base64

    jm_id = (request.args.get('id') or '').strip()
    if not jm_id:
        return jsonify(ok=False, error='请输入本子编号'), 400
    if not jm_id.isdigit():
        return jsonify(ok=False, error='编号必须是纯数字'), 400

    try:
        import jmcomic
        option = _build_option()
        client = option.build_jm_client()
        album = client.get_album_detail(jm_id)
    except Exception as e:
        return jsonify(ok=False, error='%s: %s' % (type(e).__name__, e)), 500

    cover_b64 = ''
    cover_url = ''
    cover_error = ''
    try:
        cover_url = jmcomic.JmcomicText.get_album_cover_url(jm_id)
        resp = client.get_jm_image(cover_url)
        if resp.is_success:
            cover_b64 = base64.b64encode(resp.content).decode('ascii')
        else:
            cover_error = '封面请求失败：HTTP %s' % resp.http_code
    except Exception as e:
        cover_error = '%s: %s' % (type(e).__name__, e)

    authors = getattr(album, 'authors', None) or []
    tags = getattr(album, 'tags', None) or []

    return jsonify(ok=True, album={
        'id': str(album.album_id),
        'title': album.name,
        'author': '、'.join(authors) if authors else getattr(album, 'author', ''),
        'page_count': int(getattr(album, 'page_count', 0) or 0),
        'episodes': len(album.episode_list or []),
        'tags': [str(x) for x in tags][:12],
        'description': (getattr(album, 'description', '') or '').strip()[:600],
        'pub_date': getattr(album, 'pub_date', ''),
        'likes': getattr(album, 'likes', ''),
        'views': getattr(album, 'views', ''),
        'cover_url': cover_url,
        'cover_base64': cover_b64,
        'cover_error': cover_error,
    })

@app.route('/api/lookup')
def api_lookup():
    """
    输入编号后查一下是否已经下载过（精确匹配编号）。
    没下载过返回 ok=True, found=False。
    """
    jm_id = (request.args.get('id') or '').strip()
    record = _find_downloaded(jm_id)
    if record is None:
        return jsonify(ok=True, found=False, id=jm_id)

    item = _enrich([record], get_pdf_dir(), fav_files=_fav_file_set())[0]
    return jsonify(ok=True, found=True, record=item)


@app.route('/api/cover')
def api_cover():
    """
    把下载目录里 PDF 的第一页渲染成图片，作为「已下载」卡片的封面。

    卡片上只显示 84×112，所以按固定宽度 260px 渲染成 JPEG（几十 KB），
    首次渲染通常几毫秒到一两百毫秒，之后走内存缓存。
    """
    filename = _safe_name(request.args.get('file'))
    if not filename:
        return jsonify(ok=False, error='文件名无效'), 400

    # 收藏记录（不复制文件）可能指向收藏目录里的旧副本
    base_dir = get_pdf_dir()
    dir_opt = (request.args.get('dir') or '').strip()
    if dir_opt:
        allowed = {os.path.abspath(get_pdf_dir()).lower(),
                   os.path.abspath(get_fav_dir()).lower()}
        candidate = os.path.abspath(dir_opt)
        if candidate.lower() in allowed:
            base_dir = candidate

    path = os.path.join(base_dir, filename)
    if not os.path.isfile(path):
        return jsonify(ok=False, error='文件不存在'), 404

    cache_key = base_dir.lower() + '|' + filename
    cached = _cover_cache.get(cache_key)
    if cached:
        return Response(cached, mimetype='image/jpeg',
                        headers={'Cache-Control': 'max-age=86400'})

    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            if doc.page_count <= 0:
                return jsonify(ok=False, error='PDF 没有页面'), 400
            page = doc.load_page(0)
            width = page.rect.width or 1
            zoom = 260.0 / width            # 缩略图固定 260px 宽
            zoom = max(0.05, min(zoom, 2.0))
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            data = pix.tobytes('jpeg', jpg_quality=82)
    except Exception as e:
        return jsonify(ok=False, error='%s: %s' % (type(e).__name__, e)), 500

    if len(_cover_cache) > 120:
        _cover_cache.clear()
    _cover_cache[cache_key] = data
    return Response(data, mimetype='image/jpeg',
                    headers={'Cache-Control': 'max-age=86400'})


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

    # 收藏记录（不复制文件）需要指定实际所在目录；只允许这两个已知目录
    dir_opt = (data.get('dir') or '').strip()
    if dir_opt:
        allowed = {os.path.abspath(get_pdf_dir()).lower(),
                   os.path.abspath(get_fav_dir()).lower()}
        candidate = os.path.abspath(dir_opt)
        if candidate.lower() not in allowed:
            return jsonify(ok=False, error='目录不在允许范围内'), 400
        base_dir = candidate

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
    """
    删除操作：
      · scope=dl  → 删下载目录里的 PDF，并从下载日志抹去记录
      · scope=fav → 只从收藏日志抹去这一条；文件在下载目录，不动
    """
    data = request.get_json(silent=True) or {}
    filename = _safe_name(data.get('file'))
    jm_id = str(data.get('id', '')).strip()
    if not filename:
        return jsonify(ok=False, error='文件名无效'), 400

    scope = data.get('scope')

    if scope == 'fav':
        try:
            lines_removed = _remove_log_entries(get_fav_log(), jm_id, filename)
        except PermissionError:
            return jsonify(ok=False, error='收藏日志不可写，取消收藏失败'), 500
        return jsonify(ok=True, file_removed=False, log_only=True,
                       lines_removed=lines_removed)

    base_dir, log_path = _dir_for_scope(scope)
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
    """
    收藏 = 在收藏目录的 jm_fav_log.txt 里记一行文件名，**不复制 PDF**。
    文件留在下载目录，收藏页展示时直接去那里取。
    """
    data = request.get_json(silent=True) or {}
    filename = _safe_name(data.get('file'))
    jm_id = str(data.get('id', '')).strip() or '-'
    if not filename:
        return jsonify(ok=False, error='文件名无效'), 400

    src = os.path.join(get_pdf_dir(), filename)
    if not os.path.isfile(src):
        return jsonify(ok=False, error='下载目录里没有这个文件：%s' % filename), 404

    fav_dir, fav_log = get_fav_dir(), get_fav_log()
    os.makedirs(fav_dir, exist_ok=True)

    logged = {r['file'] for r in _parse_records(_read_lines(fav_log, 'all'))}
    if filename in logged:
        return jsonify(ok=True, already=True, copy=False, message='该文件已在收藏中')

    try:
        _append_log_line(fav_log, jm_id, filename)
    except PermissionError:
        return jsonify(ok=False, error='收藏夹目录没有写入权限，收藏失败。'), 500
    except Exception as e:
        return jsonify(ok=False, error='收藏失败：%s' % e), 500

    return jsonify(ok=True, already=False, copy=False,
                   message='已收藏（仅记录文件名，不复制文件）')


@app.route('/api/wipe', methods=['POST'])
def api_wipe():
    """删除下载目录与收藏目录里的全部内容（PDF 与日志），并清空图片工作区。"""
    detail = {'pdf_files': 0, 'fav_files': 0, 'logs': 0, 'errors': []}

    for key, directory in (('pdf', get_pdf_dir()), ('fav', get_fav_dir())):
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

    if os.path.isdir(WORK_DIR):
        for name in os.listdir(WORK_DIR):
            try:
                path = os.path.join(WORK_DIR, name)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception:
                pass

    _cover_cache.clear()
    _disk_cache['data'] = None
    with _state_lock:
        _state['logs'] = []

    return jsonify(ok=True, **detail)


def main():
    _load_settings()

    # 沿用上次的版本标识与域名列表，避免每次启动重新协商
    try:
        applied_version = _apply_cached_app_version()
        if applied_version:
            print('  版本标识 : %s（沿用上次）' % applied_version)
        cached_domains = _apply_cached_domains()
        if cached_domains:
            print('  域名缓存 : %s' % ', '.join(cached_domains))
    except Exception as e:
        print('  缓存注入失败：%s' % e)

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
