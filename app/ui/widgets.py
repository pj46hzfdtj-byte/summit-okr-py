"""通用组件：Card / Toast / Chip / EmptyState / PageBase。"""
from __future__ import annotations

from PySide6.QtCore import (QPropertyAnimation, Qt, QRectF, QTimer, QParallelAnimationGroup,
                            Signal)
from PySide6.QtGui import QColor, QPainter, QFont, QPen
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QSizePolicy, QVBoxLayout, QWidget)


class Card(QFrame):
    """玻璃/实色卡片容器（QSS: QFrame[card=true]；Vue .vis-card：padding 24、无阴影）。"""

    def __init__(self, parent=None, flat: bool = False, padding: int = 24, kind: str = ""):
        super().__init__(parent)
        self.setProperty("card", kind or ("flat" if flat else "true"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(padding, padding, padding, padding)
        lay.setSpacing(10)
        self._lay = lay

    def add(self, w: QWidget, stretch: int = 0):
        self._lay.addWidget(w, stretch)
        return w

    def add_layout(self, lay, stretch: int = 0):
        self._lay.addLayout(lay, stretch)

    @property
    def layout(self):  # noqa: A003
        return self._lay


class Chip(QLabel):
    def __init__(self, text: str, kind: str = "true", parent=None):
        super().__init__(text, parent)
        self.setProperty("chip", kind)  # true / success / warning / danger


class EmptyState(QLabel):
    def __init__(self, text: str = "暂无数据", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setProperty("role", "muted")
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


class RingProgress(QWidget):
    """环形进度（摘要页 KPI）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._color = "#409EFF"
        self.setFixedSize(84, 84)

    def set(self, value: float, color: str):
        self._value = max(0.0, min(1.0, value))
        self._color = color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(8, 8, self.width() - 16, self.height() - 16)
        pen = QPen(QColor(self._color).lighter(160) if QColor(self._color).lightness() > 128
                   else QColor(self._color).darker(140))
        pen.setWidth(7)
        p.setPen(pen)
        p.drawArc(r, 0, 360 * 16)
        pen2 = QPen(QColor(self._color))
        pen2.setWidth(7)
        pen2.setCapStyle(Qt.RoundCap)
        p.setPen(pen2)
        p.drawArc(r, 90 * 16, -int(self._value * 360) * 16)
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(self._color))
        p.drawText(r, Qt.AlignCenter, f"{int(self._value * 100)}%")
        p.end()


class Toast(QWidget):
    """右下角浮动提示（对齐 web 端 sonner）。"""

    def __init__(self, host: QWidget):
        super().__init__(host, Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self._host = host
        self._stack: list[QWidget] = []
        self._anim = QPropertyAnimation(self, b"pos", self)

    def _place(self):
        h = self._host.height()
        w = self._host.width()
        self.move(w - self.width() - 24, h - self.height() - 24)

    def show_msg(self, text: str, kind: str = "info"):
        colors = {"info": ("#1D1E1F", "#FFFFFF"), "error": ("#F56C6C", "#FFFFFF"),
                  "success": ("#67C23A", "#FFFFFF"), "warn": ("#E6A23C", "#FFFFFF")}
        bg, fg = colors.get(kind, colors["info"])
        for old in self._stack:
            old.deleteLater()
        self._stack.clear()
        lbl = QLabel(text, self)
        lbl.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:10px; padding:10px 16px; font-size:13px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(lbl)
        self._stack.append(lbl)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        QTimer.singleShot(3200, self.hide)

    def info(self, m): self.show_msg(m, "info")
    def error(self, m): self.show_msg(m, "error")
    def success(self, m): self.show_msg(m, "success")
    def warn(self, m): self.show_msg(m, "warn")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()
