"""ErrorRegistry — 数值错误码 + 消息模板注册表。

参考 Cocos4 的数值错误 ID 模式，为 Action<DNA> 提供紧凑的错误码和
模板化消息。每个错误码是一个 int，按领域分段：

    1000–1999  视觉检测
    2000–2999  输入模拟
    3000–3999  引擎执行
    4000–4999  插件系统
    5000–5999  系统层

使用方式：
    err = ErrorRegistry.create(1001, template_path="enemy.png")
    # → StandardizedError(code=TEMPLATE_NOT_FOUND, message="模板未找到: enemy.png", ...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.error.error_codes import StandardErrorCode, StandardizedError
from src.utils.i18n import t

__all__ = ["ErrorRegistry", "ErrorCategory"]


class ErrorCategory:
    """错误码分段常量。"""

    VISION = 1000
    INPUT = 2000
    ENGINE = 3000
    PLUGIN = 4000
    SYSTEM = 5000


@dataclass(frozen=True)
class _ErrorTemplate:
    """注册表中的错误模板。"""

    code: int
    standard_code: StandardErrorCode
    message_template: str
    recovery_template: str


class ErrorRegistry:
    """数值错误码 → StandardizedError 工厂。

    线程安全（只读注册表，初始化后不变）。
    """

    _templates: dict[int, _ErrorTemplate] = {}
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls) -> None:
        if cls._initialized:
            return
        cls._register_all()
        cls._initialized = True

    @classmethod
    def reset(cls) -> None:
        """重置注册表（仅用于测试隔离）。"""
        cls._templates.clear()
        cls._initialized = False

    @classmethod
    def _register_all(cls) -> None:
        """注册所有错误模板。"""
        templates = [
            # ── 视觉检测 1000–1999 ──
            _ErrorTemplate(
                code=1001,
                standard_code=StandardErrorCode.TEMPLATE_NOT_FOUND,
                message_template="模板未找到: {template_path}",
                recovery_template="检查模板图片路径是否正确",
            ),
            _ErrorTemplate(
                code=1002,
                standard_code=StandardErrorCode.TEMPLATE_MATCH_THRESHOLD,
                message_template="模板匹配度低于阈值: {threshold}",
                recovery_template="尝试降低阈值或使用更清晰的模板图片",
            ),
            _ErrorTemplate(
                code=1003,
                standard_code=StandardErrorCode.OCR_UNAVAILABLE,
                message_template="OCR 引擎不可用",
                recovery_template="安装 rapidocr_onnxruntime: pip install rapidocr_onnxruntime",
            ),
            _ErrorTemplate(
                code=1004,
                standard_code=StandardErrorCode.OCR_RECOGNITION_FAILED,
                message_template="OCR 识别失败: {reason}",
                recovery_template="检查截图区域是否包含清晰文字",
            ),
            _ErrorTemplate(
                code=1005,
                standard_code=StandardErrorCode.PIXEL_NOT_FOUND,
                message_template="目标颜色像素未找到: RGB{target_color}",
                recovery_template="增大容差值或检查目标区域",
            ),
            _ErrorTemplate(
                code=1006,
                standard_code=StandardErrorCode.VISION_PREPROCESS_FAILED,
                message_template="图像预处理失败: {reason}",
                recovery_template="检查 OpenCV 安装",
            ),
            # ── 输入模拟 2000–2999 ──
            _ErrorTemplate(
                code=2001,
                standard_code=StandardErrorCode.INPUT_TARGET_OUT_OF_BOUNDS,
                message_template="目标坐标超出屏幕范围: ({x}, {y})",
                recovery_template="重新框选目标区域",
            ),
            _ErrorTemplate(
                code=2002,
                standard_code=StandardErrorCode.INPUT_MOUSE_MOVE_FAILED,
                message_template="鼠标移动失败: {reason}",
                recovery_template="检查辅助功能权限",
            ),
            _ErrorTemplate(
                code=2003,
                standard_code=StandardErrorCode.INPUT_KEY_UNSUPPORTED,
                message_template="不支持的按键: {key}",
                recovery_template="使用标准键名",
            ),
            # ── 引擎执行 3000–3999 ──
            _ErrorTemplate(
                code=3001,
                standard_code=StandardErrorCode.ENGINE_GRAPH_INVALID,
                message_template="图结构无效: {reason}",
                recovery_template="检查节点连接和起始/结束节点",
            ),
            _ErrorTemplate(
                code=3002,
                standard_code=StandardErrorCode.ENGINE_NODE_TIMEOUT,
                message_template="节点执行超时: {node_id} ({timeout}s)",
                recovery_template="增加节点超时时间或优化节点逻辑",
            ),
            _ErrorTemplate(
                code=3003,
                standard_code=StandardErrorCode.ENGINE_LOOP_LIMIT,
                message_template="循环次数超限: {loop_count}/{max_loop}",
                recovery_template="检查循环退出条件或增大最大循环次数",
            ),
            _ErrorTemplate(
                code=3004,
                standard_code=StandardErrorCode.ENGINE_STOPPED,
                message_template="引擎已停止",
                recovery_template="重新启动执行",
            ),
            # ── 插件系统 4000–4999 ──
            _ErrorTemplate(
                code=4001,
                standard_code=StandardErrorCode.PLUGIN_LOAD_FAILED,
                message_template="插件加载失败: {plugin_name} — {reason}",
                recovery_template="检查插件目录和 plugin.json 格式",
            ),
            _ErrorTemplate(
                code=4002,
                standard_code=StandardErrorCode.PLUGIN_PERMISSION_DENIED,
                message_template="插件权限不足: {plugin_name} (需要 '{permission}')",
                recovery_template="在 plugin.json 的 permissions 中添加 '{permission}'",
            ),
            _ErrorTemplate(
                code=4003,
                standard_code=StandardErrorCode.PLUGIN_VERSION_MISMATCH,
                message_template="插件版本不匹配: {plugin_name} (需要 {required}, 当前 {actual})",
                recovery_template="更新插件或引擎版本",
            ),
            # ── 系统层 5000–5999 ──
            _ErrorTemplate(
                code=5001,
                standard_code=StandardErrorCode.SYSTEM_SCREENSHOT_FAILED,
                message_template="截图失败: {reason}",
                recovery_template="检查屏幕录制权限",
            ),
            _ErrorTemplate(
                code=5002,
                standard_code=StandardErrorCode.SYSTEM_FILE_NOT_FOUND,
                message_template="文件未找到: {file_path}",
                recovery_template="检查文件路径是否正确",
            ),
        ]

        for tpl in templates:
            cls._templates[tpl.code] = tpl

    @classmethod
    def create(
        cls,
        error_id: int,
        **context: Any,
    ) -> StandardizedError:
        """根据数值 ID 创建 StandardizedError。

        参数：
            error_id: 数值错误码（如 1001）
            **context: 模板变量（如 template_path="enemy.png"）

        返回：
            StandardizedError 实例

        异常：
            KeyError: 未知错误码
        """
        cls._ensure_initialized()
        tpl = cls._templates.get(error_id)
        if tpl is None:
            raise KeyError(t("error.exc.unknown_error_code", error_id=error_id))

        message = tpl.message_template.format(**context) if context else tpl.message_template
        recovery = tpl.recovery_template

        return StandardizedError(
            code=tpl.standard_code,
            message=message,
            recovery_suggestion=recovery,
            context=context,
        )

    @classmethod
    def to_numeric(cls, standard_code: StandardErrorCode) -> int:
        """将 StandardErrorCode 转为数值 ID。"""
        cls._ensure_initialized()
        for eid, tpl in cls._templates.items():
            if tpl.standard_code == standard_code:
                return eid
        raise KeyError(t("error.exc.unregistered_standard_code", standard_code=str(standard_code)))
