@echo off
chcp 65001 >nul
REM 重启前后端开发服务 (Windows)。
REM   后端: maestro\.venv 里的 uvicorn，:8000
REM   前端: frontend 的 Vite dev server，:5173
REM 日志写到项目根 logs\ 下，进程放独立窗口后台运行。
REM
REM 用法:
REM   restart.bat          重启前后端
REM   restart.bat backend  只重启后端
REM   restart.bat frontend 只重启前端
REM   restart.bat stop     停掉前后端

setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "LOG_DIR=%ROOT%\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"
if "%PRIVILEGED_API_TOKEN%"=="" set "PRIVILEGED_API_TOKEN=maestro-local-dev"

set "ACTION=%~1"
if "%ACTION%"=="" set "ACTION=all"

if /I "%ACTION%"=="backend"  ( call :start_backend & goto :done )
if /I "%ACTION%"=="frontend" ( call :start_frontend & goto :done )
if /I "%ACTION%"=="stop"     ( call :kill_port %BACKEND_PORT% 后端 & call :kill_port %FRONTEND_PORT% 前端 & echo 已停止 & goto :end )
if /I "%ACTION%"=="all"      ( call :start_backend & call :start_frontend & goto :done )

echo 用法: %~nx0 [all^|backend^|frontend^|stop]
exit /b 1

:done
echo.
echo 已在独立窗口启动。查看日志:
echo   type logs\backend.log
echo   type logs\frontend.log
goto :end

:kill_port
REM %1=端口 %2=名称
set "PORT=%~1"
set "NAME=%~2"
set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  if not "%%p"=="0" (
    set "FOUND=1"
    echo 停止 %NAME% (端口 %PORT%, pid: %%p)
    taskkill /F /PID %%p >nul 2>&1
  )
)
if not defined FOUND echo %NAME% 未在运行 (端口 %PORT%)
exit /b 0

:start_backend
call :kill_port %BACKEND_PORT% 后端
echo 启动后端 -^> http://localhost:%BACKEND_PORT% (日志: logs\backend.log)
start "maestro-backend" /D "%ROOT%\maestro" cmd /c ".venv\Scripts\uvicorn.exe maestro.main:app --reload --port %BACKEND_PORT% > "%LOG_DIR%\backend.log" 2>&1"
exit /b 0

:start_frontend
call :kill_port %FRONTEND_PORT% 前端
echo 启动前端 -^> http://localhost:%FRONTEND_PORT% (日志: logs\frontend.log)
start "maestro-frontend" /D "%ROOT%\frontend" cmd /c "npm run dev > "%LOG_DIR%\frontend.log" 2>&1"
exit /b 0

:end
endlocal
