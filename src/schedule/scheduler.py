"""调度器 — ScheduleType + ScheduleConfig + Scheduler 定时执行。"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.notification.notifier import Notifier

from src.utils.i18n import t

logger = logging.getLogger(__name__)

_DEFAULT_PERSIST_PATH = os.path.join("config", "schedules.json")


class ScheduleType(Enum):
    """调度类型。"""

    ONCE = "once"
    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass
class ScheduleConfig:
    """调度配置 — 定义定时调度任务的完整参数。

    Attributes:
        schedule_type: 调度类型
        profile_name: 要执行的配置名称
        run_at: 一次性执行时间（仅 ONCE）
        interval_seconds: 间隔秒数（仅 INTERVAL）
        daily_time: 每天时间 "HH:MM"（仅 DAILY）
        daily_days: 星期几列表 None=每天，0=周一...6=周日
        weekly_day: 每周几执行（仅 WEEKLY，0=周一）
        weekly_time: 每周时间 "HH:MM"（仅 WEEKLY）
        max_runs: 最大执行次数，None=无限
        loop_count: 每次执行的循环数
    """

    schedule_type: ScheduleType
    profile_name: str
    run_at: datetime | None = None
    interval_seconds: int = 3600
    daily_time: str = "09:00"
    daily_days: list[int] | None = None
    weekly_day: int = 0
    weekly_time: str = "09:00"
    max_runs: int | None = None
    loop_count: int = 1

    def __post_init__(self) -> None:
        for label, time_str in [("daily_time", self.daily_time),
                                ("weekly_time", self.weekly_time)]:
            parts = time_str.split(":")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                raise ValueError(
                    f"Invalid {label}: '{time_str}', expected 'HH:MM'"
                )

    def next_run_time(self, now: datetime | None = None) -> datetime | None:
        """计算下次执行时间。已完成所有执行返回 None。"""
        if now is None:
            now = datetime.now()

        if self.schedule_type == ScheduleType.ONCE:
            if self.run_at and self.run_at > now:
                return self.run_at
            return None

        if self.schedule_type == ScheduleType.INTERVAL:
            return now + timedelta(seconds=self.interval_seconds)

        if self.schedule_type == ScheduleType.DAILY:
            return self._next_daily(now)

        if self.schedule_type == ScheduleType.WEEKLY:
            return self._next_weekly(now)

        return None

    def _next_daily(self, now: datetime) -> datetime:
        hour, minute = map(int, self.daily_time.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        if self.daily_days is not None:
            while target.weekday() not in self.daily_days:
                target += timedelta(days=1)
        return target

    def _next_weekly(self, now: datetime) -> datetime:
        hour, minute = map(int, self.weekly_time.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = self.weekly_day - target.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0 and target <= now:
            days_ahead = 7
        target += timedelta(days=days_ahead)
        return target

    def to_dict(self) -> dict:
        """序列化为 JSON 兼容字典。"""
        d: dict = {
            "schedule_type": self.schedule_type.value,
            "profile_name": self.profile_name,
            "interval_seconds": self.interval_seconds,
            "daily_time": self.daily_time,
            "daily_days": self.daily_days,
            "weekly_day": self.weekly_day,
            "weekly_time": self.weekly_time,
            "max_runs": self.max_runs,
            "loop_count": self.loop_count,
        }
        if self.run_at:
            d["run_at"] = self.run_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleConfig:
        """从字典反序列化。"""
        run_at = None
        if data.get("run_at"):
            run_at = datetime.fromisoformat(data["run_at"])
        return cls(
            schedule_type=ScheduleType(data["schedule_type"]),
            profile_name=data["profile_name"],
            run_at=run_at,
            interval_seconds=data.get("interval_seconds", 3600),
            daily_time=data.get("daily_time", "09:00"),
            daily_days=data.get("daily_days"),
            weekly_day=data.get("weekly_day", 0),
            weekly_time=data.get("weekly_time", "09:00"),
            max_runs=data.get("max_runs"),
            loop_count=data.get("loop_count", 1),
        )


class ExecutorProtocol(Protocol):
    """执行器协议 — Scheduler 依赖的接口。"""

    def execute_profile(self, profile_name: str, *, loop_count: int = 1) -> object: ...


class Scheduler:
    """定时调度器 — 后台线程轮询，到期时触发执行。

    线程安全：所有公共方法通过 Lock 保护。
    """

    POLL_INTERVAL = 30

    def __init__(
        self,
        executor: ExecutorProtocol,
        notifier: Notifier,
        persist_path: str = _DEFAULT_PERSIST_PATH,
    ) -> None:
        self._executor = executor
        self._notifier = notifier
        self._persist_path = persist_path
        self._schedules: dict[str, ScheduleConfig] = {}
        self._run_counts: dict[str, int] = {}
        self._stop_event = threading.Event()
        self._stop_event.set()  # 初始为"已停止"
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def add_schedule(self, config: ScheduleConfig) -> str:
        """添加调度，返回调度 ID。"""
        schedule_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._schedules[schedule_id] = config
            self._run_counts[schedule_id] = 0

        next_time = config.next_run_time()
        logger.info(
            "%s [%s]: %s, %s=%s, %s=%s",
            t("scheduler.log.added"),
            schedule_id,
            config.schedule_type.value,
            t("scheduler.profile"),
            config.profile_name,
            t("scheduler.next_run"),
            next_time,
        )
        return schedule_id

    def remove_schedule(self, schedule_id: str) -> None:
        """移除调度。"""
        with self._lock:
            self._schedules.pop(schedule_id, None)
            self._run_counts.pop(schedule_id, None)
        logger.info("%s [%s]", t("scheduler.log.removed"), schedule_id)

    def start(self) -> None:
        """启动调度器后台线程。"""
        with self._lock:
            if not self._stop_event.is_set():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._poll_loop, name="Scheduler", daemon=True
            )
            self._thread.start()
        logger.info(t("scheduler.log.started"))

    def stop(self) -> None:
        """停止调度器并等待线程退出。"""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=5)
        logger.info(t("scheduler.log.stopped"))

    @property
    def running(self) -> bool:
        return not self._stop_event.is_set()

    def list_schedules(
        self,
    ) -> list[tuple[str, ScheduleConfig, datetime | None]]:
        """列出所有调度（含下次执行时间）。"""
        with self._lock:
            return [
                (sid, config, config.next_run_time())
                for sid, config in self._schedules.items()
            ]

    def get_run_count(self, schedule_id: str) -> int:
        """获取调度已执行次数。"""
        with self._lock:
            return self._run_counts.get(schedule_id, 0)

    def _poll_loop(self) -> None:
        """轮询主循环。"""
        while not self._stop_event.is_set():
            try:
                self._check_schedules()
            except Exception as e:
                logger.error(t("scheduler.log.poll_error", error=e))

            for _ in range(self.POLL_INTERVAL):
                if self._stop_event.wait(1.0):
                    break

    def _check_schedules(self) -> None:
        """检查所有调度是否到期。"""
        now = datetime.now()
        with self._lock:
            due: list[tuple[str, ScheduleConfig]] = []
            for sid, config in self._schedules.items():
                next_time = config.next_run_time(now)
                if next_time is None:
                    continue
                if next_time > now:
                    continue
                if config.max_runs is not None:
                    if self._run_counts.get(sid, 0) >= config.max_runs:
                        continue
                due.append((sid, config))

        for sid, config in due:
            self._execute_schedule(sid, config)

    def _execute_schedule(self, schedule_id: str, config: ScheduleConfig) -> None:
        """执行一个调度。"""
        from src.notification.notifier import Notification

        logger.info(
            t("scheduler.log.execute_start",
              id=schedule_id,
              profile=config.profile_name,
              loops=config.loop_count),
        )
        try:
            self._executor.execute_profile(
                config.profile_name, loop_count=config.loop_count
            )
            with self._lock:
                new_count = self._run_counts.get(schedule_id, 0) + 1
                self._run_counts[schedule_id] = new_count
            self._notifier.notify_async(
                Notification(
                    title=t("scheduler.notify.completed.title",
                            profile=config.profile_name),
                    message=t("scheduler.notify.completed.message",
                              id=schedule_id,
                              count=new_count),
                    level="success",
                    data={
                        "schedule_id": schedule_id,
                        "profile": config.profile_name,
                        "run_count": new_count,
                    },
                )
            )
        except Exception as e:
            logger.error(
                t("scheduler.log.execute_fail",
                  id=schedule_id, error=e),
            )
            self._notifier.notify_async(
                Notification(
                    title=t("scheduler.notify.failed.title",
                            profile=config.profile_name),
                    message=t("scheduler.notify.failed.message",
                              id=schedule_id, error=e),
                    level="error",
                    data={
                        "schedule_id": schedule_id,
                        "profile": config.profile_name,
                        "error": str(e),
                    },
                )
            )

    # ---- 持久化 ----

    def save(self, path: str = "") -> None:
        """保存调度状态到 JSON 文件。"""
        target = path or self._persist_path
        with self._lock:
            data = {
                "version": 1,
                "schedules": {
                    sid: config.to_dict()
                    for sid, config in self._schedules.items()
                },
                "run_counts": dict(self._run_counts),
            }
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(t("scheduler.log.state_saved", path=target))

    def load(self, path: str = "") -> int:
        """从 JSON 文件加载调度状态。返回加载的调度数量。"""
        target = path or self._persist_path
        if not os.path.exists(target):
            logger.debug(t("scheduler.log.file_not_found", path=target))
            return 0
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        schedules = data.get("schedules", {})
        run_counts = data.get("run_counts", {})
        with self._lock:
            for sid, config_dict in schedules.items():
                try:
                    self._schedules[sid] = ScheduleConfig.from_dict(config_dict)
                    self._run_counts[sid] = run_counts.get(sid, 0)
                except Exception as exc:
                    logger.warning(t("scheduler.log.skip_invalid_schedule", sid=sid, error=str(exc)))
        count = len(schedules)
        logger.info(t("scheduler.log.loaded_from", path=target, schedule_count=count))
        return count
