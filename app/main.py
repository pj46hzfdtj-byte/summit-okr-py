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
        self.glance = None
        self.tray = None
        # QApplication 就绪后再导入：state / pages 在模块级使用 QSettings 与注册表
        from .state import app as app_store
        from .ui import pages as _pages  # noqa: F401  触发页面注册
        self.app_store = app_store
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._raise_existing)
        self._server.listen("summitokr-py-desktop")
        # 悬浮窗快捷键（仅应用有焦点时生效——PySide6 无系统级全局热键，已知差异）
        from PySide6.QtGui import QKeySequence, QShortcut
        self._shortcut = QShortcut(QKeySequence("Ctrl+Alt+W"), self)
        self._shortcut.setContext(Qt.ApplicationShortcut)
        self._shortcut.activated.connect(self.toggle_widget)

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

    # ---------- 悬浮速览窗 ----------
    def toggle_widget(self):
        """显示/隐藏迷你悬浮总览窗（懒创建）。"""
        if self.glance is None:
            from .ui.glance import GlanceWidget
            self.glance = GlanceWidget()
            self.glance.clicked.connect(self._widget_navigate)
        if self.glance.isVisible():
            self.glance.hide()
        else:
            self.glance.show()
            self.glance.raise_()

    def _widget_navigate(self, route: str):
        """悬浮窗点击路由：唤起主窗口并直达对应页面。"""
        from .state import auth
        if not auth.is_authed:
            self.show_auth()
            return
        if self.shell is None:
            self.show_shell()
        w = self.shell
        if w.isMinimized():
            w.showNormal()
        w.raise_()
        w.activateWindow()
        if route.startswith("/objectives/"):
            w.open_objective(route.rsplit("/", 1)[-1])
        else:
            w.navigate(route)

    def show_main(self):
        """托盘「显示主窗口」。"""
        from .state import auth
        if self.shell:
            if self.shell.isMinimized():
                self.shell.showNormal()
            self.shell.raise_()
            self.shell.activateWindow()
        elif auth.is_authed:
            self.show_shell()
        else:
            self.show_auth()


def main():
    a = App(sys.argv)
    a.apply_theme()
    from .core.http import http
    from .state import auth
    from .ui.tray import SummitTray
    a.tray = SummitTray(a)
    http.set_session_expired_handler(a._on_session_expired)
    auth.initialize()  # 加载持久化 token 并异步验证会话
    if auth.is_authed:
        a.show_shell()
    else:
        a.show_auth()
    sys.exit(a.exec())


if __name__ == "__main__":
    main()
