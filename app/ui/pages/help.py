"""帮助与反馈：静态帮助内容 + 意见反馈表单。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card
from ...core import api
from ...core.worker import run_async

ABOUT_INTRO = (
    "本项目是一款基于 OKR（目标与关键结果）方法论的个人目标管理应用，完整复刻了 VIS OKR 的核心功能。"
    "通过多层级目标体系、关键结果量化、专注周期聚焦、日历任务落地、定期复盘评分五大模块，"
    "帮助你将远大愿景拆解为可执行的每日行动。内置 AI 助手可智能规划目标、拆解任务、建议评分与动机，"
    "让目标管理更高效。"
)
FLOW = ["设定目标", "拆解关键结果", "专注周期执行", "日历任务落地", "复盘评分改进"]

QUICK_START = [
    "注册账号或登录，进入「摘要」页查看目标概览与今日任务。",
    "在「目标库」创建根节点与子节点，构建多层级目标体系。",
    "在节点下创建目标，添加 KR（4 种取值方式）与记录推动进度。",
    "使用「专注周期」聚焦当期目标，设置权重与自定义周期时间。",
    "在「任务日历」规划每日任务，支持 5 种重复规则与目标关联。",
    "定期在「复盘」创建期中/期末复盘，给 KR 评分并总结。",
    "使用「AI 助手」规划目标、拆解任务、获取评分与动机建议。",
    "在「愿景」定义长期目标，在「甘特图」查看进度与滞后判定。",
]

FEATURES = [
    ("目标库", "多层级树形结构，颜色标记，级联删除"),
    ("关键结果 KR", "累计/最终/平均/最大 4 种取值 + 自定义公式，权重与最少记录数"),
    ("专注周期", "全局唯一活跃周期，目标权重，周期得分，自定义起止时间"),
    ("日历任务", "月历视图，5 种重复规则，目标关联与贡献说明，批量管理"),
    ("复盘记录", "期中版本化 + 期末自动完成目标，KR 评分，70 分健康哲学"),
    ("AI 助手", "规划目标、拆解任务、复盘评分、动机建议，对话历史，日 50 次限额"),
    ("甘特图", "进度可视化，今日红线，滞后判定，按周期或全部过滤"),
    ("愿景", "定义长期人生愿景，年龄段标签管理"),
    ("数据管理", "全量 JSON 导出/导入，跳过或覆盖策略"),
    ("个性化", "5 套主题，紧凑模式，4 种语言，外观日间/夜间/跟随系统"),
]

FAQ = [
    ("如何重置密码？", "当前版本请通过下方反馈表单联系管理员重置密码。"),
    ("数据可以导出吗？", "可以。前往「我的」→ 数据管理，导出 JSON 全量数据（含目标、KR、记录、任务、复盘等），导入时可选跳过或覆盖已存在的记录。"),
    ("支持哪些语言？", "简体中文、繁体中文、English、日本語。"),
    ("AI 助手如何配置？", "AI 助手基于 DeepSeek 模型。未配置 API Key 时自动进入 Mock 模式（返回示例数据），配置后调用真实 AI。每日限额 50 次。"),
    ("KR 的 4 种取值方式有什么区别？", "累计（所有记录求和）、最终（取最后一条记录值）、平均（所有记录平均）、最大（取最大值）。另有自定义公式可编写表达式计算。"),
    ("专注周期是什么？", "专注周期是全局唯一的时间窗口，让你聚焦当期最重要的目标。周期得分 = Σ(目标得分 × 权重) × 100。"),
    ("期中复盘和期末复盘有什么区别？", "期中复盘可在目标进行中多次创建（自动版本化）。期末复盘在目标结束时创建，会自动将目标状态推进为「已完成」。"),
    ("删除的数据能找回吗？", "可以。删除的目标、关键结果和任务进入「回收站」，保留 30 天，可随时恢复。"),
]

FEEDBACK_TYPES = [("bug", "问题反馈"), ("suggestion", "功能建议"), ("other", "其他")]


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "vis_toast", None)
    if t:
        t.show_msg(str(msg), kind)


def _section_card(title: str) -> Card:
    card = Card()
    head = QLabel(title)
    head.setProperty("role", "subtitle")
    card.add(head)
    return card


@register_page("/help")
class HelpPage(Page):
    path = "/help"

    def __init__(self, shell):
        super().__init__(shell)

        title = QLabel("帮助与反馈")
        title.setProperty("role", "title")
        self.body_layout.addWidget(title)
        sub = QLabel("了解所有功能，提交反馈建议")
        sub.setProperty("role", "muted")
        self.body_layout.addWidget(sub)

        self._build_about()
        self._build_quick_start()
        self._build_features()
        self._build_faq()
        self._build_feedback()
        self.body_layout.addStretch(1)

    # ------------------------------------------------------------------
    def _build_about(self):
        card = _section_card("关于本项目")
        intro = QLabel(ABOUT_INTRO)
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        card.add(intro)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(28)
        for num, label in (("10+", "功能模块"), ("50+", "API 端点"),
                           ("4", "界面语言"), ("AI", "智能助手")):
            col = QVBoxLayout()
            col.setSpacing(2)
            n = QLabel(num)
            n.setProperty("role", "kpi")
            n.setAlignment(Qt.AlignCenter)
            c = QLabel(label)
            c.setProperty("role", "muted")
            c.setAlignment(Qt.AlignCenter)
            col.addWidget(n)
            col.addWidget(c)
            stats_row.addLayout(col)
        stats_row.addStretch()
        card.add_layout(stats_row)

        flow_row = QHBoxLayout()
        flow_row.setSpacing(6)
        for i, step in enumerate(FLOW):
            if i > 0:
                arrow = QLabel("→")
                arrow.setProperty("role", "muted")
                flow_row.addWidget(arrow)
            pill = QLabel(step)
            pill.setAlignment(Qt.AlignCenter)
            pill.setStyleSheet(
                "background:#409EFF;color:white;border-radius:13px;padding:5px 14px;"
                "font-size:12px;font-weight:600;")
            flow_row.addWidget(pill)
        flow_row.addStretch()
        card.add_layout(flow_row)
        self.body_layout.addWidget(card)

    def _build_quick_start(self):
        card = _section_card("快速上手")
        for i, text in enumerate(QUICK_START, 1):
            row = QHBoxLayout()
            row.setSpacing(10)
            num = QLabel(str(i))
            num.setFixedSize(22, 22)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(
                "background:#409EFF;color:white;border-radius:11px;"
                "font-weight:700;font-size:12px;")
            row.addWidget(num, 0, Qt.AlignTop)
            lab = QLabel(text)
            lab.setWordWrap(True)
            row.addWidget(lab, 1)
            card.add_layout(row)
        self.body_layout.addWidget(card)

    def _build_features(self):
        card = _section_card("功能总览")
        grid = QVBoxLayout()
        grid.setSpacing(8)
        for name, desc in FEATURES:
            block = Card(flat=True, padding=10)
            n = QLabel(name)
            n.setProperty("role", "subtitle")
            d = QLabel(desc)
            d.setProperty("role", "muted")
            d.setWordWrap(True)
            block.add(n)
            block.add(d)
            grid.addWidget(block)
        card.add_layout(grid)
        self.body_layout.addWidget(card)

    def _build_faq(self):
        card = _section_card("常见问题")
        for q, a in FAQ:
            qq = QLabel("Q：%s" % q)
            qq.setProperty("role", "subtitle")
            qq.setWordWrap(True)
            aa = QLabel("A：%s" % a)
            aa.setProperty("role", "muted")
            aa.setWordWrap(True)
            card.add(qq)
            card.add(aa)
        self.body_layout.addWidget(card)

    # ------------------------------------------------------------------
    def _build_feedback(self):
        card = _section_card("意见反馈")

        lab = QLabel("反馈类型")
        lab.setProperty("role", "muted")
        card.add(lab)
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self._type_group = QButtonGroup()
        self._type_group.setExclusive(True)
        for i, (val, label) in enumerate(FEEDBACK_TYPES):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("preset", "primary" if i == 0 else "ghost")
            self._type_group.addButton(b, i)
            type_row.addWidget(b)
        type_row.addStretch()
        card.add_layout(type_row)
        self._type_group.idClicked.connect(self._pick_type)

        clab = QLabel("反馈内容")
        clab.setProperty("role", "muted")
        card.add(clab)
        self.content = QPlainTextEdit()
        self.content.setPlaceholderText("请详细描述你的问题或建议（不少于 10 字）")
        self.content.setFixedHeight(120)
        card.add(self.content)

        cont_lab = QLabel("联系方式")
        cont_lab.setProperty("role", "muted")
        card.add(cont_lab)
        self.contact = QLineEdit()
        self.contact.setPlaceholderText("邮箱或其他联系方式（可选）")
        self.contact.setMaximumWidth(320)
        card.add(self.contact)

        btns = QHBoxLayout()
        self.submit_btn = QPushButton("提交反馈")
        self.submit_btn.setProperty("preset", "primary")
        self.submit_btn.setCursor(Qt.PointingHandCursor)
        self.submit_btn.clicked.connect(self._submit)
        btns.addWidget(self.submit_btn)
        btns.addStretch()
        card.add_layout(btns)
        self.body_layout.addWidget(card)

    def _pick_type(self, idx: int):
        for i, btn in enumerate(self._type_group.buttons()):
            btn.setProperty("preset", "primary" if i == idx else "ghost")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _current_type(self) -> str:
        idx = self._type_group.checkedId()
        if 0 <= idx < len(FEEDBACK_TYPES):
            return FEEDBACK_TYPES[idx][0]
        return "bug"

    def _submit(self):
        content = self.content.toPlainText().strip()
        if len(content) < 10:
            _toast("请填写反馈内容（不少于 10 字）", "warn")
            return
        dto = {"type": self._current_type(), "content": content}
        contact = self.contact.text().strip()
        if contact:
            dto["contact"] = contact
        self.submit_btn.setEnabled(False)
        w = run_async(lambda: api.feedback_create(dto), on_ok=self._submitted)
        w.signals.finished.connect(lambda: self.submit_btn.setEnabled(True))

    def _submitted(self, _result):
        _toast("感谢你的反馈，我们已收到！", "success")
        self.content.clear()
        self.contact.clear()

    def refresh(self):
        pass
