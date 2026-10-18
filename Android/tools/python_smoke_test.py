# -*- coding: utf-8 -*-
"""
桌面端冒烟测试：不依赖 Android，直接验证 jmcore 的业务逻辑。

用法（在工程根目录）：

    python tools/python_smoke_test.py

覆盖：
  1. 记录账本：两行合并、按文件名去重、时间倒序
  2. 收藏：复制 + 写日志
  3. 收藏夹自愈纳管（编号 -）
  4. 删除：删文件 + 抹日志（一行/两行）
  5. 目录迁移：移动、同名跳过、拒绝互相包含
  6. 路径穿越防护
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY_DIR = os.path.join(ROOT, 'app', 'src', 'main', 'python')
sys.path.insert(0, PY_DIR)

import jmcore.api as api  # noqa: E402

PASS, FAIL = 0, 0


def check(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print('  PASS  %s' % name)
    else:
        FAIL += 1
        print('  FAIL  %s  %s' % (name, detail))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def main():
    # 目录可以预先建好（某些受限环境不允许脚本自己建目录）
    home = os.environ.get('JMCORE_HOME') or os.path.join(ROOT, '.smoke-test', 'run')
    pdf_dir = os.path.join(home, 'pdf')
    fav_dir = os.path.join(home, 'fav')
    work_dir = os.path.join(home, 'work')
    new_pdf = os.path.join(home, 'pdf2')
    new_fav = os.path.join(home, 'fav2')
    col_a = os.path.join(home, 'col-a')
    col_b = os.path.join(home, 'col-b')
    for path in (pdf_dir, fav_dir, work_dir, new_pdf, new_fav, col_a, col_b):
        os.makedirs(path, exist_ok=True)

    # 清理上次残留（只删已知目录里的文件）
    for folder in (pdf_dir, fav_dir, new_pdf, new_fav, col_a, col_b):
        for name in os.listdir(folder):
            try:
                os.remove(os.path.join(folder, name))
            except OSError:
                pass
    try:
        os.remove(os.path.join(home, 'settings.json'))
    except OSError:
        pass

    print('测试目录：%s' % home)
    try:
        res = json.loads(api.init(home, pdf_dir, fav_dir, work_dir))
        check('init 成功', res.get('ok') is True, res)
        if not res.get('ok'):
            return 1

        # 1) 记录合并 ------------------------------------------------------ #
        write(os.path.join(pdf_dir, 'jm_log.txt'), (
            '350234 | 董卓 上+下 | 2026-10-13 22:41:46\n'
            '350234 | 董卓 上+下.pdf | 2026-10-13 22:41:46\n'
            '350235 | 标题二 | 2026-10-14 10:00:00\n'
            '350235 | 标题二.pdf | 2026-10-14 10:00:00\n'
            '350234 | 董卓 上+下.pdf | 2026-10-15 09:00:00\n'
            'badline\n'
        ))
        records = json.loads(api.records('all', ''))['records']
        check('合并后 2 条', len(records) == 2, records)
        check('按时间倒序', records[0]['file'] == '董卓 上+下.pdf', records[0])
        check('重复文件取最新时间', records[0]['time'] == '2026-10-15 09:00:00', records[0])
        check('显示名去掉 .pdf', records[0]['name'] == '董卓 上+下', records[0])
        check('文件不存在标记', records[0]['exists'] is False, records[0])

        # 搜索
        found = json.loads(api.records('all', '350235'))['records']
        check('按编号搜索', len(found) == 1 and found[0]['id'] == '350235', found)

        # 2) 收藏 ---------------------------------------------------------- #
        write(os.path.join(pdf_dir, '董卓 上+下.pdf'), 'PDF')
        fav = json.loads(api.favorite('董卓 上+下.pdf', '350234'))
        check('收藏成功', fav.get('ok') is True, fav)
        check('收藏文件已复制',
              os.path.isfile(os.path.join(fav_dir, '董卓 上+下.pdf')))
        again = json.loads(api.favorite('董卓 上+下.pdf', '350234'))
        check('重复收藏提示已存在', again.get('already') is True, again)

        # 3) 收藏夹自愈 ---------------------------------------------------- #
        write(os.path.join(fav_dir, '未登记.pdf'), 'PDF')
        favs = json.loads(api.favorites('all', ''))
        check('自动纳管 2 条', len(favs['records']) == 2, favs['records'])
        check('纳管编号为 -',
              any(r['id'] == '-' and r['file'] == '未登记.pdf' for r in favs['records']),
              favs['records'])

        # 4) 删除 ---------------------------------------------------------- #
        removed = json.loads(api.delete('未登记.pdf', '-', 'fav'))
        check('删除收藏文件', removed.get('file_removed') is True, removed)
        check('抹掉 1 行日志', removed.get('lines_removed') == 1, removed)

        removed = json.loads(api.delete('董卓 上+下.pdf', '350234', 'dl'))
        check('删除下载文件', removed.get('file_removed') is True, removed)
        # 日志里该文件有 3 行（标题行 + 两条 .pdf 行，其中一条是后来的重复记录）
        check('抹掉全部同名日志行', removed.get('lines_removed') == 3, removed)

        # 5) 目录迁移 ------------------------------------------------------ #
        # 清空收藏目录，保证迁移结果确定
        for name in os.listdir(fav_dir):
            os.remove(os.path.join(fav_dir, name))
        write(os.path.join(fav_dir, 'a.pdf'), 'A')
        write(os.path.join(fav_dir, 'b.pdf'), 'B')

        moved = json.loads(api.update_settings(new_pdf, new_fav))
        check('迁移成功', moved.get('ok') is True, moved)
        check('收藏目录移动 2 项', moved['moves']['fav']['moved'] == 2, moved.get('moves'))
        check('旧目录已删除', not os.path.isdir(fav_dir), moved.get('moves'))

        # 同名不覆盖（用 paths.relocate 做单元级验证）
        import jmcore.paths as paths
        src = os.path.join(home, 'col-a')
        dst = os.path.join(home, 'col-b')
        write(os.path.join(src, 'x.pdf'), 'NEW')
        write(os.path.join(dst, 'x.pdf'), 'OLD')
        result = paths.relocate(src, dst)
        check('同名不覆盖', open(os.path.join(dst, 'x.pdf'), encoding='utf-8').read() == 'OLD',
              result)
        check('同名项记为跳过', result.get('skipped') == 1, result)

        # 互相包含
        nested = paths.relocate(new_pdf, os.path.join(new_pdf, 'sub'))
        check('拒绝互相包含', nested.get('fatal') is True, nested)

        # 6) 路径穿越 ------------------------------------------------------ #
        bad = json.loads(api.delete('../../evil.pdf', '1', 'dl'))
        check('路径穿越被拒', bad.get('ok') is False, bad)

        # 7) 设置持久化 ---------------------------------------------------- #
        settings = json.loads(api.settings())
        check('设置已落盘',
              settings['dirs']['pdf_dir'] == os.path.abspath(new_pdf), settings['dirs'])
        check('settings.json 存在',
              os.path.isfile(os.path.join(home, 'settings.json')))

        # 8) 响应对象兼容 curl_cffi --------------------------------------- #
        # 回归：上游 raise_if_resp_should_retry() 会读 resp.request.url，
        # 少这个属性就会 AttributeError: 'AndroidResponse' object has no attribute 'request'
        from jmcore import net

        class _FakeBackend:
            def available(self):
                return True

            def fetch(self, *args):
                return net.AndroidResponse(
                    200, 'http://example.com/x',
                    {'Set-Cookie': 'AVS=abc123; Path=/; HttpOnly\nfoo=bar; Path=/'},
                    b'{"code":200}')

        original_backends = net._BACKENDS
        net._BACKENDS = [_FakeBackend()]
        try:
            resp = net.request('GET', 'http://example.com/chapter_view_template?id=1')
            check('响应带 request.url',
                  resp.request is not None
                  and 'chapter_view_template' in resp.request.url, resp.request)
            check('响应 ok 标记', resp.ok is True, resp.ok)
            check('响应可解析 json', resp.json().get('code') == 200, resp.text)
            check('解析多条 Set-Cookie',
                  resp.cookies.get('AVS') == 'abc123' and resp.cookies.get('foo') == 'bar',
                  resp.cookies)
        finally:
            net._BACKENDS = original_backends

        # 9) 代理解析（含用户名/密码） ------------------------------------- #
        # 写法一：凭据放在 URL 里
        json.loads(api.update_runtime(8, 2, '', 'http://bob:pw@10.0.0.2:8080', '', ''))
        cfg = net._proxy_config()
        check('解析代理主机/端口',
              cfg is not None and cfg['host'] == '10.0.0.2' and cfg['port'] == 8080, cfg)
        check('解析 URL 内凭据',
              cfg is not None and cfg['user'] == 'bob' and cfg['password'] == 'pw', cfg)

        # 写法二：主机端口 + 单独的账号密码
        json.loads(api.update_runtime(8, 2, '', '127.0.0.1:7890', 'alice', 'secret'))
        cfg = net._proxy_config()
        check('独立用户名/密码',
              cfg is not None and cfg['host'] == '127.0.0.1'
              and cfg['port'] == 7890 and cfg['user'] == 'alice'
              and cfg['password'] == 'secret', cfg)

        # 留空 = 直连
        json.loads(api.update_runtime(8, 2, '', '', '', ''))
        check('清空代理后为直连', net._proxy_config() is None, net._proxy_config())

        # 10) 下载进度计数器 ------------------------------------------------ #
        from jmcore import progress as progress_mod

        counter = progress_mod.instance()
        counter.start(10)
        counter.add_image(1024)
        counter.add_image(2048)
        counter.finish()
        snap = counter.snapshot()
        check('进度：页数与百分比',
              snap['done'] == 2 and snap['total'] == 10 and snap['percent'] == 20, snap)
        check('进度：累计字节', snap['bytes'] == 3072, snap)
        check('进度：结束后 active=false', snap['active'] is False, snap)

    finally:
        shutil.rmtree(home, ignore_errors=True)

    print('\n结果：%d 通过，%d 失败' % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
