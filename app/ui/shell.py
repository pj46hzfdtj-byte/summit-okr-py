"""主窗口外壳：侧边栏导航 + 顶栏（通知铃铛）+ QStackedWidget 页面栈。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from ..state import auth
from .aurora import AuroraWidget
from .nav_items import NAV_ITEMS

# 页面注册表：path -> factory(window) -> Page
PAGES: dict[str, object] = {}


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

        root = AuroraWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- 侧边栏 ----
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(220)
        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(14, 18, 14, 14)
        sb_lay.setSpacing(10)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(self._logo_pixmap(34))
        name = QLabel("VIS OKR")
        name.setStyleSheet("font-size:16px;font-weight:800;")
        brand.addWidget(logo)
        brand.addSpacing(8)
        brand.addWidget(name)
        brand.addStretch()
        sb_lay.addLayout(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("Sidebar")
        self.nav.setIconSize(QSize(20, 20))
        for path, label, glyph in NAV_ITEMS:
            it = QListWidgetItem(_icon(glyph, "#4B5563"), label)
            it.setData(Qt.UserRole, path)
            self.nav.addItem(it)
        self.nav.currentRowChanged.connect(self._on_nav)
        sb_lay.addWidget(self.nav, 1)

        # 用户区
        user_row = QHBoxLayout()
        self.avatar = QLabel()
        self.avatar.setFixedSize(30, 30)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setStyleSheet("border-radius:15px;background:#409EFF;color:white;font-weight:700;")
        self.user_name = QLabel("")
        self.user_name.setStyleSheet("font-weight:600;")
        self.logout_btn = QToolButton()
        self.logout_btn.setText("退出")
        self.logout_btn.setAutoRaise(True)
        self.logout_btn.clicked.connect(self._logout)
        user_row.addWidget(self.avatar)
        user_row.addSpacing(6)
        user_row.addWidget(self.user_name, 1)
        user_row.addWidget(self.logout_btn)
        sb_lay.addLayout(user_row)

        outer.addWidget(self.sidebar)

        # ---- 右列：顶栏 + 栈 ----
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        topbar = QWidget()
        topbar.setObjectName("TopBar")
        topbar.setFixedHeight(52)
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(20, 0, 16, 0)
        self.page_title = QLabel("摘要")
        self.page_title.setObjectName("PageTitle")
        tb.addWidget(self.page_title)
        tb.addStretch()
        self.bell = QToolButton()
        self.bell.setText("\U0001F514")  # bell
        self.bell.setAutoRaise(True)
        self.bell.clicked.connect(self._open_notifications)
        tb.addWidget(self.bell)
        col.addWidget(topbar)

        self.stack = QStackedWidget()
        col.addWidget(self.stack, 1)
        outer.addLayout(col, 1)

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

    @staticmethod
    def _logo_pixmap(size: int) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        from PySide6.QtGui import QLinearGradient, QBrush
        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0, QColor("#3B82F6"))
        grad.setColorAt(1, QColor("#7C3AED"))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, size, size, size * 0.28, size * 0.28)
        p.setPen(QColor("white"))
        f = QFont("Segoe UI Symbol", int(size * 0.5))
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, "\u2691")  # ⚑
        p.end()
        return pm

    def _sync_user(self):
        if auth.user:
            u = auth.user
            self.user_name.setText(u.get("username", ""))
            self.avatar.setText((u.get("username") or "?")[0].upper())

    def _logout(self):
        auth.logout()

    def _on_nav(self, row: int):
        if row < 0:
            return
        path, label, _ = NAV_ITEMS[row]
        self.stack.setCurrentIndex(row)
        self.page_title.setText(label)
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
            self.page_title.setText("目标详情")
            page.open_objective(objective_id)

    def _open_notifications(self):
        page = self.pages.get("/notifications")
        if page is not None:
            self.stack.setCurrentWidget(page)
            self.page_title.setText("通知")
            refresh = getattr(page, "refresh", None)
            if callable(refresh):
                refresh()
