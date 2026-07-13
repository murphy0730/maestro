@echo off
chcp 65001 >nul
REM 一键打包 Windows 版 Electron 应用 (nsis 安装器 .exe)。
REM 全链: 冻结后端 (PyInstaller) -^> 打包前端+Electron (electron-builder)。
REM 产物: frontend\release\*.exe
REM
REM 注意: 打包链里的后端是 PyInstaller 原生二进制，无法跨平台编译。
REM       本脚本只产 Windows 包；macOS 包请在 Mac 上跑 build-mac.sh。
REM
REM 用法: build-win.bat

setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "VENV_PY=%ROOT%\maestro\.venv\Scripts\python.exe"

echo ==^> [1/4] 检查后端 venv
if not exist "%VENV_PY%" (
  echo 错误: 未找到 "%VENV_PY%" 1>&2
  echo 请先创建后端环境: cd maestro ^&^& uv venv --python 3.12 ^&^& uv pip install -e ".[dev]" 1>&2
  exit /b 1
)

echo ==^> [2/4] 确保 PyInstaller 已安装
"%VENV_PY%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo PyInstaller 缺失，安装 maestro[packaging] ...
  "%VENV_PY%" -m pip install -e "%ROOT%\maestro[packaging]"
  if errorlevel 1 exit /b 1
)

echo ==^> [3/4] 冻结后端 -^> maestro\dist\backend\
cd /d "%ROOT%\maestro"
"%VENV_PY%" -m PyInstaller maestro_backend.spec --noconfirm
if errorlevel 1 exit /b 1
if not exist "%ROOT%\maestro\dist\backend\MaestroBackend.exe" (
  echo 错误: 冻结产物 maestro\dist\backend\MaestroBackend.exe 未生成 1>&2
  exit /b 1
)

echo ==^> [4/4] 打包 Electron (vite build + electron-builder)
cd /d "%ROOT%\frontend"
if not exist node_modules (
  call npm install
  if errorlevel 1 exit /b 1
)
call npm run electron:build
if errorlevel 1 exit /b 1

echo.
echo 完成。产物在 frontend\release\:
dir /b "%ROOT%\frontend\release\*.exe" 2>nul || echo   (未找到 .exe，检查 electron-builder 输出)

endlocal
