@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set LOG_FILE=agent.log
set ENV_NAME=comfy_agent
set SCRIPT_NAME=agent_main.py

title ComfyUI Agent 控制台

:menu
cls
echo ==========================================
echo         ComfyUI Agent 控制台
echo ==========================================
echo.

:: 使用 wmic 获取运行该脚本的 Python 进程 ID
set PID=
for /f "tokens=2 delims==" %%I in ('wmic process where "name='python.exe' and commandline like '%%agent_main.py%%'" get processid /value 2^>nul ^| findstr "="') do (
    set PID=%%I
)

if defined PID (
    echo   当前状态: [运行中] (PID: !PID!)
) else (
    echo   当前状态: [已停止]
)

echo.
echo   1. 启动 Agent
echo   2. 停止 Agent
echo   3. 重启 Agent
echo   4. 查看实时日志 (按 Ctrl+C 退出查看)
echo   5. 清空日志
echo   0. 退出
echo ==========================================
set /p choice="请输入选项(0-5): "

if "%choice%"=="1" goto start_agent
if "%choice%"=="2" goto stop_agent
if "%choice%"=="3" goto restart_agent
if "%choice%"=="4" goto view_logs
if "%choice%"=="5" goto clear_logs
if "%choice%"=="0" goto end
goto menu

:start_agent
if defined PID (
    echo [提示] Agent 已经在运行中了！
    pause
    goto menu
)
echo [信息] 正在启动 Agent...
:: 启动新的 cmd 窗口执行 conda 命令，这样你能直接看到它的运行状态和报错
start "ComfyUI Agent 后台进程" cmd.exe /c "conda run --no-capture-output -n %ENV_NAME% python -u %SCRIPT_NAME% > %LOG_FILE% 2>&1"
echo [成功] 启动命令已发送！
timeout /t 2 >nul
goto menu

:stop_agent
if not defined PID (
    echo [提示] Agent 当前未运行。
    pause
    goto menu
)
echo [信息] 正在停止进程 !PID!...
taskkill /F /PID !PID! >nul 2>&1
echo [成功] Agent 已停止。
pause
goto menu

:restart_agent
if defined PID (
    echo [信息] 正在停止旧进程 !PID!...
    taskkill /F /PID !PID! >nul 2>&1
    timeout /t 1 >nul
)
echo [信息] 正在启动新 Agent...
start "ComfyUI Agent 后台进程" cmd.exe /c "conda run --no-capture-output -n %ENV_NAME% python -u %SCRIPT_NAME% > %LOG_FILE% 2>&1"
echo [成功] 重启命令已发送！
timeout /t 2 >nul
goto menu

:view_logs
if not exist %LOG_FILE% (
    echo [提示] 暂无日志文件！
    pause
    goto menu
)
echo [信息] 正在查看日志 (仅显示最后30行)... 
echo ------------------------------------------
powershell -NoProfile -Command "Get-Content %LOG_FILE% -Tail 30"
echo ------------------------------------------
pause
goto menu

:clear_logs
echo [信息] 正在清空日志...
type nul > %LOG_FILE%
echo [成功] 日志已清空。
pause
goto menu

:end
exit
