"""cv2 可用性守卫 — 集中管理 opencv-python 可选依赖检查。"""

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore[assignment]


def require_cv2(purpose: str = "this feature") -> None:
    """当 cv2 未安装时抛出 ImportError。

    Args:
        purpose: 功能描述，用于错误消息（如 "screen capture"）。
    """
    if cv2 is None:
        raise ImportError(
            f"opencv-python (cv2) is required for {purpose}. "
            "Install it with: pip install opencv-python"
        )
