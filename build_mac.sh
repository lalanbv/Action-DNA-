#!/usr/bin/env bash
# build_mac.sh — macOS 一键打包脚本
# 兼容 Python 3.11 ~ 3.14+，macOS Intel / Apple Silicon
# 使用方法: ./build_mac.sh

set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="Action-DNA"
ENTRY_POINT="main.py"
VENV_DIR=".venv_build"
REQUIRED_MAJOR=3
REQUIRED_MINOR=11

# 颜色输出
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}○${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; exit 1; }

echo "========================================="
echo "  ${APP_NAME} — macOS 一键打包"
echo "========================================="
echo ""

# ── 1. 查找 Python ──
echo "[1/6] 查找 Python..."

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        # 验证版本 >= 3.11
        VER=$("$cmd" -c "
import sys
v = sys.version_info
print(f'{v.major}.{v.minor}')
" 2>/dev/null) || continue

        MAJOR=$(echo "$VER" | cut -d. -f1)
        MINOR=$(echo "$VER" | cut -d. -f2)

        if [ "$MAJOR" -gt "$REQUIRED_MAJOR" ] || { [ "$MAJOR" -eq "$REQUIRED_MAJOR" ] && [ "$MINOR" -ge "$REQUIRED_MINOR" ]; }; then
            PYTHON="$cmd"
            ok "Python ${VER} (${cmd})"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "未找到 Python >= ${REQUIRED_MAJOR}.${REQUIRED_MINOR}，请从 https://www.python.org/downloads/ 安装"
fi

# ── 2. 检查架构 ──
echo ""
echo "[2/6] 检查运行环境..."

ARCH=$(uname -m)
case "$ARCH" in
    arm64)  ok "Apple Silicon (${ARCH})" ;;
    x86_64) ok "Intel (${ARCH})" ;;
    *)      warn "未识别架构: ${ARCH}" ;;
esac

MACOS_VER=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
ok "macOS ${MACOS_VER}"

# ── 3. 创建/激活虚拟环境 ──
echo ""
echo "[3/6] 准备构建虚拟环境..."

# 如果 venv 存在但 Python 版本不匹配，删除重建
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/pyvenv.cfg" ]; then
    VENV_VER=$(grep -m1 '^version' "$VENV_DIR/pyvenv.cfg" | sed 's/.*= *//' | cut -c1-4)
    CUR_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if [ "$VENV_VER" != "$CUR_VER" ]; then
        warn "虚拟环境 Python ${VENV_VER} 与当前 ${CUR_VER} 不匹配，重建..."
        rm -rf "$VENV_DIR"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR" || fail "创建虚拟环境失败"
    ok "虚拟环境已创建"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 升级 pip（兼容所有版本）
python -m pip install --upgrade pip --quiet 2>/dev/null || \
    python -m pip install --upgrade pip 2>/dev/null || \
    warn "pip 升级失败，继续使用当前版本"

# ── 4. 安装依赖 ──
echo ""
echo "[4/6] 安装依赖..."

pip install --quiet -r requirements.txt || fail "安装项目依赖失败"
ok "项目依赖已安装"

pip install --quiet pyinstaller || fail "安装 PyInstaller 失败"
PYI_VER=$(pyinstaller --version 2>/dev/null || echo "unknown")
ok "PyInstaller ${PYI_VER}"

# 检查 OCR 可选依赖
if pip show rapidocr_onnxruntime &>/dev/null; then
    ok "rapidocr_onnxruntime 已安装（含 OCR 支持）"
else
    warn "rapidocr_onnxruntime 未安装，OCR 功能将降级"
fi

# ── 5. 清理旧构建 ──
echo ""
echo "[5/6] 清理旧构建..."
rm -rf build/ dist/ *.spec 2>/dev/null || true
ok "清理完成"

# ── 6. 执行 PyInstaller 打包 ──
echo ""
echo "[6/6] 执行 PyInstaller 打包..."
echo ""

# 构建 --add-data 参数（自动跳过不存在的目录）
ADD_DATA_ARGS=()
for pair in \
    "config:config" \
    "assets:assets" \
    "src/utils/translations:src/utils/translations" \
    "src/plugins/builtin:src/plugins/builtin" \
    "docs:docs"
do
    SRC=$(echo "$pair" | cut -d: -f1)
    if [ -d "$SRC" ]; then
        ADD_DATA_ARGS+=(--add-data "$pair")
    fi
done

# 构建 --hidden-import 列表
HIDDEN_IMPORTS=(
    pynput.keyboard._darwin
    pynput.mouse._darwin
    pynput.keyboard
    pynput.mouse
    pyautogui
    mss
    PIL
    numpy
    cv2
    tkinter
    tkinter.filedialog
    tkinter.messagebox
    tkinter.colorchooser
    tkinter.scrolledtext
    tkinter.ttk
    PySide6.QtWidgets
    PySide6.QtCore
    PySide6.QtGui
    src.panel.qt_backend
    src.panel.qt_backend.app
    src.plugins.builtin.combat
    src.plugins.builtin.navigation
    src.plugins.builtin.task
    unittest.mock
)

HIDDEN_ARGS=()
for mod in "${HIDDEN_IMPORTS[@]}"; do
    HIDDEN_ARGS+=(--hidden-import "$mod")
done

pyinstaller \
    --name "$APP_NAME" \
    --noconfirm \
    --clean \
    --windowed \
    "${ADD_DATA_ARGS[@]}" \
    "${HIDDEN_ARGS[@]}" \
    --osx-bundle-identifier "com.action-dna.app" \
    "$ENTRY_POINT" \
    2>&1 || fail "PyInstaller 打包失败，请检查上方错误信息"

# 验证产出
echo ""
if [ -d "dist/${APP_NAME}.app" ] || [ -d "dist/${APP_NAME}/${APP_NAME}.app" ]; then
    echo "========================================="
    echo "  打包完成!"
    echo "========================================="
    echo ""
    ok "产出目录: dist/${APP_NAME}/"
    ok "可执行文件: dist/${APP_NAME}/${APP_NAME}.app"
    echo ""
    echo "  启动方式:"
    echo "    open dist/${APP_NAME}/${APP_NAME}.app"
    echo ""
    echo "  分发方式:"
    echo "    压缩 dist/${APP_NAME}/ 目录为 .zip"
    echo ""

    # 计算产出大小（兼容 onedir 和 onefile 两种布局）
    if [ -d "dist/${APP_NAME}" ]; then
        DIST_SIZE=$(du -sh "dist/${APP_NAME}" 2>/dev/null | cut -f1)
    elif [ -d "dist/${APP_NAME}.app" ]; then
        DIST_SIZE=$(du -sh "dist/${APP_NAME}.app" 2>/dev/null | cut -f1)
    else
        DIST_SIZE="unknown"
    fi
    ok "产出大小: ${DIST_SIZE}"
else
    fail "打包后未找到预期产出，请检查 dist/ 目录"
fi

echo ""
echo "  提示: 首次启动可能需要几秒钟初始化。"
echo "  如遇 macOS 安全提示，请前往 系统设置 > 隐私与安全性 > 允许。"
echo ""
