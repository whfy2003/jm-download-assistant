# -*- coding: utf-8 -*-
"""
jmcore.paths —— 目录与设置

与原 Flask 版（webui/app.py）的语义保持一致：

* 下载目录、收藏目录可在设置里修改；
* 修改时把旧目录里的内容整体迁移到新目录（同名不覆盖、旧目录空后删除、
  拒绝互相包含的目录）；
* 磁盘占用按「本目录占用 / 同盘其它占用 / 可用」三段统计。

Android 差异：
* 路径全部来自应用私有外部存储（Context.getExternalFilesDir），由 Java 层传入；
* settings.json 存在应用私有目录里，卸载即清理。
"""
from __future__ import annotations

import json
import os
import shutil

SETTINGS_FILE_NAME = 'settings.json'

# 全局状态（由 init() 填充）
_S = {
    'ready': False,
    'home': None,        # 应用数据根目录（Java: getExternalFilesDir("JM")）
    'settings_file': None,
    'pdf_dir': None,     # 下载目录（成品 PDF）
    'fav_dir': None,     # 收藏目录
    'work_dir': None,    # 图片工作区（合并 PDF 后清空）
    'image_threads': 16, # 图片并发数（设置页可调）
    'photo_threads': 4,  # 章节并发数
    'cookies': None,     # AVS cookie（可选）
    'proxy': None,       # 代理，如 127.0.0.1:7890
    'proxy_user': None,  # 代理认证用户名（可选）
    'proxy_pass': None,  # 代理认证密码（可选）
    'proxy_only': None,  # 只对这些域名走代理（每行一个，留空=全部）
    'proxy_type': 'auto',  # auto / http / socks（OpenClash 的 mixed 端口两种都支持）
}


# --------------------------------------------------------------------------- #
# 初始化
# --------------------------------------------------------------------------- #
def init(home: str,
         pdf_dir: str = None,
         fav_dir: str = None,
         work_dir: str = None) -> dict:
    """由 Java 层在启动时调用一次。home 必须是可写的应用私有目录。"""
    home = os.path.abspath(home)
    os.makedirs(home, exist_ok=True)

    _S['home'] = home
    _S['settings_file'] = os.path.join(home, SETTINGS_FILE_NAME)
    _S['pdf_dir'] = os.path.abspath(pdf_dir or os.path.join(home, '漫画'))
    _S['fav_dir'] = os.path.abspath(fav_dir or os.path.join(home, '收藏'))
    _S['work_dir'] = os.path.abspath(work_dir or os.path.join(home, 'work'))

    _load()
    ensure_dirs()
    _S['ready'] = True
    return snapshot()


def is_ready() -> bool:
    return bool(_S['ready'])


def _require_ready():
    if not _S['ready']:
        raise RuntimeError('jmcore 尚未初始化（请先调用 init）')


def ensure_dirs():
    for key in ('home', 'pdf_dir', 'fav_dir', 'work_dir'):
        path = _S.get(key)
        if path:
            os.makedirs(path, exist_ok=True)


# --------------------------------------------------------------------------- #
# 设置持久化
# --------------------------------------------------------------------------- #
def _load():
    path = _S['settings_file']
    if not os.path.exists(path):
        save()
        return
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return

    if isinstance(data.get('pdf_dir'), str) and data['pdf_dir'].strip():
        _S['pdf_dir'] = os.path.abspath(data['pdf_dir'].strip())
    if isinstance(data.get('fav_dir'), str) and data['fav_dir'].strip():
        _S['fav_dir'] = os.path.abspath(data['fav_dir'].strip())

    for key in ('image_threads', 'photo_threads'):
        try:
            value = int(data.get(key))
            if 1 <= value <= 64:
                _S[key] = value
        except (TypeError, ValueError):
            pass

    if isinstance(data.get('cookies'), str) and data['cookies'].strip():
        _S['cookies'] = data['cookies'].strip()
    if isinstance(data.get('proxy'), str) and data['proxy'].strip():
        _S['proxy'] = data['proxy'].strip()
    if isinstance(data.get('proxy_user'), str) and data['proxy_user'].strip():
        _S['proxy_user'] = data['proxy_user'].strip()
    if isinstance(data.get('proxy_pass'), str) and data['proxy_pass']:
        _S['proxy_pass'] = data['proxy_pass']
    if isinstance(data.get('proxy_only'), str) and data['proxy_only'].strip():
        _S['proxy_only'] = data['proxy_only'].strip()
    if isinstance(data.get('proxy_type'), str) and data['proxy_type'] in ('auto', 'http', 'socks'):
        _S['proxy_type'] = data['proxy_type']


def save():
    path = _S['settings_file']
    if not path:
        return
    data = {
        'pdf_dir': _S['pdf_dir'],
        'fav_dir': _S['fav_dir'],
        'image_threads': _S['image_threads'],
        'photo_threads': _S['photo_threads'],
        'cookies': _S['cookies'],
        'proxy': _S['proxy'],
        'proxy_user': _S['proxy_user'],
        'proxy_pass': _S['proxy_pass'],
        'proxy_only': _S['proxy_only'],
        'proxy_type': _S['proxy_type'],
    }
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass


def snapshot() -> dict:
    return {
        'home': _S['home'],
        'pdf_dir': _S['pdf_dir'],
        'fav_dir': _S['fav_dir'],
        'work_dir': _S['work_dir'],
        'image_threads': _S['image_threads'],
        'photo_threads': _S['photo_threads'],
        'has_cookies': bool(_S['cookies']),
        'proxy': _S['proxy'] or '',
        'proxy_user': _S['proxy_user'] or '',
        'has_proxy_password': bool(_S['proxy_pass']),
        'proxy_only': _S['proxy_only'] or '',
        'proxy_type': _S['proxy_type'] or 'auto',
    }


# --------------------------------------------------------------------------- #
# 取值
# --------------------------------------------------------------------------- #
def pdf_dir() -> str:
    return _S['pdf_dir']


def fav_dir() -> str:
    return _S['fav_dir']


def work_dir() -> str:
    return _S['work_dir']


def pdf_log() -> str:
    return os.path.join(pdf_dir(), 'jm_log.txt')


def fav_log() -> str:
    return os.path.join(fav_dir(), 'jm_fav_log.txt')


def image_threads() -> int:
    return int(_S['image_threads'])


def photo_threads() -> int:
    return int(_S['photo_threads'])


def cookies() -> str:
    return _S['cookies']


def proxy() -> str:
    return _S['proxy']


def proxy_credentials():
    """返回 (用户名, 密码) 或 (None, None)。"""
    return _S['proxy_user'] or None, _S['proxy_pass'] or None


def proxy_only() -> str:
    """代理白名单（每行一个域名/后缀）；空表示所有请求都走代理。"""
    return _S['proxy_only'] or ''


def proxy_type() -> str:
    """代理协议：auto / http / socks。"""
    return _S['proxy_type'] or 'auto'


def set_runtime(**kwargs):
    """设置并发数 / cookies / proxy（会自动落盘）。

    proxy_user / proxy_pass 的约定：
      * 传 None 表示「不修改」；
      * 传空字符串表示「清除」。
    """
    for key in ('image_threads', 'photo_threads'):
        if key in kwargs:
            try:
                value = int(kwargs[key])
            except (TypeError, ValueError):
                continue
            _S[key] = max(1, min(64, value))
    for key in ('cookies', 'proxy'):
        if key in kwargs:
            value = kwargs[key]
            _S[key] = (value or '').strip() or None

    if kwargs.get('proxy_user') is not None:
        _S['proxy_user'] = (kwargs['proxy_user'] or '').strip() or None
        # 用户名清空时，密码也一起清掉，避免留下无主的凭据
        if _S['proxy_user'] is None:
            _S['proxy_pass'] = None

    if kwargs.get('proxy_pass') is not None and (kwargs['proxy_pass'] or '') != '':
        _S['proxy_pass'] = kwargs['proxy_pass']

    if kwargs.get('proxy_only') is not None:
        _S['proxy_only'] = (kwargs['proxy_only'] or '').strip() or None
    if kwargs.get('proxy_type') in ('auto', 'http', 'socks'):
        _S['proxy_type'] = kwargs['proxy_type']

    save()
    return snapshot()


# --------------------------------------------------------------------------- #
# 目录迁移
# --------------------------------------------------------------------------- #
def relocate(old_dir: str, new_dir: str) -> dict:
    """把 old_dir 下的内容移动到 new_dir。

    规则与原项目一致：
      * 同名目标已存在则跳过，不覆盖；
      * 旧目录空了以后删除；
      * 新旧目录互相包含时直接拒绝，避免自我递归。
    """
    old_dir = os.path.abspath(old_dir)
    new_dir = os.path.abspath(new_dir)

    if old_dir == new_dir:
        return {'moved': 0, 'skipped': 0, 'errors': [], 'same': True}

    if new_dir.startswith(old_dir + os.sep) or old_dir.startswith(new_dir + os.sep):
        return {'moved': 0, 'skipped': 0,
                'errors': ['新旧目录不能互相包含'], 'fatal': True}

    try:
        os.makedirs(new_dir, exist_ok=True)
    except Exception as e:
        return {'moved': 0, 'skipped': 0,
                'errors': ['无法创建新目录：%s' % e], 'fatal': True}

    if not os.path.isdir(old_dir):
        return {'moved': 0, 'skipped': 0, 'errors': [],
                'note': '旧目录不存在，已直接切换'}

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


def set_dirs(new_pdf: str, new_fav: str) -> dict:
    """设置页保存入口：迁移 + 落盘。返回 {ok, moves, error?}。"""
    _require_ready()
    new_pdf = (new_pdf or '').strip().rstrip('/\\')
    new_fav = (new_fav or '').strip().rstrip('/\\')

    moves = {}
    if new_pdf and os.path.abspath(new_pdf) != os.path.abspath(pdf_dir()):
        if not os.path.isabs(new_pdf):
            return {'ok': False, 'error': '下载目录必须是绝对路径'}
        result = relocate(pdf_dir(), new_pdf)
        if result.get('fatal'):
            return {'ok': False, 'error': '下载目录迁移失败：%s' % '；'.join(result['errors'])}
        _S['pdf_dir'] = os.path.abspath(new_pdf)
        moves['pdf'] = result

    if new_fav and os.path.abspath(new_fav) != os.path.abspath(fav_dir()):
        if not os.path.isabs(new_fav):
            return {'ok': False, 'error': '收藏目录必须是绝对路径'}
        result = relocate(fav_dir(), new_fav)
        if result.get('fatal'):
            return {'ok': False, 'error': '收藏目录迁移失败：%s' % '；'.join(result['errors'])}
        _S['fav_dir'] = os.path.abspath(new_fav)
        moves['fav'] = result

    save()
    ensure_dirs()
    return {'ok': True, 'moves': moves, 'dirs': snapshot()}


# --------------------------------------------------------------------------- #
# 磁盘占用
# --------------------------------------------------------------------------- #
def dir_size(path: str) -> int:
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


def _statvfs(path: str) -> dict:
    probe = path
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        st = os.statvfs(probe or '/')
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        return {'total': total, 'free': free, 'used': max(0, total - free)}
    except Exception as e:
        return {'total': 0, 'free': 0, 'used': 0, 'error': str(e)}


def disk_info(path: str) -> dict:
    exists = os.path.isdir(path)
    info = {'path': path, 'exists': exists, 'dir_size': 0,
            'total': 0, 'used': 0, 'free': 0, 'other_used': 0,
            'drive': os.path.basename(os.path.dirname(path.rstrip('/'))) or '/'}
    info.update({k: v for k, v in _statvfs(path).items() if k in ('total', 'used', 'free')})
    info['dir_size'] = dir_size(path) if exists else 0
    info['other_used'] = max(0, info['used'] - info['dir_size'])
    return info


def disk_snapshot() -> dict:
    return {'pdf': disk_info(pdf_dir()), 'fav': disk_info(fav_dir())}


def is_writable(path: str) -> bool:
    probe = os.path.join(path, '.jm_write_probe')
    try:
        os.makedirs(path, exist_ok=True)
        with open(probe, 'w', encoding='utf-8') as f:
            f.write('x')
        os.remove(probe)
        return True
    except OSError:
        return False
