# -*- coding: utf-8 -*-
"""
JM 下载助手 —— 安装程序

功能：
  · 选择「安装位置」（程序装到哪里）
  · 选择「下载目录」与「收藏夹目录」
  · 可选创建桌面快捷方式、安装完成后立即启动
  · 已经装过旧版本时自动进入「升级模式」：只替换程序文件，
    下载目录 / 收藏目录 / settings.json / 所有漫画原样保留

打包方式：PyInstaller onefile，程序文件以数据形式内嵌在 app_files 目录。
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

APP_NAME = 'JM 下载助手'
EXE_NAME = 'JM下载助手.exe'

IS_FROZEN = getattr(sys, 'frozen', False)
BUNDLE_DIR = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'app_files')


def default_install_dir():
    """D 盘存在就装到 D 盘，否则装到用户目录（都不需要管理员权限）。"""
    if os.path.exists('D:\\'):
        return 'D:\\JM下载助手'
    return os.path.join(os.path.expanduser('~'), 'JM下载助手')


UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\JM下载助手'
APP_VERSION = '1.1'

# 升级时保留的文件：配置与用户数据都不能动
PRESERVE_NAMES = {'settings.json', 'jm_log.txt', 'jm_fav_log.txt'}


def detect_installed():
    """
    读取系统「应用」里登记的信息，判断是否已经安装过。
    返回 {'target':..., 'version':..., 'usable': bool} 或 None。
    """
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_READ)
    except FileNotFoundError:
        return None
    except Exception:
        return None

    def getv(name):
        try:
            return str(winreg.QueryValueEx(key, name)[0])
        except Exception:
            return ''

    try:
        target = getv('InstallLocation')
        version = getv('DisplayVersion')
    finally:
        winreg.CloseKey(key)

    if not target:
        return None

    target = os.path.normpath(target)
    usable = os.path.isdir(target) and os.path.isfile(os.path.join(target, EXE_NAME))
    return {'target': target, 'version': version or '?', 'usable': usable}


def read_settings_of(target):
    """读旧安装里的 settings.json（升级时用来沿用目录）。"""
    path = os.path.join(target, 'settings.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def write_settings(target, dl, fav, merge=True):
    """
    写 settings.json。
    merge=True（升级）时保留原有字段，例如 AVS，只更新两个目录；
    merge=False（全新安装）时直接覆盖。
    """
    data = read_settings_of(target) if merge else {}
    if not isinstance(data, dict):
        data = {}
    data['pdf_dir'] = dl
    data['fav_dir'] = fav
    try:
        with open(os.path.join(target, 'settings.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print('写 settings.json 失败：%s' % e)
        return False


def remove_program_files(target, log=None):
    """
    升级前清掉旧的程序文件，避免 PyInstaller 的 _internal 里残留旧依赖。
    只删 exe 与 _internal，settings.json / 漫画 / 收藏 / downloads 一律不动。
    """
    log = log or (lambda t: None)
    problems = []

    internal = os.path.join(target, '_internal')
    if os.path.isdir(internal):
        log('正在清理旧版程序组件…')
        try:
            shutil.rmtree(internal)
        except Exception as e:
            problems.append('_internal：%s' % e)

    exe = os.path.join(target, EXE_NAME)
    if os.path.isfile(exe):
        try:
            os.remove(exe)
        except Exception as e:
            problems.append('%s：%s' % (EXE_NAME, e))

    return problems



def register_uninstall(target):
    """在系统「设置 → 应用」里登记，使其能像普通软件一样卸载。"""
    import winreg

    exe = os.path.join(target, EXE_NAME)
    try:
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, 0, winreg.KEY_WRITE)
    except Exception as e:
        print('登记卸载信息失败：%s' % e)
        return False

    def setv(name, value, kind=winreg.REG_SZ):
        winreg.SetValueEx(key, name, 0, kind, value)

    try:
        setv('DisplayName', APP_NAME)
        setv('DisplayVersion', APP_VERSION)
        setv('Publisher', '本机部署版')
        setv('InstallLocation', target)
        setv('DisplayIcon', exe)
        setv('UninstallString', '"%s" --uninstall' % exe)
        setv('QuietUninstallString', '"%s" --uninstall --silent --purge=1' % exe)
        setv('NoModify', 1, winreg.REG_DWORD)
        setv('NoRepair', 1, winreg.REG_DWORD)
        setv('InstallDate', time.strftime('%Y%m%d'))
        try:
            size = 0
            for root_dir, _dirs, files in os.walk(target):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(root_dir, f))
                    except OSError:
                        pass
            setv('EstimatedSize', int(size / 1024), winreg.REG_DWORD)
        except Exception:
            pass
    finally:
        winreg.CloseKey(key)
    return True


def write_uninstall_cmd(target):
    """在安装目录里放一个双击即可卸载的入口。"""
    try:
        path = os.path.join(target, '卸载.cmd')
        with open(path, 'w', encoding='gbk', newline='\r\n') as f:
            f.write('@echo off\n')
            # %%~dp0 在 .cmd 里展开成脚本所在目录（这里用 %% 转义 Python 的格式化）
            f.write('start "" "%%~dp0%s" --uninstall\n' % EXE_NAME)
        return True
    except Exception as e:
        print('写卸载入口失败：%s' % e)
        return False


# ---------------------------------------------------------------------------
# 安装动作
# ---------------------------------------------------------------------------
def copy_files(target, progress):
    """把内嵌的程序文件复制到安装目录。"""
    os.makedirs(target, exist_ok=True)

    items = []
    for root, dirs, files in os.walk(BUNDLE_DIR):
        for name in files:
            items.append(os.path.join(root, name))
    total = len(items) or 1

    done = 0
    for src in items:
        rel = os.path.relpath(src, BUNDLE_DIR)
        dst = os.path.join(target, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        done += 1
        if done % 40 == 0 or done == total:
            progress(done / total, '正在复制程序文件… %d/%d' % (done, total))
    return total


def create_shortcut(target_exe, work_dir):
    ps = (
        "$desktop = [Environment]::GetFolderPath('Desktop');"
        "$ws = New-Object -ComObject WScript.Shell;"
        "$lnk = $ws.CreateShortcut((Join-Path $desktop '{name}.lnk'));"
        "$lnk.TargetPath = '{exe}';"
        "$lnk.WorkingDirectory = '{wd}';"
        "$lnk.Description = '{name}';"
        "$lnk.Save()"
    ).format(name=APP_NAME, exe=target_exe.replace("'", "''"), wd=work_dir.replace("'", "''"))
    subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
                   creationflags=0x08000000, timeout=40, check=False)


def _parse_args(argv):
    args = {}
    for a in argv:
        if a.startswith('--') and '=' in a:
            k, v = a[2:].split('=', 1)
            args[k.strip().lower()] = v.strip()
    return args


def silent_install(argv):
    """
    无界面安装（自动化测试 / 高级用户）：
      --silent --target=... --dl=... --fav=... --shortcut=0/1 --launch=0/1

    未显式指定 --target 且检测到已安装时，自动按「升级」处理：
    沿用原安装位置与目录，只替换程序文件，保留 settings.json 与全部数据。
    """
    args = _parse_args(argv)

    installed = detect_installed()
    upgrade = bool(installed and installed['usable'] and 'target' not in args)

    if upgrade:
        target = installed['target']
        old = read_settings_of(target)
        dl = os.path.normpath(args.get('dl') or old.get('pdf_dir') or os.path.join(target, '漫画'))
        fav = os.path.normpath(args.get('fav') or old.get('fav_dir') or os.path.join(target, '收藏'))
        print('[静默更新] 检测到已安装 v%s，按升级处理' % installed['version'])
    else:
        target = os.path.normpath(args.get('target') or default_install_dir())
        dl = os.path.normpath(args.get('dl') or os.path.join(target, '漫画'))
        fav = os.path.normpath(args.get('fav') or os.path.join(target, '收藏'))

    shortcut = args.get('shortcut', '1') not in ('0', 'false', 'no')
    launch = args.get('launch', '0') in ('1', 'true', 'yes')

    tag = '静默更新' if upgrade else '静默安装'
    print('[%s] 安装位置 : %s' % (tag, target))
    print('[%s] 下载目录 : %s' % (tag, dl))
    print('[%s] 收藏目录 : %s' % (tag, fav))

    if upgrade:
        problems = remove_program_files(target, print)
        if problems:
            print('[静默更新] 失败：旧版本可能仍在运行，请先关闭程序')
            for p in problems:
                print('   ! ' + p)
            return 2

    count = copy_files(target, lambda frac, text: None)
    write_settings(target, dl, fav, merge=upgrade)
    os.makedirs(dl, exist_ok=True)
    os.makedirs(fav, exist_ok=True)

    if shortcut:
        create_shortcut(os.path.join(target, EXE_NAME), target)

    write_uninstall_cmd(target)
    register_uninstall(target)

    print('[静默安装] 已复制 %d 个文件' % count)
    print('[静默安装] 完成：%s' % os.path.join(target, EXE_NAME))

    if launch:
        subprocess.Popen([os.path.join(target, EXE_NAME)], cwd=target)
    return 0


# ---------------------------------------------------------------------------
# 界面
# ---------------------------------------------------------------------------
def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    brand = '#5b5bd6'
    state = {'installing': False, 'done': False, 'target': '', 'upgrade': False}

    installed = detect_installed()
    upgrading = bool(installed and installed['usable'])
    old_cfg = read_settings_of(installed['target']) if upgrading else {}

    if upgrading:
        state['upgrade'] = True
        init_install = installed['target']
        init_dl = old_cfg.get('pdf_dir') or os.path.join(init_install, '漫画')
        init_fav = old_cfg.get('fav_dir') or os.path.join(init_install, '收藏')
    else:
        init_install = default_install_dir()
        init_dl = os.path.join(init_install, '漫画')
        init_fav = os.path.join(init_install, '收藏')

    root = tk.Tk()
    root.title(APP_NAME + (' · 更新' if upgrading else ' · 安装'))
    root.configure(bg='#ffffff')
    root.resizable(False, False)

    w = 720
    root.geometry('720x1')      # 先定宽度，高度等控件放完后按内容自适应

    tk.Label(root, text=APP_NAME, font=('Microsoft YaHei', 18, 'bold'),
             bg='#ffffff', fg='#1a1c23').pack(pady=(20, 2))

    subtitle = tk.Label(
        root,
        text=('更新到新版本 v%s（当前已安装 v%s）' % (APP_VERSION, installed['version'])
              if upgrading else '安装向导 · 选择安装位置与两个数据目录'),
        font=('Microsoft YaHei', 10), bg='#ffffff', fg='#5b6070')
    subtitle.pack(pady=(0, 6 if upgrading else 16))

    if upgrading:
        banner = tk.Frame(root, bg='#eef0fb', highlightbackground='#c9cbf2', highlightthickness=1)
        banner.pack(fill='x', padx=30, pady=(6, 10))
        tk.Label(banner,
                 text='升级模式：只替换程序文件，以下目录与全部漫画都会原样保留',
                 font=('Microsoft YaHei', 9, 'bold'), bg='#eef0fb', fg='#5b5bd6',
                 anchor='w').pack(fill='x', padx=12, pady=(8, 1))
        tk.Label(banner,
                 text='下载目录：%s\n收藏目录：%s' % (init_dl, init_fav),
                 font=('Microsoft YaHei', 9), bg='#eef0fb', fg='#6b6fc0',
                 justify='left', anchor='w', wraplength=600).pack(fill='x', padx=12, pady=(0, 8))

    body = tk.Frame(root, bg='#ffffff')
    body.pack(fill='x', padx=30)
    body.columnconfigure(0, weight=1)

    rows = []
    widgets = []

    def add_row(row, label, hint, initial, browse_title, on_change=None):
        tk.Label(body, text=label, font=('Microsoft YaHei', 10, 'bold'),
                 bg='#ffffff', fg='#1a1c23', anchor='w').grid(row=row * 3, column=0, sticky='w')
        tk.Label(body, text=hint, font=('Microsoft YaHei', 9),
                 bg='#ffffff', fg='#9aa0ae', anchor='w').grid(row=row * 3 + 1, column=0, sticky='w', pady=(2, 0))

        var = tk.StringVar(value=initial)
        line = tk.Frame(body, bg='#ffffff')
        line.grid(row=row * 3 + 2, column=0, sticky='ew', pady=(6, 14))

        entry = tk.Entry(line, textvariable=var, font=('Microsoft YaHei', 10), relief='solid', bd=1)
        entry.pack(side='left', fill='x', expand=True, ipady=6)

        def browse():
            chosen = filedialog.askdirectory(title=browse_title, initialdir=var.get() or os.path.expanduser('~'))
            if chosen:
                var.set(os.path.normpath(chosen))
                if on_change:
                    on_change()

        btn = tk.Button(line, text='浏览…', font=('Microsoft YaHei', 9), command=browse,
                        bg='#eef1f6', fg='#3a4653', relief='flat', padx=14, pady=5,
                        activebackground='#e2e8f1')
        btn.pack(side='left', padx=(8, 0))

        rows.append(var)
        widgets.append((entry, btn))
        return var

    install_var = tk.StringVar(value=init_install)
    dl_var = tk.StringVar(value=init_dl)
    fav_var = tk.StringVar(value=init_fav)

    def sync_sub_dirs():
        """安装位置变了，若下面两个还是默认值就跟着变。"""
        base = install_var.get().strip()
        if not base:
            return
        if not dl_var.get() or dl_var.get().endswith('\\漫画'):
            dl_var.set(os.path.join(base, '漫画'))
        if not fav_var.get() or fav_var.get().endswith('\\收藏'):
            fav_var.set(os.path.join(base, '收藏'))

    add_row(0, '安装位置', '程序本体装到这里（建议放在 D 盘或用户目录，不要用 C:\\Program Files）',
            install_var.get(), '选择安装位置', sync_sub_dirs)
    install_entry_var = rows[0]
    install_entry_var.trace_add('write', lambda *a: sync_sub_dirs())

    add_row(1, '下载目录', '下载好的漫画 PDF 与记录日志保存在这里', dl_var.get(), '选择下载目录')
    add_row(2, '收藏夹目录', '点星标收藏时，PDF 会复制一份到这里', fav_var.get(), '选择收藏夹目录')

    shortcut_var = tk.BooleanVar(value=True)
    launch_var = tk.BooleanVar(value=True)
    opts = tk.Frame(root, bg='#ffffff')
    opts.pack(pady=(2, 6))
    tk.Checkbutton(opts, text='在桌面创建快捷方式', variable=shortcut_var,
                   font=('Microsoft YaHei', 10), bg='#ffffff', fg='#3a4653',
                   activebackground='#ffffff', selectcolor='#ffffff').pack(side='left', padx=10)
    tk.Checkbutton(opts, text='安装完成后立即启动', variable=launch_var,
                   font=('Microsoft YaHei', 10), bg='#ffffff', fg='#3a4653',
                   activebackground='#ffffff', selectcolor='#ffffff').pack(side='left', padx=10)

    bar = ttk.Progressbar(root, orient='horizontal', length=600, mode='determinate')
    bar.pack(pady=(12, 4))
    status = tk.Label(root, text='准备就绪', font=('Microsoft YaHei', 9),
                      bg='#ffffff', fg='#5b6070')
    status.pack()

    def progress(frac, text):
        bar['value'] = frac * 100
        status.config(text=text)
        root.update_idletasks()

    def do_install(target, dl, fav, shortcut, launch, upgrade):
        try:
            progress(0.02, '正在检查目标位置…')

            if upgrade:
                progress(0.05, '正在清理旧版程序组件…')
                problems = remove_program_files(target)
                if problems:
                    raise RuntimeError(
                        '旧版本可能还在运行，请先关闭「%s」窗口后再试。\n\n%s'
                        % (APP_NAME, '\n'.join(problems)))
            elif os.path.isdir(target):
                existing = os.listdir(target)
                if existing and EXE_NAME not in existing and not any(
                        n.lower().startswith('jm') for n in existing):
                    # 目录非空且看起来不是本程序，交给主线程询问
                    state['conflict'] = True

            progress(0.15 if upgrade else 0.05, '正在复制程序文件…')
            count = copy_files(target, progress)

            progress(0.9, '正在写入配置…')
            # 升级时 merge=True：只更新两个目录，AVS 等其它设置原样保留
            write_settings(target, dl, fav, merge=upgrade)
            os.makedirs(dl, exist_ok=True)
            os.makedirs(fav, exist_ok=True)

            if shortcut:
                progress(0.95, '正在创建桌面快捷方式…')
                create_shortcut(os.path.join(target, EXE_NAME), target)

            progress(0.97, '正在登记卸载信息…')
            write_uninstall_cmd(target)
            register_uninstall(target)

            progress(1.0, '更新完成（共 %d 个文件）' % count)
            state['done'] = True
            state['target'] = target
            state['launch'] = launch
        except Exception as e:
            state['error'] = str(e)
        finally:
            state['installing'] = False
            root.after(0, finish)

    def finish():
        if state.get('error'):
            messagebox.showerror(APP_NAME, '安装失败：\n%s' % state['error'])
            start_btn.config(state='normal',
                             text='立即更新' if state['upgrade'] else '重试安装')
            return
        if state.get('done'):
            start_btn.config(state='disabled',
                             text='更新完成' if state['upgrade'] else '安装完成')
            if state.get('launch'):
                try:
                    subprocess.Popen([os.path.join(state['target'], EXE_NAME)],
                                     cwd=state['target'])
                except Exception:
                    pass
            if state['upgrade']:
                tip = ('更新完成！\n\n程序位置：%s\n\n'
                       '下载目录、收藏目录与全部漫画都没有改动。' % state['target'])
            else:
                tip = ('安装完成！\n\n程序位置：%s\n\n'
                       '以后双击桌面上的「%s」即可使用。' % (state['target'], APP_NAME))
            if messagebox.showinfo(APP_NAME, tip):
                root.destroy()

    def on_start():
        if state['installing']:
            return
        target = os.path.normpath(install_entry_var.get().strip())
        dl = os.path.normpath(rows[1].get().strip())
        fav = os.path.normpath(rows[2].get().strip())

        if not target or not dl or not fav:
            messagebox.showwarning(APP_NAME, '三个路径都不能为空。')
            return
        for p, name in ((target, '安装位置'), (dl, '下载目录'), (fav, '收藏夹目录')):
            if not os.path.splitdrive(p)[0]:
                messagebox.showwarning(APP_NAME, '%s 请填写带盘符的完整路径。' % name)
                return
        if os.path.normcase(dl) == os.path.normcase(fav):
            messagebox.showwarning(APP_NAME, '下载目录与收藏夹目录不能相同。')
            return
        if os.path.normcase(target) == os.path.normcase(dl) or os.path.normcase(target) == os.path.normcase(fav):
            messagebox.showwarning(APP_NAME, '下载目录 / 收藏夹目录不能就是安装位置本身，请放在它下面或别处。')
            return

        if state['upgrade']:
            if not messagebox.askyesno(
                    APP_NAME,
                    '将把「%s」更新到 v%s。\n\n'
                    '· 只替换程序文件（%s 与 _internal）\n'
                    '· 下载目录 / 收藏目录 / 全部漫画与设置原样保留\n\n是否继续？'
                    % (target, APP_VERSION, EXE_NAME)):
                return
        else:
            # 目标目录已存在且非空 → 先问清楚
            if os.path.isdir(target) and os.listdir(target):
                if not messagebox.askyesno(APP_NAME,
                                           '目标文件夹已存在且不为空：\n%s\n\n'
                                           '继续安装会把同名文件覆盖掉（其它文件保留）。\n是否继续？' % target):
                    return

        try:
            os.makedirs(target, exist_ok=True)
        except Exception as e:
            messagebox.showerror(APP_NAME, '无法创建安装位置：\n%s' % e)
            return

        state['installing'] = True
        state.pop('error', None)
        state.pop('done', None)
        start_btn.config(state='disabled',
                         text='正在更新…' if state['upgrade'] else '正在安装…')
        threading.Thread(target=do_install,
                         args=(target, dl, fav, bool(shortcut_var.get()),
                               bool(launch_var.get()), state['upgrade']),
                         daemon=True).start()

    btns = tk.Frame(root, bg='#ffffff')
    btns.pack(pady=(14, 16))
    start_btn = tk.Button(btns,
                          text='立即更新' if upgrading else '开始安装',
                          font=('Microsoft YaHei', 11, 'bold'),
                          bg=brand, fg='#ffffff', relief='flat', padx=32, pady=8,
                          activebackground='#4d4dc9', activeforeground='#ffffff',
                          command=on_start)
    start_btn.pack(side='left', padx=8)
    tk.Button(btns, text='退出', font=('Microsoft YaHei', 10),
              bg='#eef1f6', fg='#3a4653', relief='flat', padx=24, pady=8,
              activebackground='#e2e8f1', command=root.destroy).pack(side='left', padx=8)

    def switch_to_fresh():
        """从「升级」切回「全新安装」：解锁路径输入。"""
        if not messagebox.askyesno(
                APP_NAME,
                '改为全新安装？\n\n'
                '这会让你重新选择安装位置与数据目录。\n'
                '如果选到同一个目录，程序文件仍会覆盖，但不会有任何数据被删除。'):
            return
        state['upgrade'] = False
        for entry, btn in widgets:
            entry.config(state='normal', bg='#ffffff')
            btn.config(state='normal')
        start_btn.config(text='开始安装')
        fresh_btn.pack_forget()

    if upgrading:
        # 放在按钮行里（而不是窗口最底部），避免窗口高度不够时被裁掉
        fresh_btn = tk.Button(btns, text='改为全新安装', font=('Microsoft YaHei', 10),
                              bg='#eef1f6', fg='#3a4653', relief='flat', padx=20, pady=8,
                              activebackground='#e2e8f1', command=switch_to_fresh)
        fresh_btn.pack(side='left', padx=8)

        # 升级模式下路径不可编辑，防止误改
        for entry, btn in widgets:
            entry.config(state='readonly', bg='#f4f5f8')
            btn.config(state='disabled')

    if not os.path.isdir(BUNDLE_DIR):
        status.config(text='警告：未找到内嵌的程序文件（app_files）', fg='#e5484d')

    # 按实际内容自适应高度，避免按钮被挤出窗口
    root.update_idletasks()
    win_h = max(560 if upgrading else 520, root.winfo_reqheight() + 8)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry('%dx%d+%d+%d' % (w, win_h, (sw - w) // 2, max(20, (sh - win_h) // 3)))

    root.mainloop()


if __name__ == '__main__':
    if '--silent' in sys.argv:
        sys.exit(silent_install(sys.argv))
    main()
