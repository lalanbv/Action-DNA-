"""日志模块

在 root logger 上配置 handler（控制台 + 文件），
这样所有通过 logging.getLogger(__name__) 创建的模块 logger
都会通过 propagate 机制输出到同一组 handler。
"""

import logging
import os
import sys
from datetime import datetime

from src.utils.paths import get_logs_dir


LOG_DIR = get_logs_dir()


def setup_logger(name: str = "ActionDNA", level: int = logging.INFO) -> logging.Logger:
    """配置 root logger 并返回具名 logger。

    handler 注册在 root logger 上，所有子 logger（包括
    logging.getLogger(__name__) 创建的模块 logger）自动继承。
    """
    root = logging.getLogger()
    if root.handlers:
        return logging.getLogger(name)

    root.setLevel(level)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出 — 立即刷新
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.flush = lambda: sys.stdout.flush()  # type: ignore[method-assign]
    root.addHandler(sh)

    # 文件输出 — 每次写入后刷新，确保日志完整
    os.makedirs(LOG_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fh = logging.FileHandler(
        os.path.join(LOG_DIR, f"{today}.log"), encoding="utf-8"
    )
    fh.setFormatter(fmt)
    # 包装 emit 以确保每次写入后 flush
    original_emit = fh.emit
    def _flushing_emit(record):
        original_emit(record)
        fh.flush()
    fh.emit = _flushing_emit  # type: ignore[method-assign]
    root.addHandler(fh)

    # 抑制第三方库的冗余日志
    for noisy in ("PIL", "urllib3", "requests", "pyautogui"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger(name)


# 全局 logger 实例
log = setup_logger()
