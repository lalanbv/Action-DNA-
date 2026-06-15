"""PluginLoader — 约定式插件加载器。

调用者:
  - main.py 启动序列: 创建 PluginLoader, scan(), load_all(), start_watcher()
  - plugin_interface.py / plugin_context.py 通过 import 使用

功能:
  - 约定式扫描: 遍历目录发现包含 plugin.json 的插件包
  - 依赖解析: 拓扑排序确保加载顺序，循环依赖检测
  - 生命周期管理: load/unload/reload
  - 热重载: 文件变更监控（可选）
  - 错误隔离: 单个插件失败不影响系统
"""

from __future__ import annotations

import contextlib
import importlib
import json
import logging
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata
from src.utils.i18n import t
from src.utils.platform import IS_FROZEN
from src.core.plugins.capabilities import (
    DescriptorPlugin,
    DialogPlugin,
    EventHandlerPlugin,
    SettingsPlugin,
)

if TYPE_CHECKING:
    from src.core.engine.node_registry import NodeRegistry
    from src.core.events.bus import TypedEventBus
    from src.core.input import InputController
    from src.core.vision import ScreenCapture, TemplateMatcher

logger = logging.getLogger(__name__)


class PluginState(Enum):
    """插件生命周期状态。"""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVE = "active"
    UNLOADED = "unloaded"
    ERROR = "error"


@dataclass
class PluginEntry:
    """插件注册条目。"""

    metadata: PluginMetadata
    state: PluginState = PluginState.DISCOVERED
    instance: PluginInterface | None = None
    module: Any = None
    context: PluginContext | None = None
    load_time: float = 0.0
    error_message: str | None = None
    capabilities: set[str] | None = None


class PluginLoader:
    """约定式插件加载器。

    扫描约定目录，自动发现、加载和管理插件。

    扫描目录（按优先级）:
    1. src/plugins/builtin/*/   — 内置插件
    2. plugins/*/               — 用户插件（项目根目录下）

    约定规则:
    - 每个插件是一个 Python 包（包含 __init__.py）
    - 必须包含 plugin.json 清单文件
    - __init__.py 中必须导出一个继承 PluginInterface 的类
    - 清单中声明的入口类名必须与 __init__.py 中一致
    """

    def __init__(
        self,
        node_registry: NodeRegistry,
        event_bus: TypedEventBus,
        screen_capture: ScreenCapture | None = None,
        template_matcher: TemplateMatcher | None = None,
        input_controller: InputController | None = None,
        watch_interval: float = 2.0,
        enable_hot_reload: bool = False,
    ) -> None:
        self._node_registry = node_registry
        self._event_bus = event_bus
        self._screen_capture = screen_capture
        self._template_matcher = template_matcher
        self._input_controller = input_controller
        self._watch_interval = watch_interval
        self._enable_hot_reload = enable_hot_reload

        self._plugins: dict[str, PluginEntry] = {}
        self._scan_dirs: list[Path] = []
        self._lock = threading.Lock()
        self._watcher_thread: threading.Thread | None = None
        self._stop_watcher = threading.Event()
        self._file_mtimes: dict[str, float] = {}
        self._added_sys_paths: set[str] = set()
        self._topo_cache: list[str] | None = None
        self._app_version: str | None = None

    # ---- 扫描与发现 ----

    def add_scan_dir(self, directory: str | Path) -> None:
        """添加插件扫描目录。"""
        path = Path(directory)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            logger.debug(t("plugins.log.scan_dir_created", path=path))
        self._scan_dirs.append(path)
        logger.debug(t("plugins.log.scan_dir_added", path=path))

    def scan(self) -> list[str]:
        """扫描所有扫描目录，发现插件。

        返回新发现的插件 ID 列表。
        """
        discovered: list[str] = []

        for scan_dir in self._scan_dirs:
            if not scan_dir.is_dir():
                continue

            for entry in scan_dir.iterdir():
                if not entry.is_dir():
                    continue

                manifest_path = entry / "plugin.json"
                if not manifest_path.exists():
                    continue

                plugin_id = entry.name

                if plugin_id in self._plugins:
                    logger.debug(t("plugins.log.skip_existing", plugin_id=plugin_id))
                    continue

                try:
                    metadata = self._parse_manifest(manifest_path)
                except Exception as e:
                    logger.error(t("plugins.log.parse_manifest_failed", manifest_path=manifest_path, error=e))
                    continue

                errors = self._validate_metadata(metadata)
                if errors:
                    logger.error(
                        "插件 '%s' 清单验证失败: %s",
                        plugin_id,
                        "; ".join(errors),
                    )
                    continue

                if not self._check_version_compat(metadata):
                    logger.warning(
                        "插件 '%s' 需要应用版本 %s+，当前版本不兼容",
                        plugin_id,
                        metadata.min_app_version,
                    )
                    continue

                entry_obj = PluginEntry(metadata=metadata)
                self._plugins[plugin_id] = entry_obj
                self._invalidate_topo_cache()
                discovered.append(plugin_id)
                logger.info(
                    "发现插件: %s v%s (%s)",
                    metadata.plugin_name,
                    metadata.version,
                    metadata.plugin_id,
                )

        return discovered

    # ---- 加载与卸载 ----

    def load_all(self) -> tuple[list[str], list[str]]:
        """加载所有已发现的插件。

        执行依赖排序后依次加载。
        返回: (成功加载的插件 ID 列表, 加载失败的插件 ID 列表)
        """
        sorted_ids = self._topological_sort()

        loaded: list[str] = []
        failed: list[str] = []

        for plugin_id in sorted_ids:
            try:
                self.load(plugin_id)
                loaded.append(plugin_id)
            except Exception as e:
                failed.append(plugin_id)
                entry = self._plugins.get(plugin_id)
                if entry:
                    entry.state = PluginState.ERROR
                    entry.error_message = str(e)
                logger.error(t("plugins.log.load_failed", plugin_id=plugin_id, error=e))

        return loaded, failed

    def initialize_all(self) -> tuple[list[str], list[str]]:
        """初始化所有已加载的插件（Phase 2: resolve → init）。

        调用每个已加载插件的 on_initialize() 回调，用于依赖注入
        和跨插件连接（如事件订阅、描述符注册后处理）。
        返回: (成功初始化的插件 ID 列表, 失败的插件 ID 列表)
        """
        initialized: list[str] = []
        failed: list[str] = []

        sorted_ids = self._topological_sort()

        for plugin_id in sorted_ids:
            entry = self._plugins.get(plugin_id)
            if entry is None or entry.state != PluginState.LOADED:
                continue
            if not entry.instance:
                continue

            try:
                if hasattr(entry.instance, "on_initialize"):
                    entry.instance.on_initialize(entry.context)
                initialized.append(plugin_id)
            except Exception as e:
                failed.append(plugin_id)
                entry.state = PluginState.ERROR
                entry.error_message = str(e)
                logger.error(t("plugins.log.initialize_failed", plugin_id=plugin_id, error=e))

        return initialized, failed

    def activate_all(self) -> tuple[list[str], list[str]]:
        """激活所有已初始化的插件（Phase 3: activate）。

        调用每个已加载插件的 on_activate() 回调，标记为 ACTIVE。
        激活后的插件可响应运行时事件和用户交互。
        返回: (成功激活的插件 ID 列表, 失败的插件 ID 列表)
        """
        activated: list[str] = []
        failed: list[str] = []

        sorted_ids = self._topological_sort()

        for plugin_id in sorted_ids:
            entry = self._plugins.get(plugin_id)
            if entry is None or entry.state not in (PluginState.LOADED,):
                continue
            if not entry.instance:
                continue

            try:
                if hasattr(entry.instance, "on_activate"):
                    entry.instance.on_activate(entry.context)
                entry.state = PluginState.ACTIVE
                activated.append(plugin_id)
            except Exception as e:
                failed.append(plugin_id)
                entry.state = PluginState.ERROR
                entry.error_message = str(e)
                logger.error(t("plugins.log.activate_failed", plugin_id=plugin_id, error=e))

        return activated, failed

    def load_all_staged(self) -> dict[str, tuple[list[str], list[str]]]:
        """完整的分阶段插件加载流程。

        Phase 1: scan → discover
        Phase 2: load_all → resolve + load
        Phase 3: initialize_all → cross-plugin init
        Phase 4: activate_all → mark active

        返回: {"load": (ok, fail), "init": (ok, fail), "activate": (ok, fail)}
        """
        results: dict[str, tuple[list[str], list[str]]] = {}
        results["load"] = self.load_all()
        results["init"] = self.initialize_all()
        results["activate"] = self.activate_all()
        return results

    def _load_module(self, plugin_id: str, module_name: str):
        """加载插件模块，兼容打包模式和第三方插件。"""
        # 内置插件在打包模式下已编译进归档，直接按包名 import
        if IS_FROZEN:
            builtin_path = f"src.plugins.builtin.{plugin_id}"
            try:
                module = importlib.import_module(builtin_path)
                sys.modules[module_name] = module
                return module
            except ModuleNotFoundError:
                pass  # 非内置插件，回退到文件加载

        # 开发模式 / 第三方插件：从文件路径加载
        plugin_dir = self._find_plugin_dir(plugin_id)
        if plugin_dir is None:
            raise RuntimeError(f"找不到插件目录: '{plugin_id}'")

        init_file = plugin_dir / "__init__.py"
        if not init_file.exists():
            raise RuntimeError(
                f"插件 '{plugin_id}' 目录缺少 __init__.py"
            )
        spec = importlib.util.spec_from_file_location(
            module_name, str(init_file),
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"插件 '{plugin_id}' 无法创建模块 spec"
            )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        return module

    def load(self, plugin_id: str) -> None:
        """加载单个插件。

        流程:
        1. 检查状态（必须是 DISCOVERED / UNLOADED / ERROR）
        2. 检查依赖（所有依赖必须已加载）
        3. 动态导入插件模块
        4. 实例化插件入口类
        5. 创建 PluginContext
        6. 调用 on_load()
        7. 调用 register_nodes()
        8. 更新状态为 LOADED
        """
        entry = self._plugins.get(plugin_id)
        if entry is None:
            raise ValueError(f"未发现插件: '{plugin_id}'")

        if entry.state not in (
            PluginState.DISCOVERED,
            PluginState.UNLOADED,
            PluginState.ERROR,
        ):
            raise RuntimeError(
                f"插件 '{plugin_id}' 状态为 {entry.state.value}，无法加载"
            )

        metadata = entry.metadata

        # 1. 检查依赖
        missing = self._check_dependencies(metadata)
        if missing:
            raise RuntimeError(
                f"插件 '{plugin_id}' 缺少依赖: {missing}"
            )

        # 2. 动态导入
        module_name = f"dna_plugin.{plugin_id}"
        module = self._load_module(plugin_id, module_name)

        try:
            # 3. 查找入口类
            entry_class_name = metadata.entry_class
            plugin_class = getattr(module, entry_class_name, None)
            if plugin_class is None:
                raise RuntimeError(
                    f"插件 '{plugin_id}' 的 __init__.py 中未找到类 '{entry_class_name}'"
                )

            # 5. 实例化
            instance = plugin_class()

            if not isinstance(instance, PluginInterface):
                raise RuntimeError(
                    f"插件 '{plugin_id}' 入口类未实现 PluginInterface"
                )

            # 6. 创建上下文
            permissions = set(metadata.permissions)
            plugin_dir = ""
            if hasattr(module, "__file__") and module.__file__:
                plugin_dir = os.path.dirname(os.path.abspath(module.__file__))
            project_root = os.getcwd()
            context = PluginContext(
                plugin_id=plugin_id,
                node_registry=self._node_registry,
                event_bus=self._event_bus,
                screen_capture=self._screen_capture
                if "screen_capture" in permissions
                else None,
                template_matcher=self._template_matcher
                if "template_matcher" in permissions
                else None,
                input_controller=self._input_controller
                if "input_control" in permissions
                else None,
                permissions=permissions,
                plugin_dir=plugin_dir,
                project_root=project_root,
            )

            # 7. 调用 on_load
            instance.on_load(context)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise

        # 7.5 检测能力 Mixin
        capabilities: set[str] = set()
        if isinstance(instance, SettingsPlugin):
            capabilities.add("settings")
        if isinstance(instance, DescriptorPlugin):
            capabilities.add("descriptors")
        if isinstance(instance, DialogPlugin):
            capabilities.add("dialogs")
        if isinstance(instance, EventHandlerPlugin):
            capabilities.add("event_handlers")
            # 自动订阅事件处理器
            for event_type, handler in instance.get_event_handlers().items():
                context.event_bus.subscribe(event_type, handler)

        # 8. 注册节点
        instance.register_nodes(context.registry)

        # 9. 记录文件 mtime（热重载用，打包模式下无磁盘文件可追踪）
        if self._enable_hot_reload and not IS_FROZEN:
            plugin_dir = self._find_plugin_dir(plugin_id)
            if plugin_dir is not None:
                for py_file in plugin_dir.rglob("*.py"):
                    self._file_mtimes[str(py_file)] = py_file.stat().st_mtime

        # 10. 更新条目
        entry.instance = instance
        entry.module = module
        entry.context = context
        entry.state = PluginState.LOADED
        entry.load_time = time.time()
        entry.error_message = None
        entry.capabilities = capabilities
        self._invalidate_topo_cache()

        logger.info(
            "插件已加载: %s v%s (注册了 %d 个节点)",
            metadata.plugin_name,
            metadata.version,
            len(context.registered_types),
        )

    def unload(self, plugin_id: str) -> None:
        """卸载单个插件。"""
        entry = self._plugins.get(plugin_id)
        if entry is None:
            raise ValueError(f"未发现插件: '{plugin_id}'")

        if entry.state not in (PluginState.LOADED, PluginState.ACTIVE):
            raise RuntimeError(
                f"插件 '{plugin_id}' 状态为 {entry.state.value}，无法卸载"
            )

        if entry.instance:
            try:
                entry.instance.on_unload()
            except Exception as e:
                logger.warning(t("plugins.log.on_unload_exception", plugin_id=plugin_id, error=e))

        if entry.context:
            for type_key in entry.context.registered_types:
                try:
                    self._node_registry.unregister(type_key)
                except Exception as e:
                    logger.warning(t("plugins.log.unregister_node_failed", type_key=type_key, error=e))

        entry.state = PluginState.UNLOADED
        entry.instance = None
        entry.context = None
        if entry.module:
            module_name = f"dna_plugin.{plugin_id}"
            sys.modules.pop(module_name, None)
            entry.module = None
        self._invalidate_topo_cache()

        # 清理 sys.path 中由此插件添加的条目
        plugin_dir = self._find_plugin_dir(plugin_id)
        if plugin_dir is not None:
            parent_dir = str(plugin_dir.parent)
            if parent_dir in self._added_sys_paths:
                self._added_sys_paths.discard(parent_dir)
                with contextlib.suppress(ValueError):
                    sys.path.remove(parent_dir)

        logger.info(t("plugins.log.unloaded", plugin_id=plugin_id))

    def reload(self, plugin_id: str) -> None:
        """重新加载插件（先卸载再加载）。"""
        self._invalidate_topo_cache()
        with self._lock:
            if plugin_id in self._plugins:
                entry = self._plugins[plugin_id]
                if entry.state in (PluginState.LOADED, PluginState.ACTIVE):
                    self.unload(plugin_id)
            self.load(plugin_id)
        logger.info(t("plugins.log.reloaded", plugin_id=plugin_id))

    def unload_all(self) -> list[str]:
        """卸载所有已加载的插件（逆序卸载以尊重依赖关系）。"""
        sorted_ids = self._topological_sort()
        sorted_ids.reverse()

        unloaded: list[str] = []
        for plugin_id in sorted_ids:
            entry = self._plugins.get(plugin_id)
            if entry and entry.state in (PluginState.LOADED, PluginState.ACTIVE):
                try:
                    self.unload(plugin_id)
                    unloaded.append(plugin_id)
                except Exception as e:
                    logger.error(t("plugins.log.unload_failed", plugin_id=plugin_id, error=e))
        return unloaded

    # ---- 热重载 ----

    def start_watcher(self) -> None:
        """启动文件监控线程。"""
        if not self._enable_hot_reload:
            logger.info(t("plugins.log.hot_reload_disabled"))
            return

        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            return

        self._stop_watcher.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="PluginWatcher",
        )
        self._watcher_thread.start()
        logger.info(t("plugins.log.watcher_started"))

    def stop_watcher(self) -> None:
        """停止文件监控线程。"""
        self._stop_watcher.set()
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5.0)
        logger.info(t("plugins.log.watcher_stopped"))

    def _watch_loop(self) -> None:
        """文件变更监控循环。"""
        while not self._stop_watcher.is_set():
            try:
                self._check_file_changes()
            except Exception as e:
                logger.error(t("plugins.log.watcher_check_exception", error=e))
            self._stop_watcher.wait(self._watch_interval)

    def _check_file_changes(self) -> None:
        """检查插件文件是否变更。"""
        changed: list[str] = []
        with self._lock:
            items = list(self._plugins.items())
        for plugin_id, entry in items:
            if entry.state not in (PluginState.LOADED, PluginState.ACTIVE):
                continue

            plugin_dir = self._find_plugin_dir(plugin_id)
            if plugin_dir is None:
                continue

            for py_file in plugin_dir.rglob("*.py"):
                mtime = py_file.stat().st_mtime
                key = str(py_file)

                if key in self._file_mtimes:
                    if mtime > self._file_mtimes[key]:
                        logger.info(
                            "检测到插件 '%s' 文件变更: %s",
                            plugin_id,
                            py_file.name,
                        )
                        changed.append(plugin_id)
                        for f in plugin_dir.rglob("*.py"):
                            self._file_mtimes[str(f)] = f.stat().st_mtime
                        break
                else:
                    self._file_mtimes[key] = mtime

        for plugin_id in changed:
            self.reload(plugin_id)

    # ---- 依赖解析 ----

    def _invalidate_topo_cache(self) -> None:
        self._topo_cache = None

    def _topological_sort(self) -> list[str]:
        """拓扑排序插件依赖（Kahn 算法）。结果缓存直到插件集变更。"""
        if self._topo_cache is not None:
            return self._topo_cache

        graph: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}

        for plugin_id, entry in self._plugins.items():
            if plugin_id not in graph:
                graph[plugin_id] = []
                in_degree[plugin_id] = 0

            for dep in entry.metadata.dependencies:
                if dep not in self._plugins:
                    logger.warning(
                        "插件 '%s' 的依赖 '%s' 不存在",
                        plugin_id,
                        dep,
                    )
                    continue
                graph.setdefault(dep, []).append(plugin_id)
                in_degree[plugin_id] = in_degree.get(plugin_id, 0) + 1

        queue = deque(pid for pid, deg in in_degree.items() if deg == 0)
        result: list[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)

            for neighbor in graph.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self._plugins):
            raise RuntimeError(
                "插件依赖存在循环: "
                f"已排序 {len(result)} 个，总共 {len(self._plugins)} 个"
            )

        self._topo_cache = result
        return result

    def _check_dependencies(self, metadata: PluginMetadata) -> list[str]:
        """检查依赖是否已加载。"""
        missing: list[str] = []
        for dep_id in metadata.dependencies:
            dep_entry = self._plugins.get(dep_id)
            if dep_entry is None:
                missing.append(dep_id)
            elif dep_entry.state not in (PluginState.LOADED, PluginState.ACTIVE):
                missing.append(f"{dep_id} (状态: {dep_entry.state.value})")
        return missing

    # ---- 清单解析 ----

    def _parse_manifest(self, path: Path) -> PluginMetadata:
        """解析 plugin.json 清单。"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return PluginMetadata(
            plugin_id=data["plugin_id"],
            plugin_name=data["plugin_name"],
            version=data["version"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            dependencies=tuple(data.get("dependencies", [])),
            permissions=tuple(data.get("permissions", [])),
            min_app_version=data.get("min_app_version", "2.0.0"),
            entry_class=data.get("entry_class", "Plugin"),
        )

    def _validate_metadata(self, meta: PluginMetadata) -> list[str]:
        """验证清单完整性。"""
        errors: list[str] = []
        if not meta.plugin_id:
            errors.append("plugin_id 不能为空")
        if not meta.plugin_name:
            errors.append("plugin_name 不能为空")
        if not meta.version:
            errors.append("version 不能为空")
        parts = meta.version.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            errors.append(f"version 格式无效: '{meta.version}'，应为 X.Y.Z")
        valid_permissions = {
            "screen_capture",
            "template_matcher",
            "input_control",
            "events",
            "file_read",
            "file_write",
            "network",
        }
        errors.extend(f"未知权限: '{perm}'" for perm in meta.permissions if perm not in valid_permissions)
        return errors

    def _check_version_compat(self, meta: PluginMetadata) -> bool:
        """检查应用版本兼容性。"""
        if self._app_version is None:
            from src.core.config import load_config
            self._app_version = load_config().app_version
        return self._compare_versions(self._app_version, meta.min_app_version) >= 0

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """比较两个版本号，返回 -1/0/1。"""
        from itertools import zip_longest

        parts1 = [int(p) for p in v1.split(".")]
        parts2 = [int(p) for p in v2.split(".")]
        for a, b in zip_longest(parts1, parts2, fillvalue=0):
            if a < b:
                return -1
            if a > b:
                return 1
        return 0

    def _find_plugin_dir(self, plugin_id: str) -> Path | None:
        """查找插件目录。"""
        for scan_dir in self._scan_dirs:
            candidate = scan_dir / plugin_id
            if candidate.is_dir():
                return candidate
        return None

    # ---- 查询 ----

    def get_plugin(self, plugin_id: str) -> PluginEntry | None:
        """获取插件条目。"""
        return self._plugins.get(plugin_id)

    def get_all_plugins(self) -> dict[str, PluginEntry]:
        """获取所有插件。"""
        return dict(self._plugins)

    def get_loaded_plugins(self) -> dict[str, PluginEntry]:
        """获取已加载的插件。"""
        return {
            pid: entry
            for pid, entry in self._plugins.items()
            if entry.state in (PluginState.LOADED, PluginState.ACTIVE)
        }

    def get_plugin_capabilities(self, plugin_id: str) -> set[str]:
        """获取插件能力集合。

        返回能力标签: "settings", "descriptors", "dialogs", "event_handlers"
        """
        entry = self._plugins.get(plugin_id)
        if entry and entry.capabilities:
            return set(entry.capabilities)
        return set()

    # ---- manifest 读写 ----

    def get_manifest_data(self, plugin_id: str) -> dict | None:
        """读取插件 plugin.json 原始数据。"""
        plugin_dir = self._find_plugin_dir(plugin_id)
        if plugin_dir is None:
            return None
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def update_manifest(self, plugin_id: str, updates: dict) -> None:
        """更新 plugin.json 中指定字段并保存。

        updates: 需要更新的字段键值对，如 {"enabled": false}
        只更新已存在的字段，不添加新字段（enabled 除外）。
        """
        plugin_dir = self._find_plugin_dir(plugin_id)
        if plugin_dir is None:
            raise ValueError(f"找不到插件目录: '{plugin_id}'")
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            raise ValueError(f"插件清单不存在: '{manifest_path}'")

        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.update(updates)

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.write("\n")

        logger.info(t("plugins.log.manifest_updated", plugin_id=plugin_id, updated_keys=list(updates.keys())))

    def get_registered_node_types(self, plugin_id: str) -> list[str]:
        """获取插件注册的节点类型列表。"""
        entry = self._plugins.get(plugin_id)
        if entry and entry.context:
            return list(entry.context.registered_types)
        return []
