"""复盘页：复盘时间线卡片 + 全部/期中/期末筛选 + 新建/编辑（期中）/删除。"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QRadioButton, QScrollArea,
                               QSlider, QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, EmptyState
from ...core import api
from ...core.worker import run_async

TYPE_LABEL = {"midterm": "期中", "final": "期末"}


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


def _fmt_dt(s: Any) -> str:
    dt = _parse_dt(s)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def _pct(v: Any) -> int:
    try:
        return int(round(max(0.0, min(1.0, float(v or 0))) * 100))
    except (TypeError, ValueError):
        return 0


def _score_color(v01: float) -> str:
    if v01 >= 0.7:
        return "#67C23A"
    if v01 >= 0.4:
        return "#E6A23C"
    return "#F56C6C"


def _progress_bar(value: int, color: str) -> QWidget:
    from PySide6.QtWidgets import QProgressBar
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(max(0, min(100, value)))
    bar.setTextVisible(False)
    bar.setFixedHeight(8)
    bar.setStyleSheet("QProgressBar::chunk{background:%s;border-radius:4px;}" % color)
    return bar


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


class _KrSliderRow(QWidget):
    """单个 KR 评分行：标题 + 滑块(0-100) + 分值标签。"""

    def __init__(self, title: str, score01: float, parent=None):
        super().__init__(parent)
        self.krid = None  # 由外部填充
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        lab = QLabel(title)
        lab.setMinimumWidth(120)
        lab.setMaximumWidth(220)
        h.addWidget(lab)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(_pct(score01))
        h.addWidget(self.slider, 1)
        self.val = QLabel("%d" % self.slider.value())
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val.setFixedWidth(34)
        self.slider.valueChanged.connect(lambda v: self.val.setText(str(v)))
        h.addWidget(self.val)

    def score(self) -> float:
        return self.slider.value() / 100.0


class _ReviewDialog(QDialog):
    """新建 / 编辑复盘。

    mode="create": 选目标 + 类型 + 动态加载 KR 滑块；
    mode="edit"  : 仅期中，评分/自评/文本可改（目标与类型锁定）。
    """

    def __init__(self, parent, objectives: list, review: Optional[dict] = None,
                 kr_titles: Optional[dict] = None):
        super().__init__(parent)
        self._obj_map = {o.get("id"): o for o in (objectives or []) if isinstance(o, dict)}
        self._editing = review is not None
        self.setWindowTitle("编辑期中复盘" if self._editing else "新建复盘")
        self.setMinimumWidth(520)
        self._kr_rows = []  # _KrSliderRow
        self._kr_titles = dict(kr_titles or {})
        self._pending_oid = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(8)

        def muted(s):
            lab = QLabel(s)
            lab.setProperty("role", "muted")
            return lab

        if not self._editing:
            outer.addWidget(muted("选择目标 *"))
            self.obj_combo = QComboBox()
            self.obj_combo.addItem("（请选择）", None)
            for o in objectives or []:
                self.obj_combo.addItem(str(o.get("title") or "")[:36], o.get("id"))
            self.obj_combo.currentIndexChanged.connect(self._on_obj_change)
            outer.addWidget(self.obj_combo)

            row = QHBoxLayout()
            self.radio_mid = QRadioButton("期中复盘")
            self.radio_mid.setChecked(True)
            self.radio_final = QRadioButton("期末复盘")
            self.radio_final.setEnabled(False)  # 选择目标后按状态启用
            row.addWidget(self.radio_mid)
            row.addWidget(self.radio_final)
            row.addStretch()
            outer.addLayout(row)
            outer.addWidget(muted("目标需为「进行中」或「待复盘」才能期末复盘"))

            self.krs_holder = QScrollArea()
            self.krs_holder.setWidgetResizable(True)
            self.krs_holder.setMaximumHeight(240)
            self.krs_inner = QWidget()
            self.krs_lay = QVBoxLayout(self.krs_inner)
            self.krs_lay.setContentsMargins(8, 6, 8, 6)
            self.krs_lay.setSpacing(6)
            self.krs_lay.addWidget(muted("选择目标后自动加载关键结果评分"))
            self.krs_holder.setWidget(self.krs_inner)
            outer.addWidget(self.krs_holder)
            self._loading_krs = False
        else:
            self.obj_combo = None
            self.radio_mid = None
            self.radio_final = None
            oid = review.get("objectiveId")
            title = ""
            for o in objectives or []:
                if o.get("id") == oid:
                    title = str(o.get("title") or "")
                    break
            head = QHBoxLayout()
            lab = QLabel("目标：" + (title or "-"))
            lab.setProperty("role", "subtitle")
            head.addWidget(lab)
            head.addStretch()
            outer.addLayout(head)
            outer.addWidget(muted("保存后将生成新的版本"))

            self.krs_inner = None
            self.krs_lay = None
            self.krs_holder = None
            kr_box = QVBoxLayout()
            kr_box.setSpacing(6)
            for ks in review.get("krScores") or []:
                if not isinstance(ks, dict):
                    continue
                krid = ks.get("keyResultId")
                r = _KrSliderRow(self._kr_titles.get(krid) or str(krid or "")[:8],
                                 float(ks.get("score") or 0))
                r.krid = krid
                kr_box.addWidget(r)
                self._kr_rows.append(r)
            if not self._kr_rows:
                kr_box.addWidget(muted("该复盘没有 KR 评分明细"))
            outer.addLayout(kr_box)

        outer.addWidget(muted("自我评分 *（70 分是健康的 OKR 分数）"))
        srow = QHBoxLayout()
        self.self_slider = QSlider(Qt.Horizontal)
        self.self_slider.setRange(0, 100)
        init_self = _pct((review or {}).get("selfRating")) if self._editing else 70
        self.self_slider.setValue(init_self)
        self.self_val = QLabel(str(init_self))
        self.self_val.setFixedWidth(34)
        self.self_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.self_slider.valueChanged.connect(lambda v: self.self_val.setText(str(v)))
        srow.addWidget(self.self_slider, 1)
        srow.addWidget(self.self_val)
        outer.addLayout(srow)

        outer.addWidget(muted("问题总结"))
        self.problems = QPlainTextEdit()
        self.problems.setPlaceholderText("遇到了什么问题？")
        self.problems.setFixedHeight(56)
        if self._editing:
            self.problems.setPlainText((review or {}).get("problems") or "")
        outer.addWidget(self.problems)

        outer.addWidget(muted("解决方案"))
        self.solutions = QPlainTextEdit()
        self.solutions.setPlaceholderText("如何解决这些问题？")
        self.solutions.setFixedHeight(56)
        if self._editing:
            self.solutions.setPlainText((review or {}).get("solutions") or "")
        outer.addWidget(self.solutions)

        outer.addWidget(muted("感想"))
        self.thoughts = QPlainTextEdit()
        self.thoughts.setPlaceholderText("写下你的感想")
        self.thoughts.setFixedHeight(56)
        if self._editing:
            self.thoughts.setPlainText((review or {}).get("thoughts") or "")
        outer.addWidget(self.thoughts)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("保存新版本" if self._editing else "创建")
        ok.setProperty("preset", "primary")
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addLayout(btns)

    # ---- 新建：目标切换 -> 异步加载 KR ----
    def _on_obj_change(self, _idx: int):
        oid = self.obj_combo.currentData()
        obj = self._obj_map.get(oid) or {}
        can_final = obj.get("status") in ("in_progress", "pending_review")
        self.radio_final.setEnabled(bool(can_final))
        if not can_final and self.radio_final.isChecked():
            self.radio_mid.setChecked(True)
        _clear_layout(self.krs_lay)
        self._kr_rows = []
        if not oid:
            self.krs_lay.addWidget(QLabel("选择目标后自动加载关键结果评分"))
            return
        self._pending_oid = oid
        self._loading_krs = True
        self.krs_lay.addWidget(QLabel("正在加载关键结果…"))
        run_async(lambda: api.kr_list_by_objective(oid),
                  on_ok=self._krs_loaded, on_err=self._krs_failed)

    def _krs_failed(self, _msg: str):
        self._loading_krs = False

    def _krs_loaded(self, krs):
        self._loading_krs = False
        if self.obj_combo.currentData() != self._pending_oid:
            return  # 用户已切换目标，丢弃过期结果
        _clear_layout(self.krs_lay)
        self._kr_rows = []
        krs = krs or []
        if not krs:
            self.krs_lay.addWidget(QLabel("该目标没有关键结果，无法复盘"))
            return
        for kr in krs:
            if not isinstance(kr, dict):
                continue
            krid = kr.get("id")
            self._kr_titles[krid] = str(kr.get("title") or "")
            r = _KrSliderRow(str(kr.get("title") or ""), float(kr.get("currentProgress") or 0))
            r.krid = krid
            self.krs_lay.addWidget(r)
            self._kr_rows.append(r)

    def _on_ok(self):
        if not self._editing:
            if not self.obj_combo.currentData():
                _toast("请选择目标", "warn")
                return
            if self._loading_krs:
                _toast("关键结果加载中，请稍候", "warn")
                return
            if not self._kr_rows:
                _toast("该目标没有关键结果，无法复盘", "warn")
                return
        self.accept()

    def values(self) -> dict:
        dto = {
            "krScores": [{"keyResultId": r.krid, "score": round(r.score(), 2)}
                         for r in self._kr_rows if r.krid],
            "selfRating": round(self.self_slider.value() / 100.0, 2),
            "problems": self.problems.toPlainText().strip() or None,
            "solutions": self.solutions.toPlainText().strip() or None,
            "thoughts": self.thoughts.toPlainText().strip() or None,
        }
        if not self._editing:
            dto["objectiveId"] = self.obj_combo.currentData()
            dto["type"] = "final" if self.radio_final.isChecked() else "midterm"
        return dto


@register_page("/reviews")
class ReviewsPage(Page):
    path = "/reviews"

    def __init__(self, shell):
        super().__init__(shell)
        self._reviews: list = []
        self._objectives: list = []
        self._obj_map: dict = {}
        self._kr_titles: dict = {}

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        title = QLabel("复盘")
        title.setProperty("role", "title")
        hl.addWidget(title)
        hl.addStretch()
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部", None)
        self.type_combo.addItem("期中", "midterm")
        self.type_combo.addItem("期末", "final")
        self.type_combo.currentIndexChanged.connect(self._render)
        hl.addWidget(self.type_combo)
        btn_new = QPushButton("＋ 新建复盘")
        btn_new.setProperty("preset", "primary")
        btn_new.clicked.connect(self._create)
        hl.addWidget(btn_new)
        self.body_layout.addWidget(header)

        self._dyn = QWidget()
        self._dyn_lay = QVBoxLayout(self._dyn)
        self._dyn_lay.setContentsMargins(0, 0, 0, 0)
        self._dyn_lay.setSpacing(12)
        self.body_layout.addWidget(self._dyn, 1)
        self.body_layout.addStretch(1)
        self._ready = True

    # ---------------- 数据 ----------------
    def refresh(self):
        run_async(lambda: (api.review_list(), api.objective_list()), on_ok=self._apply)

    def _apply(self, result):
        reviews, objs = result
        self._reviews = reviews or []
        obj_list = objs.get("list") if isinstance(objs, dict) else (objs or [])
        self._objectives = obj_list or []
        self._obj_map = {o.get("id"): o for o in self._objectives if isinstance(o, dict)}
        need = {r.get("objectiveId") for r in self._reviews
                if isinstance(r, dict) and r.get("objectiveId")}
        need = {i for i in need if i and not self._has_all_krs(i)}
        if need:
            run_async(lambda: self._fetch_krs(need), on_ok=self._krs_ok)
        self._render()

    def _has_all_krs(self, oid) -> bool:
        for r in self._reviews:
            if not isinstance(r, dict) or r.get("objectiveId") != oid:
                continue
            for ks in r.get("krScores") or []:
                if isinstance(ks, dict) and ks.get("keyResultId") \
                        and ks.get("keyResultId") not in self._kr_titles:
                    return False
        return True

    def _fetch_krs(self, oids):
        out = {}
        for oid in oids:
            try:
                for kr in api.kr_list_by_objective(oid) or []:
                    if isinstance(kr, dict) and kr.get("id"):
                        out[kr["id"]] = str(kr.get("title") or "")
            except Exception:  # noqa: BLE001
                continue
        return out

    def _krs_ok(self, titles):
        if isinstance(titles, dict):
            self._kr_titles.update(titles)
        self._render()

    # ---------------- 渲染 ----------------
    def _render(self):
        _clear_layout(self._dyn_lay)
        type_ = self.type_combo.currentData()
        reviews = [r for r in self._reviews
                   if isinstance(r, dict) and (not type_ or r.get("type") == type_)]
        if not reviews:
            self._dyn_lay.addWidget(EmptyState("还没有复盘记录，点击右上角「新建复盘」总结阶段性成果"))
            return
        for r in reviews:
            self._dyn_lay.addWidget(self._review_card(r))

    def _review_card(self, r: dict) -> Card:
        card = Card()
        head = QHBoxLayout()
        rtype = r.get("type") or "midterm"
        head.addWidget(Chip(TYPE_LABEL.get(rtype, rtype), "success" if rtype == "final" else "warning"))
        ver = QLabel("v%s" % (r.get("version") or 1))
        ver.setProperty("role", "muted")
        head.addWidget(ver)
        obj = self._obj_map.get(r.get("objectiveId"))
        otitle = QLabel(str((obj or {}).get("title") or ""))
        otitle.setProperty("role", "muted")
        head.addWidget(otitle)
        if obj and obj.get("id"):
            link = QPushButton("查看目标")
            link.setProperty("preset", "ghost")
            link.setCursor(Qt.PointingHandCursor)
            link.setStyleSheet("padding:2px 8px;font-size:12px;")
            link.clicked.connect(lambda: self.shell.open_objective(obj["id"]))
            head.addWidget(link)
        head.addStretch()
        self_pct = _pct(r.get("selfRating"))
        head.addWidget(Chip("自评 %d" % self_pct,
                            "success" if self_pct >= 70 else ("warning" if self_pct >= 40 else "danger")))
        oscore = r.get("objectiveScore")
        if oscore is not None:
            head.addWidget(Chip("目标 %s" % oscore, "true"))
        when = QLabel(_fmt_dt(r.get("createdAt")))
        when.setProperty("role", "muted")
        head.addWidget(when)
        if rtype == "midterm":
            b_edit = QPushButton("编辑")
            b_edit.setProperty("preset", "ghost")
            b_edit.clicked.connect(lambda: self._edit(r))
            head.addWidget(b_edit)
        b_del = QPushButton("删除")
        b_del.setCursor(Qt.PointingHandCursor)
        b_del.setStyleSheet("padding:2px 8px;font-size:12px;color:#F56C6C;")
        b_del.clicked.connect(lambda: self._delete(r))
        head.addWidget(b_del)
        card.add_layout(head)

        for ks in r.get("krScores") or []:
            if not isinstance(ks, dict):
                continue
            krid = ks.get("keyResultId")
            s01 = float(ks.get("score") or 0) if isinstance(ks.get("score"), (int, float)) else 0.0
            row = QHBoxLayout()
            name = QLabel(self._kr_titles.get(krid) or str(krid or "")[:8])
            name.setMinimumWidth(120)
            name.setMaximumWidth(220)
            row.addWidget(name)
            row.addWidget(_progress_bar(_pct(s01), _score_color(s01)), 1)
            val = QLabel(str(_pct(s01)))
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val.setFixedWidth(34)
            row.addWidget(val)
            note = ks.get("note")
            if note:
                nl = QLabel(str(note))
                nl.setProperty("role", "muted")
                row.addWidget(nl)
            card.add_layout(row)

        for label, key in (("问题", "problems"), ("解决方案", "solutions"), ("感想", "thoughts")):
            text = r.get(key)
            if text:
                cap = QLabel(label)
                cap.setProperty("role", "muted")
                body = QLabel(str(text))
                body.setWordWrap(True)
                card.add(cap)
                card.add(body)
        return card

    # ---------------- 操作 ----------------
    def _create(self):
        dlg = _ReviewDialog(self, self._objectives, kr_titles=self._kr_titles)
        if dlg.exec() == QDialog.Accepted:
            dto = dlg.values()
            rtype = dto.get("type")

            def _ok(_r):
                _toast("期末复盘完成，目标已结束" if rtype == "final" else "期中复盘已创建",
                       "success")
                self.refresh()
            run_async(lambda: api.review_create(dto), on_ok=_ok)

    def _edit(self, r: dict):
        dlg = _ReviewDialog(self, self._objectives, review=r, kr_titles=self._kr_titles)
        if dlg.exec() == QDialog.Accepted:
            dto = dlg.values()
            rid = r.get("id")
            run_async(lambda: api.review_update(rid, dto),
                      on_ok=lambda _x: (_toast("复盘已更新（新版本）", "success"), self.refresh()))

    def _delete(self, r: dict):
        if QMessageBox.question(self, "提示", "确定删除该复盘记录？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        rid = r.get("id")
        run_async(lambda: api.review_delete(rid),
                  on_ok=lambda _x: (_toast("删除成功", "success"), self.refresh()))
