"""主窗口外壳：全宽顶栏（折叠+logo+铃铛+用户chip）+ 240px 可折叠侧栏 + 页面栈。

布局与 web-vue MainLayout.vue 对齐：
  topbar 56px（traffic-lights / collapse-btn / logo-mark+logo-text / bell / user-chip）
  body-area = sidebar 240（折叠 64）+ app-content
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from ..state import auth
from .aurora import AuroraWidget
from .nav_items import NAV_ITEMS

# 页面注册表：path -> factory(window) -> Page
PAGES: dict[str, object] = {}

SIDEBAR_W = 240
SIDEBAR_COLLAPSED_W = 64


def register_page(path: str):
    def deco(factory):
        PAGES[path] = factory
        return factory
    return deco


def _icon(key: str, color: str) -> QIcon:
    from .icons import make_icon
    return make_icon(key, color)


class Shell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VIS OKR")
        self.resize(1280, 800)
        self.setMinimumSize(960, 620)
        self._collapsed = False

        root = AuroraWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- 全宽顶栏（Vue .topbar：56px） ----
        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(56)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(16, 0, 16, 0)
        tb.setSpacing(10)

        # 装饰性 traffic lights（与 Vue 一致）
        for cls, col in (("close", "#FF5F57"), ("min", "#FEBC2E"), ("max", "#28C840")):
            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet("background:%s;border-radius:6px;" % col)
            tb.addWidget(dot)
        tb.addSpacing(6)

        self.collapse_btn = QToolButton()
        self.collapse_btn.setText("\u2261")  # ≡
        self.collapse_btn.setFixedSize(36, 36)
        self.collapse_btn.setAutoRaise(True)
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.clicked.connect(self._toggle_sidebar)
        tb.addWidget(self.collapse_btn)

        self.logo_mark = QLabel("O")
        self.logo_mark.setFixedSize(28, 28)
        self.logo_mark.setAlignment(Qt.AlignCenter)
        tb.addWidget(self.logo_mark)
        self.logo_text = QLabel("VIS OKR")
        tb.addWidget(self.logo_text)
        tb.addStretch()

        self.bell = QToolButton()
        self.bell.setIcon(self._bell_icon("#606266"))
        self.bell.setFixedSize(36, 36)
        self.bell.setAutoRaise(True)
        self.bell.setCursor(Qt.PointingHandCursor)
        self.bell.clicked.connect(self._open_notifications)
        tb.addWidget(self.bell)

        # 用户 chip（Vue .user-chip：头像 + 用户名 + 下拉菜单）
        self.user_btn = QToolButton()
        self.user_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.user_btn.setAutoRaise(True)
        self.user_btn.setCursor(Qt.PointingHandCursor)
        self.user_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.user_btn)
        menu.addAction("我的", lambda: self.navigate("/profile"))
        menu.addAction("退出登录", self._logout)
        self.user_btn.setMenu(menu)
        self.avatar = QLabel()
        self.avatar.setFixedSize(28, 28)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.user_btn.setIcon(self._avatar_icon())
        self.user_btn.setText(" ")
        tb.addWidget(self.user_btn)

        outer.addWidget(topbar)

        # ---- body：侧栏 + 内容 ----
        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("SidebarPanel")
        self.sidebar.setFixedWidth(SIDEBAR_W)
        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(8, 8, 8, 8)
        sb_lay.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("Sidebar")
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setFrameShape(QListWidget.NoFrame)
        for path, label, glyph in NAV_ITEMS:
            it = QListWidgetItem(_icon(glyph, "#606266"), label)
            it.setData(Qt.UserRole, path)
            it.setData(Qt.UserRole + 1, glyph)
            it.setToolTip(label)
            self.nav.addItem(it)
        self.nav.currentRowChanged.connect(self._on_nav)
        sb_lay.addWidget(self.nav, 1)
        body_lay.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        body_lay.addWidget(self.stack, 1)
        outer.addWidget(body, 1)

        # ---- 页面（先按导航顺序入栈，保证 row==stack index；隐藏页追加在后） ----
        self.pages: dict[str, QWidget] = {}
        ordered = [p for p, _, _ in NAV_ITEMS if p in PAGES]
        ordered += [p for p in PAGES if p not in ordered]
        for path in ordered:
            page = PAGES[path](self)
            self.pages[path] = page
            self.stack.addWidget(page)

        auth.changed.connect(self._sync_user)
        self._sync_user()
        self.nav.setCurrentRow(0)

    # ---------- 主题联动 ----------
    def _tokens(self):
        return self.property("vis_tokens")

    def on_theme_changed(self):
        """apply_theme 后调用：用当前 tokens 刷新动态配色部件。"""
        t = self._tokens()
        if t is None:
            return
        self.logo_mark.setStyleSheet(
            "background:%s;color:#FFFFFF;border-radius:6px;"
            "font-family:%s;font-size:16px;font-weight:800;" % (t.primary, "Consolas"))
        self.logo_text.setStyleSheet(
            "font-size:15px;font-weight:700;letter-spacing:-0.3px;color:%s;" % t.fg)
        self.user_btn.setStyleSheet("QToolButton{background:transparent;border:none;color:%s;font-weight:500;}" % t.fg)
        self.user_btn.setIcon(self._avatar_icon())
        self.collapse_btn.setIcon(self._menu_icon(t.secondary_fg))
        self.collapse_btn.setStyleSheet(
            "QToolButton{background:transparent;border:none;font-size:18px;border-radius:6px;}"
            "QToolButton:hover{background:%s;}" % t.hairline)
        self.bell.setIcon(self._bell_icon(t.secondary_fg))
        self.bell.setStyleSheet(
            "QToolButton{background:transparent;border:none;font-size:16px;border-radius:6px;}"
            "QToolButton:hover{background:%s;}" % t.hairline)
        self._refresh_nav_icons()

    def _refresh_nav_icons(self):
        t = self._tokens()
        if t is None:
            return
        cur = self.nav.currentRow()
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            glyph = it.data(Qt.UserRole + 1)
            color = t.sidebar_active_fg if i == cur else t.sidebar_fg
            it.setIcon(_icon(glyph, color))

    @staticmethod
    def _menu_icon(color: str) -> QIcon:
        pm = QPixmap(18, 18)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        pen = QPen(QColor(color))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        for y in (4, 9, 14):
            p.drawLine(3, y, 15, y)
        p.end()
        return QIcon(pm)

    @staticmethod
    def _bell_icon(color: str) -> QIcon:
        pm = QPixmap(18, 18)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(color))
        pen.setWidthF(1.5)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(3.5, 3, 11, 11), 0, 180 * 16)
        p.drawLine(3, 8, 3, 12)
        p.drawLine(15, 8, 15, 12)
        p.drawLine(2, 12, 16, 12)
        p.drawArc(QRectF(7, 12.5, 4, 4), 180 * 16, 180 * 16)
        p.end()
        return QIcon(pm)

    def _avatar_icon(self) -> QIcon:
        t = self._tokens()
        primary = getattr(t, "primary", "#1E40AF")
        pm = QPixmap(28, 28)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(primary))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 28, 28)
        p.setPen(QColor("#FFFFFF"))
        f = QFont("Segoe UI", 10)
        f.setBold(True)
        p.setFont(f)
        ch = "?"
        if auth.user:
            ch = (auth.user.get("username") or "?")[0].upper()
        p.drawText(pm.rect(), Qt.AlignCenter, ch)
        p.end()
        return QIcon(pm)

    # ---------- 交互 ----------
    def _toggle_sidebar(self):
        self._collapsed = not self._collapsed
        self.sidebar.setFixedWidth(SIDEBAR_COLLAPSED_W if self._collapsed else SIDEBAR_W)
        self.logo_text.setVisible(not self._collapsed)
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            label = NAV_ITEMS[i][1]
            it.setText("" if self._collapsed else label)

    def _sync_user(self):
        if auth.user:
            self.user_btn.setText(auth.user.get("username", ""))
            self.user_btn.setIcon(self._avatar_icon())

    def _logout(self):
        if QMessageBox.question(self, "提示", "确定退出登录吗？") == QMessageBox.Yes:
            auth.logout()

    def _on_nav(self, row: int):
        if row < 0:
            return
        path, _label, _ = NAV_ITEMS[row]
        self.stack.setCurrentIndex(row)
        self._refresh_nav_icons()
        page = self.pages.get(path)
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    def navigate(self, path: str):
        """跨页跳转（如目标库 → 详情）。"""
        for i, (p, _label, _) in enumerate(NAV_ITEMS):
            if p == path:
                self.nav.setCurrentRow(i)
                return True
        return False

    def open_objective(self, objective_id: str):
        page = self.pages.get("/objectives/detail")
        if page is not None and hasattr(page, "open_objective"):
            self.stack.setCurrentWidget(page)
            page.open_objective(objective_id)

    def _open_notifications(self):
        page = self.pages.get("/notifications")
        if page is not None:
            self.stack.setCurrentWidget(page)
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
