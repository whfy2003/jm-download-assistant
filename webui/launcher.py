# -*- coding: utf-8 -*-
"""
JM 下载助手 —— 桌面启动器（打包成 exe 后由用户双击）

流程：
  1. 若同目录没有 settings.json（第一次使用），弹出设置向导：
     选择「下载目录」和「收藏夹目录」，可勾选创建桌面快捷方式
  2. 启动本地网页服务，并自动打开浏览器

程序目录（exe 所在目录）会保存：settings.json、option.yml、downloads\\ 工作区
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

APP_NAME = 'JM 下载助手'
PORT = 8080
IS_FROZEN = getattr(sys, 'frozen', False)


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
def app_dir():
    """可写目录：打包后是 exe 所在目录，源码运行时是项目根目录。"""
    if IS_FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))       # webui
    return os.path.dirname(here)                            # 项目根


def res_dir():
    """资源目录：打包后是解包目录，源码运行时是 webui 目录。"""
    if IS_FROZEN:
        return os.path.join(getattr(sys, '_MEIPASS', app_dir()), 'webui')
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = app_dir()
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
DEFAULT_DOWNLOAD = os.path.join(APP_DIR, '漫画')
DEFAULT_FAVORITE = os.path.join(APP_DIR, '收藏')


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return None
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('pdf_dir') and data.get('fav_dir'):
            return data
    except Exception:
        pass
    return None


def save_settings(pdf_dir, fav_dir):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'pdf_dir': pdf_dir, 'fav_dir': fav_dir}, f,
                  ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 桌面快捷方式
# ---------------------------------------------------------------------------
def create_shortcut():
    exe = sys.executable if IS_FROZEN else os.path.join(res_dir(), 'launcher.py')
    ps = (
        "$desktop = [Environment]::GetFolderPath('Desktop');"
        "$ws = New-Object -ComObject WScript.Shell;"
        "$lnk = $ws.CreateShortcut((Join-Path $desktop '{name}.lnk'));"
        "$lnk.TargetPath = '{exe}';"
        "$lnk.WorkingDirectory = '{wd}';"
        "$lnk.Description = '{name}';"
        "$lnk.Save()"
    ).format(name=APP_NAME, exe=exe.replace("'", "''"), wd=APP_DIR.replace("'", "''"))

    try:
        subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
            creationflags=0x08000000, timeout=40, check=False)
        return True
    except Exception as e:
        print('创建快捷方式失败：%s' % e)
        return False


# ---------------------------------------------------------------------------
# 卸载
# ---------------------------------------------------------------------------
UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\JM下载助手'


def desktop_dir():
    try:
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command', "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=25,
            creationflags=0x08000000).stdout.strip()
        if out and os.path.isdir(out):
            return out
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Desktop')


def remove_path(path, retries=4):
    """删除文件或目录；Windows 上可能被短暂占用，重试几次。"""
    if not os.path.exists(path):
        return True
    last = None
    for i in range(retries):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return True
        except Exception as e:
            last = e
            time.sleep(0.5)
    print('  ! 删除失败：%s（%s）' % (path, last))
    return False


def remove_shortcut():
    return remove_path(os.path.join(desktop_dir(), APP_NAME + '.lnk'))


def remove_registry_entry():
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def do_uninstall(purge_data, log=None):
    """
    执行卸载：快捷方式 → 注册表 →(可选)数据目录 → 程序文件 → 自删。

    要点：下载目录 / 收藏夹目录如果位于安装目录内部（这是默认布局），
    只要用户没勾选「同时删除数据」，就完整保留，绝不连带删除。
    """
    log = log or (lambda t: print(t))
    cfg = load_settings() or {}
    target = APP_DIR

    keep = set()
    for key in ('pdf_dir', 'fav_dir'):
        d = cfg.get(key)
        if d:
            keep.add(os.path.abspath(d).lower())

    log('正在删除桌面快捷方式…')
    remove_shortcut()

    log('正在清理系统卸载信息…')
    remove_registry_entry()

    if purge_data:
        for key, label in (('pdf_dir', '下载目录'), ('fav_dir', '收藏夹目录')):
            d = cfg.get(key)
            if d and os.path.isdir(d):
                log('正在删除%s：%s' % (label, d))
                remove_path(d)
        keep.clear()

    log('正在删除程序文件…')
    self_path = os.path.abspath(sys.executable).lower() if IS_FROZEN else None
    for name in os.listdir(target):
        p = os.path.join(target, name)
        ap = os.path.abspath(p).lower()
        if ap in keep:
            log('保留数据目录：%s' % p)
            continue
        if self_path and ap == self_path:
            continue
        remove_path(p)

    log('正在收尾…')
    exe = os.path.abspath(sys.executable) if IS_FROZEN else ''
    if exe:
        # 运行中的进程锁着自己的 _internal，只能等退出后再删；
        # 最后一步 rmdir 不带 /s：目录里若还有数据目录就不会被删掉。
        subprocess.Popen(
            'cmd /c ping 127.0.0.1 -n 4 >nul'
            ' & rmdir /s /q "%s\\_internal" >nul 2>&1'
            ' & del /f /q "%s" >nul 2>&1'
            ' & rmdir "%s" 2>nul' % (target, exe, target),
            shell=True, creationflags=0x08000000)
    return True


def run_uninstaller():
    """卸载入口。带界面时由用户勾选是否一并删除数据。"""
    import tkinter as tk
    from tkinter import messagebox

    cfg = load_settings() or {}
    pdf_dir = cfg.get('pdf_dir') or ''
    fav_dir = cfg.get('fav_dir') or ''

    brand = '#5b5bd6'
    root = tk.Tk()
    root.title(APP_NAME + ' · 卸载')
    root.configure(bg='#ffffff')
    root.resizable(False, False)
    w = 660
    root.geometry('660x1')

    tk.Label(root, text='卸载 ' + APP_NAME, font=('Microsoft YaHei', 17, 'bold'),
             bg='#ffffff', fg='#1a1c23').pack(pady=(24, 6))
    tk.Label(root, text='将要删除程序目录：', font=('Microsoft YaHei', 10),
             bg='#ffffff', fg='#5b6070').pack()
    tk.Label(root, text=APP_DIR, font=('Consolas', 10), bg='#ffffff', fg='#3a4653',
             wraplength=580).pack(pady=(2, 16))

    box = tk.Frame(root, bg='#fff8ec', highlightbackground='#f3d9a8', highlightthickness=1)
    box.pack(fill='x', padx=30)
    purge_var = tk.BooleanVar(value=False)
    tk.Checkbutton(box, text='同时删除下载目录与收藏夹里的漫画和日志', variable=purge_var,
                   font=('Microsoft YaHei', 10, 'bold'), bg='#fff8ec', fg='#7a5a17',
                   activebackground='#fff8ec', selectcolor='#fff8ec',
                   anchor='w').pack(fill='x', padx=12, pady=(10, 2))
    tk.Label(box, text='下载目录：%s\n收藏夹目录：%s' % (pdf_dir or '（未设置）', fav_dir or '（未设置）'),
             font=('Microsoft YaHei', 9), bg='#fff8ec', fg='#9a7b33', justify='left',
             anchor='w', wraplength=560).pack(fill='x', padx=34, pady=(0, 10))
    tk.Label(root, text='不勾选 = 只删程序，漫画与记录全部保留，重装后还能接着用。',
             font=('Microsoft YaHei', 9), bg='#ffffff', fg='#9aa0ae').pack(pady=(8, 0))

    status = tk.Label(root, text='', font=('Microsoft YaHei', 9), bg='#ffffff', fg='#5b6070')
    status.pack(pady=(8, 0))

    def do_it():
        btn.config(state='disabled')
        cancel_btn.config(state='disabled')
        root.update_idletasks()

        def log(text):
            status.config(text=text)
            root.update_idletasks()

        try:
            do_uninstall(bool(purge_var.get()), log)
        except Exception as e:
            messagebox.showerror(APP_NAME, '卸载时出错：\n%s' % e)
            return
        messagebox.showinfo(APP_NAME, '已卸载完成。\n\n程序目录会在几秒后自动清空。')
        root.destroy()

    btns = tk.Frame(root, bg='#ffffff')
    btns.pack(pady=(16, 20))
    btn = tk.Button(btns, text='开始卸载', font=('Microsoft YaHei', 11, 'bold'),
                    bg='#e5484d', fg='#ffffff', relief='flat', padx=30, pady=8,
                    activebackground='#c93a3f', activeforeground='#ffffff', command=do_it)
    btn.pack(side='left', padx=8)
    cancel_btn = tk.Button(btns, text='取消', font=('Microsoft YaHei', 10),
                           bg='#eef1f6', fg='#3a4653', relief='flat', padx=24, pady=8,
                           activebackground='#e2e8f1', command=root.destroy)
    cancel_btn.pack(side='left', padx=8)

    root.update_idletasks()
    win_h = max(430, root.winfo_reqheight() + 8)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry('%dx%d+%d+%d' % (w, win_h, (sw - w) // 2, max(20, (sh - win_h) // 3)))
    root.mainloop()


# ---------------------------------------------------------------------------
# 首次运行向导
# ---------------------------------------------------------------------------
def run_wizard():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    brand = '#5b5bd6'
    result = {'ok': False, 'pdf': DEFAULT_DOWNLOAD, 'fav': DEFAULT_FAVORITE, 'shortcut': True}

    root = tk.Tk()
    root.title(APP_NAME + ' · 首次设置')
    root.configure(bg='#ffffff')
    root.resizable(False, False)

    w = 680
    root.geometry('680x1')      # 先定宽度，高度等控件放完后按内容自适应

    tk.Label(root, text=APP_NAME, font=('Microsoft YaHei', 18, 'bold'),
             bg='#ffffff', fg='#1a1c23').pack(pady=(22, 4))
    tk.Label(root, text='第一次使用，请先选好两个文件夹；以后也能在网页里的「设置」页随时修改。',
             font=('Microsoft YaHei', 10), bg='#ffffff', fg='#5b6070').pack(pady=(0, 18))

    body = tk.Frame(root, bg='#ffffff')
    body.pack(fill='x', padx=30)

    def add_row(row, label, hint, initial, browse_title):
        tk.Label(body, text=label, font=('Microsoft YaHei', 10, 'bold'),
                 bg='#ffffff', fg='#1a1c23', anchor='w').grid(row=row * 3, column=0, sticky='w')
        tk.Label(body, text=hint, font=('Microsoft YaHei', 9),
                 bg='#ffffff', fg='#9aa0ae', anchor='w').grid(row=row * 3 + 1, column=0, sticky='w', pady=(2, 0))

        var = tk.StringVar(value=initial)
        line = tk.Frame(body, bg='#ffffff')
        line.grid(row=row * 3 + 2, column=0, sticky='ew', pady=(6, 16))

        entry = tk.Entry(line, textvariable=var, font=('Microsoft YaHei', 10),
                         relief='solid', bd=1)
        entry.pack(side='left', fill='x', expand=True, ipady=6)

        def browse():
            chosen = filedialog.askdirectory(title=browse_title, initialdir=var.get() or APP_DIR)
            if chosen:
                var.set(os.path.normpath(chosen))

        tk.Button(line, text='浏览…', font=('Microsoft YaHei', 9), command=browse,
                  bg='#eef1f6', fg='#3a4653', relief='flat', padx=14, pady=5,
                  activebackground='#e2e8f1').pack(side='left', padx=(8, 0))
        return var

    pdf_var = add_row(0, '下载目录', '下载好的漫画 PDF 与记录日志会保存在这里', DEFAULT_DOWNLOAD, '选择下载目录')
    fav_var = add_row(1, '收藏夹目录', '在网页里点星标收藏时，PDF 会复制一份到这里', DEFAULT_FAVORITE, '选择收藏夹目录')

    body.columnconfigure(0, weight=1)

    shortcut_var = tk.BooleanVar(value=True)
    tk.Checkbutton(root, text='在桌面创建快捷方式', variable=shortcut_var,
                   font=('Microsoft YaHei', 10), bg='#ffffff', fg='#3a4653',
                   activebackground='#ffffff', selectcolor='#ffffff').pack(pady=(4, 6))

    def on_start():
        pdf = os.path.normpath(pdf_var.get().strip())
        fav = os.path.normpath(fav_var.get().strip())

        if not pdf or not fav:
            messagebox.showwarning(APP_NAME, '两个目录都不能为空。')
            return
        if not os.path.splitdrive(pdf)[0] or not os.path.splitdrive(fav)[0]:
            messagebox.showwarning(APP_NAME, '请填写带盘符的完整路径，例如 D:\\漫画\\JM')
            return
        if pdf.lower() == fav.lower():
            messagebox.showwarning(APP_NAME, '下载目录与收藏夹目录不能相同。')
            return

        try:
            os.makedirs(pdf, exist_ok=True)
            os.makedirs(fav, exist_ok=True)
        except Exception as e:
            messagebox.showerror(APP_NAME, '无法创建目录：\n%s' % e)
            return

        result.update(ok=True, pdf=pdf, fav=fav, shortcut=bool(shortcut_var.get()))
        root.destroy()

    def on_cancel():
        root.destroy()

    btns = tk.Frame(root, bg='#ffffff')
    btns.pack(pady=(10, 18))
    tk.Button(btns, text='开始使用', font=('Microsoft YaHei', 11, 'bold'),
              bg=brand, fg='#ffffff', relief='flat', padx=30, pady=8,
              activebackground='#4d4dc9', activeforeground='#ffffff',
              command=on_start).pack(side='left', padx=8)
    tk.Button(btns, text='退出', font=('Microsoft YaHei', 10),
              bg='#eef1f6', fg='#3a4653', relief='flat', padx=22, pady=8,
              activebackground='#e2e8f1', command=on_cancel).pack(side='left', padx=8)

    root.protocol('WM_DELETE_WINDOW', on_cancel)

    # 按实际内容自适应高度，避免按钮被挤出窗口
    root.update_idletasks()
    win_h = max(460, root.winfo_reqheight() + 8)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry('%dx%d+%d+%d' % (w, win_h, (sw - w) // 2, max(20, (sh - win_h) // 3)))

    root.mainloop()

    return result if result['ok'] else None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    os.chdir(APP_DIR)
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    os.environ.setdefault('PYTHONUTF8', '1')

    cfg = load_settings()
    if cfg is None:
        cfg = run_wizard()
        if cfg is None:
            print('已取消设置，程序退出。')
            return
        save_settings(cfg['pdf'], cfg['fav'])
        print('已保存设置：')
        print('  下载目录  : %s' % cfg['pdf'])
        print('  收藏夹目录: %s' % cfg['fav'])
        if cfg.get('shortcut'):
            create_shortcut()
            print('  桌面快捷方式：已创建（或已更新）')

    # 延迟打开浏览器，等 Flask 起来
    def open_browser():
        time.sleep(2.5)
        try:
            webbrowser.open('http://127.0.0.1:%d' % PORT)
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    sys.path.insert(0, res_dir())
    import app as webapp

    webapp.main()


if __name__ == '__main__':
    if '--uninstall' in sys.argv:
        if '--silent' in sys.argv:
            do_uninstall('--purge=1' in sys.argv)
        else:
            run_uninstaller()
    else:
        main()
