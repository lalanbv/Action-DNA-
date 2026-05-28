"""QtRegionPicker — Qt 原生区域框选器（替代 Tkinter 版本）。

截图后显示全屏覆盖层，让用户拖拽选择矩形区域。
使用 QWidget 实现，避免 Tkinter + Qt 共存导致 macOS 崩溃。

修复：
- 多显示器支持：遍历所有屏幕，计算虚拟桌面完整几何
- 混合 DPI 支持：使用实际截图尺寸与显示尺寸的比例计算缩放
- 坐标转换：画布坐标 → mss 坐标 → 逻辑坐标（pyautogui）
- macOS 可见性：窗口标志直接在构造函数中传入，避免 setWindowFlags() 隐藏问题
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import Qt, QPoint, QRect, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QPen, QColor, QPixmap, QImage
from PySide6.QtWidgets import QWidget, QApplication

from src.core.vision._cv2_guard import cv2, require_cv2
from src.panel.canvas.theme import current_theme
from src.panel.region_coords import RegionCoordConverter
from src.utils.i18n import t

logger = logging.getLogger(__name__)


class QtRegionPicker(QWidget):
    """全屏覆盖层区域框选器。

    Args:
        parent: 父窗口（主窗口），确保 macOS 正确管理窗口层级
        capture: ScreenCapture 实例
        callback: 选择完成回调 callback(left, top, width, height)，逻辑像素
        on_cancel: 取消回调（可选）
        pre_captured_bgr: 预截取的 BGR 截图（可选）
    """

    def __init__(
        self,
        parent: QWidget | None,
        capture,
        callback: Callable[[int, int, int, int], None],
        *,
        on_cancel: Callable[[], None] | None = None,
        pre_captured_bgr=None,
    ) -> None:
        # 关键修复：直接在构造函数中传入窗口标志 + 父窗口。
        # 旧代码先 super().__init__(None, Window) 再调用 setWindowFlags()，
        # 但 setWindowFlags() 内部调用 setParent() 会隐藏 widget。
        # macOS/PySide6 上，隐藏后的 widget 即使调用 show() 也可能无法正确恢复。
        super().__init__(
            parent,
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self._callback = callback
        self._on_cancel = on_cancel
        self._closed = False

        self._start_pos: QPoint | None = None
        self._selection: QRect | None = None

        # 截图：优先使用预截图（主窗口已恢复时使用）
        if pre_captured_bgr is not None:
            screen_bgr = pre_captured_bgr
        else:
            screen_bgr = capture.grab()
        require_cv2("region picker")
        screen_rgb = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2RGB)
        # 保持引用防止 GC 回收（QImage 引用此数组的数据）
        self._screen_rgb = screen_rgb
        shot_h, shot_w = screen_rgb.shape[:2]

        self.setWindowTitle(t("region.title"))
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 计算显示区域 — 遍历所有屏幕取并集
        virtual_geo = self._virtual_desktop_geometry()
        max_w = virtual_geo.width() - 60
        max_h = virtual_geo.height() - 80
        display_scale = min(max_w / shot_w, max_h / shot_h, 1.0)
        self._converter = RegionCoordConverter.from_capture(capture, display_scale)

        display_w = int(shot_w * display_scale)
        display_h = int(shot_h * display_scale)

        # BGR numpy → QImage → QPixmap（QPixmap.copy 确保数据独立）
        h, w, ch = screen_rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(screen_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        if qimg.isNull():
            logger.error("QImage is null (shape=%s, bpl=%d)", screen_rgb.shape, bytes_per_line)
            self._close()
            return

        self._pixmap = QPixmap.fromImage(qimg).scaled(
            display_w, display_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._pixmap.isNull():
            logger.error("QPixmap is null after fromImage+scaled (display=%dx%d)", display_w, display_h)
            self._close()
            return

        self.setFixedSize(display_w, display_h)
        pos_x = virtual_geo.x() + (virtual_geo.width() - display_w) // 2
        pos_y = virtual_geo.y() + (virtual_geo.height() - display_h) // 2
        self.move(pos_x, pos_y)

        self._accent_color = QColor(current_theme().accent_red)

        logger.debug(
            "QtRegionPicker: pos=(%d,%d) size=%dx%d shot=%dx%d scale=%.3f",
            pos_x, pos_y, display_w, display_h, shot_w, shot_h, display_scale,
        )

        self.show()
        self.raise_()
        self.activateWindow()
        # macOS 可能在构造函数返回后重新激活主窗口，延迟确保置顶
        QTimer.singleShot(50, self.raise_)
        QTimer.singleShot(150, self.raise_)

    @staticmethod
    def _virtual_desktop_geometry() -> QRect:
        """计算所有屏幕的并集几何（支持多显示器）。"""
        screens = QApplication.screens()
        if not screens:
            return QRect(0, 0, 1920, 1080)
        union = screens[0].availableGeometry()
        for s in screens[1:]:
            union = union.united(s.availableGeometry())
        return union

    # ── 事件处理 ──

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.position().toPoint()
            self._selection = None
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            cur = event.position().toPoint()
            self._selection = QRect(self._start_pos, cur).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._selection is not None:
            sel = self._selection
            lx, ly, w, h = self._converter.to_logical_rect(
                sel.left(), sel.top(), sel.right(), sel.bottom(),
            )
            self._close()
            if w > 10 and h > 10:
                self._callback(lx, ly, w, h)

    # ── 绘制 ──

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制截图
        painter.drawPixmap(0, 0, self._pixmap)

        if self._selection is not None:
            sel = self._selection
            w = self.width()
            h = self.height()

            # 半透明遮罩（选区外变暗）
            dim = QColor(0, 0, 0, 128)
            # 上
            if sel.top() > 0:
                painter.fillRect(0, 0, w, sel.top(), dim)
            # 下
            if sel.bottom() < h:
                painter.fillRect(0, sel.bottom(), w, h - sel.bottom(), dim)
            # 左
            if sel.left() > 0:
                painter.fillRect(0, sel.top(), sel.left(), sel.height(), dim)
            # 右
            if sel.right() < w:
                painter.fillRect(sel.right(), sel.top(), w - sel.right(), sel.height(), dim)

            # 选区边框
            pen = QPen(self._accent_color, 2)
            painter.setPen(pen)
            painter.drawRect(sel)

        painter.end()

    # ── 关闭 ──

    def _cancel(self) -> None:
        if self._closed:
            return
        self._close()
        if self._on_cancel:
            self._on_cancel()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.close()
        self.deleteLater()


def show_region_picker(
    app: QWidget,
    capture,
    callback: Callable[[int, int, int, int], None],
    *,
    on_cancel: Callable[[], None] | None = None,
) -> None:
    """截图后隐藏主窗口，弹出全屏区域框选器。

    流程：
    1. 立即截图（包含当前屏幕所有内容）
    2. 隐藏主窗口
    3. 创建全屏覆盖层，显示截图让用户框选区域
    4. 框选完成后恢复主窗口

    不再使用透明度技巧（setWindowOpacity(0)），因为：
    - 200ms 延迟在慢系统上不够，截图仍包含窗口
    - 透明度恢复后窗口可能抢夺焦点，导致框选器无法操作
    - macOS 上透明窗口行为不可预测
    """
    try:
        screen_bgr = capture.grab()
    except Exception:
        logger.exception("Screen capture failed in region picker")
        return

    app.hide()
    QApplication.processEvents()

    def _on_picker_done(*_args) -> None:
        app.show()
        app.raise_()
        app.activateWindow()

    def _on_picker_cancel() -> None:
        app.show()
        app.raise_()
        app.activateWindow()
        if on_cancel:
            on_cancel()

    original_callback = callback

    def _wrapped_callback(lx: int, ly: int, w: int, h: int) -> None:
        _on_picker_done()
        original_callback(lx, ly, w, h)

    try:
        QtRegionPicker(
            app, capture, _wrapped_callback, on_cancel=_on_picker_cancel,
            pre_captured_bgr=screen_bgr,
        )
    except Exception:
        logger.exception("Failed to create QtRegionPicker")
        app.show()
        app.raise_()
        app.activateWindow()
