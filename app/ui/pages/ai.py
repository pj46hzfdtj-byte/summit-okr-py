"""AI 助手：规划目标 / 拆解任务 / 复盘评分 / 动机建议（QTabWidget 四页签）。"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QProgressBar, QPushButton, QTabWidget,
                               QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip
from ...core import api
from ...core.worker import run_async

CALC_LABEL = {"sum": "求和", "final": "最终值", "average": "平均值",
              "max": "最大值", "custom": "自定义"}


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "summit_toast", None)
    if t:
        t.show_msg(str(msg), kind)


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


def _pct(v: Any) -> int:
    try:
        return int(round(max(0.0, min(1.0, float(v or 0))) * 100))
    except (TypeError, ValueError):
        return 0


def _flatten_groups(nodes: Any, out: List[dict]) -> List[dict]:
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        out.append(n)
        _flatten_groups(n.get("children"), out)
    return out


def _field(label: str) -> Tuple[QVBoxLayout, QWidget]:
    lay = QVBoxLayout()
    lay.setSpacing(4)
    lab = QLabel(label)
    lab.setProperty("role", "muted")
    lay.addWidget(lab)
    return lay, lab


def _gen_btn(text: str = "AI 生成") -> QPushButton:
    b = QPushButton(text)
    b.setProperty("preset", "primary")
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedWidth(120)
    return b


@register_page("/ai-assistant")
class AiAssistantPage(Page):
    path = "/ai-assistant"

    def __init__(self, shell):
        super().__init__(shell)
        self._loading = False
        self._objectives: List[dict] = []
        self._groups: List[dict] = []
        self._plan_goal: Optional[dict] = None
        self._plan_tasks: Optional[dict] = None
        self._motivations: List[str] = []
        self._kr_rows: List[Tuple[QCheckBox, dict]] = []
        self._task_rows: List[Tuple[QCheckBox, dict]] = []
        self._mot_rows: List[Tuple[QCheckBox, str]] = []

        # ---- 顶部：标题 + 今日用量 ----
        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("AI 助手")
        title.setProperty("role", "title")
        hl.addWidget(title)
        hl.addStretch()
        self.usage_lbl = QLabel("")
        self.usage_lbl.setProperty("role", "muted")
        hl.addWidget(self.usage_lbl)
        self.body_layout.addWidget(header)

        # ---- 四页签 ----
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_plan_goal_tab(), "规划目标")
        self.tabs.addTab(self._build_plan_tasks_tab(), "拆解任务")
        self.tabs.addTab(self._build_score_tab(), "复盘评分")
        self.tabs.addTab(self._build_motivations_tab(), "动机建议")
        card = Card()
        card.add(self.tabs, 1)
        self.body_layout.addWidget(card, 1)

    # ================= 页签构建 =================
    def _build_plan_goal_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 12, 6, 6)
        lay.setSpacing(12)

        f1, _ = _field("大目标")
        self.pg_goal = QLineEdit()
        self.pg_goal.setPlaceholderText("例如：考研上岸 / 半年内减重 10kg / 季度营收破百万")
        f1.addWidget(self.pg_goal)
        lay.addLayout(f1)

        f2, _ = _field("背景说明")
        self.pg_context = QPlainTextEdit()
        self.pg_context.setPlaceholderText("可选：补充时间、现状、约束等")
        self.pg_context.setFixedHeight(64)
        f2.addWidget(self.pg_context)
        lay.addLayout(f2)

        f3, _ = _field("所属节点")
        self.pg_group = QComboBox()
        f3.addWidget(self.pg_group)
        lay.addLayout(f3)

        self.pg_btn = _gen_btn()
        self.pg_btn.clicked.connect(self._run_plan_goal)
        row = QHBoxLayout()
        row.addWidget(self.pg_btn)
        row.addStretch()
        lay.addLayout(row)

        self.pg_result = QWidget()
        self.pg_result_lay = QVBoxLayout(self.pg_result)
        self.pg_result_lay.setContentsMargins(0, 0, 0, 0)
        self.pg_result_lay.setSpacing(10)
        self.pg_result.setVisible(False)
        lay.addWidget(self.pg_result)
        lay.addStretch()
        return w

    def _build_plan_tasks_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 12, 6, 6)
        lay.setSpacing(12)

        f1, _ = _field("关联目标")
        self.pt_objective = QComboBox()
        f1.addWidget(self.pt_objective)
        lay.addLayout(f1)

        f2, _ = _field("背景说明")
        self.pt_context = QPlainTextEdit()
        self.pt_context.setPlaceholderText("可选：不选目标时，可仅凭上下文拆解任务")
        self.pt_context.setFixedHeight(64)
        f2.addWidget(self.pt_context)
        lay.addLayout(f2)

        self.pt_btn = _gen_btn()
        self.pt_btn.clicked.connect(self._run_plan_tasks)
        row = QHBoxLayout()
        row.addWidget(self.pt_btn)
        row.addStretch()
        lay.addLayout(row)

        self.pt_result = QWidget()
        self.pt_result_lay = QVBoxLayout(self.pt_result)
        self.pt_result_lay.setContentsMargins(0, 0, 0, 0)
        self.pt_result_lay.setSpacing(10)
        self.pt_result.setVisible(False)
        lay.addWidget(self.pt_result)
        lay.addStretch()
        return w

    def _build_score_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 12, 6, 6)
        lay.setSpacing(12)

        f1, _ = _field("关联目标")
        self.sc_objective = QComboBox()
        f1.addWidget(self.sc_objective)
        lay.addLayout(f1)

        self.sc_btn = _gen_btn()
        self.sc_btn.clicked.connect(self._run_suggest_score)
        row = QHBoxLayout()
        row.addWidget(self.sc_btn)
        row.addStretch()
        lay.addLayout(row)

        self.sc_result = QWidget()
        self.sc_result_lay = QVBoxLayout(self.sc_result)
        self.sc_result_lay.setContentsMargins(0, 0, 0, 0)
        self.sc_result_lay.setSpacing(10)
        self.sc_result.setVisible(False)
        lay.addWidget(self.sc_result)
        lay.addStretch()
        return w

    def _build_motivations_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 12, 6, 6)
        lay.setSpacing(12)

        f1, _ = _field("目标标题")
        self.mt_title = QLineEdit()
        self.mt_title.setPlaceholderText("例如：考研上岸")
        f1.addWidget(self.mt_title)
        lay.addLayout(f1)

        f2, _ = _field("背景说明")
        self.mt_context = QPlainTextEdit()
        self.mt_context.setPlaceholderText("可选：补充时间、现状、约束等")
        self.mt_context.setFixedHeight(64)
        f2.addWidget(self.mt_context)
        lay.addLayout(f2)

        self.mt_btn = _gen_btn()
        self.mt_btn.clicked.connect(self._run_motivations)
        row = QHBoxLayout()
        row.addWidget(self.mt_btn)
        row.addStretch()
        lay.addLayout(row)

        self.mt_result = QWidget()
        self.mt_result_lay = QVBoxLayout(self.mt_result)
        self.mt_result_lay.setContentsMargins(0, 0, 0, 0)
        self.mt_result_lay.setSpacing(10)
        self.mt_result.setVisible(False)
        lay.addWidget(self.mt_result)
        lay.addStretch()
        return w

    # ================= 数据加载 =================
    def refresh(self):
        if self._loading:
            return
        self._loading = True
        run_async(lambda: (api.ai_usage(),
                           api.objective_list(),
                           api.goal_group_tree()),
                  on_ok=self._apply_shared, on_err=self._shared_err)

    def _shared_err(self, msg: str):
        self._loading = False
        _toast(msg, "error")

    def _apply_shared(self, result):
        self._loading = False
        try:
            usage, obj_data, groups = result
        except (TypeError, ValueError):
            return
        if isinstance(usage, dict):
            self.usage_lbl.setText("今日用量 %s/%s" % (usage.get("used", 0), usage.get("limit", 0)))
        objs = obj_data.get("list") if isinstance(obj_data, dict) else obj_data
        self._objectives = [o for o in (objs or []) if isinstance(o, dict)]
        self._groups = _flatten_groups(groups, [])
        self._fill_combo(self.pg_group, [(g.get("name") or "", g.get("id")) for g in self._groups])
        obj_items = [(o.get("title") or "", o.get("id")) for o in self._objectives]
        self._fill_combo(self.pt_objective, [("（不关联）", None)] + obj_items)
        self._fill_combo(self.sc_objective, obj_items)
        if getattr(self, "mt_apply", None) is not None:
            self._fill_combo(self.mt_apply, obj_items)

    @staticmethod
    def _fill_combo(combo: QComboBox, items: List[Tuple[str, Any]]):
        cur = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for text, data in items:
            combo.addItem(str(text), data)
        if cur is not None:
            idx = combo.findData(cur)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    # ================= 生成任务通用 =================
    @staticmethod
    def _run_gen(btn: QPushButton, fn, on_ok):
        orig = btn.text()
        btn.setEnabled(False)
        btn.setText("生成中…")
        w = run_async(fn, on_ok=on_ok)

        def _done():
            btn.setEnabled(True)
            btn.setText(orig)
        w.signals.finished.connect(_done)

    # ================= Tab1 规划目标 =================
    def _run_plan_goal(self):
        goal = self.pg_goal.text().strip()
        if not goal:
            _toast("请输入大目标", "warn")
            return
        ctx = self.pg_context.toPlainText().strip()
        dto = {"goal": goal}
        if ctx:
            dto["context"] = ctx
        self._run_gen(self.pg_btn, lambda: api.ai_plan_goal(dto), self._show_plan_goal)

    def _show_plan_goal(self, result):
        self._plan_goal = result if isinstance(result, dict) else None
        _clear_layout(self.pg_result_lay)
        self._kr_rows = []
        res = self._plan_goal
        if not res:
            self.pg_result.setVisible(True)
            self.pg_result_lay.addWidget(QLabel("AI 未返回结果，请重试"))
            return
        obj = res.get("objective") or {}
        card = Card()
        t = QLabel(str(obj.get("title") or ""))
        t.setProperty("role", "subtitle")
        t.setWordWrap(True)
        card.add(t)
        mots = obj.get("motivations") or []
        feas = obj.get("feasibilities") or []
        if mots or feas:
            chips = QHBoxLayout()
            chips.setSpacing(6)
            for m in mots:
                chips.addWidget(Chip("动机·%s" % m, "success"))
            for f in feas:
                chips.addWidget(Chip("可行·%s" % f, "true"))
            chips.addStretch()
            card.add_layout(chips)
        head = QLabel("关键结果")
        head.setProperty("role", "subtitle")
        card.add(head)
        for kr in res.get("keyResults") or []:
            if not isinstance(kr, dict):
                continue
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox()
            cb.setChecked(True)
            title = QLabel("%s %s" % (kr.get("emoji") or "", kr.get("title") or "")
                           if kr.get("emoji") else str(kr.get("title") or ""))
            h.addWidget(cb)
            h.addWidget(title, 1)
            rng = QLabel("%s → %s" % (kr.get("initialValue"), kr.get("targetValue")))
            rng.setProperty("role", "muted")
            h.addWidget(rng)
            calc = QLabel(CALC_LABEL.get(str(kr.get("calculationType") or ""),
                                         str(kr.get("calculationType") or "")))
            calc.setProperty("role", "muted")
            calc.setFixedWidth(70)
            h.addWidget(calc)
            wt = QLabel(str(kr.get("weight") if kr.get("weight") is not None else "-"))
            wt.setProperty("role", "muted")
            wt.setFixedWidth(40)
            wt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            h.addWidget(wt)
            card.add(row)
            self._kr_rows.append((cb, kr))
        apply_btn = QPushButton("应用所选")
        apply_btn.setProperty("preset", "primary")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self._apply_plan_goal)
        card.add(apply_btn)
        self.pg_result_lay.addWidget(card)
        self.pg_result.setVisible(True)

    def _apply_plan_goal(self):
        res = self._plan_goal
        if not res:
            return
        gid = self.pg_group.currentData()
        if not gid:
            _toast("请选择目标节点", "warn")
            return
        krs = [kr for cb, kr in self._kr_rows if cb.isChecked()]
        if not krs:
            _toast("请至少勾选一个 KR", "warn")
            return
        obj = res.get("objective") or {}
        obj_dto = {
            "goalGroupId": gid,
            "title": str(obj.get("title") or ""),
            "motivations": obj.get("motivations") or [],
            "feasibilities": obj.get("feasibilities") or [],
        }

        def _do():
            created = api.objective_create(obj_dto)
            oid = created.get("id") if isinstance(created, dict) else None
            if oid:
                for kr in krs:
                    dto = {"objectiveId": oid,
                           "title": str(kr.get("title") or ""),
                           "initialValue": kr.get("initialValue", 0),
                           "targetValue": kr.get("targetValue", 100),
                           "calculationType": kr.get("calculationType") or "sum"}
                    if kr.get("emoji"):
                        dto["emoji"] = kr.get("emoji")
                    if kr.get("weight") is not None:
                        dto["weight"] = kr.get("weight")
                    api.kr_create(dto)
            return oid

        self.pg_btn.setEnabled(False)
        run_async(_do, on_ok=self._after_apply("goal"),
                  on_finished=lambda: self.pg_btn.setEnabled(True))

    # ================= Tab2 拆解任务 =================
    def _run_plan_tasks(self):
        oid = self.pt_objective.currentData()
        ctx = self.pt_context.toPlainText().strip()
        if not oid and not ctx:
            _toast("请选择目标或填写背景说明", "warn")
            return
        dto = {}
        if oid:
            dto["objectiveId"] = oid
        if ctx:
            dto["context"] = ctx

        def _fn():
            return api.ai_plan_tasks(dto)
        self._run_gen(self.pt_btn, _fn, self._show_plan_tasks)

    def _show_plan_tasks(self, result):
        self._plan_tasks = result if isinstance(result, dict) else None
        _clear_layout(self.pt_result_lay)
        self._task_rows = []
        tasks = (self._plan_tasks or {}).get("tasks") or []
        self.pt_result.setVisible(True)
        if not tasks:
            self.pt_result_lay.addWidget(QLabel("AI 未返回任务，请重试"))
            return
        card = Card()
        head = QLabel("任务列表")
        head.setProperty("role", "subtitle")
        card.add(head)
        for tk in tasks:
            if not isinstance(tk, dict):
                continue
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            cb = QCheckBox()
            cb.setChecked(True)
            col = QVBoxLayout()
            col.setSpacing(2)
            t = QLabel(str(tk.get("title") or ""))
            col.addWidget(t)
            desc_bits = []
            if tk.get("description"):
                desc_bits.append(str(tk.get("description")))
            if tk.get("contribution"):
                desc_bits.append("贡献于：%s" % tk.get("contribution"))
            if desc_bits:
                d = QLabel(" · ".join(desc_bits))
                d.setProperty("role", "muted")
                d.setWordWrap(True)
                col.addWidget(d)
            h.addWidget(cb)
            h.addLayout(col, 1)
            card.add(row)
            self._task_rows.append((cb, tk))
        apply_btn = QPushButton("应用所选")
        apply_btn.setProperty("preset", "primary")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self._apply_plan_tasks)
        card.add(apply_btn)
        self.pt_result_lay.addWidget(card)

    def _apply_plan_tasks(self):
        picked = [tk for cb, tk in self._task_rows if cb.isChecked()]
        if not picked:
            _toast("请至少勾选一个任务", "warn")
            return
        oid = self.pt_objective.currentData()

        def _do():
            for tk in picked:
                dto = {"objectiveId": oid, "title": str(tk.get("title") or "")}
                for k in ("description", "scheduledAt", "repeatRule", "contribution"):
                    if tk.get(k):
                        dto[k] = tk.get(k)
                api.task_create(dto)
            return len(picked)

        self.pt_btn.setEnabled(False)
        run_async(_do, on_ok=self._after_apply("tasks"),
                  on_finished=lambda: self.pt_btn.setEnabled(True))

    # ================= Tab3 复盘评分 =================
    def _run_suggest_score(self):
        oid = self.sc_objective.currentData()
        if not oid:
            _toast("请选择目标", "warn")
            return
        self._run_gen(self.sc_btn,
                      lambda: (api.ai_suggest_score(oid), api.kr_list_by_objective(oid)),
                      self._show_score)

    def _show_score(self, result):
        _clear_layout(self.sc_result_lay)
        self.sc_result.setVisible(True)
        try:
            score, krs = result
        except (TypeError, ValueError):
            self.sc_result_lay.addWidget(QLabel("AI 未返回评分，请重试"))
            return
        if not isinstance(score, dict):
            self.sc_result_lay.addWidget(QLabel("AI 未返回评分，请重试"))
            return
        kr_titles = {}
        for kr in (krs or []):
            if isinstance(kr, dict) and kr.get("id"):
                kr_titles[kr.get("id")] = kr.get("title") or ""
        card = Card()
        top = QHBoxLayout()
        cap = QLabel("AI 建议自评")
        cap.setProperty("role", "subtitle")
        top.addWidget(cap)
        top.addStretch()
        rating = QLabel("%d%%" % _pct(score.get("selfRating")))
        rating.setProperty("role", "kpi")
        top.addWidget(rating)
        card.add_layout(top)
        if score.get("reasoning"):
            r = QLabel(str(score.get("reasoning")))
            r.setWordWrap(True)
            r.setProperty("role", "muted")
            card.add(r)
        for row in score.get("krScores") or []:
            if not isinstance(row, dict):
                continue
            line = QHBoxLayout()
            line.setSpacing(10)
            name = QLabel(kr_titles.get(row.get("keyResultId")) or str(row.get("keyResultId") or ""))
            name.setMaximumWidth(200)
            line.addWidget(name)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(_pct(row.get("score")))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setStyleSheet("QProgressBar::chunk{background:#67C23A;border-radius:4px;}")
            line.addWidget(bar, 1)
            pv = QLabel("%d" % _pct(row.get("score")))
            pv.setProperty("role", "muted")
            pv.setFixedWidth(30)
            pv.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            line.addWidget(pv)
            note = QLabel(str(row.get("note") or ""))
            note.setProperty("role", "muted")
            note.setMaximumWidth(220)
            line.addWidget(note)
            card.add_layout(line)
        self.sc_result_lay.addWidget(card)

    # ================= Tab4 动机建议 =================
    def _run_motivations(self):
        title = self.mt_title.text().strip()
        if not title:
            _toast("请输入目标标题", "warn")
            return
        ctx = self.mt_context.toPlainText().strip()
        dto = {"objectiveTitle": title}
        if ctx:
            dto["context"] = ctx
        self._run_gen(self.mt_btn, lambda: api.ai_suggest_motivations(dto),
                      self._show_motivations)

    def _show_motivations(self, result):
        _clear_layout(self.mt_result_lay)
        self._mot_rows = []
        mots = (result or {}).get("motivations") if isinstance(result, dict) else None
        self._motivations = [str(m) for m in (mots or [])]
        self.mt_result.setVisible(True)
        if not self._motivations:
            self.mt_result_lay.addWidget(QLabel("AI 未返回动机，请重试"))
            return
        card = Card()
        for m in self._motivations:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox()
            cb.setChecked(True)
            lab = QLabel(m)
            lab.setWordWrap(True)
            h.addWidget(cb)
            h.addWidget(lab, 1)
            card.add(row)
            self._mot_rows.append((cb, m))
        f, _ = _field("应用到")
        self.mt_apply = QComboBox()
        f.addWidget(self.mt_apply)
        card.add_layout(f)
        # 补填当前目标列表（refresh 可能先于本控件存在）
        self._fill_combo(self.mt_apply,
                         [(o.get("title") or "", o.get("id")) for o in self._objectives])
        apply_btn = QPushButton("应用所选")
        apply_btn.setProperty("preset", "primary")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self._apply_motivations)
        card.add(apply_btn)
        self.mt_result_lay.addWidget(card)

    def _apply_motivations(self):
        oid = getattr(self, "mt_apply", None) and self.mt_apply.currentData()
        if not oid:
            _toast("请选择目标", "warn")
            return
        picked = [m for cb, m in self._mot_rows if cb.isChecked()]
        if not picked:
            _toast("请至少勾选一条动机", "warn")
            return
        obj = next((o for o in self._objectives if o.get("id") == oid), None)
        existing = [str(x) for x in ((obj or {}).get("motivations") or [])]
        merged = existing + [m for m in picked if m not in existing]
        run_async(lambda: api.objective_update(oid, {"motivations": merged}),
                  on_ok=self._after_apply("motivations"))

    # ================= 应用完成回调 =================
    def _after_apply(self, which: str):
        def _cb(_result):
            _toast("应用成功", "success")
            if which == "goal":
                self._plan_goal = None
                _clear_layout(self.pg_result_lay)
                self.pg_result.setVisible(False)
                self.pg_goal.clear()
                self.pg_context.clear()
            elif which == "tasks":
                self._plan_tasks = None
                _clear_layout(self.pt_result_lay)
                self.pt_result.setVisible(False)
                self.pt_context.clear()
            elif which == "motivations":
                self._motivations = []
                _clear_layout(self.mt_result_lay)
                self.mt_result.setVisible(False)
                self.mt_title.clear()
                self.mt_context.clear()
            self.refresh()
        return _cb
