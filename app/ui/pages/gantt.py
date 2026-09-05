"""甘特图页：自绘时间轴（paintEvent）+ 全部/当前周期切换 + 条形点击跳详情。"""
from __future__ import annotations

import datetime
from typing import Any, List, Optional

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, EmptyState
from ...core import api
from ...core.worker import run_async

DAY_MS = 86400000.0
ROW_H = 40
BAR_H = 18
AXIS_H = 26
LABEL_W = 150   # 左侧标签列宽
PAD_R = 16


def _parse_dt(s: Any) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
    except Exception:  # noqa: BLE001
        return None


def _ts(s: Any, default: float = 0.0) -> float:
    dt = _parse_dt(s)
    return dt.timestamp() * 1000.0 if dt else default


def _clamp01(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v or 0)))
    except (TypeError, ValueError):
        return 0.0


def _md(dt: Optional[datetime.datetime]) -> str:
    return dt.strftime("%m-%d") if dt else "--"


def _toast_err(msg: str):
    from PySide6.QtWidgets import QApplication
    toast = getattr(QApplication.instance(), "vis_toast", None)
    if toast:
        toast.show_msg(str(msg), "error")
    else:
        print("[gantt api error]", msg)


class GanttChart(QWidget):
    """自绘甘特图：时间刻度轴 + 网格线 + 今日红线 + 每目标条形（轨道/实心/应达刻度）。"""

    bar_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[dict] = []
        self._today_ms: float = 0.0
        self._bars: List[tuple] = []  # (QRect, objective_id)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def set_data(self, items: List[dict], today_iso: Any):
        self._items = [i for i in items if isinstance(i, dict)]
        self._today_ms = _ts(today_iso, datetime.datetime.now().timestamp() * 1000.0)
        self._bars = []
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        return QRect(0, 0, 600, AXIS_H + max(1, len(self._items)) * ROW_H + 12).size()

    # ---------------- 布局计算 ----------------
    def _layout(self):
        items = self._items
        if not items:
            return None
        starts = [_ts(i.get("startAt")) for i in items]
        ends = [_ts(i.get("endAt")) for i in items]
        min_start = min(starts)
        max_end = max(ends)
        span = max(max_end - min_start, DAY_MS)
        # 右侧给标题文字预留时间缓冲（按绘图区宽度换算）
        plot_w = max(200, self.width() - LABEL_W - PAD_R)
        max_label_px = min(320.0, max(_title_px(str(i.get("title") or "")) for i in items) + 28)
        label_pad = ((max_label_px) * span) / plot_w
        domain_min = min_start
        total = (max_end + label_pad) - domain_min
        if total <= 0:
            total = DAY_MS

        def to_x(ms: float) -> float:
            return LABEL_W + ((ms - domain_min) / total) * plot_w

        ticks = []
        for k in range(7):
            v = domain_min + total * k / 6.0
            dt = datetime.datetime.fromtimestamp(v / 1000.0)
            ticks.append((to_x(v), dt.strftime("%m-%d")))
        return {"to_x": to_x, "ticks": ticks, "starts": starts, "ends": ends,
                "min": domain_min, "total": total, "plot_w": plot_w}

    # ---------------- 绘制 ----------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        lay = self._layout()
        if lay is None:
            p.end()
            return
        tokens = self.window().property("vis_tokens") if self.window() else None
        muted_fg = QColor(getattr(tokens, "muted_fg", "#6B7280")) if tokens else QColor("#6B7280")
        border = QColor(getattr(tokens, "border", "#E4E7ED")) if tokens else QColor("#E4E7ED")
        destructive = QColor(getattr(tokens, "destructive", "#F56C6C")) if tokens else QColor("#F56C6C")
        warning = QColor(getattr(tokens, "warning", "#E6A23C")) if tokens else QColor("#E6A23C")

        body_top = AXIS_H
        body_h = len(self._items) * ROW_H
        to_x = lay["to_x"]

        # 网格线 + 顶部刻度
        axis_font = QFont()
        axis_font.setPointSize(8)
        p.setFont(axis_font)
        for x, label in lay["ticks"]:
            p.setPen(QPen(border))
            p.drawLine(int(x), body_top, int(x), body_top + body_h)
            p.setPen(muted_fg)
            tw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(QRect(int(x - tw / 2), 2, tw + 8, AXIS_H - 4),
                       Qt.AlignLeft | Qt.AlignVCenter, label)

        small = QFont()
        small.setPointSize(8)
        self._bars = []
        for idx, item in enumerate(self._items):
            top = body_top + idx * ROW_H
            start = lay["starts"][idx]
            end = max(lay["ends"][idx], start + DAY_MS * 0.02)
            x1 = to_x(start)
            x2 = to_x(end)
            bar_w = max(2.0, x2 - x1)
            bar_rect = QRect(int(x1), top + (ROW_H - BAR_H) // 2, int(bar_w), BAR_H)
            self._bars.append((bar_rect, str(item.get("id") or "")))

            lagging = bool(item.get("isLagging"))
            color = QColor(destructive) if lagging else QColor(str(item.get("color") or "#409EFF"))
            if not color.isValid():
                color = QColor("#409EFF")

            # 左侧标签列：日期区间
            p.setFont(small)
            p.setPen(muted_fg)
            sdt = _parse_dt(item.get("startAt"))
            edt = _parse_dt(item.get("endAt"))
            p.drawText(QRect(0, top, LABEL_W - 10, ROW_H),
                       Qt.AlignRight | Qt.AlignVCenter,
                       "%s ~ %s" % (_md(sdt), _md(edt)))

            # 浅色轨道（计划工期）
            track = QColor(color)
            track.setAlpha(64)
            p.setPen(Qt.NoPen)
            p.setBrush(track)
            p.drawRoundedRect(bar_rect, BAR_H / 2.0, BAR_H / 2.0)

            # 实心填充（当前进度）
            prog = _clamp01(item.get("currentProgress"))
            if prog > 0:
                fill_w = max(BAR_H if prog < 1.0 else bar_w, bar_w * prog)
                fill = QRect(bar_rect.x(), bar_rect.y(),
                             int(min(fill_w, bar_rect.width())), bar_rect.height())
                p.setBrush(color)
                p.drawRoundedRect(fill, BAR_H / 2.0, BAR_H / 2.0)

            # 应达进度刻度线
            exp = _clamp01(item.get("expectedProgress"))
            ex = bar_rect.x() + int(bar_rect.width() * exp)
            p.setPen(QPen(muted_fg, 2))
            p.drawLine(ex, bar_rect.top() - 3, ex, bar_rect.bottom() + 3)

            # 信心度角标
            conf = str(item.get("worstConfidence") or "")
            conf_color = None
            if conf == "off_track":
                conf_color = destructive
            elif conf == "at_risk":
                conf_color = warning
            if conf_color is not None:
                p.setPen(Qt.NoPen)
                p.setBrush(conf_color)
                p.drawEllipse(QRect(bar_rect.x() - 10,
                                    bar_rect.center().y() - 4, 8, 8))

            # 条形右侧标题
            p.setFont(small)
            p.setPen(destructive if lagging else muted_fg)
            title = str(item.get("title") or "")
            avail = self.width() - (bar_rect.right() + 8) - PAD_R
            title = _elide(p, title, max(0, avail))
            p.drawText(QRect(bar_rect.right() + 8, top,
                             max(0, self.width() - bar_rect.right() - 8 - PAD_R), ROW_H),
                       Qt.AlignLeft | Qt.AlignVCenter, title)

        # 今日红线 + 「今日」标签
        tx = to_x(self._today_ms)
        if lay["min"] <= self._today_ms <= lay["min"] + lay["total"]:
            p.setPen(QPen(destructive, 2))
            p.drawLine(int(tx), body_top - 4, int(tx), body_top + body_h)
            p.setFont(small)
            fm = p.fontMetrics()
            tag_w = fm.horizontalAdvance("今日") + 10
            tag = QRect(int(tx) + 4, 2, tag_w, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(destructive)
            p.drawRoundedRect(tag, 4, 4)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(tag, Qt.AlignCenter, "今日")
        p.end()

    # ---------------- 交互 ----------------
    def _hit(self, pos) -> Optional[str]:
        for rect, oid in self._bars:
            if rect.adjusted(-2, -6, 2, 6).contains(pos):
                return oid
        return None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            oid = self._hit(e.pos())
            if oid:
                self.bar_clicked.emit(oid)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        oid = self._hit(e.pos())
        if oid:
            item = next((i for i in self._items if str(i.get("id")) == oid), None)
            if item:
                sdt, edt = _parse_dt(item.get("startAt")), _parse_dt(item.get("endAt"))
                tip = "%s\n%s ~ %s\n进度: %d%% · 应达: %d%%\n%s" % (
                    item.get("title") or "", _md(sdt), _md(edt),
                    round(_clamp01(item.get("currentProgress")) * 100),
                    round(_clamp01(item.get("expectedProgress")) * 100),
                    "⚠ 滞后" if item.get("isLagging") else "✅ 正常")
                self.setToolTip(tip)
                from PySide6.QtGui import QToolTip
                QToolTip.showText(e.globalPos(), tip, self)
        else:
            self.setToolTip("")
        super().mouseMoveEvent(e)


def _title_px(s: str) -> float:
    w = 0.0
    for ch in s:
        w += 12.0 if ord(ch) > 255 else 7.0
    return w


def _elide(p: QPainter, text: str, avail_px: int) -> str:
    fm = p.fontMetrics()
    if fm.horizontalAdvance(text) <= avail_px or avail_px <= 8:
        return text if avail_px > 8 else ""
    while text and fm.horizontalAdvance(text + "…") > avail_px:
        text = text[:-1]
    return text + "…"


@register_page("/gantt")
class GanttPage(Page):
    path = "/gantt"

    def __init__(self, shell):
        super().__init__(shell)
        self._scope = "all"

        head = QHBoxLayout()
        title = QLabel("甘特图")
        title.setProperty("role", "title")
        head.addWidget(title)
        head.addStretch()
        self._btn_all = QPushButton("全部")
        self._btn_cycle = QPushButton("当前周期")
        for b in (self._btn_all, self._btn_cycle):
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("preset", "ghost")
        self._btn_all.clicked.connect(lambda: self._set_scope("all"))
        self._btn_cycle.clicked.connect(lambda: self._set_scope("cycle"))
        head.addWidget(self._btn_all)
        head.addWidget(self._btn_cycle)
        self.body_layout.addLayout(head)

        self._card = Card(padding=20)
        self._chart = GanttChart()
        self._chart.bar_clicked.connect(lambda oid: self.shell.open_objective(oid))
        self._empty = EmptyState("暂无甘特数据")
        self._card.add(self._chart)
        self.body_layout.addWidget(self._card)
        self._legend()
        self.body_layout.addStretch(1)
        self._sync_scope_buttons()

    def _legend(self):
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addStretch()
        specs = [("18x8 rounded rgba(64,158,255,64)", "计划工期"),
                 ("18x8 rounded #409EFF", "当前进度"),
                 ("2x12 rounded #6B7280", "应达进度"),
                 ("18x8 rounded #F56C6C", "滞后")]
        for style, text in specs:
            parts = style.split(" ", 2)
            w, h = int(parts[0].split("x")[0]), int(parts[0].split("x")[1])
            sw = QLabel()
            sw.setFixedSize(w, h)
            radius = h // 2
            sw.setStyleSheet("background:%s;border-radius:%dpx;" % (parts[2], radius))
            lbl = QLabel(text)
            lbl.setProperty("role", "muted")
            g = QHBoxLayout()
            g.setSpacing(6)
            g.addWidget(sw)
            g.addWidget(lbl)
            row.addLayout(g)
        row.addStretch()
        self.body_layout.addLayout(row)

    def _sync_scope_buttons(self):
        self._btn_all.setProperty("preset", "primary" if self._scope == "all" else "ghost")
        self._btn_cycle.setProperty("preset", "primary" if self._scope == "cycle" else "ghost")
        for b in (self._btn_all, self._btn_cycle):
            b.style().unpolish(b)
            b.style().polish(b)

    def _set_scope(self, scope: str):
        if scope == self._scope:
            return
        self._scope = scope
        self._sync_scope_buttons()
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        scope = self._scope
        run_async(lambda: api.gantt_get(scope=scope), on_ok=self._apply, on_err=_toast_err)

    def _apply(self, data: Any):
        items = []
        today = None
        if isinstance(data, dict):
            raw = data.get("items")
            if isinstance(raw, list):
                items = raw
            today = data.get("todayLine")
        elif isinstance(data, list):
            items = data
        _clear_layout_keep(self._card.layout, (self._chart, self._empty))
        if items:
            self._chart.set_data(items, today)
            self._card.add(self._chart)
            self._chart.show()
        else:
            self._card.add(self._empty)
            self._empty.show()


def _clear_layout_keep(lay, keep):
    """清空布局；keep 中的常驻控件只移出、不销毁。"""
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w is None:
            continue
        if any(w is k for k in keep):
            w.setParent(None)
            w.hide()
        else:
            w.deleteLater()
