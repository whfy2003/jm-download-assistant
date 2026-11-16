# -*- coding: utf-8 -*-
"""
源码版启动器（无窗口）

双击后用同目录的 .venv 在后台启动 webui/app.py：

  · 不弹任何控制台窗口，服务输出写进 logs/server.log
  · 服务已经在跑就只打开浏览器，不重复启动
  · 启动起来后自动打开浏览器，然后就退出
  · 想停止就运行同目录的 stop-jm-web.cmd（按 8080 端口结束进程）

打包（无窗口）：
  pyinstaller --noconfirm --onefile --windowed --name "启动源码版" ^
    --icon "E:\\JM web\\jm.ico" --distpath "E:\\JM web" ^
    --workpath "E:\\JM web\\_build\\launcher" --specpath "E:\\JM web\\_build" ^
    "E:\\JM web\\launch_source.py"
"""
import os
import subprocess
import sys
import time
import webbrowser

PORT = 8080
CREATE_NO_WINDOW = 0x08000000      # Windows: 子进程别开控制台


def app_root():
    """exe 所在目录；源码直接运行时是脚本所在目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


ROOT = app_root()
PYTHON = os.path.join(ROOT, '.venv', 'Scripts', 'python.exe')
APP = os.path.join(ROOT, 'webui', 'app.py')
LOG = os.path.join(ROOT, 'logs', 'server.log')


def notify(text):
    """没控制台就弹窗，有控制台就打印。"""
    if getattr(sys, 'frozen', False):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, 'JM 下载助手', 0x40)
            return
        except Exception:
            pass
    try:
        print(text)
    except Exception:
        pass


def port_busy():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', PORT)) == 0


def main():
    if not os.path.isfile(PYTHON):
        notify('找不到虚拟环境：\n%s\n\n.venv 可能被移动或删除了，请重新部署。' % PYTHON)
        return 1

    if not os.path.isfile(APP):
        notify('找不到程序入口：\n%s' % APP)
        return 1

    if port_busy():
        webbrowser.open('http://127.0.0.1:%d' % PORT)
        return 0

    log_handle = None
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        log_handle = open(LOG, 'w', encoding='utf-8', errors='replace')
    except Exception:
        log_handle = None

    env = dict(os.environ)
    env.setdefault('PYTHONIOENCODING', 'utf-8')
    env.setdefault('PYTHONUTF8', '1')

    flags = CREATE_NO_WINDOW if os.name == 'nt' else 0

    try:
        subprocess.Popen(
            [PYTHON, '-X', 'utf8', APP],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            close_fds=True,
        )
    except Exception as e:
        notify('启动失败：\n%s' % e)
        return 1

    # 等端口真正起来再开浏览器，最多等 15 秒
    started = False
    for _ in range(60):
        time.sleep(0.25)
        if port_busy():
            started = True
            break

    if not started:
        notify('服务启动超时，详情看日志：\n%s' % LOG)
        return 1

    webbrowser.open('http://127.0.0.1:%d' % PORT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
