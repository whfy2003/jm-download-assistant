# -*- coding: utf-8 -*-
"""
jmcore.store —— 下载记录 / 收藏记录

日志格式（与 Flask 版完全一致，保证记录文件可以互认）：

    编号 | 文件名 | 时间

* 一个本子写两行：标题行 + `.pdf` 行，两行共用同一时间戳；
* 读取时按 `(编号, 时间)` 分组后合并成一条；
* 同一文件名出现多次时只保留时间最新的一条；
* 收藏夹里「有文件但没日志」的内容会自动登记，编号记为 `-`。
"""
from __future__ import annotations

import os
import time
from datetime import datetime

import jmcore.paths as paths

RECENT_LIMIT = 500


# --------------------------------------------------------------------------- #
# 基础读写
# --------------------------------------------------------------------------- #
def read_lines(log_path: str, scope: str = 'all') -> list:
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    if scope == 'recent':
        return lines[-RECENT_LIMIT:]
    return lines


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _mtime_str(path: str) -> str:
    try:
        return datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
    except OSError:
        return ''


def append_log_line(log_path: str, jm_id: str, filename: str) -> None:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write('%s | %s | %s\n' % (jm_id, filename, _now()))


def append_record_pair(log_path: str, jm_id: str, stem: str) -> None:
    """写两行（标题行 + .pdf 行），共用同一时间戳。"""
    ts = _now()
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write('%s | %s | %s\n' % (jm_id, stem, ts))
        f.write('%s | %s.pdf | %s\n' % (jm_id, stem, ts))


def remove_log_entries(log_path: str, jm_id: str, filename: str) -> int:
    """抹去该文件对应的日志行（文件名行 + 去掉 .pdf 的标题行）。"""
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


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def parse_records(lines: list) -> list:
    """把日志行合并成记录列表（按时间倒序）。"""
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
        group = groups[key]
        pdfs = [n for n in group['names'] if n.lower().endswith('.pdf')]
        if pdfs:
            filename = pdfs[0]
            display = filename[:-4]
        else:
            display = group['names'][0]
            filename = display + '.pdf'

        record = {'id': group['id'], 'name': display,
                  'file': filename, 'time': group['time']}
        prev = by_file.get(filename)
        if prev is None or record['time'] > prev['time']:
            by_file[filename] = record

    return sorted(by_file.values(), key=lambda r: r['time'], reverse=True)


def list_pdf_names(directory: str) -> set:
    try:
        return {n for n in os.listdir(directory) if n.lower().endswith('.pdf')}
    except OSError:
        return set()


# --------------------------------------------------------------------------- #
# 记录补充信息
# --------------------------------------------------------------------------- #
def enrich(records: list, base_dir: str, fav_files: set = None) -> list:
    out = []
    for record in records:
        item = dict(record)
        item['exists'] = os.path.isfile(os.path.join(base_dir, record['file']))
        # 让 Java 侧知道这条记录的文件到底在哪个目录（收藏记录指向下载目录）
        item['dir'] = base_dir
        if fav_files is not None:
            item['fav'] = record['file'] in fav_files
        out.append(item)
    return out


def filter_by_query(records: list, q: str) -> list:
    q = (q or '').strip()
    if not q:
        return records
    return [r for r in records if q in str(r.get('id', ''))]


# --------------------------------------------------------------------------- #
# 下载记录
# --------------------------------------------------------------------------- #
def download_records(scope: str = 'all', q: str = '') -> list:
    records = parse_records(read_lines(paths.pdf_log(), scope))
    records = filter_by_query(records, q)
    return enrich(records, paths.pdf_dir(), fav_files=list_pdf_names(paths.fav_dir()))


# --------------------------------------------------------------------------- #
# 收藏记录
# --------------------------------------------------------------------------- #
def sync_fav_directory():
    """把收藏夹里「有文件但没日志」的内容纳管（编号记为 -）。

    :return: (新增条数, 警告信息)
    """
    fav_dir, fav_log = paths.fav_dir(), paths.fav_log()
    if not os.path.isdir(fav_dir):
        return 0, None

    files = list_pdf_names(fav_dir)
    logged = {r['file'] for r in parse_records(read_lines(fav_log, 'all'))}
    missing = sorted(files - logged)
    if not missing:
        return 0, None

    try:
        with open(fav_log, 'a', encoding='utf-8') as f:
            for name in missing:
                ts = _mtime_str(os.path.join(fav_dir, name)) or _now()
                f.write('- | %s | %s\n' % (name, ts))
        return len(missing), None
    except PermissionError:
        return 0, '收藏目录没有写入权限，日志暂时无法登记'
    except Exception as e:
        return 0, str(e)


def fav_records(scope: str = 'all', q: str = '') -> list:
    """
    收藏记录 = 收藏目录里那份日志 + 每条记录在**下载目录**里的实际文件。

    移动端收藏不复制 PDF（省空间），所以文件本体一直在下载目录；
    老版本留在收藏目录里的副本也兼容：优先下载目录，其次收藏目录。
    """
    fav_dir, fav_log = paths.fav_dir(), paths.fav_log()
    records = parse_records(read_lines(fav_log, scope))
    logged = {r['file'] for r in records}

    # 老版本（会复制文件）留在收藏目录里的副本，补登记进日志
    for name in sorted(list_pdf_names(fav_dir) - logged):
        records.append({
            'id': '-',
            'name': os.path.splitext(name)[0],
            'file': name,
            'time': _mtime_str(os.path.join(fav_dir, name)),
        })

    records.sort(key=lambda r: r['time'], reverse=True)
    records = filter_by_query(records, q)

    pdf_dir = paths.pdf_dir()
    out = []
    for r in records:
        item = dict(r)
        in_download = os.path.isfile(os.path.join(pdf_dir, r['file']))
        in_fav = os.path.isfile(os.path.join(fav_dir, r['file']))
        item['exists'] = in_download or in_fav
        item['fav'] = True
        item['in_download'] = in_download
        item['dir'] = pdf_dir if in_download else (fav_dir if in_fav else pdf_dir)
        out.append(item)
    return out


# --------------------------------------------------------------------------- #
# 文件操作辅助
# --------------------------------------------------------------------------- #
def safe_name(raw: str):
    """只接受纯文件名，挡住 ../ 之类的路径穿越。"""
    text = str(raw or '').strip()
    # 先挡路径分隔符：basename('../../x') 会变成 'x'，那样看着"合法"其实可疑
    if not text or text in ('.', '..') or '/' in text or '\\' in text:
        return None
    name = os.path.basename(text)
    if not name or name in ('.', '..'):
        return None
    return name


def dir_for_scope(scope: str):
    if scope == 'fav':
        return paths.fav_dir(), paths.fav_log()
    return paths.pdf_dir(), paths.pdf_log()


def delete_file(scope: str, filename: str, jm_id: str) -> dict:
    """
    删除操作：
      · scope='dl'  → 删除下载目录里的 PDF，并从下载日志抹去记录
      · scope='fav' → 只从收藏日志抹去这一条；下载目录里的文件不动
                      （收藏本来就不复制文件，取消收藏不该删掉原文件）
    """
    name = safe_name(filename)
    if not name:
        return {'ok': False, 'error': '文件名无效'}

    if scope == 'fav':
        try:
            lines_removed = remove_log_entries(paths.fav_log(), jm_id, name)
        except PermissionError:
            return {'ok': False, 'error': '收藏日志不可写，取消收藏失败'}
        return {'ok': True, 'file_removed': False, 'log_only': True,
                'lines_removed': lines_removed}

    base_dir, log_path = dir_for_scope(scope)
    path = os.path.join(base_dir, name)

    file_removed = False
    if os.path.isfile(path):
        try:
            os.remove(path)
            file_removed = True
        except PermissionError:
            return {'ok': False, 'error': '没有删除权限，删除失败。'}
        except Exception as e:
            return {'ok': False, 'error': '删除文件失败：%s' % e}

    try:
        lines_removed = remove_log_entries(log_path, jm_id, name)
    except PermissionError:
        return {'ok': False, 'error': '文件已删除，但日志不可写，记录未能抹去'}

    return {'ok': True, 'file_removed': file_removed, 'lines_removed': lines_removed}


def add_favorite(filename: str, jm_id: str) -> dict:
    """
    收藏 = 在收藏目录的 jm_fav_log.txt 里记一行文件名，**不复制 PDF**。

    移动端存储紧张，复制一份会翻倍占用；收藏页展示时直接去下载目录取文件。
    """
    name = safe_name(filename)
    if not name:
        return {'ok': False, 'error': '文件名无效'}

    if not os.path.isfile(os.path.join(paths.pdf_dir(), name)):
        return {'ok': False, 'error': '下载目录里没有这个文件：%s' % name}

    fav_log = paths.fav_log()
    os.makedirs(paths.fav_dir(), exist_ok=True)

    logged = {r['file'] for r in parse_records(read_lines(fav_log, 'all'))}
    if name in logged:
        return {'ok': True, 'already': True, 'copy': False,
                'message': '该文件已在收藏中'}

    try:
        append_log_line(fav_log, jm_id or '-', name)
    except PermissionError:
        return {'ok': False, 'error': '收藏目录没有写入权限，收藏失败。'}
    except Exception as e:
        return {'ok': False, 'error': '收藏失败：%s' % e}

    return {'ok': True, 'already': False, 'copy': False,
            'message': '已收藏（仅记录，不复制文件）'}


# --------------------------------------------------------------------------- #
# 下载完成后登记
# --------------------------------------------------------------------------- #
def snapshot_pdfs() -> set:
    return list_pdf_names(paths.pdf_dir())


def newest_pdf_stem(before: set):
    """下载前后对比，找出新生成的 PDF（决定记录里的标题）。"""
    pdf_dir = paths.pdf_dir()
    added = list_pdf_names(pdf_dir) - before
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


def cleanup_empty_dirs(root: str) -> None:
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


def now() -> str:
    """给上层用的当前时间戳。"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
