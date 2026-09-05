"""登录 / 注册页：Aurora 背景 + 居中玻璃卡片（对齐 Flutter/Android auth_page）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from ..config import DEMO_EMAIL, DEMO_PASSWORD
from ..core.worker import run_async
from ..state import auth
from .aurora import AuroraWidget
from .widgets import Card


class AuthDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VIS OKR - 登录")
        self.setModal(True)
        self.resize(460, 640)
        self._register = False

        # 让子控件（AuroraWidget）能解析到当前主题 token
        from PySide6.QtWidgets import QApplication
        app_inst = QApplication.instance()
        dark = getattr(getattr(app_inst, "app_store", None), "system_dark", False)
        theme = getattr(getattr(app_inst, "app_store", None), "theme", "light")
        mode = getattr(getattr(app_inst, "app_store", None), "mode", "system")
        from .theme import build_tokens
        self.setProperty("vis_tokens", build_tokens(theme, mode, dark))

        root = AuroraWidget()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(root)

        col = QVBoxLayout(root)
        col.setAlignment(Qt.AlignCenter)
        col.setContentsMargins(36, 36, 36, 36)

        brand = QLabel("\u2691  VIS OKR")
        brand.setAlignment(Qt.AlignCenter)
        brand.setStyleSheet("font-size:24px;font-weight:800;")
        col.addWidget(brand)
        slogan = QLabel("让每一个目标，都被认真达成")
        slogan.setAlignment(Qt.AlignCenter)
        slogan.setProperty("role", "muted")
        col.addWidget(slogan)
        col.addSpacing(20)

        card = Card(padding=22)
        self.email = QLineEdit(DEMO_EMAIL)
        self.email.setPlaceholderText("you@example.com")
        self.username = QLineEdit()
        self.username.setPlaceholderText("你的昵称")
        self.username.setVisible(False)
        self.password = QLineEdit(DEMO_PASSWORD)
        self.password.setEchoMode(QLineEdit.Password)
        for lbl, w in (("邮箱", self.email), ("用户名", self.username), ("密码", self.password)):
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 0, 0, 0)
            lab = QLabel(lbl)
            lab.setFixedWidth(48)
            lab.setProperty("role", "muted")
            row.addWidget(lab)
            row.addWidget(w, 1)
            if w is self.username:
                row_w.setVisible(False)
                self._user_row = row_w
            card.add(row_w)

        self.submit = QPushButton("登录")
        self.submit.setProperty("preset", "primary")
        self.submit.setMinimumHeight(42)
        self.submit.clicked.connect(self._submit)
        card.add(self.submit)

        toggle_row = QHBoxLayout()
        toggle_row.setAlignment(Qt.AlignCenter)
        self.toggle_hint = QLabel("还没有账号？")
        self.toggle_hint.setProperty("role", "muted")
        self.toggle_btn = QPushButton("注册")
        self.toggle_btn.setProperty("preset", "ghost")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle)
        toggle_row.addWidget(self.toggle_hint)
        toggle_row.addWidget(self.toggle_btn)
        card.add_layout(toggle_row)

        tip = QLabel("演示账号 demo@visokr.com / password123")
        tip.setAlignment(Qt.AlignCenter)
        tip.setProperty("role", "muted")
        card.add(tip)
        col.addWidget(card)

        self.error_lbl = QLabel("")
        self.error_lbl.setAlignment(Qt.AlignCenter)
        self.error_lbl.setStyleSheet("color:#F56C6C;")
        col.addWidget(self.error_lbl)

    def _toggle(self):
        self._register = not self._register
        self._user_row.setVisible(self._register)
        self.submit.setText("注册" if self._register else "登录")
        self.toggle_hint.setText("已有账号？" if self._register else "还没有账号？")
        self.toggle_btn.setText("登录" if self._register else "注册")

    def _submit(self):
        email = self.email.text().strip()
        pwd = self.password.text()
        if not email or not pwd:
            self.error_lbl.setText("请填写邮箱和密码")
            return
        if self._register and not self.username.text().strip():
            self.error_lbl.setText("请填写用户名")
            return
        self.submit.setEnabled(False)
        self.submit.setText("请稍候…")
        username = self.username.text().strip()
        if self._register:
            fn = lambda: auth.register(email, username, pwd)  # noqa: E731
        else:
            fn = lambda: auth.login(email, pwd)  # noqa: E731

        def ok(_):
            self.accept()

        def err(msg):
            self.error_lbl.setText(msg)
            self.submit.setEnabled(True)
            self.submit.setText("注册" if self._register else "登录")

        run_async(fn, on_ok=ok, on_err=err)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._submit()
        else:
            super().keyPressEvent(e)
