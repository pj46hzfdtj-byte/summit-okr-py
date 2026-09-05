"""设计系统：token（5 配色 × 日/夜外观）+ QSS 生成 + Aurora 背景绘制。

token 值与 react-desktop globals.css / Flutter theme.dart 对齐。
Qt 样式表颜色使用 #AARRGGBB（alpha 在前）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QLinearGradient, QRadialGradient, QPainter, QFont
from PySide6.QtWidgets import QWidget

THEMES = ["light", "blue", "green", "purple", "macos"]
MODES = ["light", "dark", "system"]

FONT_FAMILY = '"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif'


def _a(hex6: str, alpha: float) -> str:
    """#RRGGBB + alpha(0-1) -> #AARRGGBB"""
    return f"#{int(max(0.0, min(1.0, alpha)) * 255):02X}{hex6.lstrip('#')}"


@dataclass
class Tokens:
    theme: str
    mode: str  # 解析后的实际外观 light/dark
    radius: int = 12
    primary: str = "#409eff"
    primary_fg: str = "#FFFFFF"
    primary_soft: str = "#ECF5FF"
    bg: str = "#F5F7FA"
    fg: str = "#1F2329"
    card: str = "#FFFFFF"
    card_fg: str = "#1F2329"
    popover: str = "#FFFFFF"
    secondary: str = "#F0F2F5"
    secondary_fg: str = "#374151"
    muted: str = "#F3F4F6"
    muted_fg: str = "#6B7280"
    accent: str = "#ECF5FF"
    accent_fg: str = "#409EFF"
    destructive: str = "#F56C6C"
    success: str = "#67C23A"
    warning: str = "#E6A23C"
    border: str = "#E4E7ED"
    input: str = "#DCDFE6"
    sidebar: str = "#FFFFFF"
    sidebar_fg: str = "#4B5563"
    sidebar_active: str = "#ECF5FF"
    sidebar_active_fg: str = "#409EFF"
    aurora: bool = False          # 是否绘制极光壁纸
    glass_card: str = ""          # macOS 玻璃卡片底色（非空则启用）
    glass_border: str = ""
    hairline: str = "#0F000000"


def build_tokens(theme: str, mode: str, system_dark: bool = False) -> Tokens:
    """theme: light/blue/green/purple/macos；mode: light/dark/system。"""
    dark = mode == "dark" or (mode == "system" and system_dark)
    t = Tokens(theme=theme, mode="dark" if dark else "light")

    if dark:
        t.bg, t.fg, t.card, t.card_fg = "#141414", _a("#FFFFFF", 0.87), "#1D1E1F", _a("#FFFFFF", 0.87)
        t.popover, t.secondary, t.secondary_fg = "#262727", "#2B2C2E", _a("#FFFFFF", 0.8)
        t.muted, t.muted_fg = "#262727", _a("#FFFFFF", 0.55)
        t.border, t.input = _a("#FFFFFF", 0.12), _a("#FFFFFF", 0.15)
        t.sidebar, t.sidebar_fg = "#18181B", _a("#FFFFFF", 0.65)
        t.primary_fg = "#FFFFFF"
        t.hairline = _a("#FFFFFF", 0.08)
    else:
        t.bg, t.fg, t.card, t.card_fg = "#F5F7FA", "#1F2329", "#FFFFFF", "#1F2329"
        t.popover, t.secondary, t.secondary_fg = "#FFFFFF", "#F0F2F5", "#374151"
        t.muted, t.muted_fg = "#F3F4F6", "#6B7280"
        t.border, t.input = "#E4E7ED", "#DCDFE6"
        t.sidebar, t.sidebar_fg = "#FFFFFF", "#4B5563"
        t.hairline = _a("#000000", 0.06)

    # 配色主题
    if theme == "blue":
        t.primary = "#0A84FF" if dark else "#1A73E8"
        t.accent = t.sidebar_active = _a("#409EFF", 0.16) if dark else "#EAF3FB"
        t.accent_fg = t.sidebar_active_fg = "#79BBFF" if dark else "#1A73E8"
        t.primary_soft = t.accent
        if not dark:
            t.bg = "#F0F5FF"
    elif theme == "green":
        t.primary = "#4C9A50" if dark else "#2E7D32"
        t.accent = t.sidebar_active = _a("#2E7D32", 0.16) if dark else "#E9EFE2"
        t.accent_fg = t.sidebar_active_fg = "#8CC63F" if dark else "#2E7D32"
        t.primary_soft = t.accent
        if not dark:
            t.bg = "#F1F8F1"
    elif theme == "purple":
        t.primary = "#9D6BFF" if dark else "#7C3AED"
        t.accent = t.sidebar_active = _a("#7C3AED", 0.16) if dark else "#F3E8FE"
        t.accent_fg = t.sidebar_active_fg = "#C4A5FF" if dark else "#7C3AED"
        t.primary_soft = t.accent
        if not dark:
            t.bg = "#F5F0FB"
    elif theme == "macos":
        t.radius = 16
        t.aurora = True
        t.primary = "#0A84FF" if dark else "#007AFF"
        t.success = "#30D158" if dark else "#34C759"
        t.warning = "#FF9F0A"
        t.destructive = "#FF453A" if dark else "#FF3B30"
        t.accent = t.sidebar_active = _a("#0A84FF", 0.32) if dark else _a("#007AFF", 0.16)
        t.accent_fg = t.sidebar_active_fg = "#D6EAFF" if dark else "#004085"
        t.primary_soft = _a("#0A84FF", 0.18) if dark else "#E6F2FF"
        t.glass_card = ("linear-gradient(135deg, rgba(90,90,105,0.38), rgba(58,58,70,0.28))"
                        if dark else
                        "linear-gradient(135deg, rgba(255,255,255,0.72), rgba(255,255,255,0.52))")
        t.glass_border = _a("#FFFFFF", 0.10) if dark else _a("#FFFFFF", 0.60)
        if dark:
            t.fg = t.card_fg = _a("#FFFFFF", 0.87)
            t.muted_fg = _a("#FFFFFF", 0.55)
            t.border = _a("#FFFFFF", 0.12)
            t.hairline = _a("#FFFFFF", 0.10)
        else:
            t.fg = t.card_fg = _a("#000000", 0.85)
            t.muted_fg = _a("#000000", 0.5)
            t.border = _a("#000000", 0.08)
            t.hairline = _a("#000000", 0.07)
    else:  # light 基准（含夜间）
        t.primary = "#409EFF"
        t.accent = t.sidebar_active = _a("#409EFF", 0.16) if dark else "#ECF5FF"
        t.accent_fg = t.sidebar_active_fg = "#79BBFF" if dark else "#409EFF"
        t.primary_soft = t.accent

    return t


# ---------- Aurora 壁纸色值（与 globals.css 一致） ----------
def aurora_stops(dark: bool):
    if dark:
        base = [QColor("#15161C"), QColor("#191622"), QColor("#14191D")]
        spots = [
            (0.08, -0.06, "#1E50B4", 0.45),
            (0.92, 0.12, "#8C3CA0", 0.35),
            (0.70, 1.05, "#146E78", 0.32),
            (0.22, 0.88, "#965A28", 0.25),
        ]
    else:
        base = [QColor("#EEF3FB"), QColor("#F3EEF8"), QColor("#EEF6F6")]
        spots = [
            (0.08, -0.06, "#78AAFF", 0.50),
            (0.92, 0.12, "#FFBEE6", 0.42),
            (0.70, 1.05, "#A0E6DC", 0.40),
            (0.22, 0.88, "#FFDCAA", 0.35),
        ]
    return base, spots


def paint_aurora(p: QPainter, rect: QRectF, dark: bool):
    """在 rect 上绘制 Aurora 渐变壁纸。"""
    p.save()
    w, h = rect.width(), rect.height()
    grad = QLinearGradient(rect.topLeft(), QPointF(rect.right(), rect.bottom() * 0.3))
    base, spots = aurora_stops(dark)
    grad.setColorAt(0.0, base[0]); grad.setColorAt(0.45, base[1]); grad.setColorAt(1.0, base[2])
    p.fillRect(rect, grad)
    for fx, fy, hexc, alpha in spots:
        center = QPointF(rect.left() + fx * w, rect.top() + fy * h)
        r = max(w, h) * 0.55
        rg = QRadialGradient(center, r)
        c = QColor(hexc); c.setAlphaF(alpha)
        c0 = QColor(c); c0.setAlphaF(0.0)
        rg.setColorAt(0.0, c); rg.setColorAt(1.0, c0)
        p.fillRect(rect, rg)
    p.restore()


class AuroraMixin:
    """为 QWidget 子类提供 aurora 背景绘制；非 macOS 时填纯色 bg。"""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        t = self.window().property("vis_tokens") if self.window() else None
        if t is not None and getattr(t, "aurora", False):
            paint_aurora(p, rect, t.mode == "dark")
        elif t is not None:
            p.fillRect(rect, QColor(t.bg))
        else:
            p.fillRect(rect, QColor("#F5F7FA"))
        p.end()


def build_qss(t: Tokens) -> str:
    """全局 QSS：由 tokens 生成。"""
    rad = t.radius
    rad_sm = max(4, rad - 4)
    card_bg = "#1E2026" if (t.theme == "macos" and t.mode == "dark") else (
        "#FFFFFF" if t.theme == "macos" else t.card)
    return f"""
* {{ font-family: {FONT_FAMILY}; font-size: 14px; color: {t.fg}; outline: none; }}
QWidget#AuroraRoot {{ background: transparent; }}
QMainWindow, QDialog {{ background: {'transparent' if t.aurora else t.bg}; }}

QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 20px; font-weight: 700; }}
QLabel[role="subtitle"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {t.muted_fg}; font-size: 12px; }}
QLabel[role="kpi"] {{ font-size: 26px; font-weight: 700; color: {t.primary}; }}

/* 卡片 */
QFrame[card="true"] {{
  background: {card_bg};
  border: 1px solid {t.glass_border if t.theme == 'macos' else t.border};
  border-radius: {rad}px;
}}
QFrame[card="flat"] {{
  background: {t.secondary};
  border: none;
  border-radius: {rad_sm}px;
}}

/* 输入 */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
  background: {t.card if not t.aurora else card_bg};
  border: 1px solid {t.input};
  border-radius: {rad_sm}px;
  padding: 7px 10px;
  color: {t.fg};
  selection-background-color: {_a(t.primary, 0.9)};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{
  border: 1px solid {t.primary};
}}
QDateEdit, QDateTimeEdit {{ min-width: 110px; }}
QDateTimeEdit {{ min-width: 150px; }}
QLineEdit:disabled, QComboBox:disabled {{ background: {t.muted}; color: {t.muted_fg}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
  background: {t.popover if not t.aurora else card_bg};
  border: 1px solid {t.border};
  border-radius: {rad_sm}px;
  selection-background-color: {t.accent};
  selection-color: {t.accent_fg};
  padding: 4px;
}}

/* 按钮 */
QPushButton {{
  background: {t.secondary};
  color: {t.secondary_fg};
  border: 1px solid {t.border};
  border-radius: {rad_sm}px;
  padding: 7px 14px;
  font-weight: 500;
}}
QPushButton:hover {{ background: {t.muted}; }}
QPushButton:pressed {{ background: {t.border}; }}
QPushButton:disabled {{ color: {t.muted_fg}; background: {t.muted}; border-color: {t.border}; }}
QPushButton[preset="primary"] {{
  background: {t.primary}; color: {t.primary_fg}; border: none; font-weight: 600;
}}
QPushButton[preset="primary"]:hover {{ background: {t.accent_fg if t.mode=='dark' else t.primary}; }}
QPushButton[preset="primary"]:disabled {{ background: {t.muted}; color: {t.muted_fg}; }}
QPushButton[preset="danger"] {{ background: {t.destructive}; color: #FFFFFF; border: none; }}
QPushButton[preset="ghost"] {{ background: transparent; border: none; color: {t.primary}; }}
QPushButton[preset="ghost"]:hover {{ background: {t.accent}; }}

/* 侧边栏 */
QListWidget#Sidebar {{
  background: transparent; border: none; padding: 8px;
}}
QListWidget#Sidebar::item {{
  color: {t.sidebar_fg};
  border-radius: {rad_sm}px;
  padding: 10px 12px;
  margin: 2px 0;
}}
QListWidget#Sidebar::item:selected {{
  background: {t.sidebar_active}; color: {t.sidebar_active_fg}; font-weight: 600;
}}
QListWidget#Sidebar::item:hover {{ background: {t.hairline}; }}
QListWidget#Sidebar::item:selected:hover {{ background: {t.sidebar_active}; }}

/* 顶栏 */
QFrame#TopBar {{
  background: {'transparent' if t.aurora else t.card};
  border-bottom: 1px solid {t.hairline};
}}
QLabel#PageTitle {{ font-size: 17px; font-weight: 700; }}

/* 进度条 */
QProgressBar {{
  background: {t.muted};
  border: none;
  border-radius: 5px;
  height: 10px;
  text-align: right;
  color: {t.muted_fg};
  font-size: 11px;
}}
QProgressBar::chunk {{ background: {t.primary}; border-radius: 5px; }}

/* 标签 chip */
QLabel[chip="true"] {{
  background: {t.accent}; color: {t.accent_fg};
  border-radius: 9px; padding: 2px 10px; font-size: 12px; font-weight: 500;
}}
QLabel[chip="success"] {{ background: {_a(t.success, 0.15)}; color: {t.success}; }}
QLabel[chip="warning"] {{ background: {_a(t.warning, 0.15)}; color: {t.warning}; }}
QLabel[chip="danger"] {{ background: {_a(t.destructive, 0.15)}; color: {t.destructive}; }}

/* Tab */
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
  background: transparent; color: {t.muted_fg};
  padding: 8px 16px; border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {t.primary}; border-bottom: 2px solid {t.primary}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {t.fg}; }}

/* 列表/表格 */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView {{
  background: transparent; border: none;
}}
QTreeWidget::item, QTableWidget::item, QListWidget::item {{
  padding: 6px; border-radius: 6px;
}}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
  background: {t.accent}; color: {t.accent_fg};
}}
QHeaderView::section {{
  background: transparent; border: none; color: {t.muted_fg};
  padding: 6px; font-weight: 600; font-size: 12px;
}}

/* 滚动条 */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.muted_fg}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 4px; min-width: 30px; }}

/* 对话框 / 菜单 / 提示 */
QDialog {{ background: {t.popover if not t.aurora else card_bg}; }}
QMenu {{
  background: {t.popover if not t.aurora else card_bg};
  border: 1px solid {t.border}; border-radius: {rad_sm}px; padding: 6px;
}}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.accent}; color: {t.accent_fg}; }}
QToolTip {{
  background: {t.popover}; color: {t.fg};
  border: 1px solid {t.border}; border-radius: 6px; padding: 5px 8px;
}}

/* 复选/单选 */
QRadioButton, QCheckBox {{ spacing: 8px; background: transparent; }}
QRadioButton::indicator, QCheckBox::indicator {{
  width: 16px; height: 16px; border-radius: 4px;
  border: 1px solid {t.input}; background: {t.card};
}}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
  background: {t.primary}; border: 1px solid {t.primary};
}}

/* 滑块 */
QSlider::groove:horizontal {{ height: 4px; background: {t.muted}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.primary}; border-radius: 2px; }}
QSlider::handle:horizontal {{
  width: 16px; height: 16px; margin: -6px 0;
  background: {t.card}; border: 1px solid {t.border}; border-radius: 8px;
}}

/* 分组 */
QGroupBox {{
  border: 1px solid {t.border}; border-radius: {rad}px;
  margin-top: 10px; padding-top: 8px; font-weight: 600; background: transparent;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {t.muted_fg}; }}

/* 分割线 */
QFrame[sep="true"] {{ background: {t.border}; max-height: 1px; border: none; }}
"""
