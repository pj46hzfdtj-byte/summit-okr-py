"""任务日历页：任务列表 + 完成/过期/重复 + 筛选 + 新建 + 批量删除 + 清理过期。"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import QDateTime, Qt, QDate, QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, EmptyState
from ...core import api
from ...core.worker import run_async

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

        card = Card()
        self.list_lay = QVBoxLayout()
        self.list_lay.setContentsMargins(0, 0, 0, 0)
        self.list_lay.setSpacing(2)
        card.add_layout(self.list_lay, 1)
        self.empty = EmptyState("暂无任务，点击右上角「新建任务」开始安排")
        self.empty.hide()
        card.add(self.empty)
        self.body_layout.addWidget(card, 1)
        self._ready = True

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
            return
        self.empty.hide()
        today = datetime.date.today()
        for t in tasks:
            self.list_lay.addWidget(self._row(t, today))
        self._update_batch_btn()

    def _row(self, t: dict, today) -> QWidget:
        tid = t.get("id")
        completed = t.get("status") == "completed"
        sched = _parse_dt(t.get("scheduledAt"))
        overdue = (not completed) and sched is not None and sched.date() < today

        row = QWidget()
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
