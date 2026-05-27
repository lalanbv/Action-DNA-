# 插件示例

本目录包含完整的插件示例，供插件开发者参考。

## 示例列表

| 示例 | 文件 | 演示内容 |
|------|------|----------|
| 自动喝药 | `example_autopotion.py` | 模板匹配 + 点击、单个描述符、权限声明、单元测试模式 |
| 快速旅行 | `example_quick_travel.py` | 多描述符注册、固定坐标操作、最简插件 |

## 使用方法

1. 选择一个示例
2. 复制到 `src/plugins/builtin/<plugin_id>/`
3. 重命名为 `__init__.py`
4. 创建对应的 `plugin.json`（文件底部有模板）
5. 重启应用，PluginLoader 自动扫描加载

## 完整 API 参考

参见 [docs/plugin_api.md](../plugin_api.md)。

## 完整开发指南

参见 [docs/plugin_guide.md](../plugin_guide.md)。
