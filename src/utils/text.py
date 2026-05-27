"""text — 共享文本处理工具函数。"""


def truncate(text: str, limit: int) -> str:
    """截断文本，超出 limit 时追加省略号。"""
    if not text:
        return ""
    return text[:limit] + ("…" if len(text) > limit else "")
