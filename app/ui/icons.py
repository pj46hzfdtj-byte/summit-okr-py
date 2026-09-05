"""侧边栏图标：QPainter 绘制的单色线性图标（11 个，与导航项一一对应）。"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QSize, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication


def _pix(size: int, color: str, draw) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(size * 0.075)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = size
    draw(p, s)
    p.end()
    return pm


def _bars(p, s):  # 摘要
    m, gap = s * 0.18, s * 0.10
    x = m
    for h in (0.32, 0.52, 0.42, 0.62):
        p.drawLine(int(x), int(s - m), int(x), int(s - m - h * s))
        x += (s - 2 * m) / 3


def _tree(p, s):  # 目标库
    p.drawEllipse(QPointF(s * 0.2, s * 0.2), s * 0.07, s * 0.07)
    p.drawEllipse(QPointF(s * 0.8, s * 0.5), s * 0.07, s * 0.07)
    p.drawEllipse(QPointF(s * 0.8, s * 0.85), s * 0.07, s * 0.07)
    p.drawLine(int(s * 0.27), int(s * 0.2), int(s * 0.55), int(s * 0.2))
    p.drawLine(int(s * 0.55), int(s * 0.2), int(s * 0.55), int(s * 0.85))
    p.drawLine(int(s * 0.55), int(s * 0.5), int(s * 0.73), int(s * 0.5))
    p.drawLine(int(s * 0.55), int(s * 0.85), int(s * 0.73), int(s * 0.85))


def _target(p, s):  # 专注周期
    c = s / 2
    for r in (0.34, 0.20):
        p.drawEllipse(QPointF(c, c), s * r, s * r)
    p.drawEllipse(QPointF(c, c), s * 0.05, s * 0.05)


def _calendar(p, s):  # 任务日历
    m = s * 0.16
    p.drawRoundedRect(QRectF(m, m * 1.4, s - 2 * m, s - m * 2.4), s * 0.08, s * 0.08)
    p.drawLine(int(m), int(s * 0.38), int(s - m), int(s * 0.38))
    p.drawLine(int(s * 0.34), int(m * 0.7), int(s * 0.34), int(m * 1.7))
    p.drawLine(int(s * 0.66), int(m * 0.7), int(s * 0.66), int(m * 1.7))


def _gantt(p, s):  # 甘特图
    rows = [(0.22, 0.55), (0.40, 0.78), (0.30, 0.62)]
    for i, (x1, x2) in enumerate(rows):
        y = s * (0.25 + i * 0.25)
        p.drawLine(int(s * x1), int(y), int(s * x2), int(y))
    p.drawLine(int(s * 0.5), int(s * 0.12), int(s * 0.5), int(s * 0.88))


def _pen(p, s):  # 复盘
    m = s * 0.2
    p.drawLine(int(s * m), int(s - s * m), int(s - s * m), int(s * m))
    p.drawEllipse(QPointF(s * m, s - s * m), s * 0.06, s * 0.06)
    p.drawLine(int(s * 0.35), int(s * 0.75), int(s * 0.6), int(s * 0.5))


def _sparkle(p, s):  # AI
    def star(cx, cy, r):
        p.drawLine(int(cx - r), int(cy), int(cx + r), int(cy))
        p.drawLine(int(cx), int(cy - r), int(cx), int(cy + r))
    star(s * 0.4, s * 0.4, s * 0.18)
    star(s * 0.75, s * 0.7, s * 0.10)


def _sunrise(p, s):  # 愿景
    m = s * 0.18
    p.drawLine(int(m), int(s * 0.72), int(s - m), int(s * 0.72))
    rect = QRectF(s * 0.3, s * 0.32, s * 0.4, s * 0.4)
    p.drawArc(rect, 0, 180 * 16)
    p.drawLine(int(s * 0.5), int(s * 0.2), int(s * 0.5), int(s * 0.28))
    p.drawLine(int(s * 0.28), int(s * 0.3), int(s * 0.34), int(s * 0.36))
    p.drawLine(int(s * 0.72), int(s * 0.3), int(s * 0.66), int(s * 0.36))


def _trash(p, s):  # 回收站
    m = s * 0.25
    p.drawRoundedRect(QRectF(m, s * 0.32, s - 2 * m, s * 0.45), s * 0.05, s * 0.05)
    p.drawLine(int(s * 0.18), int(s * 0.32), int(s * 0.82), int(s * 0.32))
    p.drawLine(int(s * 0.4), int(s * 0.24), int(s * 0.6), int(s * 0.24))
    p.drawLine(int(s * 0.42), int(s * 0.44), int(s * 0.42), int(s * 0.66))
    p.drawLine(int(s * 0.58), int(s * 0.44), int(s * 0.58), int(s * 0.66))


def _help(p, s):  # 帮助
    c = s / 2
    p.drawEllipse(QPointF(c, c), s * 0.32, s * 0.32)
    from PySide6.QtGui import QFont
    p.setFont(QFont("Segoe UI", int(s * 0.34), QFont.Bold))
    p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "?")


def _person(p, s):  # 我的
    p.drawEllipse(QPointF(s * 0.5, s * 0.32), s * 0.14, s * 0.14)
    rect = QRectF(s * 0.22, s * 0.55, s * 0.56, s * 0.56)
    p.drawArc(rect, 0, 180 * 16)


def _aim(p, s):  # KPI：总目标数（Aim）
    c = s / 2
    p.drawEllipse(QPointF(c, c), s * 0.32, s * 0.32)
    p.drawEllipse(QPointF(c, c), s * 0.16, s * 0.16)
    for ang in (0, 90, 180, 270):
        import math
        x1 = c + math.cos(math.radians(ang)) * s * 0.32
        y1 = c + math.sin(math.radians(ang)) * s * 0.32
        x2 = c + math.cos(math.radians(ang)) * s * 0.46
        y2 = c + math.sin(math.radians(ang)) * s * 0.46
        p.drawLine(int(x1), int(y1), int(x2), int(y2))


def _trend(p, s):  # KPI：进行中（TrendCharts）
    m = s * 0.16
    p.drawPolyline(QPolygonF([QPointF(s * x, s * y) for x, y in
                              ((0.14, 0.72), (0.4, 0.46), (0.58, 0.6), (0.86, 0.28))]))
    p.drawLine(int(s * 0.86), int(s * 0.28), int(s * 0.66), int(s * 0.28))
    p.drawLine(int(s * 0.86), int(s * 0.28), int(s * 0.86), int(s * 0.48))
    p.drawLine(int(m), int(s * 0.84), int(s - m), int(s * 0.84))


def _check(p, s):  # KPI：已复盘（CircleCheck）
    c = s / 2
    p.drawEllipse(QPointF(c, c), s * 0.34, s * 0.34)
    p.drawPolyline(QPolygonF([QPointF(s * x, s * y) for x, y in
                              ((0.34, 0.52), (0.46, 0.64), (0.68, 0.4))]))


def _warn(p, s):  # KPI：滞后（WarningFilled）
    p.drawPolyline(QPolygonF([QPointF(s * 0.5, s * 0.14), QPointF(s * 0.9, s * 0.82),
                              QPointF(s * 0.1, s * 0.82), QPointF(s * 0.5, s * 0.14)]))
    p.drawLine(int(s * 0.5), int(s * 0.42), int(s * 0.5), int(s * 0.62))
    p.drawEllipse(QPointF(s * 0.5, s * 0.71), s * 0.025, s * 0.025)


_DRAWERS = {
    "bars": _bars, "tree": _tree, "target": _target, "calendar": _calendar,
    "gantt": _gantt, "pen": _pen, "sparkle": _sparkle, "sunrise": _sunrise,
    "trash": _trash, "help": _help, "person": _person,
    "aim": _aim, "trend": _trend, "check": _check, "warn": _warn,
}


def make_pixmap(key: str, color: str = "#4B5563", size: int = 20) -> QPixmap:
    return _pix(size, color, _DRAWERS[key])


def make_icon(key: str, color: str = "#4B5563", size: int = 40) -> QIcon:
    return QIcon(_pix(size, color, _DRAWERS[key]))
