"""目标库：GoalGroup 树（QTreeWidget）+ 节点 CRUD + 快速进入目标详情。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..page_base import Page
from ..shell import register_page
from ..widgets import Card, Chip, EmptyState
from ...core import api
from ...core.worker import run_async

PRESET_COLORS = ["#409EFF", "#1E40AF", "#67C23A", "#F56C6C",
                 "#E6A23C", "#7C3AED", "#0EA5E9", "#EC4899"]


def _toast(msg: str, kind: str = "info"):
    from PySide6.QtWidgets import QApplication
    t = getattr(QApplication.instance(), "summit_toast", None)
    if t:
        t.show_msg(msg, kind)


def _valid_color(s, default="#409EFF"):
    c = QColor(s or "")
    return c.name() if c.isValid() and (s or "").strip() else default


def _dot(color: str, size: int = 10) -> QLabel:
    d = QLabel()
    d.setFixedSize(size, size)
    d.setStyleSheet("background:%s;border-radius:%dpx;" % (_valid_color(color), size // 2))
    return d


def _mini_btn(text: str, preset: str = "ghost") -> QPushButton:
    b = QPushButton(text)
    b.setProperty("preset", preset)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet("padding:2px 8px;font-size:12px;")
    return b


class _Row(QWidget):
    """树行容器：整行可点击 / 双击。"""
    clicked = Signal()
    double_clicked = Signal()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(e)


class _ColorPicker(QWidget):
    """预设色板 + hex 输入。"""

    def __init__(self, parent=None, color: str = "#409EFF"):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._hex = QLineEdit(_valid_color(color))
        self._hex.setFixedWidth(90)
        self._swatches = []
        for c in PRESET_COLORS:
            b = QPushButton()
            b.setFixedSize(20, 20)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:%s;border:2px solid transparent;border-radius:5px;}"
                "QPushButton:checked{border:2px solid #1F2329;}" % c)
            b.clicked.connect(lambda _=False, cc=c: self._pick(cc))
            self._swatches.append((b, c))
            lay.addWidget(b)
        lay.addWidget(self._hex)
        lay.addStretch()
        self._hex.textChanged.connect(self._sync_swatch)
        self._sync_swatch(self._hex.text())

    def _pick(self, c: str):
        self._hex.setText(c)

    def _sync_swatch(self, text: str):
        norm = _valid_color(text, "").lower()
        for b, c in self._swatches:
            b.setChecked(c.lower() == norm and bool(norm))

    def color(self) -> str:
        return _valid_color(self._hex.text())


class _NodeDialog(QDialog):
    """节点创建 / 编辑对话框。

    mode:
      - create_root : 新建根节点（可选关联愿景）
      - create_child: 在指定父节点下新建
      - edit        : 编辑现有节点（根节点可改愿景关联）
    """

    def __init__(self, parent, title: str, node: dict = None, parent_node: dict = None,
                 visions: list = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        visions = visions or []
        is_root_ctx = (node is None and parent_node is None) or (node is not None and not node.get("parentId"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        if parent_node is not None:
            row = QHBoxLayout()
            row.addWidget(QLabel("父节点："))
            row.addWidget(_dot(parent_node.get("color") or "#409EFF", 8))
            lab = QLabel(parent_node.get("name") or "")
            lab.setProperty("role", "subtitle")
            row.addWidget(lab)
            row.addStretch()
            lay.addLayout(row)

        form = QVBoxLayout()
        form.setSpacing(4)
        lab = QLabel("名称 *")
        lab.setProperty("role", "muted")
        form.addWidget(lab)
        self.name_edit = QLineEdit((node or {}).get("name") or "")
        self.name_edit.setPlaceholderText("如：技术提升")
        form.addWidget(self.name_edit)
        lay.addLayout(form)

        if is_root_ctx:
            form2 = QVBoxLayout()
            form2.setSpacing(4)
            lab2 = QLabel("所属愿景")
            lab2.setProperty("role", "muted")
            form2.addWidget(lab2)
            self.vision_combo = QComboBox()
            self.vision_combo.addItem("（不关联）", None)
            cur_vid = (node or {}).get("visionId")
            for v in visions:
                self.vision_combo.addItem((v.get("content") or "")[:24], v.get("id"))
            if cur_vid:
                idx = self.vision_combo.findData(cur_vid)
                if idx >= 0:
                    self.vision_combo.setCurrentIndex(idx)
            form2.addWidget(self.vision_combo)
            lay.addLayout(form2)
        else:
            self.vision_combo = None

        form3 = QVBoxLayout()
        form3.setSpacing(4)
        lab3 = QLabel("颜色")
        lab3.setProperty("role", "muted")
        form3.addWidget(lab3)
        self.color_picker = _ColorPicker(color=(node or {}).get("color") or "#1E40AF")
        form3.addWidget(self.color_picker)
        lay.addLayout(form3)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setProperty("preset", "primary")
        ok.clicked.connect(self._on_ok)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        self.name_edit.returnPressed.connect(self._on_ok)

    def _on_ok(self):
        if not self.name_edit.text().strip():
            _toast("请输入节点名称", "warn")
            return
        self.accept()

    def values(self):
        return {
            "name": self.name_edit.text().strip(),
            "color": self.color_picker.color(),
            "visionId": self.vision_combo.currentData() if self.vision_combo else None,
        }


@register_page("/goal-groups")
class GoalGroupsPage(Page):
    path = "/goal-groups"

    def __init__(self, shell):
        super().__init__(shell)
        self._visions: list = []
        self._loading = False

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        title = QLabel("目标库")
        title.setProperty("role", "title")
        hl.addWidget(title)
        hl.addStretch()
        self.btn_new = QPushButton("＋ 新建节点")
        self.btn_new.setProperty("preset", "primary")
        self.btn_new.clicked.connect(self._create_root)
        hl.addWidget(self.btn_new)
        self.body_layout.addWidget(header)

        card = Card()
        self.tree = QTreeWidget()
        self.tree.setColumnCount(1)
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.empty = EmptyState("还没有目标节点，点击右上角「新建节点」开始规划")
        self.empty.hide()
        card.add(self.tree, 1)
        card.add(self.empty)
        self.body_layout.addWidget(card, 1)

    # ---------- 数据加载 ----------
    def refresh(self):
        if self._loading:
            return
        self._loading = True
        run_async(lambda: (api.goal_group_tree(True), api.vision_list()),
                  on_ok=self._apply, on_err=self._load_err)

    def _load_err(self, msg: str):
        self._loading = False
        _toast(msg, "error")

    def _apply(self, result):
        self._loading = False
        tree, visions = result
        self._visions = visions or []
        self.tree.clear()
        nodes = tree or []
        if not nodes:
            self.tree.hide()
            self.empty.show()
            return
        self.empty.hide()
        self.tree.show()
        for node in nodes:
            self._add_group(self.tree.invisibleRootItem(), node)
        self.tree.expandAll()

    # ---------- 树构建 ----------
    def _add_group(self, parent_item: QTreeWidgetItem, node: dict):
        item = QTreeWidgetItem(parent_item)
        self.tree.setItemWidget(item, 0, self._group_row(node))
        for child in node.get("children") or []:
            self._add_group(item, child)
        for obj in node.get("objectives") or []:
            oi = QTreeWidgetItem(item)
            self.tree.setItemWidget(oi, 0, self._objective_row(obj))

    def _group_row(self, node: dict) -> QWidget:
        row = _Row()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(8)
        lay.addWidget(_dot(node.get("color") or "#409EFF", 10))
        name = QLabel(node.get("name") or "")
        if not node.get("parentId"):
            name.setStyleSheet("font-weight:700;")
        lay.addWidget(name)
        vision = node.get("vision")
        if node.get("visionId") or vision:
            vtxt = ""
            if isinstance(vision, dict):
                vtxt = (vision.get("content") or "")[:12]
            lay.addWidget(Chip("愿景·" + (vtxt or str(node.get("visionId"))[:8]), "warning"))
        objs = node.get("objectives") or []
        if objs:
            lay.addWidget(Chip(str(len(objs)), "true"))
        lay.addStretch()

        b_child = _mini_btn("＋子节点")
        b_child.clicked.connect(lambda: self._create_child(node))
        lay.addWidget(b_child)
        b_obj = _mini_btn("＋目标")
        b_obj.clicked.connect(lambda: self._quick_create_objective(node))
        lay.addWidget(b_obj)
        b_edit = _mini_btn("编辑")
        b_edit.clicked.connect(lambda: self._edit_node(node))
        lay.addWidget(b_edit)
        b_del = _mini_btn("删除")
        b_del.setStyleSheet("padding:2px 8px;font-size:12px;color:#F56C6C;")
        b_del.clicked.connect(lambda: self._delete_node(node))
        lay.addWidget(b_del)

        row.double_clicked.connect(lambda: self._edit_node(node))
        if objs:
            row.clicked.connect(lambda: self.shell.open_objective(objs[0].get("id")))
        return row

    def _objective_row(self, obj: dict) -> QWidget:
        row = _Row()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(8)
        lay.addWidget(_dot(obj.get("color") or "#409EFF", 8))
        t = QLabel(obj.get("title") or "")
        t.setProperty("role", "muted")
        t.setStyleSheet("font-size:13px;")
        lay.addWidget(t)
        lay.addStretch()
        oid = obj.get("id")
        if oid:
            row.clicked.connect(lambda: self.shell.open_objective(oid))
        return row

    # ---------- CRUD ----------
    def _create_root(self):
        dlg = _NodeDialog(self, "新建根节点", visions=self._visions)
        if dlg.exec() == QDialog.Accepted:
            v = dlg.values()
            run_async(lambda: api.goal_group_create(
                {"parentId": None, "name": v["name"], "color": v["color"],
                 "visionId": v["visionId"]}),
                on_ok=self._saved("创建成功"))

    def _create_child(self, node: dict):
        dlg = _NodeDialog(self, "新建子节点", parent_node=node)
        if dlg.exec() == QDialog.Accepted:
            v = dlg.values()
            pid = node.get("id")
            run_async(lambda: api.goal_group_create(
                {"parentId": pid, "name": v["name"], "color": v["color"]}),
                on_ok=self._saved("创建成功"))

    def _edit_node(self, node: dict):
        dlg = _NodeDialog(self, "编辑节点", node=node, visions=self._visions)
        if dlg.exec() == QDialog.Accepted:
            v = dlg.values()
            gid = node.get("id")
            dto = {"name": v["name"], "color": v["color"]}
            if not node.get("parentId"):
                dto["visionId"] = v["visionId"]
            run_async(lambda: api.goal_group_update(gid, dto),
                      on_ok=self._saved("更新成功"))

    def _delete_node(self, node: dict):
        ret = QMessageBox.question(
            self, "危险操作",
            "确定删除节点「%s」吗？其子节点与目标将一并移除。" % (node.get("name") or ""),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        gid = node.get("id")
        run_async(lambda: api.goal_group_delete(gid), on_ok=self._saved("删除成功"))

    def _quick_create_objective(self, node: dict):
        dlg = _NodeDialog(self, "新建目标 · " + (node.get("name") or ""),
                          parent_node=node)
        dlg.name_edit.setPlaceholderText("目标标题")
        if dlg.exec() == QDialog.Accepted:
            v = dlg.values()
            gid = node.get("id")
            run_async(lambda: api.objective_create(
                {"goalGroupId": gid, "title": v["name"], "color": v["color"]}),
                on_ok=self._obj_created)

    def _obj_created(self, obj):
        _toast("目标创建成功", "success")
        self.refresh()
        if isinstance(obj, dict) and obj.get("id"):
            self.shell.open_objective(obj["id"])

    def _saved(self, msg: str):
        def _cb(_result):
            _toast(msg, "success")
            self.refresh()
        return _cb
