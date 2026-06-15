"""框架无关的共享层（Model + Controller）—— 非 UI 的、两后端共用的逻辑。

对照规格 docs/superpowers/specs/2026-06-15-theme-dedup-unify-design.md §3.1：
本包收纳非主题的框架无关逻辑（页面编排、注册元数据、组件契约规格等），
tkinter 与 Qt 两个 View 层各自 import 本包，互不 import 对方。

当前内容：
- ``controllers.workflow_ops`` —— 工作流图编排纯逻辑（D5 下沉）。
"""
