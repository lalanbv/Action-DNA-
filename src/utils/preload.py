"""Background module preloader — warms heavy C extension caches before the main thread needs them.

Usage::

    from src.utils.preload import start_preload, ensure_preloaded
    start_preload()          # returns immediately
    # ... later ...
    ensure_preloaded(2.0)    # block until ready (or timeout)
"""

from __future__ import annotations

import logging
import threading
from typing import Sequence

logger = logging.getLogger(__name__)

_MODULES: dict[str, Sequence[str]] = {
    "vision": (
        "numpy",
        "cv2",
        "mss",
    ),
    "input": (
        "pyautogui",
        "pynput",
    ),
}

_done: threading.Event | None = None


def start_preload() -> None:
    """Start background preloading of heavy modules (idempotent)."""
    global _done
    if _done is not None:
        return
    _done = threading.Event()

    def _preload() -> None:
        for _group, modules in _MODULES.items():
            for name in modules:
                try:
                    __import__(name)
                except ImportError:
                    pass
                except Exception:  # noqa: BLE001
                    logger.debug("Preload skipped: %s", name, exc_info=True)
        _done.set()

    threading.Thread(target=_preload, name="preload", daemon=True).start()


def ensure_preloaded(timeout: float = 5.0) -> None:
    """Block until preload finishes (or timeout). No-op if preload not started."""
    if _done is not None:
        _done.wait(timeout=timeout)
