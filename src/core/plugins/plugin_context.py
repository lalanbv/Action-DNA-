"""PluginContext — 插件上下文，提供受控的服务访问。

调用者:
  - plugin_loader.py: 创建 PluginContext 实例传给 on_load()
  - 所有插件 on_load(context) 中使用 context.registry / context.event_bus 等
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.engine.node_registry import NodeRegistry
    from src.core.events.bus import TypedEventBus
    from src.core.input import InputController
    from src.core.vision import ScreenCapture, TemplateMatcher

from src.core.error.exceptions import PluginPermissionError
from src.core.plugins.plugin_node_registry import PluginNodeRegistry

logger = logging.getLogger(__name__)

# 允许插件读取的公共目录（相对于项目根目录）
_PUBLIC_READ_DIRS: tuple[str, ...] = ("assets", "config")
# 禁止写入的目录
_FORBIDDEN_WRITE_DIRS: tuple[str, ...] = ("src", "tests", "DNA_Design_Scheme")


class PluginContext:
    """插件上下文 — 插件加载时获得的受控环境。

    设计原则:
    - 最小权限: 默认只提供注册能力，其他服务需声明权限
    - 受控访问: 插件通过此上下文访问核心服务，不直接 import
    - 审计追踪: 所有注册操作都经过此上下文记录
    """

    def __init__(
        self,
        plugin_id: str,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        screen_capture: ScreenCapture | None = None,
        template_matcher: TemplateMatcher | None = None,
        input_controller: InputController | None = None,
        permissions: set[str] | None = None,
        plugin_dir: str = "",
        project_root: str = "",
    ) -> None:
        self._plugin_id = plugin_id
        self._node_registry = node_registry
        self._event_bus = event_bus
        self._screen_capture = screen_capture
        self._template_matcher = template_matcher
        self._input_controller = input_controller
        self._permissions = permissions or set()
        self._plugin_dir = plugin_dir
        self._project_root = project_root or os.getcwd()
        self._registered_types: list[str] = []
        self._registry: PluginNodeRegistry = PluginNodeRegistry(
            plugin_id=self._plugin_id,
            delegate=self._node_registry,
            on_register=self._on_node_registered,
        )

    # ---- 权限检查 ----

    def _check_permission(self, perm: str) -> None:
        """检查插件是否声明了指定权限，未声明则抛出 PluginPermissionError。"""
        if perm not in self._permissions:
            raise PluginPermissionError.from_code(
                4002,
                plugin_name=self._plugin_id,
                permission=perm,
            )

    def _resolve_plugin_dir(self) -> str:
        """解析插件目录路径。"""
        if self._plugin_dir:
            return self._plugin_dir
        # 回退：src/plugins/builtin/<plugin_id> 或 src/plugins/<plugin_id>
        builtin = os.path.join(self._project_root, "src", "plugins", "builtin", self._plugin_id)
        if os.path.isdir(builtin):
            return builtin
        return os.path.join(self._project_root, "src", "plugins", self._plugin_id)

    # ---- 节点注册 ----

    @property
    def registry(self) -> PluginNodeRegistry:
        """获取插件命名空间注册表（自动添加 plugin_id 前缀）。"""
        return self._registry

    def _on_node_registered(self, full_type_key: str) -> None:
        """节点注册回调（追踪和卸载时注销）。"""
        self._registered_types.append(full_type_key)

    @property
    def registered_types(self) -> list[str]:
        """此插件已注册的节点类型列表。"""
        return list(self._registered_types)

    # ---- 服务访问（权限控制）----

    @property
    def event_bus(self) -> TypedEventBus:
        """访问事件总线（需要 'events' 权限）。"""
        self._check_permission("events")
        return self._event_bus

    @property
    def screen_capture(self) -> ScreenCapture:
        """访问截图服务（需要 'screen_capture' 权限）。"""
        self._check_permission("screen_capture")
        if self._screen_capture is None:
            raise RuntimeError("截图服务未初始化")
        return self._screen_capture

    @property
    def template_matcher(self) -> TemplateMatcher:
        """访问模板匹配服务（需要 'template_matcher' 权限）。"""
        self._check_permission("template_matcher")
        if self._template_matcher is None:
            raise RuntimeError("模板匹配服务未初始化")
        return self._template_matcher

    @property
    def input_controller(self) -> InputController:
        """访问输入控制器（需要 'input_control' 权限）。"""
        self._check_permission("input_control")
        if self._input_controller is None:
            raise RuntimeError("输入控制器未初始化")
        return self._input_controller

    # ---- 文件和网络权限 ----

    def get_file_reader(self) -> object:
        """获取文件读取能力（需要 'file_read' 权限）。

        返回一个受控的文件读取器，限制访问范围为插件目录和公共只读目录。
        """
        self._check_permission("file_read")
        plugin_dir = self._resolve_plugin_dir()
        return _FileReaderProxy(self._plugin_id, plugin_dir, self._project_root)

    def get_file_writer(self) -> object:
        """获取文件写入能力（需要 'file_write' 权限）。

        返回一个受控的文件写入器，限制写入范围为插件目录、profiles、assets。
        """
        self._check_permission("file_write")
        plugin_dir = self._resolve_plugin_dir()
        return _FileWriterProxy(self._plugin_id, plugin_dir, self._project_root)

    def get_network_client(self) -> object:
        """获取网络访问能力（需要 'network' 权限）。

        返回一个受控的网络客户端。
        """
        self._check_permission("network")
        return _NetworkProxy(self._plugin_id)

    # ---- 对话框注册 ----

    def register_dialog(self, action_type: str, dialog_class: type) -> None:
        """为节点类型注册自定义配置对话框。

        参数:
            action_type: 节点类型键（不含插件前缀，自动添加）
            dialog_class: tkinter Toplevel 子类
        """
        full_key = f"{self._plugin_id}.{action_type}"
        from src.core.plugins.dialog_registry import DialogRegistry

        DialogRegistry.register(full_key, dialog_class)
        logger.debug("插件 '%s' 注册对话框: %s", self._plugin_id, full_key)


class _FileReaderProxy:
    """受控的文件读取代理 — 限制插件读取文件的范围。

    允许读取:
    - 插件自身目录下的所有文件
    - 项目公共目录（assets/, config/）
    禁止读取:
    - 项目源码目录（src/）
    - 其他插件目录
    - 系统敏感路径
    """

    def __init__(self, plugin_id: str, plugin_dir: str, project_root: str) -> None:
        self._plugin_id = plugin_id
        self._plugin_dir = os.path.realpath(plugin_dir)
        self._project_root = os.path.realpath(project_root)

    def _validate_path(self, path: str) -> str:
        """验证并规范化路径，返回绝对路径或抛出 PermissionError。"""
        abs_path = os.path.realpath(path)

        # 允许：插件自身目录
        if abs_path.startswith(self._plugin_dir + os.sep) or abs_path == self._plugin_dir:
            return abs_path

        # 允许：项目公共只读目录
        for public_dir in _PUBLIC_READ_DIRS:
            allowed = os.path.realpath(os.path.join(self._project_root, public_dir))
            if abs_path.startswith(allowed + os.sep) or abs_path == allowed:
                return abs_path

        raise PermissionError(
            f"插件 '{self._plugin_id}' 无权读取: {path} "
            f"(仅限插件目录或 {', '.join(_PUBLIC_READ_DIRS)})"
        )

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        safe_path = self._validate_path(path)
        with open(safe_path, "r", encoding=encoding) as f:
            return f.read()

    def read_bytes(self, path: str) -> bytes:
        safe_path = self._validate_path(path)
        with open(safe_path, "rb") as f:
            return f.read()


class _FileWriterProxy:
    """受控的文件写入代理 — 限制插件写入文件的范围。

    允许写入:
    - 插件自身目录下的所有文件
    - profiles/ 目录下的配置文件
    禁止写入:
    - 项目源码目录（src/, tests/）
    - 设计文档目录
    - 系统敏感路径
    """

    def __init__(self, plugin_id: str, plugin_dir: str, project_root: str) -> None:
        self._plugin_id = plugin_id
        self._plugin_dir = os.path.realpath(plugin_dir)
        self._project_root = os.path.realpath(project_root)

    def _validate_path(self, path: str) -> str:
        """验证并规范化路径，返回绝对路径或抛出 PermissionError。"""
        abs_path = os.path.realpath(path)

        # 禁止：敏感目录
        for forbidden in _FORBIDDEN_WRITE_DIRS:
            forbidden_abs = os.path.realpath(os.path.join(self._project_root, forbidden))
            if abs_path.startswith(forbidden_abs + os.sep):
                raise PermissionError(
                    f"插件 '{self._plugin_id}' 无权写入源码目录: {path}"
                )

        # 允许：插件自身目录
        if abs_path.startswith(self._plugin_dir + os.sep) or abs_path == self._plugin_dir:
            return abs_path

        # 允许：profiles 目录
        profiles_dir = os.path.realpath(os.path.join(self._project_root, "profiles"))
        if abs_path.startswith(profiles_dir + os.sep):
            return abs_path

        # 允许：assets 目录（图片等资源）
        assets_dir = os.path.realpath(os.path.join(self._project_root, "assets"))
        if abs_path.startswith(assets_dir + os.sep):
            return abs_path

        raise PermissionError(
            f"插件 '{self._plugin_id}' 无权写入: {path} "
            f"(仅限插件目录、profiles 或 assets)"
        )

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        safe_path = self._validate_path(path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "w", encoding=encoding) as f:
            f.write(content)

    def write_bytes(self, path: str, data: bytes) -> None:
        safe_path = self._validate_path(path)
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "wb") as f:
            f.write(data)


class _NetworkProxy:
    """受控的网络访问代理 — 限制插件的网络请求。

    - 仅允许 HTTPS 请求
    - 记录所有网络访问日志
    - 限制请求超时（防止阻塞）
    """

    _ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})

    def __init__(self, plugin_id: str) -> None:
        self._plugin_id = plugin_id

    def _validate_url(self, url: str) -> None:
        """验证 URL 安全性。"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme.lower() not in self._ALLOWED_SCHEMES:
            raise PermissionError(
                f"插件 '{self._plugin_id}' 仅允许 HTTPS 请求，拒绝: {parsed.scheme}://"
            )

    def request(self, method: str, url: str, **kwargs: object) -> object:
        self._validate_url(url)
        logger.info("插件 '%s' 网络请求: %s %s", self._plugin_id, method, url)

        import urllib.request
        req = urllib.request.Request(url, method=method)
        timeout = 30  # 固定超时防止阻塞
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
