"""愿景页：愿景卡片网格（状态/年龄段/进度环/关联目标）+ 新建/编辑/达成/重置/删除。"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, EmptyState, RingProgress
from ...core import api
from ...core.worker import run_async

STATUS_LABEL = {
    "upcoming": "即将到来",
    "in_progress": "进行中",
    "achieved": "已达成",
    "expired": "已过期",
}
STATUS_CHIP = {
    "upcoming": "true",
    "in_progress": "warning",
    "achieved": "success",
    "expired": "danger",
}
OBJ_STATUS_LABEL = {
    "unplanned": "未计划",
    "not_started": "未开始",
    "in_progress": "进行中",
    "pending_review": "待复盘",
    "completed": "已复盘",
}


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


def _age_from_birth(birth: Any) -> Optional[int]:
    dt = _parse_dt(birth)
    if not dt:
        return None
    today = datetime.date.today()
    age = today.year - dt.year
    if (today.month, today.day) < (dt.month, dt.day):
        age -= 1
    return age if age >= 0 else None


def _age_text(v: dict) -> str:
    start, end = v.get("startAge"), v.get("endAge")
    if start is not None and end is not None:
        return "%s-%s 岁" % (start, end)
    if start is not None:
        return "%s+ 岁" % start
    if end is not None:
        return "~%s 岁" % end
    return ""


def _progress_color(p: float) -> str:
    if p >= 0.7:
        return "#67C23A"
    if p >= 0.4:
        return "#E6A23C"
    return "#F56C6C"


class _VisionDialog(QDialog):
    """新建 / 编辑愿景。"""

    def __init__(self, parent, vision: Optional[dict] = None):
        super().__init__(parent)
        self._editing = vision is not None
        self.setWindowTitle("编辑愿景" if self._editing else "新建愿景")
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(8)

        lab = QLabel("愿景内容 *")
        lab.setProperty("role", "muted")
        lay.addWidget(lab)
        self.content_edit = QLineEdit((vision or {}).get("content") or "")
        self.content_edit.setPlaceholderText("例如：成为一名技术专家 / 环游世界 / 创办一家公司")
        lay.addWidget(self.content_edit)

        lab2 = QLabel("年龄段（可选）")
        lab2.setProperty("role", "muted")
        lay.addWidget(lab2)
        row = QHBoxLayout()
        self.start_check, self.start_spin = _age_widget((vision or {}).get("startAge"))
        row.addWidget(self.start_check)
        row.addWidget(self.start_spin)
        row.addWidget(QLabel("~"))
        self.end_check, self.end_spin = _age_widget((vision or {}).get("endAge"))
        row.addWidget(self.end_check)
        row.addWidget(self.end_spin)
        row.addWidget(QLabel("岁"))
        row.addStretch()
        lay.addLayout(row)

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
        self.content_edit.returnPressed.connect(self._on_ok)

    def _on_ok(self):
        if not self.content_edit.text().strip():
            _toast("请输入愿景内容", "warn")
            return
        s = self.start_spin.value() if self.start_check.isChecked() else None
        e = self.end_spin.value() if self.end_check.isChecked() else None
        if s is not None and e is not None and e <= s:
            _toast("结束年龄必须大于起始年龄", "warn")
            return
        self.accept()

    def values(self) -> dict:
        dto = {"content": self.content_edit.text().strip()}
        if self.start_check.isChecked():
            dto["startAge"] = self.start_spin.value()
        if self.end_check.isChecked():
            dto["endAge"] = self.end_spin.value()
        return dto


def _age_widget(value: Optional[int]):
    """复选框 + 年龄数字输入；返回 (checkbox, spinbox)。"""
    check = QCheckBox()
    spin = QSpinBox()
    spin.setRange(0, 150)
    spin.setEnabled(False)
    if value is not None:
        check.setChecked(True)
        spin.setEnabled(True)
        try:
            spin.setValue(int(value))
        except (TypeError, ValueError):
            pass
    check.toggled.connect(spin.setEnabled)
    return check, spin


class _ClickRow(QWidget):
    """可点击行（关联目标跳转）。"""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


@register_page("/visions")
class VisionsPage(Page):
    path = "/visions"

    def __init__(self, shell):
        super().__init__(shell)
        self._visions: list = []
        self._age: Optional[int] = None

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)
        title = QLabel("愿景")
        title.setProperty("role", "title")
        hl.addWidget(title)
        self.age_lab = QLabel("")
        self.age_lab.setProperty("role", "muted")
        hl.addWidget(self.age_lab)
        hl.addStretch()
        btn_new = QPushButton("＋ 新建愿景")
        btn_new.setProperty("preset", "primary")
        btn_new.clicked.connect(self._create)
        hl.addWidget(btn_new)
        self.body_layout.addWidget(header)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(14)
        self.body_layout.addWidget(self._grid_host)
        self.body_layout.addStretch(1)

    # ---------------- 数据 ----------------
    def refresh(self):
        run_async(lambda: (api.vision_list(), api.user_me()), on_ok=self._apply)

    def _apply(self, result):
        visions, me = result
        self._visions = visions or []
        self._age = _age_from_birth((me or {}).get("birthDate") if isinstance(me, dict) else None)
        self.age_lab.setText("当前年龄：%d 岁" % self._age if self._age is not None else "")
        self._render()

    def _render(self):
        while self._grid.count():
            it = self._grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if not self._visions:
            self._grid.addWidget(EmptyState("还没有愿景，点击右上角「新建愿景」描绘人生蓝图"), 0, 0, 2, 2)
            return
        cols = 2
        for i, v in enumerate(self._visions):
            if not isinstance(v, dict):
                continue
            self._grid.addWidget(self._card(v), i // cols, i % cols)
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

    def _card(self, v: dict) -> Card:
        card = Card()
        head = QHBoxLayout()
        status = str(v.get("status") or "upcoming")
        head.addWidget(Chip(STATUS_LABEL.get(status, status),
                            STATUS_CHIP.get(status, "true")))
        age_txt = _age_text(v)
        if age_txt:
            head.addWidget(Chip(age_txt, "true"))
        head.addStretch()
        prog = v.get("progress")
        if prog is not None:
            try:
                p = max(0.0, min(1.0, float(prog)))
            except (TypeError, ValueError):
                p = 0.0
            ring = RingProgress()
            ring.set(p, _progress_color(p))
            ring.setFixedSize(56, 56)
            head.addWidget(ring)
        card.add_layout(head)

        content = QLabel(str(v.get("content") or ""))
        content.setWordWrap(True)
        content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card.add(content)

        objs = v.get("objectives") or []
        if objs:
            box = Card(flat=True)
            cap = QHBoxLayout()
            cl = QLabel("关联目标")
            cl.setProperty("role", "muted")
            cap.addWidget(cl)
            cap.addStretch()
            cn = QLabel(str(len(objs)))
            cn.setProperty("role", "muted")
            cap.addWidget(cn)
            box.add_layout(cap)
            for obj in objs:
                if not isinstance(obj, dict):
                    continue
                oid = obj.get("id")
                row = _ClickRow()
                rh = QHBoxLayout(row)
                rh.setContentsMargins(4, 2, 4, 2)
                rh.setSpacing(6)
                dot = QLabel()
                dot.setFixedSize(8, 8)
                dot.setStyleSheet("background:%s;border-radius:4px;"
                                  % (obj.get("color") or "#409EFF"))
                rh.addWidget(dot)
                t = QLabel(str(obj.get("title") or ""))
                t.setProperty("role", "muted")
                rh.addWidget(t, 1)
                ost = str(obj.get("status") or "")
                if ost:
                    rh.addWidget(Chip(OBJ_STATUS_LABEL.get(ost, ost), "true"))
                if oid:
                    row.clicked.connect(lambda o=oid: self.shell.open_objective(o))
                box.add(row)
            card.add(box)

        btns = QHBoxLayout()
        btns.addStretch()
        vid = v.get("id")
        if status != "achieved":
            b_ach = QPushButton("达成")
            b_ach.setProperty("preset", "ghost")
            b_ach.setStyleSheet("color:#67C23A;")
            b_ach.clicked.connect(lambda: self._achieve(vid))
            btns.addWidget(b_ach)
        else:
            b_reset = QPushButton("重置状态")
            b_reset.setProperty("preset", "ghost")
            b_reset.clicked.connect(lambda: self._reset(vid))
            btns.addWidget(b_reset)
        b_edit = QPushButton("编辑")
        b_edit.setProperty("preset", "ghost")
        b_edit.clicked.connect(lambda: self._edit(v))
        btns.addWidget(b_edit)
        b_del = QPushButton("删除")
        b_del.setProperty("preset", "ghost")
        b_del.setStyleSheet("color:#F56C6C;")
        b_del.clicked.connect(lambda: self._delete(vid))
        btns.addWidget(b_del)
        card.add_layout(btns)
        return card

    # ---------------- 操作 ----------------
    def _create(self):
        dlg = _VisionDialog(self)
        if dlg.exec() == QDialog.Accepted:
            dto = dlg.values()
            run_async(lambda: api.vision_create(dto),
                      on_ok=lambda _r: (_toast("创建成功", "success"), self.refresh()))

    def _edit(self, v: dict):
        dlg = _VisionDialog(self, vision=v)
        if dlg.exec() == QDialog.Accepted:
            dto = dlg.values()
            vid = v.get("id")
            run_async(lambda: api.vision_update(vid, dto),
                      on_ok=lambda _r: (_toast("修改成功", "success"), self.refresh()))

    def _achieve(self, vid):
        if not vid:
            return
        run_async(lambda: api.vision_achieve(vid),
                  on_ok=lambda _r: (_toast("已标记达成", "success"), self.refresh()))

    def _reset(self, vid):
        if not vid:
            return
        run_async(lambda: api.vision_reset(vid),
                  on_ok=lambda _r: (_toast("状态已重置", "success"), self.refresh()))

    def _delete(self, vid):
        if not vid:
            return
        if QMessageBox.question(self, "删除愿景", "删除后不可恢复，确定删除该愿景？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        run_async(lambda: api.vision_delete(vid),
                  on_ok=lambda _r: (_toast("删除成功", "success"), self.refresh()))
