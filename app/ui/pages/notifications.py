"""通知中心：规则驱动通知列表 + 已读 / 删除 / 全部已读 + 点击跳转。"""
from __future__ import annotations

import datetime
import json
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, EmptyState
from ...core import api
from ...core.worker import run_async

# title 存 i18n key（后端规则引擎），本地化渲染（对齐 web 端 zh-CN）
TITLE_TPL = {
    "notif.reviewPending.title": "目标「{objectiveTitle}」已到期，别忘了做复盘",
    "notif.staleKr.title": "关键结果「{krTitle}」已 14 天没有更新记录",
    "notif.cycleEnding.title": "专注周期「{cycleName}」将在 {days} 天后结束",
    "notif.taskOverdue.title": "你有 {count} 个任务已逾期未完成",
    "notif.checkinReminder.title": "本周还没有 Check-in，花一分钟记录一下进展吧",
}


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "vis_toast", None)
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


def _render_title(item: dict) -> str:
    raw = str(item.get("title") or "")
    tpl = TITLE_TPL.get(raw)
    if not tpl:
        return raw
    body = item.get("body")
    params: dict = {}
    if isinstance(body, dict):
        params = body
    elif isinstance(body, str) and body.strip():
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                params = parsed
        except ValueError:
            pass
    try:
        return tpl.format(**{k: params.get(k, "") for k in
                             ("objectiveTitle", "krTitle", "cycleName", "days", "count")})
    except KeyError:
        return raw


def _body_text(item: dict) -> str:
    body = item.get("body") or item.get("content")
    if isinstance(body, dict):
        return ""
    if isinstance(body, str) and body.strip() and body.strip() not in ("{}",):
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return ""
        except ValueError:
            pass
        return body.strip()
    return ""


def _extract_objective_id(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    parts = [p for p in str(link).split("?")[0].split("#")[0].split("/") if p]
    if len(parts) >= 2 and parts[0] == "objectives":
        return parts[1]
    return None


class _ClickCard(Card):
    """整卡可点击（打开通知并跳转）。"""

    def __init__(self, on_click, parent=None):
        super().__init__(parent, padding=12)
        self._on_click = on_click
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.pos()):
            self._on_click()
        super().mouseReleaseEvent(e)


@register_page("/notifications")
class NotificationsPage(Page):
    path = "/notifications"

    def __init__(self, shell):
        super().__init__(shell)
        self._loading = False

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("通知中心")
        title.setProperty("role", "title")
        hl.addWidget(title)
        self.unread_lbl = QLabel("")
        self.unread_lbl.setProperty("role", "muted")
        hl.addSpacing(8)
        hl.addWidget(self.unread_lbl, 0, Qt.AlignBottom)
        hl.addStretch()
        self.btn_all = QPushButton("全部已读")
        self.btn_all.setProperty("preset", "ghost")
        self.btn_all.setCursor(Qt.PointingHandCursor)
        self.btn_all.clicked.connect(self._mark_all)
        self.btn_all.setVisible(False)
        hl.addWidget(self.btn_all)
        self.body_layout.addWidget(header)

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
        run_async(api.notification_list, on_ok=self._apply, on_err=self._err)

    def _err(self, msg: str):
        self._loading = False
        _toast(msg, "error")

    def _apply(self, data):
        self._loading = False
        items = []
        unread = 0
        if isinstance(data, dict):
            items = data.get("list") or []
            unread = int(data.get("unread") or 0)
        elif isinstance(data, list):
            items = data
            unread = sum(1 for x in items if isinstance(x, dict) and not x.get("read"))
        items = [x for x in items if isinstance(x, dict)]

        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

        self.unread_lbl.setText("未读 %d" % unread if unread else "")
        self.btn_all.setVisible(bool(unread))
        if not items:
            self._list_lay.addWidget(EmptyState("暂无通知"))
            return
        for item in items:
            self._list_lay.addWidget(self._item_card(item))

    def _item_card(self, item: dict) -> Card:
        nid = item.get("id")
        read = bool(item.get("read"))
        link = item.get("link")
        oid = _extract_objective_id(link)

        def _open():
            if not read and nid:
                run_async(lambda: api.notification_mark_read(nid),
                          on_ok=lambda _r: self.refresh())
            if oid:
                self.shell.open_objective(oid)
            elif link and str(link).startswith("/"):
                self.shell.navigate(str(link).split("?")[0])

        card = _ClickCard(_open)
        row = QHBoxLayout()
        row.setSpacing(10)
        if not read:
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet("background:#409EFF;border-radius:4px;")
            row.addWidget(dot, 0, Qt.AlignTop | Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(3)
        t = QLabel(_render_title(item))
        t.setWordWrap(True)
        if not read:
            t.setStyleSheet("font-weight:700;")
        col.addWidget(t)
        body = _body_text(item)
        if body:
            b = QLabel(body)
            b.setProperty("role", "muted")
            b.setWordWrap(True)
            col.addWidget(b)
        when = QLabel(_fmt_dt(item.get("createdAt")))
        when.setProperty("role", "muted")
        col.addWidget(when)
        row.addLayout(col, 1)

        if not read and nid:
            b_read = QPushButton("已读")
            b_read.setProperty("preset", "ghost")
            b_read.setCursor(Qt.PointingHandCursor)
            b_read.clicked.connect(lambda: self._mark_one(nid))
            row.addWidget(b_read, 0, Qt.AlignTop)
        if nid:
            b_del = QPushButton("删除")
            b_del.setProperty("preset", "ghost")
            b_del.setCursor(Qt.PointingHandCursor)
            b_del.setStyleSheet("color:#F56C6C;")
            b_del.clicked.connect(lambda: self._delete(nid))
            row.addWidget(b_del, 0, Qt.AlignTop)
        card.add_layout(row)
        return card

    # ------------------------------------------------------------------
    def _mark_one(self, nid: str):
        run_async(lambda: api.notification_mark_read(nid),
                  on_ok=lambda _r: self.refresh())

    def _mark_all(self):
        run_async(api.notification_mark_all_read, on_ok=lambda _r: self.refresh())

    def _delete(self, nid: str):
        run_async(lambda: api.notification_delete(nid),
                  on_ok=lambda _r: self.refresh())
