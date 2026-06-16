@echo off
:: build_windows.bat - Action-DNA Windows one-click build
:: Compatible with ANY CPython >= 3.11 (3.11 / 3.12 / 3.13 / 3.14 / 3.15 ...).
:: Windows 10/11 x64. Usage: double-click, or run "build_windows.bat" in cmd.
::
:: LAYERED DESIGN (bottom-up):
::   L0 Encoding : PURE ASCII on purpose (see ENCODING NOTE below).
::   L1 Python   : auto-detect any CPython >= 3.11 on PATH or via the py launcher.
::   L2 Virtualenv: build into .venv_build; reuse if same Python, rebuild if not.
::   L3 pip index: Tsinghua mirror first (reliable in CN), official PyPI fallback.
::   L4 pip      : upgrade pip (non-fatal).
::   L5 Deps     : install requirements.txt (mirror first, official fallback).
::   L6 PyInstaller: install + version check.
::   L7 Clean    : remove previous build/spec.
::   L8 Build    : generate spec + run PyInstaller.
::   L9 Verify   : check the produced exe.
::
:: ENV OVERRIDES (optional):
::   ADNA_PIP_INDEX   - pip index URL (default: Tsinghua mirror).
::   ADNA_PIP_TRUSTED - trusted host for the index (default: pypi.tuna.tsinghua.edu.cn).
::   HTTPS_PROXY/HTTP_PROXY - pip honours these automatically for proxy networks.
::
:: ENCODING NOTE (do NOT break): This file is PURE ASCII.
::   A .bat with Chinese/UTF-8 text breaks on Chinese Windows:
::     - UTF-8 with BOM   : the BOM is glued before line 1, so "@echo off" is
::                          ignored and every command is echoed.
::     - UTF-8 without BOM: cmd reads it as the OEM codepage (GBK/CP936); UTF-8
::                          Chinese becomes mojibake and some bytes split
::                          statements (errors like "'13' is not recognized").
::   ASCII works on every locale. If Chinese output is mandatory, re-save as GBK.

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Action-DNA Windows Build

set "APP_NAME=Action-DNA"
set "ENTRY_POINT=main.py"
set "VENV_DIR=.venv_build"
:: Virtualenv interpreter, called directly. We do NOT "call activate.bat":
:: it leaks its own @echo off into this script and hides pip progress, which
:: previously made the build look frozen at "call activate.bat".
set "VPY=%VENV_DIR%\Scripts\python.exe"
set "REQUIRED_MAJOR=3"
set "REQUIRED_MINOR_MIN=11"

:: pip index: Tsinghua mirror by default (fast and reliable from China).
:: Official PyPI is ALWAYS tried as an automatic fallback if the mirror fails,
:: so this also works outside China (just slower on the first miss).
set "PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
set "PIP_TRUSTED=pypi.tuna.tsinghua.edu.cn"
if defined ADNA_PIP_INDEX set "PIP_INDEX=%ADNA_PIP_INDEX%"
if defined ADNA_PIP_TRUSTED set "PIP_TRUSTED=%ADNA_PIP_TRUSTED%"

echo =========================================
echo   %APP_NAME% - Windows one-click build
echo =========================================
echo.

:: ============================================================
:: [L1] Find Python - accept ANY CPython >= 3.11
:: ============================================================
echo [L1] Finding Python CPython ^>= 3.11 ...

set PYTHON=
:: Probe order: the user's PATH default first, then the py launcher across
:: current and near-future versions. The FIRST one that is >= 3.11 wins, so
:: whatever the user has (3.13, 3.14, both...) just works.
:: Note 1: "py -3.x" contains a space, so it MUST be quoted in the for-list,
::         otherwise for splits it into "py" and "-3.x".
:: Note 2: "if defined FOUND_MAJOR" guards against the Windows Store python
::         stub, which exits 0 but prints no version (empty compare = syntax error).
for %%C in (python python3 "py -3.14" "py -3.13" "py -3.12" "py -3.11" "py -3.15") do (
    if not defined PYTHON (
        set FOUND_MAJOR=
        set FOUND_MINOR=
        set PY_VER_RAW=
        %%C --version >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=2 delims= " %%V in ('%%C --version 2^>^&1') do set PY_VER_RAW=%%V
            for /f "tokens=1,2 delims=." %%A in ("!PY_VER_RAW!") do (
                set FOUND_MAJOR=%%A
                set FOUND_MINOR=%%B
            )
            if defined FOUND_MAJOR (
                if !FOUND_MAJOR! gtr %REQUIRED_MAJOR% (
                    set PYTHON=%%C
                    set PY_VERSION=!PY_VER_RAW!
                )
                if !FOUND_MAJOR! equ %REQUIRED_MAJOR% if !FOUND_MINOR! geq %REQUIRED_MINOR_MIN% (
                    set PYTHON=%%C
                    set PY_VERSION=!PY_VER_RAW!
                )
            )
        )
    )
)

if not defined PYTHON (
    echo   [FAIL] No CPython ^>= 3.11 found.
    echo   Install Python 3.11+ from https://www.python.org/downloads/
    echo   and tick "Add Python to PATH".
    pause
    exit /b 1
)
echo   [OK] Python !PY_VERSION! - !PYTHON!

:: ============================================================
:: [L2] Check architecture
:: ============================================================
echo.
echo [L2] Checking architecture...
for /f %%A in ('%PYTHON% -c "import struct; print(\"64-bit\" if struct.calcsize(\"P\")*8==64 else \"32-bit\")"') do set ARCH=%%A
echo   [OK] !ARCH! Python

:: ============================================================
:: [L3] Prepare virtualenv (reuse if same Python, rebuild if not)
:: ============================================================
echo.
echo [L3] Preparing build virtualenv...

if exist "%VENV_DIR%\pyvenv.cfg" (
    set VENV_VER=
    for /f "tokens=2 delims== " %%A in ('findstr /b /i "version" "%VENV_DIR%\pyvenv.cfg"') do set VENV_VER=%%A
    set VENV_VER=!VENV_VER:~0,4!
    for /f "tokens=1,2 delims=." %%A in ("!PY_VERSION!") do set CUR_VER=%%A.%%B
    if /i "!VENV_VER!" neq "!CUR_VER!" (
        echo   [INFO] Existing venv is Python !VENV_VER!, current is !CUR_VER! - rebuilding...
        rmdir /s /q "%VENV_DIR%" 2>nul
    )
)

if not exist "%VPY%" (
    echo   Creating build virtualenv with !PY_VERSION! ...
    %PYTHON% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo   [FAIL] Could not create the virtualenv.
        pause
        exit /b 1
    )
    echo   [OK] Virtualenv created
) else (
    echo   [OK] Reusing existing virtualenv
)

:: ============================================================
:: [L4] Upgrade pip (non-fatal)
:: ============================================================
echo.
echo [L4] Upgrading pip via !PIP_INDEX! ...
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check --no-input -i "%PIP_INDEX%" --trusted-host "%PIP_TRUSTED%"
if !errorlevel! neq 0 echo   [WARN] pip upgrade failed - continuing with the bundled pip.

:: ============================================================
:: [L5] Install project dependencies (mirror first, official fallback)
:: ============================================================
echo.
echo [L5] Installing project dependencies...
echo   [INFO] First run downloads opencv / PySide6 / numpy etc., hundreds of MB.
echo          This may take several minutes; progress scrolls on screen.
echo          Only worry if there is NO output for a long time.

set DEPS_OK=
"%VPY%" -m pip install -r requirements.txt --prefer-binary --disable-pip-version-check --no-input -i "%PIP_INDEX%" --trusted-host "%PIP_TRUSTED%" && set DEPS_OK=1
if not "!DEPS_OK!"=="1" (
    echo   [WARN] Mirror install failed - retrying with official PyPI...
    "%VPY%" -m pip install -r requirements.txt --prefer-binary --disable-pip-version-check --no-input && set DEPS_OK=1
)
if not "!DEPS_OK!"=="1" (
    echo.
    echo   [FAIL] Could not install project dependencies from either source.
    echo          Check your network / proxy / firewall.
    echo          To use a different mirror, set ADNA_PIP_INDEX and ADNA_PIP_TRUSTED.
    pause
    exit /b 1
)
echo   [OK] Project dependencies installed

:: ============================================================
:: [L6] Install PyInstaller + version check
:: ============================================================
echo.
echo [L6] Installing PyInstaller...
set PYI_OK=
"%VPY%" -m pip install pyinstaller --prefer-binary --disable-pip-version-check --no-input -i "%PIP_INDEX%" --trusted-host "%PIP_TRUSTED%" && set PYI_OK=1
if not "!PYI_OK!"=="1" (
    echo   [WARN] Mirror install failed - retrying with official PyPI...
    "%VPY%" -m pip install pyinstaller --prefer-binary --disable-pip-version-check --no-input && set PYI_OK=1
)
if not "!PYI_OK!"=="1" (
    echo   [FAIL] Could not install PyInstaller.
    pause
    exit /b 1
)
:: Read the version via a temp file to avoid for/f quote-escaping headaches.
"%VPY%" -m PyInstaller --version >"%TEMP%\adna_pyiver.txt" 2>nul
set PYI_VER=
if exist "%TEMP%\adna_pyiver.txt" set /p PYI_VER=<"%TEMP%\adna_pyiver.txt"
del "%TEMP%\adna_pyiver.txt" >nul 2>&1
echo   [OK] PyInstaller !PYI_VER! ready

:: Optional OCR dependency check (graceful degradation if absent)
"%VPY%" -m pip show rapidocr_onnxruntime >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] rapidocr_onnxruntime installed - OCR enabled
) else (
    echo   [INFO] rapidocr_onnxruntime not installed - OCR will degrade gracefully
)

:: ============================================================
:: [L7] Clean previous build
:: ============================================================
echo.
echo [L7] Cleaning previous build...
if exist build rmdir /s /q build 2>nul
if exist dist  rmdir /s /q dist  2>nul
del /q *.spec 2>nul
echo   [OK] Cleaned

:: ============================================================
:: [L8] Generate spec file and build
:: ============================================================
echo.
echo [L8] Generating spec and running PyInstaller...
echo.

:: Every ( and ) inside the ( ... ) echo block MUST be escaped as ^( and ^),
:: otherwise cmd's character-by-character parenthesis counting becomes
:: unbalanced and it aborts with "( was unexpected".
(
echo # -*- mode: python ; coding: utf-8 -*-
echo.
echo import sys, os
echo.
echo block_cipher = None
echo.
echo a = Analysis^(
echo     ['main.py'],
echo     pathex=[],
echo     binaries=[],
echo     datas=[
if exist "config" (
    echo         ^('config', 'config'^),
)
if exist "assets" (
    echo         ^('assets', 'assets'^),
)
if exist "src\utils\translations" (
    echo         ^(r'src\utils\translations', 'src/utils/translations'^),
)
if exist "src\plugins\builtin" (
    echo         ^(r'src\plugins\builtin', 'src/plugins/builtin'^),
)
if exist "docs" (
    echo         ^('docs', 'docs'^),
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
echo pyz = PYZ^(a.pure, a.zipped_data, cipher=block_cipher^)
echo.
echo exe = EXE^(
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
echo coll = COLLECT^(
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

:: Build with the spec file (invoked as a module; no activate needed)
"%VPY%" -m PyInstaller --noconfirm --clean "%APP_NAME%.spec" 2>&1
if !errorlevel! neq 0 (
    echo.
    echo   [FAIL] PyInstaller build failed - see the errors above.
    pause
    exit /b 1
)

:: ============================================================
:: [L9] Verify output
:: ============================================================
echo.
if exist "dist\%APP_NAME%\%APP_NAME%.exe" (
    echo =========================================
    echo   Build complete!
    echo =========================================
    echo.
    echo   [OK] Output folder: dist\%APP_NAME%\
    echo   [OK] Executable:    dist\%APP_NAME%\%APP_NAME%.exe
    echo.
    echo   Run:        dist\%APP_NAME%\%APP_NAME%.exe
    echo   Distribute: zip the dist\%APP_NAME%\ folder
    echo.
) else (
    echo   [FAIL] Expected output not found: dist\%APP_NAME%\%APP_NAME%.exe
    echo   Inspect the dist\ folder.
)

echo.
echo   Tip: first launch may take a few seconds to initialize.
echo   If Windows Defender flags it, choose "Run anyway".
echo.
pause
