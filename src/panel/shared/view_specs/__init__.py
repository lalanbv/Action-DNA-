"""组件契约规格（Phase 2，规格 §5.1）。

契约 = 纯数据描述（props/state/events 语义），非抽象基类。两后端各自
idiomatically 实现（tk widgets.py 工厂 / Qt widgets.py 工厂），由
``tests/unit/panel/test_view_specs.py`` 校验两后端工厂接受相同 props。

YAGNI：只为与主题/统一相关的核心组件立约（button/entry/checkbox），
不强行覆盖全部控件。
"""
