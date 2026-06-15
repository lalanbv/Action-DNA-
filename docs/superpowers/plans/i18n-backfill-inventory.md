# i18n 补齐清单(121 处)

## `src/core/config.py` (logger 4 + 异常 0)

- L72 [logger] `logger.debug("配置文件不存在: %s", self._config_path)`
- L74 [logger] `logger.warning("配置文件加载失败: %s: %s", self._config_path, e)`
- L378 [logger] `logger.warning("配置文件解析失败，使用默认配置: %s: %s", path, e)`
- L401 [logger] `logger.warning("保存配置失败: %s: %s", path, e)`

## `src/core/debug/breakpoint_manager.py` (logger 1 + 异常 0)

- L63 [logger] `logger.debug("添加断点: %s (类型: %s)", node_id, bp_type.value)`

## `src/core/debug/debugger.py` (logger 9 + 异常 0)

- L98 [logger] `logger.info("调试器状态: %s → %s", old_state.value, new_state.value)`
- L103 [logger] `logger.error("调试器回调异常: %s", e)`
- L175 [logger] `logger.info("[日志断点] %s: %s", node_id, bp.log_message)`
- L196 [logger] `logger.error("断点回调异常: %s", e)`
- L317 [logger] `logger.debug("获取光标位置失败", exc_info=True)`
- L321 [logger] `logger.debug("获取屏幕尺寸失败", exc_info=True)`
- L328 [logger] `logger.debug("获取活动区域失败", exc_info=True)`
- L335 [logger] `logger.debug("获取缓存年龄失败", exc_info=True)`
- L342 [logger] `logger.debug("获取引擎状态失败", exc_info=True)`

## `src/core/debug/ring_buffer_log.py` (logger 2 + 异常 0)

- L97 [logger] `logger.error("RingBufferLog 回调异常: %s", e)`
- L173 [logger] `logger.info("日志已导出: %s (%d 条)", filepath, len(data))`

## `src/core/editor/undo_manager.py` (logger 4 + 异常 0)

- L44 [logger] `logger.debug("命令已合并: %s", command.description)`
- L60 [logger] `logger.debug("撤销: %s", command.description)`
- L70 [logger] `logger.debug("重做: %s", command.description)`
- L123 [logger] `logger.exception("撤销管理器回调异常")`

## `src/core/engine/descriptors/sub_graph_descriptor.py` (logger 0 + 异常 1)

- L131 [exception] `raise FileNotFoundError(f"子图配置不存在: {config_path}")`

## `src/core/engine/graph_engine.py` (logger 0 + 异常 2)

- L115 [exception] `raise ValueError(f"层 '{layer.name}' 已存在")`
- L423 [exception] `raise RuntimeError(f"未注册的节点类型: {action_type}") from None`

## `src/core/error/error_registry.py` (logger 0 + 异常 2)

- L212 [exception] `raise KeyError(f"未知错误码: {error_id}")`
- L231 [exception] `raise KeyError(f"未注册的标准错误码: {standard_code}")`

## `src/core/events/bus.py` (logger 1 + 异常 0)

- L164 [logger] `logger.error("UI 事件处理器出错", exc_info=True)`

## `src/core/input/global_hotkey_backend.py` (logger 6 + 异常 0)

- L241 [logger] `logger.debug("pynput GlobalHotKeys 已重启，绑定数: %d", len(self._bindings))`
- L243 [logger] `logger.error("pynput GlobalHotKeys 启动失败: %s", e)`
- L288 [logger] `logger.error("keyboard 注册热键失败 '%s': %s", key_combo, e)`
- L307 [logger] `logger.info("全局热键后端: pynput")`
- L312 [logger] `logger.info("全局热键后端: keyboard")`
- L315 [logger] `logger.info("全局热键不可用，回退到 tkinter 绑定")`

## `src/core/input/hotkey_manager.py` (logger 5 + 异常 0)

- L103 [logger] `logger.debug("注册快捷键: %s -> %s (%s)", key_combo, action_name, description)`
- L299 [logger] `logger.error("注册全局热键失败 '%s': %s", binding.key_combination, e)`
- L316 [logger] `logger.error("tkinter 快捷键绑定失败 '%s': %s", tk_key, e)`
- L348 [logger] `logger.debug("PySide6 不可用，跳过 Qt 快捷键注册")`
- L350 [logger] `logger.error("Qt 快捷键绑定失败 '%s': %s", binding.key_combination, e)`

## `src/core/io/importer.py` (logger 0 + 异常 1)

- L274 [exception] `raise ValueError(f"不支持的宏脚本版本: {version} (需要 {self.SUPPORTED_VERSION})")`

## `src/core/io/script_exporter.py` (logger 1 + 异常 1)

- L80 [logger] `logger.info("脚本已导出: %s (%d 节点, %d 模板)", output_path, node_count, template_count)`
- L206 [exception] `raise ValueError("图中没有有效的 START 节点")`

## `src/core/layers/breakpoint_layer.py` (logger 3 + 异常 3)

- L87 [exception] `raise ValueError(f"无效的调试模式: {mode}, 有效值: {valid}") from None`
- L180 [logger] `logger.info("移除断点: %s", node_id)`
- L227 [exception] `raise StopExecution("执行被请求停止")`
- L232 [exception] `raise StopExecution("调试模式：用户请求停止")`
- L260 [logger] `logger.debug("断点截图已保存: %s", filepath)`
- L262 [logger] `logger.debug("保存断点截图失败: %s", e)`

## `src/core/layers/debug_screenshot_layer.py` (logger 3 + 异常 0)

- L85 [logger] `logger.info("调试截图已保存: %s", ss_path)`
- L91 [logger] `logger.info("调试模板已保存: %s", tpl_debug)`
- L93 [logger] `logger.warning("保存调试截图失败: %s", e)`

## `src/core/layers/failsafe_layer.py` (logger 1 + 异常 0)

- L50 [logger] `logger.warning("FailSafe 检查时发生异常（非致命）", exc_info=True)`

## `src/core/layers/timing_layer.py` (logger 1 + 异常 0)

- L112 [logger] `logger.info("========== 执行性能报告 ==========")`

## `src/core/plugins/manifest_validator.py` (logger 0 + 异常 1)

- L31 [exception] `raise ValueError(f"无效版本号格式: {version_str!r}，预期 'X.Y.Z'")`

## `src/core/plugins/plugin_loader.py` (logger 0 + 异常 5)

- L312 [exception] `raise RuntimeError(f"找不到插件目录: '{plugin_id}'")`
- L350 [exception] `raise ValueError(f"未发现插件: '{plugin_id}'")`
- L466 [exception] `raise ValueError(f"未发现插件: '{plugin_id}'")`
- L785 [exception] `raise ValueError(f"找不到插件目录: '{plugin_id}'")`
- L788 [exception] `raise ValueError(f"插件清单不存在: '{manifest_path}'")`

## `src/core/safe_eval.py` (logger 3 + 异常 0)

- L44 [logger] `logger.warning("表达式语法错误: %s, 错误: %s", expression, e)`
- L49 [logger] `logger.warning("表达式包含不允许的节点: %s", expression)`
- L56 [logger] `logger.warning("表达式评估失败: %s → %s", expression, e)`

## `src/core/serialization.py` (logger 0 + 异常 2)

- L97 [exception] `raise ValueError("缺少必需字段 'action_type'")`
- L101 [exception] `raise ValueError(f"未注册的 ActionType: {atype.name}")`

## `src/core/variables/pool.py` (logger 8 + 异常 4)

- L81 [logger] `logger.warning("变量 '%s' 在 %s 作用域已存在，覆盖", name, scope.value)`
- L92 [logger] `logger.debug("声明变量: %s [%s] = %r (%s)", name, var_type.value, value, scope.value)`
- L115 [exception] `raise KeyError(f"变量 '{name}' 在 {scope.value} 作用域中不存在")`
- L145 [logger] `logger.debug("变量 '%s' 未声明，自动创建", name)`
- L166 [logger] `logger.debug("设置变量: %s = %r -> %r (%s)", name, old_value, value, scope.value)`
- L207 [logger] `logger.debug("进入作用域: %s (栈深度: %d)", scope.value, len(self._scope_stack))`
- L222 [logger] `logger.debug("退出作用域: %s", scope.value)`
- L257 [logger] `logger.warning("模板引用的变量 '%s' 不存在", var_name)`
- L387 [exception] `raise KeyError(f"未知的内置变量: '{name}'")`
- L398 [logger] `logger.error("变量变更回调出错: %s", e)`
- L419 [exception] `raise TypeError(f"无法推断 tuple 值的类型: {value!r}，仅支持长度 2 (COORD) 或 4 (COORD_RECT) 的 int tuple")`
- L422 [exception] `raise TypeError(f"无法推断值 {value!r} 的变量类型")`

## `src/core/variables/typed_variable.py` (logger 0 + 异常 1)

- L62 [exception] `raise ValueError(f"检测到循环引用: {chain}")`

## `src/core/vision/buffer_pool.py` (logger 0 + 异常 2)

- L53 [exception] `raise RuntimeError("DoubleBufferPool 缓冲区未初始化")`
- L108 [exception] `raise RuntimeError("BufferPool 缓冲区未初始化")`

## `src/core/vision/ocr_recognizer.py` (logger 4 + 异常 0)

- L56 [logger] `logger.info("OCR 引擎初始化成功 (rapidocr-onnxruntime)")`
- L58 [logger] `logger.error("OCR 引擎初始化失败: %s", e)`
- L112 [logger] `logger.error("OCR 识别失败: %s", e)`
- L150 [logger] `logger.warning("未注册的 ROI: '%s'", roi_name)`

## `src/core/vision/pixel_searcher.py` (logger 1 + 异常 0)

- L164 [logger] `logger.warning("未知颜色预设: '%s'", color_name)`

## `src/core/vision/vision_pipeline.py` (logger 2 + 异常 0)

- L234 [logger] `logger.warning("VisionPipeline 上下文缺少 _matcher，使用模块级懒加载实例")`
- L523 [logger] `logger.error("管线步骤 '%s' 执行失败 (%.1fms): %s", step.name, elapsed_ms, e)`

## `src/panel/app.py` (logger 4 + 异常 0)

- L139 [logger] `logger.warning("延迟注册页面模块失败: %s", mod_name, exc_info=True)`
- L391 [logger] `logger.debug("监控轮询: 窗口已关闭")`
- L395 [logger] `logger.warning("监控轮询异常", exc_info=True)`
- L540 [logger] `logger.exception("重启失败，尝试恢复服务")`

## `src/panel/backend_selector.py` (logger 1 + 异常 0)

- L31 [logger] `logger.debug("无法从配置文件读取 GUI 后端设置，使用默认值")`

## `src/panel/controllers/action_chain_controller.py` (logger 0 + 异常 1)

- L55 [exception] `raise ValueError("请先添加至少一个动作步骤")`

## `src/panel/controllers/base_controller.py` (logger 0 + 异常 1)

- L63 [exception] `raise RuntimeError("执行器运行中，无法修改")`

## `src/panel/controllers/workflow_controller.py` (logger 0 + 异常 1)

- L247 [exception] `raise ValueError("请先创建流程节点")`

## `src/panel/dialogs/__init__.py` (logger 0 + 异常 1)

- L52 [exception] `raise ValueError(f"未注册的 ActionType: {step.action_type}")`

## `src/panel/pages/action_chain_page.py` (logger 2 + 异常 0)

- L354 [logger] `logger.exception("创建步骤失败: %s", action_type)`
- L368 [logger] `logger.exception("打开步骤对话框失败: %s", action_type)`

## `src/panel/pages/page_registry.py` (logger 1 + 异常 0)

- L109 [logger] `logger.debug("注册页面: %s → %s:%s", page_id, module, page_class.__qualname__)`

## `src/panel/qt_backend/app.py` (logger 3 + 异常 0)

- L354 [logger] `logger.warning("监控轮询异常", exc_info=True)`
- L493 [logger] `logger.exception("重启失败，尝试恢复服务")`
- L550 [logger] `logger.warning("关闭清理异常", exc_info=True)`

## `src/panel/qt_backend/dialogs/step_dialogs.py` (logger 0 + 异常 1)

- L55 [exception] `raise ValueError(f"未注册的 ActionType: {step.action_type}")`

## `src/plugins/builtin/combat/__init__.py` (logger 2 + 异常 0)

- L355 [logger] `logger.info("CombatPlugin 加载中...")`
- L358 [logger] `logger.info("CombatPlugin 卸载中...")`

## `src/plugins/builtin/navigation/__init__.py` (logger 2 + 异常 0)

- L379 [logger] `logger.info("NavigationPlugin 加载中...")`
- L382 [logger] `logger.info("NavigationPlugin 卸载中...")`

## `src/plugins/builtin/task/__init__.py` (logger 2 + 异常 0)

- L351 [logger] `logger.info("TaskPlugin 加载中...")`
- L354 [logger] `logger.info("TaskPlugin 卸载中...")`

## `src/recorder/recorder.py` (logger 10 + 异常 0)

- L113 [logger] `logger.info("宏录制已开始")`
- L266 [logger] `logger.error("不支持的平台: Linux")`
- L421 [logger] `logger.warning("CGEventTap 被系统超时禁用，尝试重新启用")`
- L436 [logger] `logger.info("CGEvent 首次捕获: type=%d (%s)", event_type, etype_name)`
- L557 [logger] `logger.error("无法创建 CGEventTap — 请检查辅助功能权限")`
- L564 [logger] `logger.info("macOS CGEventTap 已启动，开始捕获事件")`
- L569 [logger] `logger.info("macOS CGEventTap 已停止")`
- L662 [logger] `logger.info("Windows pynput 监听已启动，开始捕获事件")`
- L665 [logger] `logger.error("Windows 宏录制启动失败: %s", e)`
- L673 [logger] `logger.info("Windows pynput 监听已停止")`

## `src/schedule/scheduler.py` (logger 4 + 异常 0)

- L349 [logger] `logger.info("调度状态已保存到 %s", target)`
- L355 [logger] `logger.debug("调度文件不存在: %s", target)`
- L367 [logger] `logger.warning("跳过无效调度 %s: %s", sid, exc)`
- L369 [logger] `logger.info("从 %s 加载了 %d 个调度", target, count)`

## `src/utils/restart.py` (logger 1 + 异常 0)

- L26 [logger] `logger.info("重启应用: %s", " ".join(cmd))`

