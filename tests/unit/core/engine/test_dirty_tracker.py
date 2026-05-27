"""DirtyTracker 测试 — 脏标记追踪器。"""

from src.core.engine.dirty_tracker import DirtyTracker


class TestMarkDirty:
    """标记脏节点。"""

    def test_mark_single_node(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_dirty("node_a")
        assert tracker.needs_eval("node_a", 1) is True

    def test_mark_multiple_nodes(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_dirty("node_a")
        tracker.mark_dirty("node_b")
        assert tracker.needs_eval("node_a", 1) is True
        assert tracker.needs_eval("node_b", 1) is True

    def test_mark_all_dirty(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_all_dirty(["a", "b", "c"])
        assert tracker.dirty_nodes == frozenset({"a", "b", "c"})


class TestMarkClean:
    """标记节点已评估。"""

    def test_mark_clean_after_dirty(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_dirty("node_a")
        tracker.mark_clean("node_a", 1)
        assert tracker.needs_eval("node_a", 1) is False

    def test_mark_clean_older_generation_still_dirty(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_clean("node_a", 1)
        # 当前 generation=2，但 node_a 只评估到 generation=1
        assert tracker.needs_eval("node_a", 2) is True

    def test_mark_clean_same_generation(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_clean("node_a", 2)
        assert tracker.needs_eval("node_a", 2) is False


class TestPropagateDownstream:
    """脏标记向下传播。"""

    def test_linear_chain(self) -> None:
        tracker = DirtyTracker()
        # A → B → C
        successors = {"a": ["b"], "b": ["c"], "c": []}
        tracker.mark_dirty("a")
        tracker.propagate_downstream(lambda n: successors.get(n, []), "a")
        # mark_dirty("a") + propagate adds b, c
        assert tracker.dirty_nodes == frozenset({"a", "b", "c"})

    def test_diamond_graph(self) -> None:
        tracker = DirtyTracker()
        # A → B, A → C, B → D, C → D
        successors = {
            "a": ["b", "c"],
            "b": ["d"],
            "c": ["d"],
            "d": [],
        }
        tracker.mark_dirty("a")
        tracker.propagate_downstream(lambda n: successors.get(n, []), "a")
        # mark_dirty("a") + propagate adds b, c, d
        assert tracker.dirty_nodes == frozenset({"a", "b", "c", "d"})

    def test_no_successors(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_dirty("leaf")
        tracker.propagate_downstream(lambda n: [], "leaf")
        # mark_dirty("leaf") stays, propagate adds nothing
        assert tracker.dirty_nodes == frozenset({"leaf"})

    def test_cycle_safe(self) -> None:
        """循环图不应无限循环。"""
        tracker = DirtyTracker()
        # A → B → A（循环）
        successors = {"a": ["b"], "b": ["a"]}
        tracker.mark_dirty("a")
        tracker.propagate_downstream(lambda n: successors.get(n, []), "a")
        assert "b" in tracker.dirty_nodes


class TestReset:
    def test_reset_clears_all(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_dirty("a")
        tracker.mark_clean("b", 1)
        tracker.reset()
        assert tracker.dirty_nodes == frozenset()
        assert tracker.needs_eval("b", 0) is False


class TestDirtyNodes:
    def test_returns_frozenset(self) -> None:
        tracker = DirtyTracker()
        tracker.mark_dirty("a")
        result = tracker.dirty_nodes
        assert isinstance(result, frozenset)
        assert result == frozenset({"a"})

    def test_empty_tracker(self) -> None:
        tracker = DirtyTracker()
        assert tracker.dirty_nodes == frozenset()
