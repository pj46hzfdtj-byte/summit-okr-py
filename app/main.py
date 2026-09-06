"""Summit OKR 桌面端（PySide6）入口。"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication

from PySide6.QtWidgets import QDialog

from .config import ORG_NAME, SETTINGS_APP, SETTINGS_ORG
from .ui.theme import build_qss, build_tokens


class App(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setOrganizationName(SETTINGS_ORG)
        self.setApplicationName(SETTINGS_APP)
        self.shell = None
        self.toast = None
        self.summit_toast = None
        # QApplication 就绪后再导入：state / pages 在模块级使用 QSettings 与注册表
        from .state import app as app_store
        from .ui import pages as _pages  # noqa: F401  触发页面注册
        self.app_store = app_store
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._raise_existing)
        self._server.listen("summitokr-py-desktop")

    # ---------- 主题 ----------
    @staticmethod
    def _system_dark() -> bool:
        """Windows 注册表判断系统是否为深色模式。"""
        try:
            s = QSettings("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize",
                          QSettings.NativeFormat)
            return int(s.value("AppsUseLightTheme", 1)) == 0
        except Exception:
            return False

    def apply_theme(self):
        from .state import app as app_store
        dark = self._system_dark()
        app_store.system_dark = dark
        tokens = build_tokens(app_store.theme, app_store.mode, dark)
        self.setStyleSheet(build_qss(tokens))
        if self.shell:
            self.shell.setProperty("summit_tokens", tokens)
            on_theme = getattr(self.shell, "on_theme_changed", None)
            if callable(on_theme):
                on_theme()
            self.shell.update()

    def _on_auth_changed(self):
        from .core.http import tokens
        from .state import auth
        if auth.user is None and not tokens.access:
            QTimer.singleShot(0, self.show_auth)

    def _raise_existing(self):
        sock = self._server.nextPendingConnection()
        if sock:
            sock.readAll()
            # 唤起当前可见的顶层窗口（主窗口或登录对话框）
            from PySide6.QtWidgets import QWidget
            for w in self.topLevelWidgets():
                if isinstance(w, QWidget) and w.isVisible():
                    if w.isMinimized():
                        w.showNormal()
                    w.raise_()
                    w.activateWindow()
                    break
            sock.disconnectFromServer()

    def _on_session_expired(self):
        QTimer.singleShot(0, self.show_auth)

    def show_auth(self):
        from .ui.auth_page import AuthDialog
        if self.shell:
            self.shell.hide()
            self.shell.deleteLater()
            self.shell = None
        dlg = AuthDialog()
        if dlg.exec() == QDialog.Accepted:
            self.show_shell()
        else:
            self.quit()

    def show_shell(self):
        from .state import auth
        from .ui.shell import Shell
        from .ui.widgets import Toast
        self.shell = Shell()
        self.apply_theme()
        self.toast = Toast(self.shell)
        self.summit_toast = self.toast
        auth.changed.connect(self._on_auth_changed)
        self.shell.show()


def main():
    a = App(sys.argv)
    a.apply_theme()
    from .core.http import http
    from .state import auth
    http.set_session_expired_handler(a._on_session_expired)
    auth.initialize()  # 加载持久化 token 并异步验证会话
    if auth.is_authed:
        a.show_shell()
    else:
        a.show_auth()
    sys.exit(a.exec())


if __name__ == "__main__":
    main()
