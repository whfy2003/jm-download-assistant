@echo off
rem ============================================================
rem  停止监听 8080 端口的 JM Web 服务
rem ============================================================
chcp 65001 >nul
setlocal
set "PORT=8080"
set "FOUND="

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
  echo 正在结束 PID %%p ...
  taskkill /F /PID %%p >nul 2>&1
  set "FOUND=1"
)

if defined FOUND (
  echo 已停止端口 %PORT% 上的服务。
) else (
  echo 端口 %PORT% 上没有正在监听的服务。
)
endlocal
