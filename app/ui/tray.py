"""系统托盘：显示/隐藏悬浮窗、显示主窗口、退出。

图标沿用自绘风格（参考 shell._avatar_icon：纯色圆底 + 白色内容），紫色圆底 + 白色对勾。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _tray_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#7C3AED"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, 56, 56)
    pen = QPen(QColor("#FFFFFF"))
    pen.setWidthF(6.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(20, 33), QPointF(29, 42), QPointF(45, 23)]))
    p.end()
    return QIcon(pm)


class SummitTray(QSystemTrayIcon):
    def __init__(self, app):
        super().__init__(_tray_icon(), app)
        self.setToolTip("Summit OKR")
        menu = QMenu()
        menu.addAction("显示/隐藏悬浮窗", app.toggle_widget)
        menu.addAction("显示主窗口", app.show_main)
        menu.addSeparator()
        menu.addAction("退出", app.quit)
        self.setContextMenu(menu)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.show()
