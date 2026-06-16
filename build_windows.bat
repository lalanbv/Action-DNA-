@echo off
:: build_windows.bat — Windows 一键打包脚本
:: 兼容 Python 3.11 ~ 3.14+，Windows 10/11 x64
:: 使用方法: 双击运行或在 cmd 中执行 build_windows.bat

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

set APP_NAME=Action-DNA
set ENTRY_POINT=main.py
set VENV_DIR=.venv_build
set REQUIRED_MAJOR=3
set REQUIRED_MINOR=11

echo =========================================
echo   %APP_NAME% — Windows 一键打包
echo =========================================
echo.

:: ── 1. 查找 Python ──
echo [1/6] 查找 Python...

set PYTHON=
for %%C in (python py -3.14 -3.13 -3.12 -3.11) do (
    if not defined PYTHON (
        set FOUND_MAJOR=
        set FOUND_MINOR=
        %%C --version >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=2 delims= " %%V in ('%%C --version 2^>^&1') do set PY_VER_RAW=%%V
            for /f "tokens=1,2 delims=." %%A in ("!PY_VER_RAW!") do (
                set FOUND_MAJOR=%%A
                set FOUND_MINOR=%%B
            )
            if !FOUND_MAJOR! gtr %REQUIRED_MAJOR% (
                set PYTHON=%%C
                set PY_VERSION=!PY_VER_RAW!
            )
            if defined FOUND_MAJOR if !FOUND_MAJOR! equ %REQUIRED_MAJOR% if !FOUND_MINOR! geq %REQUIRED_MINOR% (
                set PYTHON=%%C
                set PY_VERSION=!PY_VER_RAW!
            )
        )
    )
)

if not defined PYTHON (
    echo   [FAIL] 未找到 Python ^>= 3.11
    echo   请从 https://www.python.org/downloads/ 安装
    echo   安装时勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo   [OK] Python !PY_VERSION! (!PYTHON!)

:: ── 2. 检查架构 ──
echo.
echo [2/6] 检查运行环境...

for /f %%A in ('%PYTHON% -c "import struct; print(\"64-bit\" if struct.calcsize(\"P\")*8==64 else \"32-bit\")"') do set ARCH=%%A
echo   [OK] !ARCH! Python

:: ── 3. 创建/激活虚拟环境 ──
echo.
echo [3/6] 准备构建虚拟环境...

:: 如果 venv 存在但 Python 版本不匹配，删除重建
if exist "%VENV_DIR%\pyvenv.cfg" (
    for /f "tokens=1,2 delims== " %%A in ('findstr /b "version" "%VENV_DIR%\pyvenv.cfg"') do set VENV_VER=%%B
    set VENV_VER=!VENV_VER:~0,4!
    for /f "tokens=1,2 delims=." %%A in ("!PY_VERSION!") do set CUR_VER=%%A.%%B
    if "!VENV_VER!" neq "!CUR_VER!" (
        echo   [INFO] 虚拟环境 Python !VENV_VER! 与当前 !CUR_VER! 不匹配，重建...
        rmdir /s /q "%VENV_DIR%" 2>nul
    )
)

if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo   创建构建虚拟环境...
    %PYTHON% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo   [FAIL] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo   [OK] 虚拟环境已创建
)

call "%VENV_DIR%\Scripts\activate.bat"

:: 升级 pip
python -m pip install --upgrade pip --quiet 2>nul || (
    echo   [WARN] pip 升级失败，继续使用当前版本
)

:: ── 4. 安装依赖 ──
echo.
echo [4/6] 安装依赖...

pip install --quiet -r requirements.txt
if !errorlevel! neq 0 (
    echo   [FAIL] 安装项目依赖失败
    pause
    exit /b 1
)
echo   [OK] 项目依赖已安装

pip install --quiet pyinstaller
if !errorlevel! neq 0 (
    echo   [FAIL] 安装 PyInstaller 失败
    pause
    exit /b 1
)
for /f "tokens=*" %%V in ('pyinstaller --version 2^>^&1') do set PYI_VER=%%V
echo   [OK] PyInstaller !PYI_VER!

:: 检查 OCR 可选依赖
pip show rapidocr_onnxruntime >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] rapidocr_onnxruntime 已安装（含 OCR 支持）
) else (
    echo   [INFO] rapidocr_onnxruntime 未安装，OCR 功能将降级
)

:: ── 5. 清理旧构建 ──
echo.
echo [5/6] 清理旧构建...
if exist build rmdir /s /q build 2>nul
if exist dist  rmdir /s /q dist  2>nul
del /q *.spec 2>nul
echo   [OK] 清理完成

:: ── 6. 生成 spec 文件并打包 ──
echo.
echo [6/6] 执行 PyInstaller 打包...
echo.

:: 生成 spec 文件（避免 cmd 行长度限制和转义问题）
(
echo # -*- mode: python ; coding: utf-8 -*-
echo.
echo import sys, os
echo.
echo block_cipher = None
echo.
echo a = Analysis(
echo     ['main.py'],
echo     pathex=[],
echo     binaries=[],
echo     datas=[
if exist "config" (
    echo         ('config', 'config'^),
)
if exist "assets" (
    echo         ('assets', 'assets'^),
)
if exist "src\utils\translations" (
    echo         (r'src\utils\translations', 'src/utils/translations'^),
)
if exist "src\plugins\builtin" (
    echo         (r'src\plugins\builtin', 'src/plugins/builtin'^),
)
if exist "docs" (
    echo         ('docs', 'docs'^),
)
echo     ],
echo     hiddenimports=[
echo         'pynput.keyboard._win32',
echo         'pynput.mouse._win32',
echo         'pynput.keyboard',
echo         'pynput.mouse',
echo         'keyboard',
echo         'pyautogui',
echo         'mss',
echo         'PIL',
echo         'numpy',
echo         'cv2',
echo         'tkinter',
echo         'tkinter.filedialog',
echo         'tkinter.messagebox',
echo         'tkinter.colorchooser',
echo         'tkinter.scrolledtext',
echo         'tkinter.ttk',
echo         'PySide6.QtWidgets',
echo         'PySide6.QtCore',
echo         'PySide6.QtGui',
echo         'src.panel.qt_backend',
echo         'src.panel.qt_backend.app',
echo         'src.plugins.builtin.combat',
echo         'src.plugins.builtin.navigation',
echo         'src.plugins.builtin.task',
echo         'unittest.mock',
echo     ],
echo     hookspath=[],
echo     hooksconfig={},
echo     runtime_hooks=[],
echo     excludes=[],
echo     collect_submodules=['src'],
echo     cipher=block_cipher,
echo     noarchive=False,
echo ^)
echo.
echo pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher^)
echo.
echo exe = EXE(
echo     pyz,
echo     a.scripts,
echo     [],
echo     exclude_binaries=True,
echo     name='%APP_NAME%',
echo     debug=False,
echo     bootloader_ignore_signals=False,
echo     strip=False,
echo     upx=False,
echo     console=False,
echo     disable_windowed_traceback=False,
echo     target_arch=None,
echo     codesign_identity=None,
echo     entitlements_file=None,
echo ^)
echo.
echo coll = COLLECT(
echo     exe,
echo     a.binaries,
echo     a.zipfiles,
echo     a.datas,
echo     strip=False,
echo     upx=False,
echo     upx_exclude=[],
echo     name='%APP_NAME%',
echo ^)
) > "%APP_NAME%.spec"

:: 用 spec 文件打包
pyinstaller --noconfirm --clean "%APP_NAME%.spec" 2>&1

if !errorlevel! neq 0 (
    echo.
    echo   [FAIL] PyInstaller 打包失败，请检查上方错误信息。
    pause
    exit /b 1
)

:: 验证产出
echo.
if exist "dist\%APP_NAME%\%APP_NAME%.exe" (
    echo =========================================
    echo   打包完成!
    echo =========================================
    echo.
    echo   [OK] 产出目录: dist\%APP_NAME%\
    echo   [OK] 可执行文件: dist\%APP_NAME%\%APP_NAME%.exe
    echo.
    echo   启动方式:
    echo     dist\%APP_NAME%\%APP_NAME%.exe
    echo.
    echo   分发方式:
    echo     将 dist\%APP_NAME%\ 目录压缩为 .zip
    echo.
) else (
    echo   [FAIL] 打包后未找到预期产出 dist\%APP_NAME%\%APP_NAME%.exe
    echo   请检查 dist\ 目录内容。
)

echo.
echo   提示: 首次启动可能需要几秒钟初始化。
echo   如遇 Windows Defender 误报，请选择 "仍要运行"。
echo.
pause
