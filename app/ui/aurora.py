"""Aurora 背景控件：macOS 主题绘制极光壁纸，其余主题纯色。"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from .theme import paint_aurora


class AuroraWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AuroraRoot")
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def paintEvent(self, _):
        t = self.window().property("summit_tokens") if self.window() else None
        p = QPainter(self)
        rect = QRectF(self.rect())
        if t is not None and t.aurora:
            paint_aurora(p, rect, t.mode == "dark")
        else:
            p.fillRect(rect, QColor(t.bg if t is not None else "#F5F7FA"))
        p.end()
