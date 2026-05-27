"""内置节点描述符 — 每种动作类型对应一个描述符子类。"""

from src.core.engine.descriptors.click_image_descriptor import (  # noqa: F401
    ClickImageDescriptor,
)
from src.core.engine.descriptors.click_pos_descriptor import (  # noqa: F401
    ClickPosDescriptor,
)
from src.core.engine.descriptors.condition_descriptor import (  # noqa: F401
    ConditionDescriptor,
)
from src.core.engine.descriptors.extended_descriptors import (  # noqa: F401
    HoldKeyDescriptor,
    IdleBehaviorDescriptor,
    KeyComboDescriptor,
    MouseDragDescriptor,
    MouseScrollDescriptor,
    MultiKeySequenceDescriptor,
    StartTimerDescriptor,
)
from src.core.engine.descriptors.flow_descriptors import (  # noqa: F401
    EndDescriptor,
    LoopDescriptor,
    MergeDescriptor,
    StartDescriptor,
)
from src.core.engine.descriptors.press_key_descriptor import (  # noqa: F401
    PressKeyDescriptor,
)
from src.core.engine.descriptors.pixel_search_descriptor import (  # noqa: F401
    PixelSearchDescriptor,
)
from src.core.engine.descriptors.ocr_descriptor import (  # noqa: F401
    OCRDescriptor,
)
from src.core.engine.descriptors.record_descriptor import (  # noqa: F401
    RecordBridge,
)
from src.core.engine.descriptors.wait_descriptor import (  # noqa: F401
    WaitDescriptor,
    WaitRandomDescriptor,
)
