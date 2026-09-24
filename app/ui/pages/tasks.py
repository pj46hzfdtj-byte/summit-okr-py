"""任务日历页：任务列表 + 完成/过期/重复 + 筛选 + 新建 + 批量删除 + 清理过期。

VisOKR 风格：顶部横向周日期条、右下浮动「＋」FAB、完成庆祝浮层、已完成行绿色高亮。
"""
from __future__ import annotations

import datetime
import random
from typing import Any, Optional

from PySide6.QtCore import QDateTime, Qt, QDate, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..theme import _a
from ..widgets import Card, Chip, EmptyState
from ...core import api
from ...core.worker import run_async

WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]

CELEBRATE_MESSAGES = [
    "又近了一步，继续加油！",
    "坚持就是胜利！",
    "今天的努力看得见！",
    "离目标更近了！",
    "太棒了，保持节奏！",
]

REPEAT_LABEL = {
    "none": "不重复",
    "daily": "每日",
    "weekly": "每周",
    "monthly": "每月",
    "yearly": "每年",
    "weekdays": "工作日",
}


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "summit_toast", None)
    if t:
        t.show_msg(str(msg), kind)


def _parse_dt(s: Any) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
    except Exception:  # noqa: BLE001
        return None


def _iso_utc_from_dt(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_utc_from_qdate(d: QDate) -> str:
    py = d.toPython()
    return _iso_utc_from_dt(datetime.datetime(py.year, py.month, py.day))


def _qdate_from_iso(s: Any) -> QDate:
    dt = _parse_dt(s)
    if dt:
        return QDate(dt.year, dt.month, dt.day)
    return QDate.currentDate()


def _clear_layout(lay) -> None:
    while lay.count():
        it = lay.takeAt(0)
        w = it.widget()
        if w:
            w.deleteLater()
        else:
            sub = it.layout()
            if sub:
                _clear_layout(sub)


class _TaskDialog(QDialog):
    """新建任务对话框。"""

    def __init__(self, parent, objectives: list, preset_date: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("新建任务")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        def field(label, widget):
            lab = QLabel(label)
            lab.setProperty("role", "muted")
            lay.addWidget(lab)
            lay.addWidget(widget)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("任务名称")
        field("标题 *", self.title_edit)

        self.obj_combo = QComboBox()
        self.obj_combo.addItem("不关联", None)
        for o in objectives or []:
            self.obj_combo.addItem(str(o.get("title") or "")[:30], o.get("id"))
        field("关联目标", self.obj_combo)

        self.contrib_edit = QLineEdit()
        self.contrib_edit.setPlaceholderText("该任务对目标的贡献（可选）")
        field("贡献说明", self.contrib_edit)

        self.sched_edit = QDateTimeEdit()
        self.sched_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.sched_edit.setCalendarPopup(True)
        base = _parse_dt(preset_date) or datetime.datetime.now()
        self.sched_edit.setDateTime(QDateTime(base.year, base.month, base.day, 9, 0, 0))
        field("计划时间", self.sched_edit)

        self.repeat_combo = QComboBox()
        for rule, label in REPEAT_LABEL.items():
            self.repeat_combo.addItem(label, rule)
        field("重复规则", self.repeat_combo)

        self.repeat_end_check = QCheckBox("设置重复截止日期")
        self.repeat_end_check.setEnabled(False)
        lay.addWidget(self.repeat_end_check)
        self.repeat_end_edit = QDateEdit()
        self.repeat_end_edit.setCalendarPopup(True)
        self.repeat_end_edit.setEnabled(False)
        self.repeat_end_edit.setDate(QDate.currentDate().addDays(30))
        lay.addWidget(self.repeat_end_edit)
        self.repeat_combo.currentIndexChanged.connect(self._sync_repeat)
        self.repeat_end_check.toggled.connect(self.repeat_end_edit.setEnabled)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("创建")
        ok.setProperty("preset", "primary")
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        self.title_edit.returnPressed.connect(self._on_ok)

    def _sync_repeat(self, _idx: int):
        has = self.repeat_combo.currentData() != "none"
        self.repeat_end_check.setEnabled(has)
        if not has:
            self.repeat_end_check.setChecked(False)
        self.repeat_end_edit.setEnabled(has and self.repeat_end_check.isChecked())
        self.repeat_end_check.toggled.connect(self.repeat_end_edit.setEnabled)

    def _on_ok(self):
        if not self.title_edit.text().strip():
            _toast("请输入任务名称", "warn")
            return
        self.accept()

    def values(self) -> dict:
        rule = self.repeat_combo.currentData() or "none"
        dto = {
            "title": self.title_edit.text().strip(),
            "objectiveId": self.obj_combo.currentData(),
            "scheduledAt": _iso_utc_from_dt(self.sched_edit.dateTime().toPython()),
            "repeatRule": rule,
        }
        contrib = self.contrib_edit.text().strip()
        if contrib:
            dto["contribution"] = contrib
        if rule != "none" and self.repeat_end_check.isChecked():
            dto["repeatEndDate"] = _iso_utc_from_qdate(self.repeat_end_edit.date())
        return dto


# ================= VisOKR 风格部件 =================

class _WeekDay(QFrame):
    """周条中的单个日期胶囊：星期 + 日号 + 完成点 + n/m 计数。"""

    clicked = Signal(QDate)

    def __init__(self, date: QDate, weekday: str, parent=None):
        super().__init__(parent)
        self.date = date
        self.setObjectName("weekDay")
        self.setCursor(Qt.PointingHandCursor)
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 7, 4, 5)
        v.setSpacing(1)
        self.wd_lab = QLabel(weekday)
        self.wd_lab.setAlignment(Qt.AlignCenter)
        self.num_lab = QLabel(str(date.day()))
        self.num_lab.setAlignment(Qt.AlignCenter)
        nf = self.num_lab.font()
        nf.setPointSize(12)
        nf.setBold(True)
        self.num_lab.setFont(nf)
        self.dot = QLabel()
        self.dot.setFixedSize(6, 6)
        self.dot.setAlignment(Qt.AlignCenter)
        dot_row = QHBoxLayout()
        dot_row.setContentsMargins(0, 0, 0, 0)
        dot_row.addStretch()
        dot_row.addWidget(self.dot)
        dot_row.addStretch()
        self.count_lab = QLabel("")
        self.count_lab.setAlignment(Qt.AlignCenter)
        cf = self.count_lab.font()
        cf.setPointSize(7)
        self.count_lab.setFont(cf)
        v.addWidget(self.wd_lab)
        v.addWidget(self.num_lab)
        v.addLayout(dot_row)
        v.addWidget(self.count_lab)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit(self.date)
        super().mouseReleaseEvent(e)

    def apply(self, count: int, completed: int, is_today: bool, is_selected: bool, tokens):
        primary = getattr(tokens, "primary", "#1E40AF") if tokens else "#1E40AF"
        success = getattr(tokens, "success", "#059669") if tokens else "#059669"
        muted_fg = getattr(tokens, "muted_fg", "#909399") if tokens else "#909399"
        fg = getattr(tokens, "fg", "#303133") if tokens else "#303133"
        soft = getattr(tokens, "primary_soft", "#E9EEF6") if tokens else "#E9EEF6"
        all_done = count > 0 and completed == count
        bg = "transparent"
        if all_done:
            bg = _a(success, 0.10)
        if is_today:
            bg = soft
        border = "1px solid transparent"
        if is_today:
            border = "1px solid %s" % _a(primary, 0.45)
        if is_selected:
            border = "1px solid %s" % primary
        self.setStyleSheet(
            "QFrame#weekDay{background:%s;border:%s;border-radius:10px;}" % (bg, border))
        num_color = success if all_done else (primary if is_today else fg)
        self.num_lab.setStyleSheet("color:%s;background:transparent;" % num_color)
        self.wd_lab.setStyleSheet("color:%s;font-size:11px;background:transparent;" % muted_fg)
        if count > 0:
            self.dot.setStyleSheet("background:%s;border-radius:3px;" % (success if all_done else primary))
            self.count_lab.setText("%d/%d" % (completed, count))
            self.count_lab.setStyleSheet("color:%s;font-size:10px;background:transparent;" % muted_fg)
        else:
            self.dot.setStyleSheet("background:transparent;")
            self.count_lab.setText("")


class _WeekStrip(Card):
    """横向周日期条（Vue .week-strip-card）：上一周/下一周/回到今天 + 7 日胶囊。"""

    day_clicked = Signal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent, padding=12)
        self._anchor = _monday_of(QDate.currentDate())  # 本周一
        self._last_tasks: list = []
        self._last_selected: Optional[QDate] = None
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.btn_prev = QPushButton("\u2039")  # ‹
        self.btn_next = QPushButton("\u203a")  # ›
        for b in (self.btn_prev, self.btn_next):
            b.setFixedWidth(28)
            b.setProperty("preset", "ghost")
            b.setCursor(Qt.PointingHandCursor)
        self.lbl = QLabel("")
        lf = self.lbl.font()
        lf.setBold(True)
        self.lbl.setFont(lf)
        self.lbl.setAlignment(Qt.AlignCenter)
        btn_today = QPushButton("回到今天")
        btn_today.setProperty("preset", "ghost")
        btn_today.setCursor(Qt.PointingHandCursor)
        head.addWidget(self.btn_prev)
        head.addStretch()
        head.addWidget(self.lbl, 2)
        head.addStretch()
        head.addWidget(self.btn_next)
        head.addWidget(btn_today)
        self.add_layout(head)

        grid = QHBoxLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self._days: list[_WeekDay] = []
        for i in range(7):
            d = self._anchor.addDays(i)
            day = _WeekDay(d, WEEKDAY_LABELS[i], self)
            day.clicked.connect(self.day_clicked.emit)
            self._days.append(day)
            grid.addWidget(day, 1)
        self.add_layout(grid)

        self.btn_prev.clicked.connect(lambda: self._shift(-7))
        self.btn_next.clicked.connect(lambda: self._shift(7))
        btn_today.clicked.connect(self.go_today)

    def _shift(self, days: int):
        self._anchor = self._anchor.addDays(days)
        self._rebuild()

    def go_today(self):
        self._anchor = _monday_of(QDate.currentDate())
        self.day_clicked.emit(QDate.currentDate())

    def ensure_contains(self, date: QDate):
        """选中日不在当前周时，把周条移到该日所在周。"""
        start = self._anchor
        end = start.addDays(6)
        if date < start or date > end:
            self._anchor = _monday_of(date)
            self.refresh(self._last_tasks, self._last_selected)

    def _rebuild(self):
        for i, day in enumerate(self._days):
            d = self._anchor.addDays(i)
            day.date = d
            day.wd_lab.setText(WEEKDAY_LABELS[i])
            day.num_lab.setText(str(d.day()))
        s, e = self._anchor, self._anchor.addDays(6)
        self.lbl.setText("%d月%d日 - %d月%d日" % (s.month(), s.day(), e.month(), e.day()))

    def refresh(self, tasks: list, selected: Optional[QDate]):
        self._last_tasks = tasks or []
        self._last_selected = selected
        self._rebuild()
        today = QDate.currentDate()
        tokens = None
        w = self.window()
        if w is not None:
            tokens = w.property("summit_tokens")
        for i, day in enumerate(self._days):
            d = self._anchor.addDays(i)
            count = completed = 0
            for t in self._last_tasks:
                if not isinstance(t, dict):
                    continue
                sched = _parse_dt(t.get("scheduledAt"))
                if sched and QDate(sched.year, sched.month, sched.day) == d:
                    count += 1
                    if t.get("status") == "completed":
                        completed += 1
            day.apply(count, completed, d == today,
                      selected is not None and d == selected, tokens)


def _monday_of(d: QDate) -> QDate:
    return d.addDays(1 - d.dayOfWeek())  # Qt: 1=周一


class _Fab(QPushButton):
    """右下浮动「＋」新建按钮（Vue .task-fab：52px 圆形主色底）。"""

    def __init__(self, parent, on_click):
        super().__init__("\uff0b", parent)  # ＋
        self.setFixedSize(52, 52)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("新建任务")
        f = self.font()
        f.setPointSize(18)
        f.setBold(True)
        self.setFont(f)
        self.clicked.connect(on_click)

    def restyle(self, tokens):
        primary = getattr(tokens, "primary", "#1E40AF") if tokens else "#1E40AF"
        fg = getattr(tokens, "primary_fg", "#FFFFFF") if tokens else "#FFFFFF"
        self.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:none;border-radius:26px;"
            "font-size:24px;font-weight:700;}"
            "QPushButton:hover{background:%s;}" % (primary, fg, _a(primary, 0.88)))


class _CelebrateToast(QWidget):
    """完成任务庆祝浮层（Vue .celebrate-toast：🎉 + 鼓励语 + 当日进度），3 秒自动消失。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 12, 20, 12)
        h.setSpacing(10)
        self.emoji = QLabel("\U0001f389")  # 🎉
        ef = self.emoji.font()
        ef.setPointSize(20)
        self.emoji.setFont(ef)
        h.addWidget(self.emoji)
        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self.title = QLabel("")
        tf = self.title.font()
        tf.setPointSize(11)
        tf.setBold(True)
        self.title.setFont(tf)
        self.sub = QLabel("")
        self.sub.setProperty("role", "muted")
        v.addWidget(self.title)
        v.addWidget(self.sub)
        h.addLayout(v)

    def show_msg(self, title: str, sub: str):
        w = self.window()
        tokens = w.property("summit_tokens") if w is not None else None
        card = getattr(tokens, "card", "#FFFFFF") if tokens else "#FFFFFF"
        success = getattr(tokens, "success", "#059669") if tokens else "#059669"
        border = getattr(tokens, "border", "#EBEEF5") if tokens else "#EBEEF5"
        self.title.setText(title)
        self.title.setStyleSheet("color:%s;background:transparent;" % success)
        self.sub.setText(sub)
        self.setStyleSheet(
            "_CelebrateToast{background:%s;border:1px solid %s;border-radius:14px;}"
            % (card, _a(success, 0.5) if not border.startswith("#A") else border))
        self.title.setText(title)  # 重设样式后恢复文本样式
        self.sub.setText(sub)
        self.adjustSize()
        host = self.parentWidget()
        if host:
            self.move(max(8, (host.width() - self.width()) // 2), 64)
        self.show()
        self.raise_()
        self._timer.start(3000)


@register_page("/tasks")
class TasksPage(Page):
    path = "/tasks"

    def __init__(self, shell):
        super().__init__(shell)
        self._tasks: list = []
        self._objectives: list = []
        self._obj_map: dict = {}
        self._select_mode = False
        self._selected: set = set()
        self._celebrate_pending = False

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        title = QLabel("任务日历")
        title.setProperty("role", "title")
        hl.addWidget(title)
        hl.addStretch()

        self.status_combo = QComboBox()
        self.status_combo.addItem("全部状态", None)
        self.status_combo.addItem("未完成", "pending")
        self.status_combo.addItem("已完成", "completed")
        self.status_combo.currentIndexChanged.connect(self._render)
        hl.addWidget(self.status_combo)

        self.date_check = QCheckBox("按日期")
        self.date_check.toggled.connect(self._on_date_check)
        hl.addWidget(self.date_check)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setEnabled(False)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(lambda _d: self._render())
        hl.addWidget(self.date_edit)

        self.btn_select = QPushButton("批量选择")
        self.btn_select.clicked.connect(self._toggle_select_mode)
        hl.addWidget(self.btn_select)

        self.btn_batch = QPushButton("删除选中")
        self.btn_batch.setProperty("preset", "danger")
        self.btn_batch.setEnabled(False)
        self.btn_batch.clicked.connect(self._batch_delete)
        hl.addWidget(self.btn_batch)

        self.btn_overdue = QPushButton("删除过期任务")
        self.btn_overdue.clicked.connect(self._delete_overdue)
        hl.addWidget(self.btn_overdue)

        btn_new = QPushButton("＋ 新建任务")
        btn_new.setProperty("preset", "primary")
        btn_new.clicked.connect(self._create)
        hl.addWidget(btn_new)
        self.body_layout.addWidget(header)

        # ---- 横向周日期条（VisOKR） ----
        self.week_strip = _WeekStrip()
        self.week_strip.day_clicked.connect(self._select_day)
        self.body_layout.addWidget(self.week_strip)

        card = Card()
        self.list_lay = QVBoxLayout()
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(2)
        card.add_layout(self.list_lay, 1)
        self.empty = EmptyState("暂无任务，点击右下角「＋」开始安排")
        self.empty.hide()
        card.add(self.empty)
        self.body_layout.addWidget(card, 1)

        # ---- 浮动「＋」FAB 与庆祝浮层（挂在 viewport 上，随页面滚动固定） ----
        vp = self.viewport()
        self.fab = _Fab(vp, self._create)
        self.celebrate = _CelebrateToast(vp)
        self._ready = True

    # ---------------- 浮动部件定位 ----------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not getattr(self, "_ready", False):
            return
        vp = self.viewport()
        self.fab.move(vp.width() - self.fab.width() - 28, vp.height() - self.fab.height() - 28)
        self.fab.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_ready", False):
            tokens = self.window().property("summit_tokens") if self.window() else None
            self.fab.restyle(tokens)
            self._layout_celebrate()

    def _layout_celebrate(self):
        vp = self.viewport()
        self.celebrate.move(max(8, (vp.width() - self.celebrate.width()) // 2), 64)
        self.celebrate.raise_()

    # ---------------- 周条交互 ----------------
    def _select_day(self, d: QDate):
        if not d.isValid():
            return
        self.date_check.blockSignals(True)
        self.date_check.setChecked(True)
        self.date_check.blockSignals(False)
        self.date_edit.setEnabled(True)
        self.date_edit.blockSignals(True)
        self.date_edit.setDate(d)
        self.date_edit.blockSignals(False)
        self._render()

    def _on_date_check(self, on: bool):
        self.date_edit.setEnabled(on)
        self._render()

    # ---------------- 数据 ----------------
    def refresh(self):
        run_async(lambda: (api.task_list(), api.objective_list()), on_ok=self._apply)

    def _apply(self, result):
        tasks, objs = result
        self._tasks = tasks or []
        obj_list = objs.get("list") if isinstance(objs, dict) else (objs or [])
        self._objectives = obj_list or []
        self._obj_map = {o.get("id"): o for o in self._objectives if isinstance(o, dict)}
        self._selected &= {t.get("id") for t in self._tasks if isinstance(t, dict)}
        self._render()
        if self._celebrate_pending:
            self._celebrate_pending = False
            done, total = self._today_progress()
            self.celebrate.show_msg(random.choice(CELEBRATE_MESSAGES),
                                    "今日进度 %d/%d" % (done, total))

    def _today_progress(self) -> tuple:
        today = datetime.date.today()
        done = total = 0
        for t in self._tasks:
            if not isinstance(t, dict):
                continue
            sched = _parse_dt(t.get("scheduledAt"))
            if sched and sched.date() == today:
                total += 1
                if t.get("status") == "completed":
                    done += 1
        return done, total

    def _refresh_week_strip(self):
        selected = self.date_edit.date() if self.date_check.isChecked() else None
        if selected is not None:
            self.week_strip.ensure_contains(selected)
        self.week_strip.refresh(self._tasks, selected)

    def _filtered(self) -> list:
        status = self.status_combo.currentData()
        out = []
        for t in self._tasks:
            if not isinstance(t, dict):
                continue
            if status and t.get("status") != status:
                continue
            if self.date_check.isChecked():
                sched = _parse_dt(t.get("scheduledAt"))
                want = self.date_edit.date().toPython()
                if not sched or sched.date() != want:
                    continue
            out.append(t)
        out.sort(key=lambda t: (t.get("status") == "completed",
                                str(t.get("scheduledAt") or "9999")))
        return out

    # ---------------- 渲染 ----------------
    def _render(self):
        _clear_layout(self.list_lay)
        tasks = self._filtered()
        if not tasks:
            self.empty.show()
            self._update_batch_btn()
            self._refresh_week_strip()
            return
        self.empty.hide()
        today = datetime.date.today()
        for t in tasks:
            self.list_lay.addWidget(self._row(t, today))
        self._update_batch_btn()
        self._refresh_week_strip()

    def _row(self, t: dict, today) -> QWidget:
        tid = t.get("id")
        completed = t.get("status") == "completed"
        sched = _parse_dt(t.get("scheduledAt"))
        overdue = (not completed) and sched is not None and sched.date() < today

        row = QWidget()
        row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)  # 防止行被拉伸铺满卡片
        if completed:  # Vue .task-item.is-completed：绿色高亮（选择器限定到行自身，避免子控件继承）
            row.setObjectName("taskRow")
            row.setStyleSheet("QWidget#taskRow{background:%s;border-radius:8px;}"
                              % _a("#059669", 0.10))
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)

        if self._select_mode:
            cb = QCheckBox()
            cb.setChecked(tid in self._selected)
            cb.toggled.connect(lambda on, i=tid: self._toggle_select(i, on))
            h.addWidget(cb)
        else:
            cb = QCheckBox()
            cb.setChecked(completed)
            cb.setToolTip("点击切换完成状态")
            cb.toggled.connect(lambda on, i=tid: self._toggle_complete(i, on))
            h.addWidget(cb)

        time_lab = QLabel(sched.strftime("%H:%M") if sched else "--:--")
        time_lab.setProperty("role", "muted")
        h.addWidget(time_lab)

        title = QLabel(str(t.get("title") or ""))
        title.setWordWrap(True)
        if completed:
            f = title.font()
            f.setStrikeOut(True)
            title.setFont(f)
            title.setProperty("role", "muted")
        h.addWidget(title, 1)

        if overdue:
            h.addWidget(Chip("过期", "danger"))
        rule = t.get("repeatRule") or "none"
        if rule != "none":
            h.addWidget(Chip(REPEAT_LABEL.get(rule, rule), "warning"))
        h.addWidget(Chip("已完成" if completed else "未完成",
                         "success" if completed else "true"))
        contrib = t.get("contribution")
        if contrib:
            c = Chip(str(contrib)[:16], "success")
            c.setToolTip(str(contrib))
            h.addWidget(c)

        oid = t.get("objectiveId")
        if oid and self._obj_map.get(oid):
            ob = QPushButton(str(self._obj_map[oid].get("title") or "目标")[:14])
            ob.setProperty("preset", "ghost")
            ob.setCursor(Qt.PointingHandCursor)
            ob.setStyleSheet("padding:2px 8px;font-size:12px;")
            ob.clicked.connect(lambda: self.shell.open_objective(oid))
            h.addWidget(ob)

        if not self._select_mode:
            dele = QPushButton("删除")
            dele.setCursor(Qt.PointingHandCursor)
            dele.setStyleSheet("padding:2px 8px;font-size:12px;color:#F56C6C;")
            dele.clicked.connect(lambda: self._delete_one(tid))
            h.addWidget(dele)
        return row

    def _update_batch_btn(self):
        n = len(self._selected)
        self.btn_batch.setText("删除选中(%d)" % n if n else "删除选中")
        self.btn_batch.setEnabled(bool(n))
        self.btn_select.setText("取消选择" if self._select_mode else "批量选择")

    # ---------------- 操作 ----------------
    def _toggle_select_mode(self):
        self._select_mode = not self._select_mode
        if not self._select_mode:
            self._selected = set()
        self._render()

    def _toggle_select(self, tid, on: bool):
        if on:
            self._selected.add(tid)
        else:
            self._selected.discard(tid)
        self._update_batch_btn()

    def _toggle_complete(self, tid, on: bool):
        if not tid:
            return
        if on:
            self._celebrate_pending = True
        run_async(lambda: api.task_complete(tid, bool(on)),
                  on_ok=lambda _r: (self.refresh(),))

    def _delete_one(self, tid):
        if not tid:
            return
        if QMessageBox.question(self, "提示", "确定删除该任务？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        run_async(lambda: api.task_delete(tid),
                  on_ok=lambda _r: (_toast("删除成功", "success"), self.refresh()))

    def _batch_delete(self):
        ids = [i for i in self._selected if i]
        if not ids:
            return
        if QMessageBox.question(self, "提示", "确定批量删除 %d 个任务？" % len(ids),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        def _ok(result):
            n = result.get("count") if isinstance(result, dict) else len(ids)
            _toast("已删除 %s 个任务" % n, "success")
            self._selected = set()
            self.refresh()
        run_async(lambda: api.task_batch_delete(ids), on_ok=_ok)

    def _delete_overdue(self):
        if QMessageBox.question(self, "清理过期任务",
                                "将删除所有超过 7 天未完成的过期任务，确定继续？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        def _ok(result):
            n = result.get("count") if isinstance(result, dict) else 0
            if not n:
                _toast("没有过期任务需要清理", "info")
            else:
                _toast("已清理 %s 个过期任务" % n, "success")
                self.refresh()
        run_async(api.task_delete_overdue, on_ok=_ok)

    def _create(self):
        preset = None
        if self.date_check.isChecked():
            preset = self.date_edit.date().toString("yyyy-MM-dd")
        dlg = _TaskDialog(self, self._objectives, preset_date=preset)
        if dlg.exec() == QDialog.Accepted:
            dto = dlg.values()
            run_async(lambda: api.task_create(dto),
                      on_ok=lambda _r: (_toast("任务创建成功", "success"), self.refresh()))
