"""通用对象池 — 参考 Cocos4 Pool<T>。

减少短生命周期对象的频繁创建/GC 压力。
适用于节点结果、回调元数据、事件数据等高频分配场景。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Generic, TypeVar

logger = logging.getLogger(__name__)

__all__ = ["Pool", "RecyclePool", "ContainerManager"]

T = TypeVar("T")


class Pool(Generic[T]):
    """通用对象池，alloc/free 手动管理，批量预分配。

    使用示例::

        pool = Pool(factory=lambda: dict(), reset=lambda d: d.clear())

        obj = pool.alloc()       # 从池中获取
        obj["key"] = "value"
        pool.free(obj)           # 归还池中

    Args:
        factory: 创建新对象的工厂函数。
        reset: 归还对象时调用的重置函数（可选）。
        batch_size: 每次扩容预分配数量，默认 16。
    """

    def __init__(
        self,
        factory: Callable[[], T],
        reset: Callable[[T], None] | None = None,
        batch_size: int = 16,
    ) -> None:
        self._factory = factory
        self._reset = reset
        self._batch_size = batch_size
        self._free: list[T] = []
        self._allocated = 0

    def alloc(self) -> T:
        """从池中分配一个对象，池空时自动扩容。"""
        if not self._free:
            self._expand()
        self._allocated += 1
        return self._free.pop()

    def free(self, obj: T) -> None:
        """归还对象到池中。"""
        if self._reset is not None:
            self._reset(obj)
        self._allocated -= 1
        self._free.append(obj)

    def free_all(self, objs: list[T]) -> None:
        """批量归还对象。"""
        for obj in objs:
            self.free(obj)

    def shrink(self, keep: int = 0) -> None:
        """缩减池中空闲对象到 keep 个。"""
        if len(self._free) > keep:
            removed = len(self._free) - keep
            del self._free[keep:]
            logger.debug("Pool shrink: released %d objects", removed)

    @property
    def free_count(self) -> int:
        """池中空闲对象数量。"""
        return len(self._free)

    @property
    def allocated_count(self) -> int:
        """当前已分配（未归还）的对象数量。"""
        return self._allocated

    def _expand(self) -> None:
        """批量预分配新对象。"""
        self._free.extend(self._factory() for _ in range(self._batch_size))


class RecyclePool(Generic[T]):
    """每帧/每轮全量复用池 — reset() 清零，add() 自动扩展。

    适用于每次迭代都会重新填充的临时数据：
    - 模板匹配中间结果
    - OCR 检测框列表
    - 像素搜索匹配点

    使用示例::

        pool = RecyclePool(factory=lambda: MatchResult())

        pool.reset()                # 每帧开始时清零
        result = pool.add()         # 添加并获取槽位
        result.x = 100
        for item in pool.items():   # 遍历有效数据
            ...
    """

    def __init__(
        self,
        factory: Callable[[], T],
        reset_fn: Callable[[T], None] | None = None,
        initial_size: int = 8,
    ) -> None:
        self._factory = factory
        self._reset_fn = reset_fn
        self._data: list[T] = [factory() for _ in range(initial_size)]
        self._count = 0

    @property
    def count(self) -> int:
        """当前有效数据数量。"""
        return self._count

    def reset(self) -> None:
        """清零有效计数，对象本身不销毁。"""
        if self._reset_fn is not None:
            for i in range(self._count):
                self._reset_fn(self._data[i])
        self._count = 0

    def add(self) -> T:
        """获取一个槽位，池满时自动扩展。"""
        if self._count >= len(self._data):
            self._data.append(self._factory())
        obj = self._data[self._count]
        self._count += 1
        return obj

    def items(self) -> list[T]:
        """返回有效数据的切片视图。"""
        return self._data[: self._count]

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, index: int) -> T:
        if index < 0 or index >= self._count:
            raise IndexError(f"RecyclePool index {index} out of range [0, {self._count})")
        return self._data[index]


class ContainerManager:
    """定期缩减所有注册池的内存占用 — 参考 Cocos4 ScalableContainerManager。

    长时间运行的自动化场景中，池可能因突发高峰而膨胀。
    ContainerManager 定期调用各池的 shrink()，回收多余内存。

    使用示例::

        manager = ContainerManager.instance()
        manager.register(my_pool)

        # 在主循环中定期调用
        manager.tick()
    """

    _instance: ContainerManager | None = None
    _lock: threading.Lock = threading.Lock()
    SHRINK_INTERVAL = 5.0  # 秒
    DEFAULT_KEEP = 4

    def __init__(self) -> None:
        self._pools: list[Pool] = []
        self._last_shrink = time.monotonic()

    @classmethod
    def instance(cls) -> ContainerManager:
        """获取全局单例（线程安全）。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, pool: Pool) -> None:
        """注册一个池到管理器。"""
        with self._lock:
            self._pools.append(pool)

    def unregister(self, pool: Pool) -> bool:
        """取消注册。返回是否成功。"""
        with self._lock:
            try:
                self._pools.remove(pool)
                return True
            except ValueError:
                return False

    def tick(self) -> None:
        """检查并执行定期缩减。应在主循环中定期调用。"""
        now = time.monotonic()
        if now - self._last_shrink >= self.SHRINK_INTERVAL:
            with self._lock:
                pools = list(self._pools)
            for pool in pools:
                pool.shrink(keep=self.DEFAULT_KEEP)
            self._last_shrink = now

    @classmethod
    def reset(cls) -> None:
        """重置单例（测试用）。"""
        with cls._lock:
            cls._instance = None
