"""目标详情：Objective 信息 + 进度 + KR 列表 + 编辑目标 + 备忘。"""
from __future__ import annotations

import json
from datetime import datetime

from PySide6.QtCore import QDateTime, Qt, QDate, QTime
from PySide6.QtWidgets import (QCheckBox, QDateEdit, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, EmptyState
from ...core import api
from ...core.worker import run_async
from .goals import _ColorPicker, _dot, _mini_btn, _toast

STATUS_LABEL = {
    "unplanned": "未计划",
    "not_started": "未开始",
    "in_progress": "进行中",
    "pending_review": "待复盘",
    "completed": "已复盘",
}
STATUS_CHIP = {
    "unplanned": "true",
    "not_started": "true",
    "in_progress": "warning",
    "pending_review": "warning",
    "completed": "success",
}
CALC_LABEL = {"sum": "求和", "final": "最终值", "average": "平均值",
              "max": "最大值", "custom": "自定义"}


def _fmt_date(iso):
    if not iso:
        return "-"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(iso)[:10]


def _as_list(v):
    """motivations/feasibilities 可能是 list 或 JSON 字符串。"""
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str) and v.strip():
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            return [v]
    return []


def _kr_progress(kr: dict) -> float:
    try:
        init = float(kr.get("initialValue") or 0)
        target = float(kr.get("targetValue") or 0)
        cur = float(kr.get("currentValue") or 0)
    except (TypeError, ValueError):
        return 0.0
    if target == init:
        return 0.0
    return max(0.0, min(1.0, (cur - init) / (target - init)))


def _pct(v) -> int:
    try:
        return int(round(max(0.0, min(1.0, float(v or 0))) * 100))
    except (TypeError, ValueError):
        return 0


def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 2)
    except (TypeError, ValueError):
        return v


def _qdate_from_iso(iso):
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
        return QDate(dt.year, dt.month, dt.day)
    except Exception:
        return QDate.currentDate()


def _iso_from_qdate(d: QDate):
    dt = QDateTime(d, QTime(0, 0))
    s = dt.toUTC().toString(Qt.ISODate)
    return s if s.endswith("Z") else s + "Z"


class _EditObjectiveDialog(QDialog):
    def __init__(self, parent, obj: dict):
        super().__init__(parent)
        self.setWindowTitle("编辑目标")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        def field(label, widget):
            lab = QLabel(label)
            lab.setProperty("role", "muted")
            lay.addWidget(lab)
            lay.addWidget(widget)

        self.title_edit = QLineEdit(obj.get("title") or "")
        field("标题 *", self.title_edit)
        self.color_picker = _ColorPicker(color=obj.get("color") or "#409EFF")
        field("颜色", self.color_picker)

        self.plan_check = QCheckBox("计划时间")
        self.plan_check.setChecked(bool(obj.get("startAt")))
        lay.addWidget(self.plan_check)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("开始"))
        self.start_edit = QDateEdit(_qdate_from_iso(obj.get("startAt")))
        self.start_edit.setCalendarPopup(True)
        self.start_edit.setDisplayFormat("yyyy-MM-dd")
        time_row.addWidget(self.start_edit)
        time_row.addSpacing(12)
        time_row.addWidget(QLabel("结束"))
        self.end_edit = QDateEdit(_qdate_from_iso(obj.get("endAt")))
        self.end_edit.setCalendarPopup(True)
        self.end_edit.setDisplayFormat("yyyy-MM-dd")
        time_row.addWidget(self.end_edit)
        time_row.addStretch()
        lay.addLayout(time_row)
        self.plan_check.toggled.connect(self.start_edit.setEnabled)
        self.plan_check.toggled.connect(self.end_edit.setEnabled)
        self.start_edit.setEnabled(self.plan_check.isChecked())
        self.end_edit.setEnabled(self.plan_check.isChecked())

        self.mot_edit = QPlainTextEdit("\n".join(_as_list(obj.get("motivations"))))
        self.mot_edit.setPlaceholderText("每行一条动机")
        self.mot_edit.setFixedHeight(80)
        field("动机（每行一条）", self.mot_edit)

        self.feas_edit = QPlainTextEdit("\n".join(_as_list(obj.get("feasibilities"))))
        self.feas_edit.setPlaceholderText("每行一条可行性")
        self.feas_edit.setFixedHeight(80)
        field("可行性（每行一条）", self.feas_edit)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("保存")
        ok.setProperty("preset", "primary")
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _on_ok(self):
        if not self.title_edit.text().strip():
            _toast("请输入目标标题", "warn")
            return
        self.accept()

    def values(self):
        use_plan = self.plan_check.isChecked()
        return {
            "title": self.title_edit.text().strip(),
            "color": self.color_picker.color(),
            "startAt": _iso_from_qdate(self.start_edit.date()) if use_plan else None,
            "endAt": _iso_from_qdate(self.end_edit.date()) if use_plan else None,
            "motivations": [s.strip() for s in self.mot_edit.toPlainText().splitlines() if s.strip()],
            "feasibilities": [s.strip() for s in self.feas_edit.toPlainText().splitlines() if s.strip()],
        }


class _TrendDialog(QDialog):
    """KR 趋势：最近记录列表（value / createdAt）。"""

    def __init__(self, parent, kr: dict, records: list):
        super().__init__(parent)
        self.setWindowTitle("趋势 · " + (kr.get("title") or ""))
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(6)
        recs = (records or [])[-20:]
        if not recs:
            lay.addWidget(QLabel("还没有记录数据"))
        for r in reversed(recs):
            row = QHBoxLayout()
            c = QLabel(_fmt_date(r.get("createdAt") or r.get("recordedAt")))
            c.setStyleSheet("color:#6B7280;font-size:12px;")
            row.addWidget(c)
            row.addStretch()
            v = QLabel(str(_num(r.get("value"))))
            v.setStyleSheet("font-weight:600;")
            row.addWidget(v)
            lay.addLayout(row)


@register_page("/objectives/detail")
class GoalDetailPage(Page):
    path = "/objectives/detail"

    def __init__(self, shell):
        super().__init__(shell)
        self._oid = None
        self._loading = False
        self._obj = None

    # ---------- 对外接口 ----------
    def open_objective(self, objective_id: str):
        self._oid = objective_id
        self.refresh()

    # ---------- 数据加载 ----------
    def refresh(self):
        if self._loading:
            return
        if not self._oid:
            self._obj = None
            self.clear_body()
            self.body_layout.addWidget(EmptyState("请选择一个目标"), 1)
            return
        self._loading = True
        oid = self._oid
        run_async(lambda: (api.objective_get(oid),
                           api.kr_list_by_objective(oid),
                           api.memo_list("objective", oid)),
                  on_ok=self._apply, on_err=self._load_err)

    def _load_err(self, msg: str):
        self._loading = False
        _toast(msg, "error")

    def _apply(self, result):
        self._loading = False
        obj, krs, memos = result
        if not isinstance(obj, dict) or obj.get("id") != self._oid:
            return
        self._obj = obj
        self._render(obj, krs or [], memos or [])

    # ---------- 渲染 ----------
    def _render(self, obj: dict, krs: list, memos: list):
        self.clear_body()

        # 头部卡
        head = Card()
        bar = QHBoxLayout()
        back = QPushButton("← 返回")
        back.setProperty("preset", "ghost")
        back.clicked.connect(lambda: self.shell.navigate("/goal-groups"))
        bar.addWidget(back)
        status = obj.get("status") or "unplanned"
        bar.addWidget(Chip(STATUS_LABEL.get(status, status), STATUS_CHIP.get(status, "true")))
        bar.addWidget(_dot(obj.get("color") or "#409EFF", 14))
        title = QLabel(obj.get("title") or "")
        title.setProperty("role", "title")
        bar.addWidget(title, 1)
        if obj.get("isLagging"):
            bar.addWidget(Chip("滞后", "danger"))
        edit_btn = QPushButton("编辑目标")
        edit_btn.clicked.connect(lambda: self._open_edit())
        bar.addWidget(edit_btn)
        head.add_layout(bar)

        gg = obj.get("goalGroup") if isinstance(obj.get("goalGroup"), dict) else {}
        meta = QHBoxLayout()
        meta.setSpacing(24)

        def kv(label, value, dot_color=None):
            col = QVBoxLayout()
            col.setSpacing(2)
            l = QLabel(label)
            l.setProperty("role", "muted")
            col.addWidget(l)
            if dot_color:
                row = QHBoxLayout()
                row.setSpacing(6)
                row.addWidget(_dot(dot_color, 8))
                v = QLabel(value)
                row.addWidget(v)
                col.addLayout(row)
            else:
                v = QLabel(value)
                v.setStyleSheet("font-weight:600;")
                col.addWidget(v)
            meta.addLayout(col)

        kv("所属节点", gg.get("name") or "-", gg.get("color"))
        kv("开始时间", _fmt_date(obj.get("startAt")))
        kv("结束时间", _fmt_date(obj.get("endAt")))
        kv("KR 数量", str(len(krs)))
        meta.addStretch()
        head.add_layout(meta)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        cur_lab = QLabel("当前进度")
        cur_lab.setProperty("role", "muted")
        prog_row.addWidget(cur_lab)
        cur_bar = QProgressBar()
        cur_bar.setRange(0, 100)
        cur_bar.setValue(_pct(obj.get("currentProgress")))
        cur_bar.setTextVisible(False)
        if obj.get("isLagging"):
            cur_bar.setStyleSheet("QProgressBar::chunk{background:#E6A23C;border-radius:5px;}")
        prog_row.addWidget(cur_bar, 1)
        cur_pct = QLabel("%d%%" % _pct(obj.get("currentProgress")))
        cur_pct.setProperty("role", "muted")
        prog_row.addWidget(cur_pct)
        exp_lab = QLabel("预期")
        exp_lab.setProperty("role", "muted")
        prog_row.addWidget(exp_lab)
        exp_bar = QProgressBar()
        exp_bar.setRange(0, 100)
        exp_bar.setValue(_pct(obj.get("expectedProgress")))
        exp_bar.setTextVisible(False)
        exp_bar.setFixedHeight(6)
        prog_row.addWidget(exp_bar, 1)
        exp_pct = QLabel("%d%%" % _pct(obj.get("expectedProgress")))
        exp_pct.setProperty("role", "muted")
        prog_row.addWidget(exp_pct)
        head.add_layout(prog_row)
        self.body_layout.addWidget(head)

        # 动机 / 可行性
        mf = Card()
        m_lab = QLabel("动机 (%d)" % len(_as_list(obj.get("motivations"))))
        m_lab.setProperty("role", "subtitle")
        mf.add(m_lab)
        mols = _as_list(obj.get("motivations"))
        if mols:
            for m in mols:
                li = QLabel("• " + m)
                li.setWordWrap(True)
                mf.add(li)
        else:
            e = QLabel("暂无动机")
            e.setProperty("role", "muted")
            mf.add(e)
        f_lab = QLabel("可行性 (%d)" % len(_as_list(obj.get("feasibilities"))))
        f_lab.setProperty("role", "subtitle")
        mf.add(f_lab)
        fals = _as_list(obj.get("feasibilities"))
        if fals:
            for f in fals:
                li = QLabel("• " + f)
                li.setWordWrap(True)
                mf.add(li)
        else:
            e = QLabel("暂无可行性")
            e.setProperty("role", "muted")
            mf.add(e)
        self.body_layout.addWidget(mf)

        # KR 列表
        kr_card = Card()
        kr_head = QHBoxLayout()
        kr_lab = QLabel("关键结果 (%d)" % len(krs))
        kr_lab.setProperty("role", "subtitle")
        kr_head.addWidget(kr_lab)
        kr_head.addStretch()
        kr_card.add_layout(kr_head)
        if not krs:
            kr_card.add(EmptyState("还没有关键结果"))
        for kr in krs:
            kr_card.add_layout(self._kr_row(kr))
        self.body_layout.addWidget(kr_card)

        # 备忘
        memo_card = Card()
        memo_lab = QLabel("备忘 (%d)" % len(memos))
        memo_lab.setProperty("role", "subtitle")
        memo_card.add(memo_lab)
        for m in memos[:10]:
            row = QHBoxLayout()
            c = QLabel(m.get("content") or "")
            c.setProperty("role", "muted")
            row.addWidget(c, 1)
            t = QLabel(_fmt_date(m.get("createdAt")))
            t.setProperty("role", "muted")
            row.addWidget(t)
            mid = m.get("id")
            del_b = _mini_btn("删除")
            del_b.setStyleSheet("padding:2px 8px;font-size:12px;color:#F56C6C;")
            del_b.clicked.connect(lambda _=False, i=mid: self._delete_memo(i))
            row.addWidget(del_b)
            memo_card.add_layout(row)
        add_row = QHBoxLayout()
        self._memo_input = QLineEdit()
        self._memo_input.setPlaceholderText("备忘内容，回车添加")
        self._memo_input.returnPressed.connect(self._add_memo)
        add_row.addWidget(self._memo_input, 1)
        add_btn = QPushButton("添加")
        add_btn.setProperty("preset", "primary")
        add_btn.clicked.connect(self._add_memo)
        add_row.addWidget(add_btn)
        memo_card.add_layout(add_row)
        self.body_layout.addWidget(memo_card)
        self.body_layout.addStretch()

    def _kr_row(self, kr: dict):
        row = QHBoxLayout()
        row.setSpacing(10)
        emo = QLabel(kr.get("emoji") or "🌟")
        emo.setStyleSheet("font-size:20px;")
        row.addWidget(emo)

        info = QVBoxLayout()
        info.setSpacing(2)
        t = QLabel(kr.get("title") or "")
        t.setStyleSheet("font-weight:600;")
        info.addWidget(t)
        unit = kr.get("unit") or ""
        v = QLabel("%s → %s / %s %s" % (_num(kr.get("initialValue")),
                                        _num(kr.get("currentValue")),
                                        _num(kr.get("targetValue")), unit))
        v.setProperty("role", "muted")
        info.addWidget(v)
        row.addLayout(info, 1)

        chip = Chip(CALC_LABEL.get(kr.get("calculationType"), kr.get("calculationType") or ""), "true")
        row.addWidget(chip)

        p = _kr_progress(kr)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(p * 100))
        bar.setTextVisible(False)
        bar.setFixedWidth(140)
        row.addWidget(bar)
        pct_lab = QLabel("%d%%" % int(p * 100))
        pct_lab.setProperty("role", "muted")
        row.addWidget(pct_lab)

        kid = kr.get("id")
        trend = _mini_btn("趋势")
        trend.clicked.connect(lambda: self._show_trend(kr))
        row.addWidget(trend)
        return row

    # ---------- 操作 ----------
    def _open_edit(self):
        if not self._obj:
            return
        dlg = _EditObjectiveDialog(self, self._obj)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        oid = self._oid
        run_async(lambda: api.objective_update(oid, v),
                  on_ok=self._saved("目标已更新"))

    def _show_trend(self, kr: dict):
        kid = kr.get("id")
        if not kid:
            return
        run_async(lambda: api.record_trend(kid),
                  on_ok=lambda recs: _TrendDialog(self, kr, recs or []).exec())

    def _add_memo(self):
        text = self._memo_input.text().strip() if self._memo_input else ""
        if not text or not self._oid:
            return
        oid = self._oid
        run_async(lambda: api.memo_create(
            {"ownerType": "objective", "ownerId": oid, "content": text}),
            on_ok=self._saved("备忘已添加"))

    def _delete_memo(self, mid):
        if not mid:
            return
        run_async(lambda: api.memo_delete(mid), on_ok=self._saved("删除成功"))

    def _saved(self, msg: str):
        def _cb(_result):
            _toast(msg, "success")
            self.refresh()
        return _cb
