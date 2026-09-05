"""专注周期页：活跃周期卡片（得分/时间进度/目标权重）+ 新建/编辑/结束周期。"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QCheckBox, QDateEdit, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, EmptyState, RingProgress
from ...core import api
from ...core.worker import run_async


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "vis_toast", None)
    if t:
        t.show_msg(str(msg), kind)


def _parse_dt(s: Any) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
    except Exception:  # noqa: BLE001
        return None


def _fmt_date(s: Any) -> str:
    dt = _parse_dt(s)
    return dt.strftime("%Y-%m-%d") if dt else "-"


def _iso_utc_from_date(d: QDate, end_of_day: bool = False) -> str:
    py = d.toPython()
    hour, minute, sec = (23, 59, 59) if end_of_day else (0, 0, 0)
    dt = datetime.datetime(py.year, py.month, py.day, hour, minute, sec)
    return dt.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _qdate_from_iso(s: Any) -> QDate:
    dt = _parse_dt(s)
    if dt:
        return QDate(dt.year, dt.month, dt.day)
    return QDate.currentDate()


def _pct(v: Any) -> int:
    try:
        return int(round(max(0.0, min(1.0, float(v or 0))) * 100))
    except (TypeError, ValueError):
        return 0


def _progress_bar(value: int, color: str) -> QWidget:
    from PySide6.QtWidgets import QProgressBar
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(max(0, min(100, value)))
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    bar.setStyleSheet("QProgressBar::chunk{background:%s;border-radius:4px;}" % color)
    return bar


class _CycleFormDialog(QDialog):
    """新建 / 编辑专注周期。

    edit=True 时仅可改名称与起止日期（对齐 web 端编辑对话框）；
    edit=False 时可勾选目标并设置权重。
    """

    def __init__(self, parent, cycle: Optional[dict] = None, objectives: Optional[list] = None):
        super().__init__(parent)
        self._edit = cycle is not None
        self.setWindowTitle("编辑专注周期" if self._edit else "新建专注周期")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        def field(label, widget):
            lab = QLabel(label)
            lab.setProperty("role", "muted")
            lay.addWidget(lab)
            lay.addWidget(widget)

        self.name_edit = QLineEdit((cycle or {}).get("name") or "")
        self.name_edit.setPlaceholderText("如：2026 Q1 专注周期")
        field("周期名称 *", self.name_edit)

        self._rows = []  # (checkbox, spinbox, oid)
        if not self._edit:
            lab = QLabel("选择目标 *（勾选并设置权重 1-10）")
            lab.setProperty("role", "muted")
            lay.addWidget(lab)
            holder = QScrollArea()
            holder.setWidgetResizable(True)
            holder.setMaximumHeight(220)
            inner = QWidget()
            ilay = QVBoxLayout(inner)
            ilay.setContentsMargins(8, 6, 8, 6)
            ilay.setSpacing(4)
            objs = objectives or []
            if not objs:
                tip = QLabel("没有可加入的目标")
                tip.setProperty("role", "muted")
                ilay.addWidget(tip)
            for o in objs:
                row = QWidget()
                rh = QHBoxLayout(row)
                rh.setContentsMargins(0, 0, 0, 0)
                cb = QCheckBox(str(o.get("title") or "")[:36])
                cb.setChecked(True)
                spin = QSpinBox()
                spin.setRange(1, 10)
                spin.setValue(5)
                rh.addWidget(cb, 1)
                rh.addWidget(QLabel("权重"))
                rh.addWidget(spin)
                ilay.addWidget(row)
                self._rows.append((cb, spin, o.get("id")))
            holder.setWidget(inner)
            lay.addWidget(holder)

            self.custom_time = QCheckBox("自定义起止日期（关闭则自动按目标时间计算）")
            self.custom_time.toggled.connect(self._sync_dates)
            lay.addWidget(self.custom_time)
            dr = QHBoxLayout()
            self.start_edit = QDateEdit()
            self.start_edit.setCalendarPopup(True)
            self.start_edit.setDate(QDate.currentDate())
            self.end_edit = QDateEdit()
            self.end_edit.setCalendarPopup(True)
            self.end_edit.setDate(QDate.currentDate().addDays(90))
            for w in (self.start_edit, self.end_edit):
                w.setEnabled(False)
            dr.addWidget(self.start_edit)
            dr.addWidget(QLabel("→"))
            dr.addWidget(self.end_edit)
            dr.addStretch()
            lay.addLayout(dr)
        else:
            dr = QHBoxLayout()
            self.start_edit = QDateEdit()
            self.start_edit.setCalendarPopup(True)
            self.start_edit.setDate(_qdate_from_iso((cycle or {}).get("startAt")))
            self.end_edit = QDateEdit()
            self.end_edit.setCalendarPopup(True)
            self.end_edit.setDate(_qdate_from_iso((cycle or {}).get("endAt")))
            dr.addWidget(QLabel("开始"))
            dr.addWidget(self.start_edit)
            dr.addWidget(QLabel("结束"))
            dr.addWidget(self.end_edit)
            dr.addStretch()
            lay.addLayout(dr)
            self.custom_time = None

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("保存" if self._edit else "创建")
        ok.setProperty("preset", "primary")
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _sync_dates(self, on: bool):
        self.start_edit.setEnabled(on)
        self.end_edit.setEnabled(on)

    def _on_ok(self):
        if not self.name_edit.text().strip():
            _toast("请填写周期名称", "warn")
            return
        if not self._edit:
            if not any(cb.isChecked() for cb, _s, _i in self._rows):
                _toast("请至少选择一个目标", "warn")
                return
            if self.custom_time.isChecked() and self.end_edit.date() < self.start_edit.date():
                _toast("结束日期必须晚于开始日期", "warn")
                return
        self.accept()

    def values(self) -> dict:
        dto = {"name": self.name_edit.text().strip()}
        if not self._edit:
            ids, weights = [], {}
            for cb, spin, oid in self._rows:
                if cb.isChecked() and oid:
                    ids.append(oid)
                    weights[oid] = spin.value()
            dto["objectiveIds"] = ids
            dto["weights"] = weights
            if self.custom_time.isChecked():
                dto["startAt"] = _iso_utc_from_date(self.start_edit.date())
                dto["endAt"] = _iso_utc_from_date(self.end_edit.date(), end_of_day=True)
        else:
            dto["startAt"] = _iso_utc_from_date(self.start_edit.date())
            dto["endAt"] = _iso_utc_from_date(self.end_edit.date(), end_of_day=True)
        return dto


@register_page("/focus-cycle")
class FocusCyclePage(Page):
    path = "/focus-cycle"

    def __init__(self, shell):
        super().__init__(shell)
        self._cycle: Optional[dict] = None
        self._objectives: list = []
        self._loading = False

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        title = QLabel("专注周期")
        title.setProperty("role", "title")
        hl.addWidget(title)
        hl.addStretch()
        self.btn_edit = QPushButton("编辑")
        self.btn_edit.setVisible(False)
        self.btn_edit.clicked.connect(self._edit_cycle)
        hl.addWidget(self.btn_edit)
        self.btn_end = QPushButton("结束周期")
        self.btn_end.setProperty("preset", "danger")
        self.btn_end.setVisible(False)
        self.btn_end.clicked.connect(self._end_cycle)
        hl.addWidget(self.btn_end)
        self.btn_new = QPushButton("＋ 新建专注周期")
        self.btn_new.setProperty("preset", "primary")
        self.btn_new.clicked.connect(self._create_cycle)
        hl.addWidget(self.btn_new)
        self.body_layout.addWidget(header)

        self._dyn = QWidget()
        self._dyn_lay = QVBoxLayout(self._dyn)
        self._dyn_lay.setContentsMargins(0, 0, 0, 0)
        self._dyn_lay.setSpacing(14)
        self.body_layout.addWidget(self._dyn, 1)
        self.body_layout.addStretch(1)

    # ---------------- 数据 ----------------
    def refresh(self):
        if self._loading:
            return
        self._loading = True
        run_async(lambda: (api.cycle_active(), api.objective_list()),
                  on_ok=self._apply, on_err=self._load_err)

    def _load_err(self, _msg: str):
        self._loading = False

    def _apply(self, result):
        self._loading = False
        cycle, objs = result
        self._cycle = cycle if isinstance(cycle, dict) else None
        obj_list = objs.get("list") if isinstance(objs, dict) else (objs or [])
        self._objectives = obj_list or []
        self._render()

    def _render(self):
        while self._dyn_lay.count():
            it = self._dyn_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        has = self._cycle is not None
        self.btn_edit.setVisible(has)
        self.btn_end.setVisible(has)
        self.btn_new.setText("＋ 新建专注周期" if not has else "＋ 新建（先结束当前周期）")
        if not has:
            self._dyn_lay.addWidget(self._empty_card())
            return
        self._dyn_lay.addWidget(self._cycle_card(self._cycle))

    def _empty_card(self) -> Card:
        card = Card()
        box = QVBoxLayout()
        box.setSpacing(12)
        empty = EmptyState("当前没有进行中的专注周期，创建一个来聚焦关键目标吧")
        box.addWidget(empty, 1)
        btn = QPushButton("立即创建")
        btn.setProperty("preset", "primary")
        btn.clicked.connect(self._create_cycle)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        row.addStretch()
        box.addLayout(row)
        card.add_layout(box, 1)
        return card

    def _cycle_card(self, cycle: dict) -> Card:
        card = Card()
        head = QHBoxLayout()
        left = QVBoxLayout()
        name = QLabel(str(cycle.get("name") or ""))
        name.setProperty("role", "subtitle")
        left.addWidget(name)
        dates = QLabel("%s → %s" % (_fmt_date(cycle.get("startAt")),
                                    _fmt_date(cycle.get("endAt"))))
        dates.setProperty("role", "muted")
        left.addWidget(dates)
        end_dt = _parse_dt(cycle.get("endAt"))
        days_left = (end_dt.date() - datetime.date.today()).days if end_dt else 0
        left.addWidget(Chip("剩余 %d 天" % days_left,
                            "danger" if days_left <= 7 else "success"))
        head.addLayout(left, 1)
        ring = RingProgress()
        score = int(cycle.get("cycleScore") or 0)
        ring.set(max(0, min(100, score)) / 100.0, "#409EFF")
        ring_box = QVBoxLayout()
        ring_box.setAlignment(Qt.AlignCenter)
        cap = QLabel("周期得分")
        cap.setProperty("role", "muted")
        cap.setAlignment(Qt.AlignCenter)
        ring_box.addWidget(ring)
        ring_box.addWidget(cap)
        head.addLayout(ring_box)
        card.add_layout(head)

        # 时间进度
        start_dt = _parse_dt(cycle.get("startAt"))
        prog = 0
        if start_dt and end_dt:
            total = (end_dt - start_dt).total_seconds()
            if total > 0:
                elapsed = (datetime.datetime.now().astimezone() - start_dt).total_seconds()
                prog = max(0, min(100, int(round(elapsed / total * 100))))
        card.add(_progress_bar(prog, "#409EFF"))
        pl = QLabel("%d%% 时间已过" % prog)
        pl.setProperty("role", "muted")
        card.add(pl)

        lab = QLabel("目标与权重")
        lab.setProperty("role", "subtitle")
        card.add(lab)
        for oco in cycle.get("objectives") or []:
            if isinstance(oco, dict):
                card.add(self._objective_row(oco))
        return card

    def _objective_row(self, oco: dict) -> QWidget:
        obj = oco.get("objective") if isinstance(oco.get("objective"), dict) else {}
        oid = oco.get("objectiveId") or obj.get("id")
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 4, 8, 4)
        h.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet("background:%s;border-radius:5px;" % (obj.get("color") or "#409EFF"))
        h.addWidget(dot)
        title = QLabel(str(obj.get("title") or "(目标已删除)"))
        title.setMaximumWidth(260)
        h.addWidget(title)
        if oid:
            link = QPushButton("查看")
            link.setProperty("preset", "ghost")
            link.setCursor(Qt.PointingHandCursor)
            link.setStyleSheet("padding:2px 8px;font-size:12px;")
            link.clicked.connect(lambda: self.shell.open_objective(oid))
            h.addWidget(link)
        p = _pct(obj.get("currentProgress"))
        h.addWidget(_progress_bar(p, "#67C23A"), 1)
        pv = QLabel("%d%%" % p)
        pv.setProperty("role", "muted")
        h.addWidget(pv)
        h.addWidget(QLabel("权重"))
        spin = QSpinBox()
        spin.setRange(1, 10)
        try:
            spin.setValue(int(oco.get("weight") or 1))
        except (TypeError, ValueError):
            spin.setValue(1)
        cid = (self._cycle or {}).get("id")

        def on_changed(val, o=oid, old=[spin.value()]):
            if not cid or not o or val == old[0]:
                return
            old[0] = val
            run_async(lambda: api.cycle_update_weight(cid, o, int(val)),
                      on_ok=lambda _r: (_toast("权重已更新", "success"), self.refresh()))
        spin.valueChanged.connect(on_changed)
        h.addWidget(spin)
        return row

    # ---------------- 操作 ----------------
    def _create_cycle(self):
        dlg = _CycleFormDialog(self, cycle=None, objectives=self._objectives)
        if dlg.exec() == QDialog.Accepted:
            dto = dlg.values()
            run_async(lambda: api.cycle_create(dto),
                      on_ok=lambda _r: (_toast("专注周期创建成功", "success"), self.refresh()))

    def _edit_cycle(self):
        cycle = self._cycle
        if not cycle:
            return
        dlg = _CycleFormDialog(self, cycle=cycle)
        if dlg.exec() == QDialog.Accepted:
            dto = dlg.values()
            cid = cycle.get("id")
            run_async(lambda: api.cycle_update(cid, dto),
                      on_ok=lambda _r: (_toast("周期已更新", "success"), self.refresh()))

    def _end_cycle(self):
        cycle = self._cycle
        if not cycle:
            return
        if QMessageBox.question(self, "结束专注周期？",
                                "结束后将不再统计周期得分，可重新创建新的专注周期。",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        cid = cycle.get("id")
        run_async(lambda: api.cycle_end(cid),
                  on_ok=lambda _r: (_toast("已结束", "success"), self.refresh()))
