"""摘要页：KPI 卡片 + 随机动机 + 活跃专注周期 + 今日任务 + 滞后目标。"""
from __future__ import annotations

import datetime
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, RingProgress
from ...core import api
from ...core.worker import run_async


def _parse_dt(s: Any) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
    except Exception:  # noqa: BLE001
        return None


def _fmt_date(s: Any) -> str:
    dt = _parse_dt(s)
    return dt.strftime("%Y-%m-%d") if dt else ""


def _pct(v: Any) -> int:
    try:
        return int(round(max(0.0, min(1.0, float(v or 0))) * 100))
    except (TypeError, ValueError):
        return 0


def _toast_err(msg: str):
    from PySide6.QtWidgets import QApplication
    toast = getattr(QApplication.instance(), "vis_toast", None)
    if toast:
        toast.show_msg(str(msg), "error")
    else:
        print("[summary api error]", msg)


class _ClickRow(QWidget):
    """可点击行（滞后目标 / 周期目标）。"""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def _clear_layout(lay: QVBoxLayout):
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w:
            w.deleteLater()
        else:
            sub = it.layout()
            if sub:
                _clear_layout(sub)


def _progress_bar(value: int, color: str) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(max(0, min(100, value)))
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    # 轨道底色沿用全局 QSS（muted），仅覆写 chunk 颜色
    bar.setStyleSheet("QProgressBar::chunk{background:%s;border-radius:4px;}" % color)
    return bar


@register_page("/summary")
class SummaryPage(Page):
    path = "/summary"

    def __init__(self, shell):
        super().__init__(shell)

        title = QLabel("摘要")
        title.setProperty("role", "title")
        self.body_layout.addWidget(title)

        # ---- KPI 行（静态骨架，_apply 中只更新数值） ----
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)

        ring_card = Card()
        ring_box = QHBoxLayout()
        ring_box.setSpacing(12)
        self._ring = RingProgress()
        ring_right = QVBoxLayout()
        self._total_val = QLabel("0")
        self._total_val.setProperty("role", "kpi")
        total_cap = QLabel("总目标")
        total_cap.setProperty("role", "muted")
        ring_right.addWidget(self._total_val)
        ring_right.addWidget(total_cap)
        ring_right.addStretch()
        ring_box.addWidget(self._ring)
        ring_box.addLayout(ring_right, 1)
        ring_card.add_layout(ring_box)
        kpi_row.addWidget(ring_card, 1)

        self._progress_val = self._stat_card(kpi_row, "进行中")
        self._completed_val = self._stat_card(kpi_row, "已复盘")
        self._lagging_val = self._stat_card(kpi_row, "滞后")
        self.body_layout.addLayout(kpi_row)

        # ---- 动态区（动机 / 周期 / 今日任务 / 滞后列表） ----
        self._dyn = QWidget()
        self._dyn_lay = QVBoxLayout(self._dyn)
        self._dyn_lay.setContentsMargins(0, 0, 0, 0)
        self._dyn_lay.setSpacing(14)
        self.body_layout.addWidget(self._dyn)
        self.body_layout.addStretch(1)

    @staticmethod
    def _stat_card(row_lay: QHBoxLayout, caption: str) -> QLabel:
        card = Card()
        val = QLabel("0")
        val.setProperty("role", "kpi")
        cap = QLabel(caption)
        cap.setProperty("role", "muted")
        card.add(val)
        card.add(cap)
        row_lay.addWidget(card, 1)
        return val

    # ------------------------------------------------------------------
    def refresh(self):
        run_async(api.summary_get, on_ok=self._apply, on_err=_toast_err)

    def _apply(self, data: Any):
        if not isinstance(data, dict):
            return
        total = int(data.get("totalObjectives") or 0)
        in_prog = int(data.get("inProgressObjectives") or 0)
        completed = int(data.get("completedObjectives") or 0)
        lagging = data.get("laggingObjectives") or []
        tasks = data.get("todayTasks") or []
        cycle = data.get("activeFocusCycle")
        motive = data.get("randomMotivation")

        self._total_val.setText(str(total))
        self._progress_val.setText(str(in_prog))
        self._completed_val.setText(str(completed))
        self._lagging_val.setText(str(len(lagging)))
        tokens = self.window().property("vis_tokens") if self.window() else None
        primary = getattr(tokens, "primary", "#409EFF") or "#409EFF"
        destructive = getattr(tokens, "destructive", "#F56C6C") or "#F56C6C"
        self._lagging_val.setStyleSheet("color:%s;" % destructive)
        self._ring.set(completed / total if total else 0.0, primary)

        _clear_layout(self._dyn_lay)

        # 随机动机
        if motive:
            card = Card(flat=True)
            box = QHBoxLayout()
            box.setSpacing(10)
            quote = QLabel("\u201c")  # “
            qf = QFont("Georgia", 26)
            qf.setBold(True)
            quote.setFont(qf)
            quote.setProperty("role", "muted")
            text = QLabel(str(motive))
            text.setWordWrap(True)
            text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            box.addWidget(quote, 0, Qt.AlignTop)
            box.addWidget(text, 1)
            card.add_layout(box)
            self._dyn_lay.addWidget(card)

        # 活跃专注周期
        if isinstance(cycle, dict):
            self._dyn_lay.addWidget(self._cycle_card(cycle))

        # 今日任务
        if tasks:
            self._dyn_lay.addWidget(self._tasks_card(tasks))

        # 滞后目标
        if lagging:
            self._dyn_lay.addWidget(self._lagging_card(lagging))

    # ------------------------------------------------------------------
    def _cycle_card(self, cycle: dict) -> Card:
        card = Card()
        head = QHBoxLayout()
        cap = QLabel("活跃专注周期")
        cap.setProperty("role", "subtitle")
        head.addWidget(cap)
        head.addStretch()
        manage = QPushButton("管理")
        manage.setProperty("preset", "ghost")
        manage.setCursor(Qt.PointingHandCursor)
        manage.clicked.connect(lambda: self.shell.navigate("/focus-cycle"))
        head.addWidget(manage)
        card.add_layout(head)

        top = QHBoxLayout()
        left = QVBoxLayout()
        name = QLabel(str(cycle.get("name") or ""))
        name.setProperty("role", "subtitle")
        dates = QLabel("%s → %s" % (_fmt_date(cycle.get("startAt")), _fmt_date(cycle.get("endAt"))))
        dates.setProperty("role", "muted")
        left.addWidget(name)
        left.addWidget(dates)
        top.addLayout(left, 1)
        right = QVBoxLayout()
        r_right = QHBoxLayout()
        r_right.addStretch()
        score_cap = QLabel("周期得分")
        score_cap.setProperty("role", "muted")
        score_val = QLabel(str(int(cycle.get("cycleScore") or 0)))
        score_val.setProperty("role", "kpi")
        right.addWidget(score_cap)
        right.addWidget(score_val)
        top.addLayout(right)
        card.add_layout(top)

        score = int(cycle.get("cycleScore") or 0)
        tokens = self.window().property("vis_tokens") if self.window() else None
        primary = getattr(tokens, "primary", "#409EFF") or "#409EFF"
        card.add(_progress_bar(score, primary))

        for oco in cycle.get("objectives") or []:
            if not isinstance(oco, dict):
                continue
            obj = oco.get("objective")
            if isinstance(obj, dict):
                card.add(self._objective_row(obj, primary, clickable=True))
        return card

    def _tasks_card(self, tasks: list) -> Card:
        card = Card()
        head = QHBoxLayout()
        cap = QLabel("今日任务")
        cap.setProperty("role", "subtitle")
        head.addWidget(cap)
        head.addStretch()
        head.addWidget(Chip(str(len(tasks)), "true"))
        card.add_layout(head)
        for task in tasks:
            if not isinstance(task, dict):
                continue
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(8, 4, 8, 4)
            h.setSpacing(10)
            done = task.get("status") == "completed"
            mark = QLabel("\u2713" if done else "")
            mark.setFixedSize(20, 20)
            mark.setAlignment(Qt.AlignCenter)
            mark.setStyleSheet("border:2px solid %s;border-radius:10px;color:%s;"
                               % ("#67C23A" if done else "#9CA3AF", "#67C23A"))
            h.addWidget(mark)
            title = QLabel(str(task.get("title") or ""))
            if done:
                f = title.font()
                f.setStrikeOut(True)
                title.setFont(f)
                title.setProperty("role", "muted")
            title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            h.addWidget(title, 1)
            when = _parse_dt(task.get("scheduledAt"))
            if when:
                h.addWidget(Chip(when.strftime("%H:%M"), "true"))
            card.add(row)
        return card

    def _lagging_card(self, lagging: list) -> Card:
        card = Card()
        head = QHBoxLayout()
        warn = QLabel("\u26a0")  # ⚠
        warn.setStyleSheet("color:#E6A23C;font-size:15px;")
        cap = QLabel("滞后目标")
        cap.setProperty("role", "subtitle")
        cap.setStyleSheet("color:#F56C6C;")
        head.addWidget(warn)
        head.addWidget(cap)
        head.addStretch()
        card.add_layout(head)
        for obj in lagging:
            if isinstance(obj, dict):
                card.add(self._objective_row(obj, "#E6A23C", clickable=True))
        return card

    def _objective_row(self, obj: dict, bar_color: str,
                       on_click: Optional[Callable[[], None]] = None,
                       clickable: bool = False) -> QWidget:
        row = _ClickRow()
        oid = obj.get("id")
        if clickable and oid:
            row.clicked.connect(lambda: self.shell.open_objective(oid))
        elif on_click:
            row.clicked.connect(on_click)
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 5, 8, 5)
        h.setSpacing(10)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet("background:%s;border-radius:5px;" % (obj.get("color") or bar_color))
        h.addWidget(dot)
        title = QLabel(str(obj.get("title") or ""))
        title.setMaximumWidth(240)
        h.addWidget(title)
        p = _pct(obj.get("currentProgress"))
        h.addWidget(_progress_bar(p, bar_color), 1)
        pv = QLabel("%d%%" % p)
        pv.setProperty("role", "muted")
        pv.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pv.setFixedWidth(40)
        h.addWidget(pv)
        return row
