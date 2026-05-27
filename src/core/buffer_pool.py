"""向后兼容垫片 — BufferPool 已迁移到 src.core.vision.buffer_pool。"""

from src.core.vision.buffer_pool import BufferPool, DoubleBufferPool

__all__ = ["BufferPool", "DoubleBufferPool"]
