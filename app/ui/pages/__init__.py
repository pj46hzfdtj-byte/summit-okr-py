"""页面注册：优先导入真实页面模块；缺失的用占位页兜底。"""
from __future__ import annotations

import importlib

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from ..page_base import Page
from ..shell import PAGES, register_page

_PAGE_MODULES = [
    "summary", "goals", "goal_detail", "tasks", "gantt", "focus", "reviews",
    "ai", "visions", "profile", "recycle", "help", "notifications",
]

for mod in _PAGE_MODULES:
    try:
        importlib.import_module(f".{mod}", __package__)
    except ImportError as e:  # 页面尚未实现
        print(f"[pages] skip {mod}: {e}")

_PLACEHOLDERS = [
    "/summary", "/goal-groups", "/focus-cycle", "/tasks", "/gantt", "/reviews",
    "/ai-assistant", "/visions", "/recycle-bin", "/help", "/profile",
    "/objectives/detail", "/notifications",
]


def _make_placeholder(path: str):
    class Placeholder(Page):
        def __init__(self, shell):
            super().__init__(shell)
            lab = QLabel(f"{path} 页面开发中…")
            lab.setAlignment(Qt.AlignCenter)
            self.body_layout.addWidget(lab, 1)
    Placeholder.__name__ = "Page_" + path.strip("/").replace("/", "_").replace("-", "_")
    return Placeholder


for _p in _PLACEHOLDERS:
    if _p not in PAGES:
        register_page(_p)(_make_placeholder(_p))
