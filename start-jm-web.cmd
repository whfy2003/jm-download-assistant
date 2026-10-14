@echo off
rem ============================================================
rem  「JM 下载助手」本地网页端 —— 双击本文件即可启动
rem    · 自动启动服务，并在几秒后弹出浏览器
rem    · 若服务已在运行，则只打开浏览器，不会重复启动
rem    · PDF 目录 : E:\漫画\JM
rem    · 访问地址 : http://127.0.0.1:8080
rem    · 停止服务 : 直接关闭本窗口（或运行 stop-jm-web.cmd）
rem ============================================================
chcp 65001 >nul
setlocal
set "JM_HOME=%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist "%JM_HOME%.venv\Scripts\python.exe" (
  echo [错误] 未找到 "%JM_HOME%.venv\Scripts\python.exe"
  echo         虚拟环境可能被删除或移动，请重新部署。
  pause
  exit /b 1
)

rem —— 已经在运行？那就只打开浏览器，绝不重复启动 ——
netstat -ano | findstr ":8080" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo 服务已经在运行，正在打开浏览器 ...
  explorer "http://127.0.0.1:8080"
  exit /b 0
)

echo ============================================================
echo    JM 下载助手 正在启动 ...
echo.
echo    PDF 目录 : E:\漫画\JM
echo    访问地址 : http://127.0.0.1:8080
echo.
echo    浏览器会在几秒后自动打开。
echo    这个黑窗口就是服务本身，关掉它 = 停止服务。
echo ============================================================
echo.

rem 等 4 秒（服务就绪）后自动打开默认浏览器
start "" /min cmd /c "timeout /t 4 /nobreak >nul & explorer http://127.0.0.1:8080"

"%JM_HOME%.venv\Scripts\python.exe" -X utf8 "%JM_HOME%webui\app.py"

endlocal
