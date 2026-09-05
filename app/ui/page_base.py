"""页面基类：滚动容器 + 刷新钩子 + toast 快捷方法。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


class Page(QScrollArea):
    """所有业务页继承本类；子类把内容控件加入 self.body_layout。"""

    path = ""

    def __init__(self, shell: QWidget):
        super().__init__()
        self.shell = shell
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._root = QWidget()
        self._root.setObjectName("PageRoot")
        self.body_layout = QVBoxLayout(self._root)
        self.body_layout.setContentsMargins(24, 24, 24, 24)
        self.body_layout.setSpacing(16)
        self.setWidget(self._root)

    def refresh(self):  # 子类覆写
        pass

    def clear_body(self):
        while self.body_layout.count():
            it = self.body_layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()

    def toast(self):
        app = self.window().window() if self.window() else None
        from PySide6.QtWidgets import QApplication
        return getattr(QApplication.instance(), "vis_toast", None)
