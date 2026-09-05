"""应用状态：认证 + 外观（主题/模式），供全局读取。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, QSettings, Signal

from .core import api
from .core.http import tokens


class AuthStore(QObject):
    changed = Signal()
    user_changed = Signal()

    def __init__(self):
        super().__init__()
        self.user: Optional[dict] = None
        self._inited = False

    def initialize(self):
        """在 QApplication（含组织名）就绪后调用：加载 token 并验证会话。"""
        if self._inited:
            return
        self._inited = True
        tokens.load()
        if tokens.access:
            # 有 token：异步拉 profile 验证；失败则清 token 并通知（触发回到登录页）
            from .core.worker import run_async

            def _fail(_):
                tokens.clear()
                self.user = None
                self.changed.emit()

            run_async(api.auth_profile, on_ok=self._profile_ok, on_err=_fail)

    @property
    def is_authed(self) -> bool:
        return tokens.access is not None

    def _profile_ok(self, user):
        self.user = user
        self.user_changed.emit()
        self.changed.emit()

    def login(self, email: str, password: str):
        data = api.auth_login(email, password)
        tokens.set_tokens(data["accessToken"], data["refreshToken"])
        self.user = data["user"]
        self.changed.emit()
        self.user_changed.emit()
        return data

    def register(self, email: str, username: str, password: str):
        data = api.auth_register(email, username, password)
        tokens.set_tokens(data["accessToken"], data["refreshToken"])
        self.user = data["user"]
        self.changed.emit()
        self.user_changed.emit()
        return data

    def logout(self):
        tokens.clear()
        self.user = None
        self.changed.emit()


class AppStore(QObject):
    """外观：theme(light/blue/green/purple/macos) + mode(light/dark/system)。"""

    theme_changed = Signal()

    def __init__(self):
        super().__init__()
        s = QSettings()
        self.theme: str = s.value("ui/theme", "light") or "light"
        self.mode: str = s.value("ui/mode", "system") or "system"
        self.compact: bool = (s.value("ui/compact", "false") == "true")
        self.system_dark: bool = False

    def set_appearance(self, theme: Optional[str] = None, mode: Optional[str] = None,
                       compact: Optional[bool] = None):
        if theme is not None:
            self.theme = theme
        if mode is not None:
            self.mode = mode
        if compact is not None:
            self.compact = compact
        s = QSettings()
        s.setValue("ui/theme", self.theme)
        s.setValue("ui/mode", self.mode)
        s.setValue("ui/compact", "true" if self.compact else "false")
        self.theme_changed.emit()


auth = AuthStore()
app = AppStore()
