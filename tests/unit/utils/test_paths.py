"""paths 单元测试 — 锁定打包/开发模式下的资源路径解析契约。

核心契约：
- 只读资源（assets/templates）在打包模式从 _MEIPASS 读取（--add-data 解压处），
  开发模式从项目根读取。
- 可写数据（profiles/、assets/logs/）始终从项目根读取，避免写入只读临时 bundle。
- get_project_root() 结果缓存。
"""

import os
import sys

import pytest

from src.utils import paths
from src.utils.paths import (
    get_assets_dir,
    get_logs_dir,
    get_profiles_dir,
    get_project_root,
)


@pytest.fixture
def reset_cache():
    """每个测试前清空 get_project_root 缓存，避免跨测试污染。"""
    paths._project_root = None
    yield
    paths._project_root = None


class TestProjectRoot:
    def test_dev_mode_returns_stable_abspath(self, reset_cache) -> None:
        root = get_project_root()
        assert os.path.isabs(root)
        # 缓存：第二次调用返回同一对象
        assert get_project_root() is root


class TestReadOnlyAssets:
    def test_dev_mode_uses_project_root(self, reset_cache, monkeypatch) -> None:
        monkeypatch.setattr(paths, "IS_FROZEN", False)
        assets = get_assets_dir()
        assert assets == os.path.join(get_project_root(), "assets", "templates")

    def test_frozen_mode_uses_meipass(self, reset_cache, monkeypatch, tmp_path) -> None:
        """打包模式：模板图片从 _MEIPASS 读取（--add-data 解压位置）。"""
        monkeypatch.setattr(paths, "IS_FROZEN", True)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        assets = get_assets_dir()
        assert assets == os.path.join(str(tmp_path), "assets", "templates")


class TestWritableData:
    def test_profiles_dir_is_project_root_even_when_frozen(
        self, reset_cache, monkeypatch, tmp_path
    ) -> None:
        """可写数据始终走项目根，即使打包模式也不写 _MEIPASS（只读临时目录）。"""
        monkeypatch.setattr(paths, "IS_FROZEN", True)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        # frozen 模式下 get_project_root 基于 sys.executable，这里用 monkeypatch 固定
        fake_root = str(tmp_path / "dist_root")
        monkeypatch.setattr(paths, "get_project_root", lambda: fake_root)
        assert get_profiles_dir() == os.path.join(fake_root, "profiles")

    def test_logs_dir_uses_project_root(self, reset_cache, monkeypatch) -> None:
        monkeypatch.setattr(paths, "IS_FROZEN", False)
        assert get_logs_dir() == os.path.join(get_project_root(), "assets", "logs")
