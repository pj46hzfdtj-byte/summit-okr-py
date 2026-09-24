"""迷你悬浮总览窗（GlanceWidget）：无边框、置顶、可拖动的桌面速览小窗。

与 Electron 端共用设计约定（见 .trae/documents/desktop-glance-widget.md）：
  320×520 固定、深色玻璃底 rgba(15,23,42,.85)、圆角 14px、1px rgba(255,255,255,.12) 描边、
  白字；样式全部内联、不随应用主题切换。
五分区：① 标题条（兼拖动区 + 关闭×）→ ② KPI 三格 → ③ 今日任务 → ④ 专注周期圆环 → ⑤ 滞后目标。
点击经 clicked = Signal(str) 发出路由，由 App._widget_navigate 唤起主窗口对应页。
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..core import api
from ..core.worker import run_async
from ..state import auth
from .widgets import RingProgress

W, H = 320, 520
EDGE_MARGIN = 6       # 外边距：给圆角留呼吸
SCREEN_MARGIN = 16    # 首次默认位置距主屏工作区边缘
TITLE_H = 36          # 标题条高度（兼拖动区）
DRAG_BOTTOM = EDGE_MARGIN + TITLE_H

FG = "#F8FAFC"
MUTED = "#99FFFFFF"
HEADER = "#CCFFFFFF"
CELL_BG = "#0FFFFFFF"
GREEN = "#4ADE80"
RED = "#F87171"
RING_BLUE = "#60A5FA"


def _hhmm(s: Any) -> str:
    if not s:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
        return dt.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return ""


def _pct(v: Any) -> int:
    try:
        return int(round(max(0.0, min(1.0, float(v or 0))) * 100))
    except (TypeError, ValueError):
        return 0


def _shorten(s: str, n: int = 24) -> str:
    return s if len(s) <= n else s[: n - 1] + "\u2026"  # …


def _clear_layout(lay: QVBoxLayout):
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w:
            w.deleteLater()
        else:
            sub = it.layout()
            if sub and isinstance(sub, QVBoxLayout):
                _clear_layout(sub)


class _ClickRow(QWidget):
    """可点击区（整块发出路由）；release 命中即 accept，避免嵌套重复触发。"""

    clicked = Signal(str)

    def __init__(self, route: str, parent=None):
        super().__init__(parent)
        self._route = route
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit(self._route)
            e.accept()
            return
        super().mouseReleaseEvent(e)


class GlanceWidget(QWidget):
    """无边框置顶速览小窗；60s 轮询 + showEvent 立即刷新 GET /summary。"""

    clicked = Signal(str)

    def __init__(self):
        super().__init__(None, Qt.Window | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowTitle("Summit OKR · 速览")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self._drag_off: Optional[QPoint] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)  # 外边距留圆角呼吸
        root.setSpacing(0)

        # ---- ① 标题条（兼拖动区） ----
        title_bar = QWidget()
        title_bar.setFixedHeight(TITLE_H)
        tb = QHBoxLayout(title_bar)
        tb.setContentsMargins(10, 0, 4, 0)
        tb.setSpacing(6)
        cap = QLabel("Summit OKR · 速览")
        cap.setStyleSheet("color:%s;font-size:13px;font-weight:700;background:transparent;" % FG)
        tb.addWidget(cap)
        tb.addStretch()
        self._off_lbl = QLabel("离线")
        self._off_lbl.setStyleSheet("color:%s;font-size:11px;background:transparent;" % MUTED)
        self._off_lbl.setVisible(False)
        tb.addWidget(self._off_lbl)
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        tb.addWidget(self._dot)
        close = QPushButton("\u00d7")  # ×
        close.setFixedSize(24, 24)
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet(
            "QPushButton{background:transparent;border:none;color:%s;font-size:16px;"
            "border-radius:10px;}"
            "QPushButton:hover{background:#28FFFFFF;}" % FG)
        close.clicked.connect(self.hide)
        tb.addWidget(close)
        root.addWidget(title_bar)
        self._set_status(False)

        # ---- 内容区（五分区之二~五） ----
        self._content = QWidget()
        self._content.setAttribute(Qt.WA_TranslucentBackground)
        self._content_lay = QVBoxLayout(self._content)
        self._content_lay.setContentsMargins(2, 2, 2, 2)
        self._content_lay.setSpacing(10)
        root.addWidget(self._content, 1)

        auth.changed.connect(self._load)
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._load)
        self._timer.start()

        self._restore_pos()
        self._load()

    # ---------- 玻璃底 ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        p.setPen(QPen(QColor(255, 255, 255, 31), 1))
        p.setBrush(QColor(15, 23, 42, 217))
        p.drawRoundedRect(r, 14, 14)
        p.end()

    # ---------- 拖动 + 位置持久化 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() <= DRAG_BOTTOM:
            self._drag_off = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_off is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_off)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag_off is not None:
            self._drag_off = None
            self._save_pos()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def _restore_pos(self):
        s = QSettings()
        pos = None
        try:
            x, y = s.value("ui/widgetX"), s.value("ui/widgetY")
            if x is not None and y is not None:
                pos = QPoint(int(x), int(y))
        except (TypeError, ValueError):
            pos = None
        if pos is None or not self._on_screen(pos):
            ag = QApplication.primaryScreen().availableGeometry()
            pos = QPoint(ag.right() - W - SCREEN_MARGIN + 1, ag.top() + SCREEN_MARGIN)
        self.move(pos)

    def _save_pos(self):
        s = QSettings()
        s.setValue("ui/widgetX", self.x())
        s.setValue("ui/widgetY", self.y())

    @staticmethod
    def _on_screen(pos: QPoint) -> bool:
        rect = QRect(pos, QSize(W, H))
        for scr in QApplication.screens():
            if scr.availableGeometry().intersects(rect):
                return True
        return False

    # ---------- 数据刷新 ----------
    def showEvent(self, e):
        super().showEvent(e)
        self._load()

    def _load(self):
        if not auth.is_authed:
            self._set_status(False)
            self._render_unauthed()
            return
        run_async(api.summary_get, on_ok=self._render, on_err=self._on_err)

    def _on_err(self, _msg: str):
        # 失败保留旧数据，仅标记离线
        self._set_status(True)

    def _set_status(self, offline: bool):
        col = "#6B7280" if offline else GREEN
        self._dot.setStyleSheet("background:%s;border-radius:4px;" % col)
        self._off_lbl.setVisible(offline)

    # ---------- 渲染 ----------
    def _render_unauthed(self):
        _clear_layout(self._content_lay)
        btn = QPushButton("未登录 · 点击登录")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:none;border-radius:10px;"
            "padding:10px 18px;font-size:13px;}"
            "QPushButton:hover{background:#28FFFFFF;}" % (CELL_BG, FG))
        btn.clicked.connect(lambda: self.clicked.emit("/login"))
        self._content_lay.addWidget(btn, 0, Qt.AlignHCenter | Qt.AlignTop)
        self._content_lay.addStretch(1)

    def _render(self, data: Any):
        if not isinstance(data, dict):
            return
        if not auth.is_authed:  # 请求返回前恰好登出
            return
        self._set_status(False)
        _clear_layout(self._content_lay)
        self._content_lay.addWidget(self._kpi_row(data))
        self._content_lay.addWidget(self._tasks_section(data.get("todayTasks") or []))
        self._content_lay.addWidget(self._cycle_section(data))
        self._content_lay.addWidget(self._lagging_section(data.get("laggingObjectives") or []))
        self._content_lay.addStretch(1)

    def _muted(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:%s;font-size:11px;background:transparent;" % MUTED)
        return lbl

    def _kpi_row(self, data: dict) -> QWidget:
        """② KPI 三格：今日记录 / 进行中目标 / 今日任务 → /summary"""
        row = _ClickRow("/summary")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        stats = (("今日记录", data.get("todayAddedRecords")),
                 ("进行中目标", data.get("inProgressObjectives")),
                 ("今日任务", data.get("todayTaskCount")))
        for cap_txt, val in stats:
            cell = QWidget()
            cell.setAttribute(Qt.WA_StyledBackground, True)
            cell.setStyleSheet("background:%s;border-radius:10px;" % CELL_BG)
            v = QLabel(str(int(val or 0)))
            v.setAlignment(Qt.AlignCenter)
            v.setStyleSheet("color:%s;font-size:20px;font-weight:800;background:transparent;" % FG)
            c = QLabel(cap_txt)
            c.setAlignment(Qt.AlignCenter)
            c.setStyleSheet("color:%s;font-size:11px;background:transparent;" % MUTED)
            col = QVBoxLayout(cell)
            col.setContentsMargins(4, 8, 4, 8)
            col.setSpacing(2)
            col.addWidget(v)
            col.addWidget(c)
            h.addWidget(cell, 1)
        return row

    def _tasks_section(self, tasks: list) -> QWidget:
        """③ 今日任务（最多 5 条）：完成✓绿色划线 / 未完成空心圆点 + 标题 + HH:mm → /tasks"""
        sec = _ClickRow("/tasks")
        v = QVBoxLayout(sec)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        head = QLabel("今日任务")
        head.setStyleSheet("color:%s;font-size:12px;font-weight:600;background:transparent;" % HEADER)
        v.addWidget(head)
        if not tasks:
            v.addWidget(self._muted("今日暂无任务"))
        for task in tasks[:5]:
            if not isinstance(task, dict):
                continue
            r = QWidget()
            h = QHBoxLayout(r)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            done = task.get("status") == "completed"
            mark = QLabel("\u2713" if done else "")  # ✓
            mark.setFixedSize(16, 16)
            mark.setAlignment(Qt.AlignCenter)
            if done:
                mark.setStyleSheet("color:%s;font-size:12px;font-weight:700;background:transparent;" % GREEN)
            else:
                mark.setStyleSheet("border:1.5px solid #66FFFFFF;border-radius:8px;background:transparent;")
            h.addWidget(mark)
            title = QLabel(_shorten(str(task.get("title") or "")))
            title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            tf = QFont()
            tf.setStrikeOut(bool(done))
            title.setFont(tf)
            title.setStyleSheet("color:%s;font-size:12px;background:transparent;"
                                % (MUTED if done else FG))
            h.addWidget(title, 1)
            when = _hhmm(task.get("scheduledAt"))
            if when:
                h.addWidget(self._muted(when))
            v.addWidget(r)
        return sec

    def _cycle_section(self, data: dict) -> QWidget:
        """④ 专注周期圆环：cycleScore% + 名称 + 剩余天数 → /focus-cycle"""
        sec = _ClickRow("/focus-cycle")
        h = QHBoxLayout(sec)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(12)
        ring = RingProgress()
        ring.setFixedSize(76, 76)
        cycle = data.get("activeFocusCycle")
        if isinstance(cycle, dict):
            score = max(0, min(100, int(cycle.get("cycleScore") or 0)))
            ring.set(score / 100.0, RING_BLUE)
            name = str(cycle.get("name") or "未命名周期")
            remain = data.get("cycleDaysRemaining")
            sub = ("%d 天剩余" % int(remain)) if remain is not None else "周期进行中"
        else:
            ring.set(0.0, RING_BLUE)
            name = "暂无活跃专注周期"
            sub = "点击查看专注周期"
        col = QVBoxLayout()
        col.setSpacing(3)
        name_lbl = QLabel(_shorten(name, 20))
        name_lbl.setStyleSheet("color:%s;font-size:13px;font-weight:600;background:transparent;" % FG)
        col.addWidget(name_lbl)
        col.addWidget(self._muted(sub))
        col.addStretch()
        h.addWidget(ring, 0, Qt.AlignVCenter)
        h.addLayout(col, 1)
        return sec

    def _lagging_section(self, lagging: list) -> QWidget:
        """⑤ 滞后目标（最多 4 条）：红点 + 标题 + 进度% → /objectives/{id}"""
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        head = QLabel("滞后目标")
        head.setStyleSheet("color:%s;font-size:12px;font-weight:600;background:transparent;" % RED)
        v.addWidget(head)
        if not lagging:
            v.addWidget(self._muted("全部目标进度正常"))
            return wrap
        for obj in lagging[:4]:
            if not isinstance(obj, dict):
                continue
            oid = obj.get("id")
            row = _ClickRow("/objectives/%s" % oid) if oid else QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 2, 0, 2)
            h.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet("background:%s;border-radius:4px;" % (obj.get("color") or RED))
            h.addWidget(dot)
            title = QLabel(_shorten(str(obj.get("title") or "")))
            title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            title.setStyleSheet("color:%s;font-size:12px;background:transparent;" % FG)
            h.addWidget(title, 1)
            pct = QLabel("%d%%" % _pct(obj.get("currentProgress")))
            pct.setStyleSheet("color:%s;font-size:11px;font-weight:600;background:transparent;" % RED)
            h.addWidget(pct)
            v.addWidget(row)
        return wrap
