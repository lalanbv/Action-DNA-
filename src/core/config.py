"""配置管理模块"""

import dataclasses
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from src.utils.i18n import t
from src.utils.paths import get_config_dir

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_PATH = os.path.join(get_config_dir(), "settings.json")


class ConfigLayer(Enum):
    """配置层级，数值越大优先级越高。"""

    DEFAULT = 0
    CONFIG_FILE = 1
    ENV_VAR = 2
    RUNTIME = 3


class ConfigurationManager:
    """多层配置管理器，支持优先级覆盖。

    查找顺序（从高到低）：RUNTIME > ENV_VAR > CONFIG_FILE > DEFAULT。
    DNA_* 环境变量自动映射为小写键名。
    """

    _ENV_PREFIX = "DNA_"

    def __init__(self, config_path: Path | None = None) -> None:
        self._layers: dict[ConfigLayer, dict[str, Any]] = {}
        self._config_path = config_path or Path("config/settings.json")

    _MISSING = object()

    def get(self, key: str, default: Any = None) -> Any:
        """按优先级从高到低查找配置值。"""
        for layer in reversed(ConfigLayer):
            layer_dict = self._layers.get(layer)
            if layer_dict is not None:
                val = layer_dict.get(key, self._MISSING)
                if val is not self._MISSING:
                    return val
        return default

    def set_default(self, key: str, value: Any) -> None:
        """设置默认层配置。"""
        self._layers.setdefault(ConfigLayer.DEFAULT, {})[key] = value

    def set_defaults(self, mapping: dict[str, Any]) -> None:
        """批量设置默认层配置。"""
        self._layers.setdefault(ConfigLayer.DEFAULT, {}).update(mapping)

    def load_config_file(self) -> None:
        """从 JSON 配置文件加载配置到 CONFIG_FILE 层。"""
        try:
            text = self._config_path.read_text(encoding="utf-8")
            data = json.loads(text)
            self._layers[ConfigLayer.CONFIG_FILE] = _flatten_dict(data)
        except FileNotFoundError:
            logger.debug("配置文件不存在: %s", self._config_path)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("配置文件加载失败: %s: %s", self._config_path, e)

    def load_env_overrides(self) -> None:
        """从 DNA_* 环境变量加载覆盖到 ENV_VAR 层。"""
        overrides: dict[str, Any] = {}
        for key, value in os.environ.items():
            if key.startswith(self._ENV_PREFIX):
                config_key = key[len(self._ENV_PREFIX) :].lower()
                overrides[config_key] = _coerce_env_value(value)
        if overrides:
            self._layers[ConfigLayer.ENV_VAR] = overrides

    def save_runtime_override(self, key: str, value: Any) -> None:
        """运行时覆盖，不持久化到文件。"""
        self._layers.setdefault(ConfigLayer.RUNTIME, {})[key] = value

    def remove_runtime_override(self, key: str) -> None:
        """移除运行时覆盖。"""
        runtime = self._layers.get(ConfigLayer.RUNTIME)
        if runtime is not None:
            runtime.pop(key, None)

    def load_all(self) -> None:
        """按顺序加载所有层（默认值需提前设置，config_file + env 自动加载）。"""
        self.load_config_file()
        self.load_env_overrides()

    def snapshot(self) -> dict[str, Any]:
        """合并所有层为一个扁平字典（低优先级先写入，高优先级覆盖）。"""
        merged: dict[str, Any] = {}
        for layer in ConfigLayer:
            layer_dict = self._layers.get(layer)
            if layer_dict is not None:
                merged.update(layer_dict)
        return merged

    @property
    def layers(self) -> dict[ConfigLayer, dict[str, Any]]:
        """返回所有层的只读视图。"""
        return {k: dict(v) for k, v in self._layers.items()}


def _flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """将嵌套字典展平为 dot-delimited 键。"""
    items: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items.update(_flatten_dict(value, full_key))
        else:
            items[full_key] = value
    return items


def _coerce_env_value(value: str) -> Any:
    """尝试将环境变量值转换为合适的 Python 类型。"""
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


@dataclass
class WindowConfig:
    """游戏窗口配置"""
    title: str = ""
    # 游戏窗口截图区域，None 表示自动检测
    capture_rect: tuple[int, int, int, int] | None = None

    def __post_init__(self) -> None:
        if not self.title:
            self.title = t("app.window_title")


@dataclass
class CombatConfig:
    """战斗配置"""
    auto_combat: bool = True
    skill_interval: float = 2.0  # 技能释放间隔（秒）
    dodge_enabled: bool = True  # 自动闪避
    heal_threshold: float = 0.3  # 血量低于 30% 时使用回复


@dataclass
class TaskConfig:
    """任务配置"""
    auto_accept_quest: bool = True  # 自动接取任务
    auto_complete_quest: bool = True  # 自动完成任务
    auto_dialog: bool = True  # 自动对话
    dialog_delay: float = 1.5  # 对话点击间隔（秒）


@dataclass
class RuntimeConfig:
    """运行时引擎参数 — 影响执行引擎和监控器的行为。"""

    loop_interval: float = 0.5  # 主循环间隔（秒）
    monitor_check_interval: float = 1.0  # 屏幕状态监控检测间隔（秒）
    monitor_poll_timeout: float = 0.1  # 监控线程 pause_event.wait 超时（秒）
    engine_pause_poll_timeout: float = 0.1  # 引擎暂停轮询超时（秒）
    rest_after_minutes: float = 60  # 连续运行 N 分钟后自动休息
    rest_duration: float = 5  # 休息时长（秒）
    monitor_poll_ms: int = 500  # GUI 状态栏轮询间隔（毫秒）
    frame_cache_ttl: float = 0.03  # SharedFrameProvider 截图缓存 TTL（秒）
    max_consecutive_failures: int = 5  # 连续失败触发安全停止的阈值


@dataclass
class EditorConfig:
    """编辑器 UI 偏好"""
    theme_mode: str = "system"  # "dark" | "light" | "system"
    gui_backend: str = "qt"  # "qt" | "tk"


@dataclass
class LanguageConfig:
    """语言偏好"""
    language: str = "zh"  # "zh" | "en"


@dataclass
class HotkeyBindingConfig:
    """单条快捷键绑定配置"""
    key_combination: str = ""
    enabled: bool = True
    use_global: bool = True


@dataclass
class HotkeyConfig:
    """快捷键配置"""
    start_stop: HotkeyBindingConfig = field(
        default_factory=lambda: HotkeyBindingConfig(key_combination="ctrl+shift+f5")
    )
    pause: HotkeyBindingConfig = field(
        default_factory=lambda: HotkeyBindingConfig(key_combination="ctrl+shift+f6")
    )
    step: HotkeyBindingConfig = field(
        default_factory=lambda: HotkeyBindingConfig(key_combination="ctrl+shift+f7")
    )
    emergency_stop: HotkeyBindingConfig = field(
        default_factory=lambda: HotkeyBindingConfig(key_combination="ctrl+shift+f12")
    )

    def get_binding(self, action_name: str) -> HotkeyBindingConfig:
        return getattr(self, action_name, HotkeyBindingConfig())


@dataclass
class ChannelConfig:
    """单个通知通道配置"""
    enabled: bool = True
    url: str = ""
    channel_type: str = "generic"
    secret: str = ""
    timeout: int = 5


@dataclass
class NotificationChannelConfigs:
    """通知通道配置集合"""
    system_notify: ChannelConfig = field(default_factory=lambda: ChannelConfig(enabled=True))
    sound: ChannelConfig = field(default_factory=lambda: ChannelConfig(enabled=True))
    webhook: ChannelConfig = field(default_factory=ChannelConfig)


@dataclass
class NotificationRuleConfig:
    """通知规则配置"""
    trigger: str = "on_complete"
    channels: list[str] = field(default_factory=lambda: ["system_notify", "sound"])
    title_template: str = ""
    message_template: str = ""
    condition: dict[str, Any] | None = None
    cooldown: float = 60.0
    enabled: bool = True


@dataclass
class NotificationConfig:
    """通知系统总配置"""
    channels: NotificationChannelConfigs = field(default_factory=NotificationChannelConfigs)
    rules: list[NotificationRuleConfig] = field(default_factory=list)


@dataclass
class ScheduleEntryConfig:
    """调度条目配置"""
    schedule_type: str = "once"
    profile_name: str = ""
    interval_seconds: int = 3600
    daily_time: str = "09:00"
    daily_days: list[int] | None = None
    weekly_day: int = 0
    weekly_time: str = "09:00"
    max_runs: int | None = None
    loop_count: int = 1
    enabled: bool = True


@dataclass
class ScheduleListConfig:
    """调度列表配置"""
    schedules: list[ScheduleEntryConfig] = field(default_factory=list)


@dataclass
class AppConfig:
    """应用总配置"""
    app_version: str = "2.0.0"
    window: WindowConfig = field(default_factory=WindowConfig)
    combat: CombatConfig = field(default_factory=CombatConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    schedule: RuntimeConfig = field(default_factory=RuntimeConfig)
    editor: EditorConfig = field(default_factory=EditorConfig)
    language: LanguageConfig = field(default_factory=LanguageConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    schedule_list: ScheduleListConfig = field(default_factory=ScheduleListConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        cfg = cls()
        if "app_version" in data:
            cfg.app_version = data["app_version"]
        if "window" in data:
            cfg.window = WindowConfig(**data["window"])
        if "combat" in data:
            cfg.combat = CombatConfig(**data["combat"])
        if "task" in data:
            cfg.task = TaskConfig(**data["task"])
        if "schedule" in data:
            cfg.schedule = RuntimeConfig(**data["schedule"])
        if "editor" in data:
            ed = data["editor"]
            if "theme_mode" in ed and ed["theme_mode"] not in ("dark", "light", "system"):
                ed = {**ed, "theme_mode": "system"}
            cfg.editor = EditorConfig(**ed)
        if "language" in data:
            cfg.language = LanguageConfig(**data["language"])
        if "hotkey" in data:
            cfg.hotkey = _parse_hotkey_config(data["hotkey"])
        if "notification" in data:
            cfg.notification = _parse_notification_config(data["notification"])
        if "schedule_list" in data:
            cfg.schedule_list = _parse_schedule_list_config(data["schedule_list"])
        return cfg


def _parse_hotkey_config(data: dict[str, Any]) -> HotkeyConfig:
    hc = HotkeyConfig()
    for name in ("start_stop", "pause", "step", "emergency_stop"):
        if name in data:
            setattr(hc, name, HotkeyBindingConfig(**data[name]))
    return hc


def _parse_notification_config(data: dict[str, Any]) -> NotificationConfig:
    nc = NotificationConfig()
    if "channels" in data:
        ch_data = data["channels"]
        for name in ("system_notify", "sound", "webhook"):
            if name in ch_data:
                setattr(nc.channels, name, ChannelConfig(**ch_data[name]))
    if "rules" in data:
        nc.rules = [NotificationRuleConfig(**r) for r in data["rules"]]
    return nc


def _parse_schedule_list_config(data: dict[str, Any]) -> ScheduleListConfig:
    sl = ScheduleListConfig()
    if "schedules" in data:
        sl.schedules = [ScheduleEntryConfig(**s) for s in data["schedules"]]
    return sl


_config_cache: AppConfig | None = None
_config_cache_path: str | None = None
_config_lock = threading.Lock()


def load_config(path: str | None = None) -> AppConfig:
    """从 JSON 文件加载配置（带缓存），文件不存在时返回默认配置"""
    global _config_cache, _config_cache_path
    path = path or DEFAULT_CONFIG_PATH
    with _config_lock:
        if _config_cache is not None and _config_cache_path == path:
            return _config_cache
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _config_cache = AppConfig.from_dict(data)
        except FileNotFoundError:
            _config_cache = AppConfig()
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("配置文件解析失败，使用默认配置: %s: %s", path, e)
            _config_cache = AppConfig()
        _config_cache_path = path
        return _config_cache


def save_config(cfg: AppConfig, path: str | None = None) -> None:
    """原子保存配置到 JSON 文件（先写临时文件再 rename）"""
    global _config_cache, _config_cache_path
    path = path or DEFAULT_CONFIG_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = dataclasses.asdict(cfg)
    dir_name = os.path.dirname(path)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except BaseException:
            os.unlink(tmp_path)
            raise
    except OSError as e:
        logger.warning("保存配置失败: %s: %s", path, e)
        return
    with _config_lock:
        _config_cache = cfg
        _config_cache_path = path
