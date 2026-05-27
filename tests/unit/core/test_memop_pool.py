"""Pool / RecyclePool / ContainerManager 单元测试。"""

import threading
import time
from dataclasses import dataclass

import pytest

from src.core.memop.pool import ContainerManager, Pool, RecyclePool


# ============================================================
# Pool
# ============================================================


class TestPool:
    """通用对象池测试。"""

    def test_alloc_returns_object(self):
        pool = Pool(factory=dict)
        obj = pool.alloc()
        assert isinstance(obj, dict)

    def test_free_and_reuse(self):
        pool = Pool(factory=list, reset=lambda l: l.clear())
        obj = pool.alloc()
        obj.append(1)
        pool.free(obj)
        reused = pool.alloc()
        assert reused is obj
        assert reused == []  # reset 被调用

    def test_batch_expansion(self):
        pool = Pool(factory=dict, batch_size=4)
        objs = [pool.alloc() for _ in range(8)]
        assert len(objs) == 8
        assert pool.free_count == 0

    def test_shrink(self):
        pool = Pool(factory=dict, batch_size=8)
        objs = [pool.alloc() for _ in range(8)]
        for obj in objs:
            pool.free(obj)
        assert pool.free_count == 8
        pool.shrink(keep=2)
        assert pool.free_count == 2

    def test_allocated_count(self):
        pool = Pool(factory=dict)
        assert pool.allocated_count == 0
        a = pool.alloc()
        assert pool.allocated_count == 1
        b = pool.alloc()
        assert pool.allocated_count == 2
        pool.free(a)
        assert pool.allocated_count == 1
        pool.free(b)
        assert pool.allocated_count == 0

    def test_free_all(self):
        pool = Pool(factory=list, reset=lambda l: l.clear())
        objs = [pool.alloc() for _ in range(5)]
        for o in objs:
            o.append("data")
        pool.free_all(objs)
        assert pool.allocated_count == 0
        assert pool.free_count >= 5  # 包含预分配的额外对象

    def test_no_reset_when_none(self):
        @dataclass
        class Item:
            value: int = 0

        pool = Pool(factory=Item)
        obj = pool.alloc()
        obj.value = 42
        pool.free(obj)
        reused = pool.alloc()
        assert reused.value == 42  # 未 reset，值保留


# ============================================================
# RecyclePool
# ============================================================


class TestRecyclePool:
    """每帧全量复用池测试。"""

    def test_add_and_items(self):
        pool = RecyclePool(factory=lambda: {"x": 0, "y": 0})
        item = pool.add()
        item["x"] = 100
        assert pool.count == 1
        items = pool.items()
        assert len(items) == 1
        assert items[0]["x"] == 100

    def test_reset_clears_count(self):
        pool = RecyclePool(factory=dict)
        pool.add()
        pool.add()
        assert pool.count == 2
        pool.reset()
        assert pool.count == 0
        assert pool.items() == []

    def test_auto_expand(self):
        pool = RecyclePool(factory=dict, initial_size=2)
        for _ in range(5):
            pool.add()
        assert pool.count == 5

    def test_getitem(self):
        pool = RecyclePool(factory=lambda: {"v": 0})
        pool.add()["v"] = 10
        pool.add()["v"] = 20
        assert pool[0]["v"] == 10
        assert pool[1]["v"] == 20

    def test_getitem_out_of_range(self):
        pool = RecyclePool(factory=dict)
        pool.add()
        with pytest.raises(IndexError):
            pool[1]

    def test_len(self):
        pool = RecyclePool(factory=dict)
        assert len(pool) == 0
        pool.add()
        assert len(pool) == 1

    def test_reset_calls_reset_fn(self):
        reset_calls: list[int] = []

        def reset_fn(item: dict) -> None:
            reset_calls.append(id(item))
            item.clear()

        pool = RecyclePool(factory=lambda: {"key": "val"}, reset_fn=reset_fn)
        pool.add()
        pool.add()
        pool.reset()
        assert len(reset_calls) == 2

    def test_reuse_after_reset(self):
        pool = RecyclePool(factory=lambda: {"v": 0}, initial_size=2)
        pool.add()["v"] = 1
        pool.add()["v"] = 2
        pool.reset()

        item = pool.add()
        item["v"] = 99
        assert pool[0]["v"] == 99

    def test_items_returns_slice(self):
        pool = RecyclePool(factory=lambda: {"i": 0}, initial_size=10)
        pool.add()["i"] = 1
        pool.add()["i"] = 2
        items = pool.items()
        assert len(items) == 2
        assert items[0] is pool[0]


# ============================================================
# ContainerManager
# ============================================================


class TestContainerManager:
    """容器管理器测试。"""

    def test_singleton(self):
        ContainerManager.reset()
        a = ContainerManager.instance()
        b = ContainerManager.instance()
        assert a is b
        ContainerManager.reset()

    def test_register_and_tick(self):
        ContainerManager.reset()
        manager = ContainerManager()
        pool = Pool(factory=dict, batch_size=8)
        for _ in range(8):
            pool.alloc()
        for _ in range(8):
            pool.free(dict())
        # free_count > DEFAULT_KEEP
        pool.shrink(keep=2)
        assert pool.free_count == 2

    def test_unregister(self):
        manager = ContainerManager()
        pool = Pool(factory=dict)
        manager.register(pool)
        assert manager.unregister(pool) is True
        assert manager.unregister(pool) is False

    def test_tick_interval(self):
        manager = ContainerManager()
        manager.SHRINK_INTERVAL = 10.0
        pool = Pool(factory=dict, batch_size=8)
        manager.register(pool)

        objs = [pool.alloc() for _ in range(8)]
        for o in objs:
            pool.free(o)

        manager._last_shrink = time.monotonic() - 0.1
        manager.tick()
        assert pool.free_count == 8  # 间隔未到，未缩减

        manager._last_shrink = time.monotonic() - 11.0
        manager.tick()
        assert pool.free_count == manager.DEFAULT_KEEP

    def test_reset(self):
        ContainerManager.reset()
        a = ContainerManager.instance()
        ContainerManager.reset()
        b = ContainerManager.instance()
        assert a is not b
        ContainerManager.reset()


# ============================================================
# 并发安全
# ============================================================


class TestConcurrency:
    """并发 alloc/free 安全性。"""

    def test_concurrent_alloc_free(self):
        pool = Pool(factory=lambda: {"v": 0}, batch_size=32)
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(100):
                    obj = pool.alloc()
                    obj["v"] = 1
                    pool.free(obj)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert pool.allocated_count == 0
