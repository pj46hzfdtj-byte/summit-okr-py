"""个人中心：资料 / 外观 / 语言 / 数据导入导出 / 账号。"""
from __future__ import annotations

import datetime
import json
from typing import List, Optional

from PySide6.QtCore import Qt, QDate, QDateTime, QTime
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDateEdit,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..theme import MODES, THEMES
from ..widgets import Card
from ...core import api
from ...core.worker import run_async
from ...state import app as app_store
from ...state import auth

THEME_LABELS = {"light": "浅色", "blue": "蓝色", "green": "绿色",
                "purple": "紫色", "macos": "macOS"}
MODE_LABELS = {"light": "日间", "dark": "夜间", "system": "跟随系统"}
LOCALES = [("zh-CN", "简体中文"), ("zh-TW", "繁體中文"),
           ("en-US", "English"), ("ja-JP", "日本語")]


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "vis_toast", None)
    if t:
        t.show_msg(str(msg), kind)


def _field(label: str) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(4)
    lab = QLabel(label)
    lab.setProperty("role", "muted")
    lay.addWidget(lab)
    return lay


class _Seg(QButtonGroup):
    """互斥按钮组：按值高亮当前项。"""

    def __init__(self, values: List[str], labels, parent=None):
        super().__init__(parent)
        self.setExclusive(True)
        self.values = list(values)
        self._labels = labels
        for i, v in enumerate(self.values):
            b = QPushButton(labels.get(v, v))
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.addButton(b, i)

    def sync(self, current: str):
        for i, btn in enumerate(self.buttons()):
            on = self.values[i] == current
            btn.setProperty("preset", "primary" if on else "ghost")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def connect_pick(self, on_pick):
        for i, btn in enumerate(self.buttons()):
            btn.clicked.connect(lambda _=False, v=self.values[i]: on_pick(v))

    def widgets(self) -> List[QPushButton]:
        return list(self.buttons())


def _iso_from_qdate(d: QDate) -> str:
    dt = QDateTime(d, QTime(0, 0))
    s = dt.toUTC().toString(Qt.ISODate)
    return s if s.endswith("Z") else s + "Z"


def _qdate_from_iso(iso) -> Optional[QDate]:
    if not iso:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
        return QDate(dt.year, dt.month, dt.day)
    except Exception:  # noqa: BLE001
        return None


@register_page("/profile")
class ProfilePage(Page):
    path = "/profile"

    def __init__(self, shell):
        super().__init__(shell)
        self._user: Optional[dict] = None
        self._loaded_once = False
        self._filling = False

        title = QLabel("个人中心")
        title.setProperty("role", "title")
        self.body_layout.addWidget(title)

        self._build_profile()
        self._build_appearance()
        self._build_language()
        self._build_data()
        self._build_account()
        self.body_layout.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self):
        run_async(api.user_me, on_ok=self._apply)

    def _apply(self, user):
        if not isinstance(user, dict):
            return
        self._user = user
        self._filling = True
        self.email.setText(str(user.get("email") or ""))
        self.username.setText(str(user.get("username") or ""))
        self.bio.setPlainText(str(user.get("bio") or ""))
        d = _qdate_from_iso(user.get("birthDate"))
        has_birth = d is not None
        self.birth_check.setChecked(has_birth)
        if has_birth:
            self.birth_edit.setDate(d)
        loc = user.get("preferredLocale") or "zh-CN"
        idx = self.locale_combo.findData(loc)
        if idx >= 0:
            self.locale_combo.setCurrentIndex(idx)
        self._filling = False

    # ================= 1. 个人资料 =================
    def _build_profile(self):
        card = Card()
        head = QLabel("个人资料")
        head.setProperty("role", "subtitle")
        card.add(head)

        f1 = _field("邮箱")
        self.email = QLineEdit()
        self.email.setReadOnly(True)
        f1.addWidget(self.email)
        card.add_layout(f1)

        f2 = _field("用户名")
        self.username = QLineEdit()
        f2.addWidget(self.username)
        card.add_layout(f2)

        f3 = _field("个人简介")
        self.bio = QPlainTextEdit()
        self.bio.setFixedHeight(80)
        f3.addWidget(self.bio)
        card.add_layout(f3)

        f4 = _field("生日（用于愿景年龄计算）")
        born_row = QHBoxLayout()
        self.birth_check = QCheckBox("设置生日")
        self.birth_edit = QDateEdit(QDate.currentDate())
        self.birth_edit.setCalendarPopup(True)
        self.birth_edit.setDisplayFormat("yyyy-MM-dd")
        self.birth_edit.setEnabled(False)
        self.birth_check.toggled.connect(self.birth_edit.setEnabled)
        born_row.addWidget(self.birth_check)
        born_row.addWidget(self.birth_edit)
        born_row.addStretch()
        f4.addLayout(born_row)
        card.add_layout(f4)

        btns = QHBoxLayout()
        btns.addStretch()
        self.save_btn = QPushButton("保存")
        self.save_btn.setProperty("preset", "primary")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_profile)
        btns.addWidget(self.save_btn)
        card.add_layout(btns)
        self.body_layout.addWidget(card)

    def _save_profile(self):
        u = self._user or {}
        dto = {
            "bio": self.bio.toPlainText().strip(),
            "birthDate": _iso_from_qdate(self.birth_edit.date())
            if self.birth_check.isChecked() else None,
            "preferredTheme": app_store.theme,
            "preferredLocale": self.locale_combo.currentData() or "zh-CN",
        }
        name = self.username.text().strip()
        if name:
            dto["username"] = name
        self.save_btn.setEnabled(False)
        w = run_async(lambda: api.user_update_me(dto), on_ok=self._profile_saved)
        w.signals.finished.connect(lambda: self.save_btn.setEnabled(True))

    def _profile_saved(self, user):
        if isinstance(user, dict):
            self._user = user
            auth.user = user
            auth.user_changed.emit()
        _toast("保存成功", "success")

    # ================= 2. 外观 =================
    def _build_appearance(self):
        card = Card()
        head = QLabel("外观")
        head.setProperty("role", "subtitle")
        card.add(head)

        row1 = QHBoxLayout()
        lab1 = QLabel("模式")
        lab1.setProperty("role", "muted")
        row1.addWidget(lab1)
        row1.addStretch()
        self._mode_seg = _Seg(MODES, MODE_LABELS)
        self._mode_seg.connect_pick(self._pick_mode)
        for b in self._mode_seg.widgets():
            row1.addWidget(b)
        card.add_layout(row1)

        row2 = QHBoxLayout()
        lab2 = QLabel("主题")
        lab2.setProperty("role", "muted")
        row2.addWidget(lab2)
        row2.addStretch()
        self._theme_seg = _Seg(THEMES, THEME_LABELS)
        self._theme_seg.connect_pick(self._pick_theme)
        for b in self._theme_seg.widgets():
            row2.addWidget(b)
        card.add_layout(row2)

        row3 = QHBoxLayout()
        self.compact_check = QCheckBox("紧凑模式")
        self.compact_check.setChecked(app_store.compact)
        self.compact_check.toggled.connect(self._pick_compact)
        row3.addWidget(self.compact_check)
        row3.addStretch()
        card.add_layout(row3)

        self.body_layout.addWidget(card)
        self._mode_seg.sync(app_store.mode)
        self._theme_seg.sync(app_store.theme)

    def _pick_mode(self, mode: str):
        if mode == app_store.mode:
            return
        app_store.set_appearance(mode=mode)
        self._mode_seg.sync(mode)
        self._persist_appearance()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().apply_theme()

    def _pick_theme(self, theme: str):
        if theme == app_store.theme:
            return
        app_store.set_appearance(theme=theme)
        self._theme_seg.sync(theme)
        self._persist_appearance()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().apply_theme()

    def _pick_compact(self, on: bool):
        if app_store.compact == bool(on):
            return
        app_store.set_appearance(compact=bool(on))
        self._persist_appearance()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().apply_theme()

    def _persist_appearance(self):
        run_async(lambda: api.user_update_me({"preferredTheme": app_store.theme}),
                  on_err=lambda _m: None)  # 本地已生效，静默失败

    # ================= 3. 语言 =================
    def _build_language(self):
        card = Card()
        head = QLabel("语言")
        head.setProperty("role", "subtitle")
        card.add(head)
        row = QHBoxLayout()
        lab = QLabel("界面语言")
        lab.setProperty("role", "muted")
        row.addWidget(lab)
        self.locale_combo = QComboBox()
        for code, name in LOCALES:
            self.locale_combo.addItem(name, code)
        self.locale_combo.currentIndexChanged.connect(self._pick_locale)
        row.addWidget(self.locale_combo)
        row.addStretch()
        card.add_layout(row)
        self.body_layout.addWidget(card)

    def _pick_locale(self, _i: int):
        if self._filling:
            return
        code = self.locale_combo.currentData()
        if not code:
            return
        run_async(lambda: api.user_update_me({"preferredLocale": code}),
                  on_ok=lambda _r: _toast("语言偏好已保存", "success"))

    # ================= 4. 数据 =================
    def _build_data(self):
        card = Card()
        head = QLabel("数据管理")
        head.setProperty("role", "subtitle")
        card.add(head)
        row = QHBoxLayout()
        self.export_btn = QPushButton("导出全量数据")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self._export)
        self.import_btn = QPushButton("导入数据（JSON）")
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.clicked.connect(self._import)
        row.addWidget(self.export_btn)
        row.addWidget(self.import_btn)
        row.addStretch()
        card.add_layout(row)
        hint = QLabel("导出包含所有目标、KR、记录、任务、复盘等数据。导入时可选跳过或覆盖已存在的记录。")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        card.add(hint)
        self.body_layout.addWidget(card)

    def _export(self):
        self.export_btn.setEnabled(False)
        w = run_async(api.data_export, on_ok=self._export_ok)
        w.signals.finished.connect(lambda: self.export_btn.setEnabled(True))

    def _export_ok(self, resp):
        from PySide6.QtWidgets import QFileDialog
        today = datetime.date.today().strftime("%Y-%m-%d")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出数据", "vis-okr-export-%s.json" % today, "JSON 文件 (*.json)")
        if not path:
            return
        try:
            content = getattr(resp, "content", None)
            if content is None:
                content = json.dumps(resp, ensure_ascii=False).encode("utf-8")
            with open(path, "wb") as f:
                f.write(content)
            _toast("导出成功", "success")
        except OSError as e:
            _toast("导出失败：%s" % e, "error")

    def _import(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "导入数据", "", "JSON 文件 (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError) as e:
            _toast("文件解析失败：%s" % e, "error")
            return
        dlg = QMessageBox(self)
        dlg.setWindowTitle("导入数据")
        dlg.setText("检测到同名数据时如何处理？")
        skip = dlg.addButton("跳过", QMessageBox.AcceptRole)
        over = dlg.addButton("覆盖", QMessageBox.AcceptRole)
        cancel = dlg.addButton("取消", QMessageBox.RejectRole)
        dlg.exec()
        clicked = dlg.clickedButton()
        if clicked is cancel or clicked is None:
            return
        conflict = "overwrite" if clicked is over else "skip"
        self.import_btn.setEnabled(False)
        w = run_async(lambda: api.data_import(payload, conflict), on_ok=self._import_ok)
        w.signals.finished.connect(lambda: self.import_btn.setEnabled(True))

    def _import_ok(self, _result):
        _toast("导入成功", "success")
        self.refresh()

    # ================= 5. 账号 =================
    def _build_account(self):
        card = Card()
        head = QLabel("账号")
        head.setProperty("role", "subtitle")
        card.add(head)
        row = QHBoxLayout()
        out = QPushButton("退出登录")
        out.setProperty("preset", "danger")
        out.setCursor(Qt.PointingHandCursor)
        out.clicked.connect(self._logout)
        row.addWidget(out)
        row.addStretch()
        card.add_layout(row)
        self.body_layout.addWidget(card)

    def _logout(self):
        ret = QMessageBox.question(self, "退出登录", "确定退出当前账号吗？",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            auth.logout()  # shell 监听 auth.changed 自动回到登录页
