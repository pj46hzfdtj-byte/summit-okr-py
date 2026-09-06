"""回收站：软删除条目列表 + 恢复 / 彻底删除 / 清空。"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, EmptyState
from ...core import api
from ...core.worker import run_async

TYPE_LABEL = {
    "objective": "目标",
    "key_result": "关键结果",
    "task": "任务",
    "review": "复盘",
    "vision": "愿景",
    "goal_group": "目标节点",
    "record": "记录",
    "memo": "备忘",
}


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "summit_toast", None)
    if t:
        t.show_msg(str(msg), kind)


def _fmt_dt(s: Any) -> str:
    if not s:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return str(s)[:16]


@register_page("/recycle-bin")
class RecycleBinPage(Page):
    path = "/recycle-bin"

    def __init__(self, shell):
        super().__init__(shell)
        self._loading = False

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("回收站")
        title.setProperty("role", "title")
        hl.addWidget(title)
        hl.addStretch()
        self.btn_empty = QPushButton("清空回收站")
        self.btn_empty.setProperty("preset", "danger")
        self.btn_empty.setCursor(Qt.PointingHandCursor)
        self.btn_empty.clicked.connect(self._empty)
        self.btn_empty.setVisible(False)
        hl.addWidget(self.btn_empty)
        self.body_layout.addWidget(header)

        hint = Card(flat=True)
        hlay = QHBoxLayout(hint)
        hlay.setContentsMargins(12, 10, 12, 10)
        info = QLabel("\u2139")  # ℹ
        info.setStyleSheet("color:#409EFF;font-weight:700;")
        hlay.addWidget(info, 0, Qt.AlignTop)
        txt = QLabel("删除的目标、关键结果和任务会保留 30 天，可随时恢复；超期自动清除。")
        txt.setProperty("role", "muted")
        txt.setWordWrap(True)
        hlay.addWidget(txt, 1)
        self.body_layout.addWidget(hint)

        self._list = QWidget()
        self._list_lay = QVBoxLayout(self._list)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(10)
        self.body_layout.addWidget(self._list)
        self.body_layout.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self):
        if self._loading:
            return
        self._loading = True
        run_async(api.recycle_list, on_ok=self._apply, on_err=self._err)

    def _err(self, msg: str):
        self._loading = False
        _toast(msg, "error")

    def _apply(self, items):
        self._loading = False
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        items = [x for x in (items or []) if isinstance(x, dict)]
        self.btn_empty.setVisible(bool(items))
        if not items:
            self._list_lay.addWidget(EmptyState("回收站是空的"))
            return
        for item in items:
            self._list_lay.addWidget(self._item_card(item))

    def _item_card(self, item: dict) -> Card:
        card = Card(padding=12)
        row = QHBoxLayout()
        row.setSpacing(10)
        etype = str(item.get("entityType") or "")
        row.addWidget(Chip(TYPE_LABEL.get(etype, etype or "未知"), "true"))
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(str(item.get("title") or "（无标题）"))
        t.setProperty("role", "subtitle")
        col.addWidget(t)
        bits = []
        if item.get("meta"):
            bits.append("归属：%s" % item.get("meta"))
        deleted = _fmt_dt(item.get("deletedAt"))
        if deleted:
            bits.append("删除于 %s" % deleted)
        if bits:
            m = QLabel(" · ".join(bits))
            m.setProperty("role", "muted")
            col.addWidget(m)
        row.addLayout(col, 1)

        etype_v = etype or None
        eid = item.get("id")

        b_restore = QPushButton("恢复")
        b_restore.setProperty("preset", "ghost")
        b_restore.setCursor(Qt.PointingHandCursor)
        b_restore.clicked.connect(lambda: self._restore(etype_v, eid))
        row.addWidget(b_restore)

        b_destroy = QPushButton("彻底删除")
        b_destroy.setProperty("preset", "danger")
        b_destroy.setCursor(Qt.PointingHandCursor)
        b_destroy.clicked.connect(
            lambda: self._destroy(etype_v, eid, str(item.get("title") or "")))
        row.addWidget(b_destroy)
        card.add_layout(row)
        return card

    # ------------------------------------------------------------------
    def _restore(self, etype: Optional[str], eid: Optional[str]):
        if not etype or not eid:
            return
        run_async(lambda: api.recycle_restore(etype, eid),
                  on_ok=self._done("已恢复到原位置"))

    def _destroy(self, etype: Optional[str], eid: Optional[str], name: str):
        if not etype or not eid:
            return
        ret = QMessageBox.question(
            self, "彻底删除",
            "确定彻底删除「%s」吗？操作不可恢复！" % name,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        run_async(lambda: api.recycle_destroy(etype, eid),
                  on_ok=self._done("已彻底删除"))

    def _empty(self):
        ret = QMessageBox.question(
            self, "清空回收站",
            "确定清空回收站吗？所有条目将被彻底删除，操作不可恢复！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        run_async(api.recycle_empty, on_ok=self._emptied)

    def _emptied(self, result):
        count = result.get("count") if isinstance(result, dict) else None
        _toast("已清空 %s 个条目" % (count if count is not None else ""), "success")
        self.refresh()

    def _done(self, msg: str):
        def _cb(_result):
            _toast(msg, "success")
            self.refresh()
        return _cb
