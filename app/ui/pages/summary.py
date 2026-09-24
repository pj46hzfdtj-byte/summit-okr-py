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
from ..theme import _a
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
    toast = getattr(QApplication.instance(), "summit_toast", None)
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

        # ---- KPI 行（Vue .kpi-grid：4 卡片，icon 方块 + mono 大数字 + 标签） ----
        self._kpi_defs = [
            ("totalObjectives", "总目标数", "aim"),
            ("inProgressObjectives", "进行中", "trend"),
            ("completedObjectives", "已复盘", "check"),
            ("laggingCount", "滞后目标", "warn"),
        ]
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(16)
        self._kpi_vals: dict[str, QLabel] = {}
        for key, label, glyph in self._kpi_defs:
            card, val = self._kpi_card(label, glyph)
            self._kpi_vals[key] = val
            kpi_row.addWidget(card, 1)
        self.body_layout.addLayout(kpi_row)

        # ---- 动态区（动机 / 周期 / 今日任务 / 滞后列表） ----
        self._dyn = QWidget()
        self._dyn_lay = QVBoxLayout(self._dyn)
        self._dyn_lay.setContentsMargins(0, 0, 0, 0)
        self._dyn_lay.setSpacing(14)
        self.body_layout.addWidget(self._dyn)
        self.body_layout.addStretch(1)

    def _kpi_card(self, caption: str, glyph: str) -> tuple[Card, QLabel]:
        """Vue .kpi-card：icon 方块（36px，color 10% 底）+ mono 大数字 + 标签。"""
        from PySide6.QtGui import QPixmap
        from ..icons import make_pixmap
        card = Card(padding=20)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setProperty("kpiGlyph", glyph)
        top.addWidget(icon_lbl)
        top.addStretch()
        card.add_layout(top)
        val = QLabel("0")
        val.setProperty("role", "kpi")
        cap = QLabel(caption)
        cap.setProperty("role", "muted")
        card.add(val)
        card.add(cap)
        card._kpi_icon = icon_lbl
        card._kpi_glyph = glyph
        return card, val

    def _style_kpi_icons(self):
        """按当前 tokens 给 KPI icon 方块上色（primary/brand2/success/destructive）。"""
        tokens = self.window().property("summit_tokens") if self.window() else None
        if tokens is None:
            return
        from ..icons import make_pixmap
        colors = [tokens.primary, tokens.brand2, tokens.success, tokens.destructive]
        i = 0
        for key, _label, _glyph in self._kpi_defs:
            val = self._kpi_vals.get(key)
            if val is None:
                continue
            card = val.parentWidget()
            icon_lbl = getattr(card, "_kpi_icon", None)
            glyph = getattr(card, "_kpi_glyph", "aim")
            if icon_lbl is None:
                continue
            c = colors[i % len(colors)]
            icon_lbl.setPixmap(make_pixmap(glyph, c, 20))
            icon_lbl.setStyleSheet("background:%s;border-radius:%dpx;" % (_a(c, 0.10), tokens.radius_ctrl))
            i += 1

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

        self._style_kpi_icons()
        self._kpi_vals["totalObjectives"].setText(str(total))
        self._kpi_vals["inProgressObjectives"].setText(str(in_prog))
        self._kpi_vals["completedObjectives"].setText(str(completed))
        self._kpi_vals["laggingCount"].setText(str(len(lagging)))
        tokens = self.window().property("summit_tokens") if self.window() else None
        primary = getattr(tokens, "primary", "#1E40AF") or "#1E40AF"

        _clear_layout(self._dyn_lay)

        # 顶部统计行（Vue .stat-row：今日添加记录 / 进行中目标 / 今日任务）
        self._dyn_lay.addWidget(self._stat_row(data))

        # 随机动机（Vue .motivation-banner：橙色渐变 + 大引号）
        if motive:
            card = Card(padding=20)
            card.setProperty("card", "motivation")
            box = QHBoxLayout()
            box.setSpacing(14)
            accent = getattr(tokens, "accent_brand", "#D97706") or "#D97706"
            quote = QLabel("\u201c")  # “
            qf = QFont("Georgia", 26)
            qf.setBold(True)
            quote.setFont(qf)
            quote.setStyleSheet("color:%s;" % accent)
            text = QLabel(str(motive))
            text.setWordWrap(True)
            text.setProperty("role", "body-strong")
            text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            box.addWidget(quote, 0, Qt.AlignTop)
            box.addWidget(text, 1)
            card.add_layout(box)
            self._dyn_lay.addWidget(card)

        # 活跃专注周期
        if isinstance(cycle, dict):
            self._dyn_lay.addWidget(self._cycle_card(cycle, data))

        # 今日任务
        if tasks:
            self._dyn_lay.addWidget(self._tasks_card(tasks))

        # 滞后目标
        if lagging:
            self._dyn_lay.addWidget(self._lagging_card(lagging))

    # ------------------------------------------------------------------
    def _stat_row(self, data: dict) -> Card:
        """Vue .stat-row：一行三个小统计项（icon + 数值 + 标签），今日任务可点击跳任务页。"""
        from ..icons import make_pixmap
        tokens = self.window().property("summit_tokens") if self.window() else None
        primary = getattr(tokens, "primary", "#1E40AF") if tokens else "#1E40AF"
        success = getattr(tokens, "success", "#059669") if tokens else "#059669"
        danger = getattr(tokens, "destructive", "#DC2626") if tokens else "#DC2626"
        muted_fg = getattr(tokens, "muted_fg", "#909399") if tokens else "#909399"

        stats = [
            ("pen", int(data.get("todayAddedRecords") or 0), "今日添加记录", primary, None),
            ("aim", int(data.get("inProgressObjectives") or 0), "进行中目标", success, None),
            ("calendar", int(data.get("todayTaskCount") or 0), "今日任务", danger, "/tasks"),
        ]
        card = Card(padding=14)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        for i, (glyph, value, label, color, link) in enumerate(stats):
            item = _ClickRow()
            h = QHBoxLayout(item)
            h.setContentsMargins(14, 6, 14, 6)
            h.setSpacing(8)
            ic = QLabel()
            ic.setPixmap(make_pixmap(glyph, color, 16))
            h.addWidget(ic)
            v = QLabel(str(value))
            vf = v.font()
            vf.setPointSize(15)
            vf.setBold(True)
            v.setFont(vf)
            v.setStyleSheet("color:%s;" % color)
            h.addWidget(v)
            cap = QLabel(label)
            cap.setStyleSheet("color:%s;font-size:12px;" % muted_fg)
            h.addWidget(cap)
            if link:
                arrow = QLabel("\u203a")  # ›
                arrow.setStyleSheet("color:%s;" % muted_fg)
                h.addWidget(arrow)
                item.clicked.connect(lambda p=link: self.shell.navigate(p))
            else:
                item.setCursor(Qt.ArrowCursor)
            row.addWidget(item, 1)
            if i < len(stats) - 1:
                sep = QWidget()
                sep.setFixedWidth(1)
                sep.setStyleSheet("background:%s;" % (getattr(tokens, "border", "#EBEEF5") if tokens else "#EBEEF5"))
                row.addWidget(sep)
        card.add_layout(row)
        return card

    # ------------------------------------------------------------------
    def _cycle_card(self, cycle: dict, summary: dict) -> Card:
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

        score = int(cycle.get("cycleScore") or 0)
        tokens = self.window().property("summit_tokens") if self.window() else None
        primary = getattr(tokens, "primary", "#409EFF") or "#409EFF"

        # Vue .cycle-body：圆环（周期进度%）+ 侧边统计（今日增加进度 / 进行中目标 / 周期剩余）
        body = QHBoxLayout()
        body.setSpacing(20)
        ring_col = QVBoxLayout()
        ring_col.setContentsMargins(6, 4, 6, 4)
        ring = RingProgress()
        ring.set(max(0.0, min(1.0, score / 100.0)), primary)
        ring_col.addWidget(ring, 0, Qt.AlignHCenter)
        ring_cap = QLabel("周期进度")
        ring_cap.setProperty("role", "muted")
        ring_cap.setAlignment(Qt.AlignCenter)
        ring_col.addWidget(ring_cap)
        body.addLayout(ring_col)

        side = QVBoxLayout()
        side.setSpacing(10)
        name = QLabel(str(cycle.get("name") or ""))
        name.setProperty("role", "subtitle")
        side.addWidget(name)
        dates = QLabel("%s → %s" % (_fmt_date(cycle.get("startAt")), _fmt_date(cycle.get("endAt"))))
        dates.setProperty("role", "muted")
        side.addWidget(dates)

        delta = summary.get("todayProgressDelta")
        delta_txt = "0" if delta is None else ("%g" % round(float(delta) * 100, 1))
        obj_n = len(cycle.get("objectives") or [])
        remain = summary.get("cycleDaysRemaining")
        items = [(delta_txt + "%", "今日增加进度"), (str(obj_n) + "个", "进行中目标")]
        if remain is not None:
            items.append((str(int(remain)) + "天", "周期剩余"))
        stats = QHBoxLayout()
        stats.setSpacing(28)
        for val_txt, cap_txt in items:
            col = QVBoxLayout()
            col.setSpacing(2)
            v = QLabel(val_txt)
            vf = v.font()
            vf.setPointSize(15)
            vf.setBold(True)
            v.setFont(vf)
            v.setStyleSheet("color:%s;" % primary)
            c2 = QLabel(cap_txt)
            c2.setProperty("role", "muted")
            col.addWidget(v)
            col.addWidget(c2)
            stats.addLayout(col)
        stats.addStretch()
        side.addLayout(stats)
        side.addStretch()
        body.addLayout(side, 1)
        card.add_layout(body)

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
