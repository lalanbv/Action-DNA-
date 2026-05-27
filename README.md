# Action\<DNA\>

Action\<DNA\> — 通过浏览器层截图 + 模板匹配 + OCR + 像素搜索 + 模拟鼠标键盘实现自动化。

## 功能特性

- **动作链自动化** — 顺序执行预设动作步骤（点击图片、等待、按键等）
- **DAG 工作流编辑器** — 可视化拖拽编辑有向无环图，支持条件分支和循环
- **宏录制** — 录制鼠标键盘操作并回放
- **插件系统** — 自定义节点描述符和对话框扩展引擎能力
- **通知系统** — 系统通知/声音/Webhook 多渠道告警
- **定时调度** — 按计划自动启动/停止工作流
- **防检测** — 鼠标轨迹缓动、随机延迟、坐标偏移
- **国际化** — 中文/英文切换，暗色/亮色主题

## 系统要求

- Python 3.11+
- macOS / Windows
- 显示器（需要屏幕截图能力）

## 安装

```bash
git clone <repo-url> Action-DNA
cd Action-DNA

python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

### 可选依赖

```bash
# OCR 文字识别（不安装时自动降级跳过）
pip install rapidocr_onnxruntime
```

## 使用

```bash
python main.py
```

1. 主页选择功能卡片
2. 可选：框选浏览器云游戏窗口区域
3. 添加动作步骤或编辑工作流 DAG
4. 保存配置 → 下次可直接加载
5. 点击「启动」循环执行

## 一键打包

项目内置 PyInstaller 打包脚本，可将应用打包为独立可执行文件，无需用户安装 Python。

### 前置要求

- Python 3.11 ~ 3.14+（3.11、3.12、3.13、3.14 均已测试兼容）
- macOS 12+ 或 Windows 10/11
- 约 1 GB 磁盘空间（构建临时文件 + 产出）

### macOS

```bash
# 赋予执行权限（仅需一次）
chmod +x build_mac.sh

# 执行打包
./build_mac.sh
```

脚本会自动：检测 Python 版本 → 创建隔离构建环境 → 安装依赖 → 执行打包 → 验证产出。

打包完成后：

- 产出目录：`dist/Action-DNA/`
- 启动方式：`open dist/Action-DNA/Action-DNA.app`
- 分发方式：将 `dist/Action-DNA/` 压缩为 `.zip`

### Windows

```cmd
:: 双击运行或在 cmd 中执行
build_windows.bat
```

脚本会自动：搜索 Python 3.11+ → 创建隔离构建环境 → 安装依赖 → 生成 .spec → 打包 → 验证产出。

打包完成后：

- 产出目录：`dist\Action-DNA\`
- 启动方式：`dist\Action-DNA\Action-DNA.exe`
- 分发方式：将 `dist\Action-DNA\` 压缩为 `.zip`

### 打包说明

| 项目 | 说明 |
| --- | --- |
| 打包工具 | PyInstaller（自动安装最新版） |
| 构建环境 | 独立虚拟环境 `.venv_build/`，不影响开发环境 |
| Python 版本 | 3.11 / 3.12 / 3.13 / 3.14 全部兼容 |
| 数据文件 | `config/`、`assets/`、翻译文件自动检测并打包 |
| OCR 支持 | 安装 `rapidocr_onnxruntime` 后打包即包含 OCR，否则自动降级 |
| 架构适配 | macOS: Apple Silicon + Intel 自动识别；Windows: x64 |
| 版本迁移 | 切换 Python 版本后自动重建虚拟环境 |

### 常见问题

| 问题 | 解决方案 |
| --- | --- |
| macOS 提示"无法验证开发者" | 系统设置 > 隐私与安全性 > 允许 |
| Windows Defender 误报 | 选择"仍要运行"，或将 `dist/` 目录加入排除项 |
| 找不到 Python | macOS: `brew install python@3.12`；Windows: 安装时勾选 "Add Python to PATH" |
| 想包含 OCR | 打包前执行 `pip install rapidocr_onnxruntime`，再运行打包脚本 |
| 构建环境损坏 | 删除 `.venv_build/` 目录后重新执行打包脚本 |

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    PanelApp (tkinter)                    │
│  HomePage → ActionChain | Workflow | Plugin | Record... │
└────────────┬──────────────────────────────┬─────────────┘
             │                              │
    ┌────────▼────────┐           ┌─────────▼──────────┐
    │ ActionExecutor   │           │   GraphEngine      │
    │ (v1 顺序执行)    │           │  (v2 DAG 拓扑排序) │
    └────────┬────────┘           └─────────┬──────────┘
             │                              │
    ┌────────▼──────────────────────────────▼──────────┐
    │              Layer 中间件管道                      │
    │  EventBridge → Retry → Timing → Logging → ...    │
    └────────────────────┬────────────────────────────┘
                         │
    ┌────────────────────▼────────────────────────────┐
    │           NodeDescriptor (16 种)                 │
    │  ClickImage | OCR | PixelSearch | Condition ... │
    └────────────────────┬────────────────────────────┘
                         │
    ┌────────────────────▼────────────────────────────┐
    │       VisionPipeline + InputController           │
    │  截图(mss) | 模板匹配(OpenCV) | OCR | 模拟输入   │
    └─────────────────────────────────────────────────┘
```

### 核心模块

| 模块 | 路径 | 说明 |
| --- | --- | --- |
| 执行引擎 | `src/core/engine/` | DAG 拓扑排序 + FSM 状态机 |
| 描述符 | `src/core/engine/descriptors/` | 16 种节点类型实现 |
| Layer 管道 | `src/core/layers/` | 7 层中间件（重试/日志/断点等） |
| 变量系统 | `src/core/variables/` | 类型化变量池 + 作用域 |
| 事件总线 | `src/core/events/` | 发布/订阅事件系统 |
| 视觉检测 | `src/core/vision/` | 模板匹配 + OCR + 像素搜索 |
| 插件系统 | `src/core/plugins/` | 动态加载 + 自定义描述符注册 |
| GUI 面板 | `src/panel/` | tkinter 页面路由 + 画布编辑器 |

## 测试

```bash
# 运行全部测试
pytest

# 按类别运行
pytest -m unit          # 单元测试
pytest -m integration   # 集成测试
pytest -m e2e           # 端到端测试

# 覆盖率报告
pytest --cov=src --cov-report=term-missing
```

## 项目结构

```
src/
├── core/           # 核心引擎（engine/layers/variables/events/vision/plugins）
├── panel/          # GUI 面板（canvas/components/dialogs/pages）
├── plugins/        # 内置插件（combat/navigation/task）
├── notification/   # 通知系统（channels: system/sound/webhook）
├── recorder/       # 宏录制
├── schedule/       # 定时调度
├── game/           # 游戏特定逻辑
└── utils/          # 工具（i18n/paths/timing）
```

详细结构见 [CLAUDE.md](CLAUDE.md)。

## 插件开发

见 [docs/plugin_guide.md](docs/plugin_guide.md)。

## 许可证

私有项目，未授权禁止使用。
