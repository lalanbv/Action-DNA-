"""下拉选择框契约（Phase 2，规格 §5.2 U2）。

两后端 ``themed_dropdown`` 工厂对齐：均接受 ``options=[(internal_value, i18n_key), ...]``
元组列表，显示文本经 i18n 翻译、存 internal value。

- tk：``src.panel.widgets.themed_dropdown``（委托 DNADropdown，options 为
  ``[(value, i18n_key), ...]``，``get_value()`` 返回 value）。
- Qt：``src.panel.qt_backend.widgets.themed_dropdown``（QComboBox + addItem(text=t(key),
  userData=value)；``currentData()`` 返回 value）。

历史分歧（已统一）：Qt 旧名 ``themed_combobox(items=list[str])`` 用纯字符串且
``currentText()`` 取值（存翻译文本，非 value）。现已对齐 tk 语义（规格 §5.2 U2），
``themed_combobox`` 保留为 deprecation alias。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DropdownSpec:
    """下拉选择框契约 —— 两后端 ``themed_dropdown`` 必须支持。"""

    #: ``[(internal_value, i18n_key), ...]``；显示文本经 i18n 翻译，存 internal value。
    options: tuple[tuple[str, str], ...] = ()
    value: str = ""
    enabled: bool = True


#: 两后端 ``themed_dropdown`` 工厂必须接受的关键字参数（props 契约）。
DROPDOWN_PROPS: tuple[str, ...] = ("options", "value")
