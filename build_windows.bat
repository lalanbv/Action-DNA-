@echo off
:: build_windows.bat - Windows one-click build script for Action-DNA
:: Recommended: Python 3.12 / 3.13. Compatible with 3.11. 3.14+ is a fallback with a warning.
:: Windows 10/11 x64
:: Usage: double-click, or run "build_windows.bat" in cmd.
::
:: ENCODING (important - do not break): This file is PURE ASCII on purpose.
::   A .bat that contains Chinese/UTF-8 text breaks on Chinese Windows:
::     - With a UTF-8 BOM: the BOM is glued in front of the first line, so
::       "@echo off" is not recognized and every command gets echoed.
::     - Without a BOM: cmd reads the file as the OEM codepage (GBK/CP936),
::       so UTF-8 Chinese becomes mojibake and some byte sequences split
::       statements, producing errors like "'13' is not recognized".
::   Keeping the file ASCII avoids this whole class of bugs on any locale.
::   If Chinese output is mandatory, re-save THIS file as GBK (CP936) instead.

chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

title Action-DNA Windows Build

set APP_NAME=Action-DNA
set ENTRY_POINT=main.py
set VENV_DIR=.venv_build
:: Call the venv interpreter directly ("%VPY%"); do NOT "call activate.bat".
::   activate.bat carries its own "@echo off", which leaks the echo state into
::   this parent script. With echo on, the last echoed line becomes
::   "call activate.bat" and it looks frozen, while pip is silently working.
::   Calling the venv python.exe directly avoids that entirely.
set "VPY=%VENV_DIR%\Scripts\python.exe"
set REQUIRED_MAJOR=3
set REQUIRED_MINOR_MIN=11
set REQUIRED_MINOR_MAX=13

echo =========================================
echo   %APP_NAME% - Windows one-click build
echo =========================================
echo.

:: -- 1. Find Python (prefer 3.12/3.13, avoid 3.14) --
echo [1/6] Finding Python...

set PYTHON=
:: Round 1: accept only 3.11~3.13. The heavy stack (opencv/PySide6/numpy/
::          onnxruntime) ships the most complete prebuilt wheels in this range,
::          which maximizes the packaging success rate.
:: Note 1: "py -3.x" contains a space, so it MUST be quoted in the for-list,
::         otherwise for splits it into the tokens "py" and "-3.x".
:: Note 2: Guard with "if defined FOUND_MAJOR" to defend against the Windows
::         Store python stub, which returns 0 yet prints no version; an empty
::         string in the comparison would trigger a syntax error.
for %%C in ("py -3.12" "py -3.13" "py -3.11" python python3) do (
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
                if !FOUND_MAJOR! equ %REQUIRED_MAJOR% if !FOUND_MINOR! geq %REQUIRED_MINOR_MIN% if !FOUND_MINOR! leq %REQUIRED_MINOR_MAX% (
                    set PYTHON=%%C
                    set PY_VERSION=!PY_VER_RAW!
                )
            )
        )
    )
)

:: Round 2: if still not found, fall back to any Python >= 3.11 (incl. 3.14)
::          and warn clearly. 3.14 is new; some deps may lack cp314 wheels. If
::          this round later fails at numpy with "from versions: none", install
::          3.12 or 3.13 and retry.
if not defined PYTHON (
    echo   [WARN] 3.11~3.13 not found, falling back to any Python ^>= 3.11 ...
    for %%C in ("py -3.14" "py -3.15" python python3) do (
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
)

if not defined PYTHON (
    echo   [FAIL] Python ^>= 3.11 not found
    echo   Recommended: install Python 3.12 or 3.13 (best wheel coverage)
    echo   Download: https://www.python.org/downloads/
    echo   Tick "Add Python to PATH" during install
    pause
    exit /b 1
)

echo   [OK] Python !PY_VERSION! (!PYTHON!)

:: -- 2. Check architecture --
echo.
echo [2/6] Checking environment...

for /f %%A in ('%PYTHON% -c "import struct; print(\"64-bit\" if struct.calcsize(\"P\")*8==64 else \"32-bit\")"') do set ARCH=%%A
echo   [OK] !ARCH! Python

:: -- 3. Create/reuse virtualenv (not activated; use %VPY% directly) --
echo.
echo [3/6] Preparing build virtualenv...

:: If a venv exists but its Python version differs, remove and recreate it.
if exist "%VENV_DIR%\pyvenv.cfg" (
    for /f "tokens=1,2 delims== " %%A in ('findstr /b "version" "%VENV_DIR%\pyvenv.cfg"') do set VENV_VER=%%B
    set VENV_VER=!VENV_VER:~0,4!
    for /f "tokens=1,2 delims=." %%A in ("!PY_VERSION!") do set CUR_VER=%%A.%%B
    if "!VENV_VER!" neq "!CUR_VER!" (
        echo   [INFO] Virtualenv Python !VENV_VER! does not match current !CUR_VER!, rebuilding...
        rmdir /s /q "%VENV_DIR%" 2>nul
    )
)

if not exist "%VPY%" (
    echo   Creating build virtualenv...
    %PYTHON% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo   [FAIL] Failed to create virtualenv
        pause
        exit /b 1
    )
    echo   [OK] Virtualenv created
) else (
    echo   [OK] Reusing existing virtualenv
)

:: Upgrade pip (show output; on failure only warn, do not abort - pip usually still works)
echo   Upgrading pip...
"%VPY%" -m pip install --upgrade pip
if !errorlevel! neq 0 (
    echo   [WARN] pip upgrade failed, continuing with the current version
)

:: -- 4. Install dependencies --
echo.
echo [4/6] Installing dependencies...
echo   [INFO] First run downloads opencv / PySide6 / numpy etc. (hundreds of MB);
echo          it may take several minutes. Download progress scrolls on screen.
echo          Only worry if there is NO output for a long time.

"%VPY%" -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo   [FAIL] Failed to install project dependencies
    echo   Common cause: Python is too new (e.g. 3.14) and lacks prebuilt wheels;
    echo            the error looks like "from versions: none". Install 3.12/3.13.
    pause
    exit /b 1
)
echo   [OK] Project dependencies installed

echo   Installing PyInstaller...
"%VPY%" -m pip install pyinstaller
if !errorlevel! neq 0 (
    echo   [FAIL] Failed to install PyInstaller
    pause
    exit /b 1
)
:: Read the version via a temp file to avoid for/f quote-escaping headaches.
"%VPY%" -m PyInstaller --version >"%TEMP%\adna_pyiver.txt" 2>nul
set PYI_VER=
if exist "%TEMP%\adna_pyiver.txt" set /p PYI_VER=<"%TEMP%\adna_pyiver.txt"
del "%TEMP%\adna_pyiver.txt" >nul 2>&1
echo   [OK] PyInstaller !PYI_VER! ready

:: Check the optional OCR dependency
"%VPY%" -m pip show rapidocr_onnxruntime >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] rapidocr_onnxruntime installed (OCR enabled)
) else (
    echo   [INFO] rapidocr_onnxruntime not installed, OCR will degrade gracefully
)

:: -- 5. Clean previous build --
echo.
echo [5/6] Cleaning previous build...
if exist build rmdir /s /q build 2>nul
if exist dist  rmdir /s /q dist  2>nul
del /q *.spec 2>nul
echo   [OK] Cleaned

:: -- 6. Generate the spec file and build --
echo.
echo [6/6] Running PyInstaller...
echo.

:: Generate the spec file (avoids cmd line-length limits and escaping issues).
:: Key: every ( and ) inside the ( ... ) echo block MUST be escaped as ^( and ^),
:: otherwise cmd's character-by-character parenthesis counting becomes unbalanced
:: and it aborts with "( was unexpected".
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

:: Build with the spec file (invoked as a module, no activate needed)
"%VPY%" -m PyInstaller --noconfirm --clean "%APP_NAME%.spec" 2>&1

if !errorlevel! neq 0 (
    echo.
    echo   [FAIL] PyInstaller build failed; check the errors above.
    pause
    exit /b 1
)

:: Verify output
echo.
if exist "dist\%APP_NAME%\%APP_NAME%.exe" (
    echo =========================================
    echo   Build complete!
    echo =========================================
    echo.
    echo   [OK] Output dir: dist\%APP_NAME%\
    echo   [OK] Executable: dist\%APP_NAME%\%APP_NAME%.exe
    echo.
    echo   To run:
    echo     dist\%APP_NAME%\%APP_NAME%.exe
    echo.
    echo   To distribute:
    echo     zip the dist\%APP_NAME%\ folder
    echo.
) else (
    echo   [FAIL] Expected output not found: dist\%APP_NAME%\%APP_NAME%.exe
    echo   Check the dist\ folder.
)

echo.
echo   Tip: first launch may take a few seconds to initialize.
echo   If Windows Defender flags it, choose "Run anyway".
echo.
pause
