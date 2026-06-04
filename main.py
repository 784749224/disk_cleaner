"""C 盘清理辅助工具 - 主程序。"""
import os
import shutil
import sys
from typing import List

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QProgressBar, QPlainTextEdit, QSpinBox, QLineEdit,
    QFileDialog, QAbstractItemView, QStatusBar, QSplitter, QProgressDialog,
)

from cleaner import build_clean_items, human_size, CleanItem
from file_info import get_info, RISK_COLORS, RISK_LABELS
from workers import (
    ScanCleanItemsThread, CleanThread, LargeFileScanThread,
    SoftwareLoadThread, AnalyzeDirThread, DeletePathThread,
    is_admin, open_in_explorer, run_uninstall,
)


# ----------------- 清理标签页 -----------------
class CleanTab(QWidget):
    def __init__(self):
        super().__init__()
        self.items: List[CleanItem] = build_clean_items()
        self.checkboxes: List[QCheckBox] = []
        self._scan_thread = None
        self._clean_thread = None
        self._total_freed = 0  # 程序运行期间累计释放字节
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        # 顶部按钮
        top = QHBoxLayout()
        self.btn_scan = QPushButton("扫描占用")
        self.btn_clean = QPushButton("清理已勾选")
        self.btn_clean.setEnabled(False)
        self.btn_select_safe = QPushButton("仅选安全项")
        self.btn_select_none = QPushButton("全不选")
        for b in (self.btn_scan, self.btn_clean, self.btn_select_safe, self.btn_select_none):
            top.addWidget(b)
        top.addStretch()
        self.lbl_total = QLabel("总计可清理: -")
        self.lbl_total.setStyleSheet("font-weight:bold;color:#2563eb;")
        top.addWidget(self.lbl_total)
        sep = QLabel(" | ")
        sep.setStyleSheet("color:#999;")
        top.addWidget(sep)
        self.lbl_freed = QLabel("累计已释放: 0 B")
        self.lbl_freed.setStyleSheet("font-weight:bold;color:#16a34a;")
        top.addWidget(self.lbl_freed)
        layout.addLayout(top)

        # 表格
        self.table = QTableWidget(len(self.items), 5)
        self.table.setHorizontalHeaderLabels(["选择", "项目", "占用", "风险", "说明"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.Stretch)

        for i, it in enumerate(self.items):
            cb = QCheckBox()
            cb.setChecked(it.risk == "safe")
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.addWidget(cb)
            wl.setAlignment(Qt.AlignCenter)
            wl.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(i, 0, wrap)
            self.checkboxes.append(cb)

            self.table.setItem(i, 1, QTableWidgetItem(it.name))
            self.table.setItem(i, 2, QTableWidgetItem("-"))
            risk_item = QTableWidgetItem("安全" if it.risk == "safe" else "谨慎")
            if it.risk != "safe":
                risk_item.setForeground(Qt.red)
            self.table.setItem(i, 3, risk_item)
            self.table.setItem(i, 4, QTableWidgetItem(it.desc))

        layout.addWidget(self.table)

        # 进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.lbl_status = QLabel("提示：先点【扫描占用】查看每项大小，再勾选清理。")
        self.lbl_status.setStyleSheet("color:#555;")
        layout.addWidget(self.lbl_status)

        # 信号
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_clean.clicked.connect(self.start_clean)
        self.btn_select_safe.clicked.connect(self._select_safe)
        self.btn_select_none.clicked.connect(self._select_none)

    # --- 选择工具 ---
    def _select_safe(self):
        for cb, it in zip(self.checkboxes, self.items):
            cb.setChecked(it.risk == "safe")

    def _select_none(self):
        for cb in self.checkboxes:
            cb.setChecked(False)

    # --- 扫描 ---
    def start_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self.btn_scan.setEnabled(False)
        self.btn_clean.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(self.items))
        self.progress.setValue(0)
        self._sizes = [0] * len(self.items)
        self.lbl_total.setText("总计可清理: -")
        self.lbl_total.setStyleSheet("font-weight:bold;color:#2563eb;")
        self.lbl_status.setText("扫描中...")

        self._scan_thread = ScanCleanItemsThread(self.items)
        self._scan_thread.item_done.connect(self._on_item_size)
        self._scan_thread.progress.connect(lambda p: self.lbl_status.setText(f"扫描: {p}"))
        self._scan_thread.finished_all.connect(self._scan_done)
        self._scan_thread.start()

    def _on_item_size(self, idx: int, size: int):
        self._sizes[idx] = size
        self.table.setItem(idx, 2, QTableWidgetItem(human_size(size)))
        self.progress.setValue(self.progress.value() + 1)

    def _scan_done(self):
        total = sum(self._sizes)
        self.lbl_total.setText(f"总计可清理: {human_size(total)}")
        self.btn_scan.setEnabled(True)
        self.btn_clean.setEnabled(True)
        self.progress.setVisible(False)
        self.lbl_status.setText("扫描完成。")

    # --- 清理 ---
    def start_clean(self):
        chosen = [it for cb, it in zip(self.checkboxes, self.items) if cb.isChecked()]
        if not chosen:
            QMessageBox.information(self, "提示", "请先勾选要清理的项目。")
            return
        cautions = [it.name for it in chosen if it.risk != "safe"]
        msg = f"确认要清理以下 {len(chosen)} 项吗？\n\n" + "\n".join(f"· {it.name}" for it in chosen)
        if cautions:
            msg += "\n\n⚠ 谨慎项: " + ", ".join(cautions)
        if QMessageBox.question(self, "确认清理", msg,
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self.btn_scan.setEnabled(False)
        self.btn_clean.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # 不确定进度
        self.lbl_status.setText("清理中...")

        self._clean_thread = CleanThread(chosen)
        self._clean_thread.item_done.connect(self._on_clean_item_done)
        self._clean_thread.log.connect(lambda s: self.lbl_status.setText(s[:120]))
        self._clean_thread.finished_all.connect(self._clean_done)
        self._clean_thread.start()

    def _on_clean_item_done(self, name: str, freed: int, deleted: int, failed: int):
        for i, it in enumerate(self.items):
            if it.name == name:
                self.table.setItem(i, 2, QTableWidgetItem(f"已清 {human_size(freed)}"))
                break

    def _clean_done(self, freed: int, deleted: int, failed: int):
        self.btn_scan.setEnabled(True)
        self.btn_clean.setEnabled(True)
        self.progress.setVisible(False)
        self._total_freed += freed
        self.lbl_total.setText(f"本次释放: {human_size(freed)}")
        self.lbl_total.setStyleSheet("font-weight:bold;color:#16a34a;")
        self.lbl_freed.setText(f"累计已释放: {human_size(self._total_freed)}")
        self.lbl_status.setText(f"完成: 释放 {human_size(freed)}, 删除 {deleted} 项, 失败 {failed} 项")
        # 通知主窗口更新状态栏
        win = self.window()
        if hasattr(win, 'on_freed'):
            win.on_freed(freed)
        QMessageBox.information(
            self, "清理完成",
            f"本次释放空间: {human_size(freed)}\n累计已释放: {human_size(self._total_freed)}\n"
            f"删除项目: {deleted}\n失败: {failed}\n\n"
            f"失败通常是文件被占用，可重启后再试或以管理员身份运行。"
        )


# ----------------- 大文件标签页 -----------------
class LargeFileTab(QWidget):
    def __init__(self):
        super().__init__()
        self._thread = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("扫描目录:"))
        self.edit_root = QLineEdit("C:\\")
        top.addWidget(self.edit_root)
        self.btn_browse = QPushButton("...")
        self.btn_browse.setMaximumWidth(40)
        self.btn_browse.clicked.connect(self._pick_dir)
        top.addWidget(self.btn_browse)

        top.addWidget(QLabel("最小大小 (MB):"))
        self.spin_size = QSpinBox()
        self.spin_size.setRange(10, 100000)
        self.spin_size.setValue(100)
        top.addWidget(self.spin_size)

        self.btn_scan = QPushButton("开始扫描")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        top.addWidget(self.btn_scan)
        top.addWidget(self.btn_stop)
        layout.addLayout(top)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["大小", "路径"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemDoubleClicked.connect(self._open_selected)
        layout.addWidget(self.table)

        bot = QHBoxLayout()
        self.btn_locate = QPushButton("在资源管理器中定位")
        self.btn_delete = QPushButton("删除选中文件")
        self.btn_delete.setStyleSheet("color:#b00;")
        bot.addWidget(self.btn_locate)
        bot.addWidget(self.btn_delete)
        bot.addStretch()
        self.lbl_status = QLabel("提示：双击行可在资源管理器中定位。删除前请确认文件用途！")
        bot.addWidget(self.lbl_status)
        layout.addLayout(bot)

        self.btn_scan.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_locate.clicked.connect(self._open_selected)
        self.btn_delete.clicked.connect(self._delete_selected)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择扫描目录", self.edit_root.text())
        if d:
            self.edit_root.setText(d.replace("/", "\\"))

    def _start(self):
        if self._thread and self._thread.isRunning():
            return
        self.table.setRowCount(0)
        self.btn_scan.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_status.setText("扫描中...")
        self._thread = LargeFileScanThread(self.edit_root.text(), self.spin_size.value())
        self._thread.progress.connect(lambda p: self.lbl_status.setText(f"扫描: {p[:80]}"))
        self._thread.finished_with.connect(self._done)
        self._thread.start()

    def _stop(self):
        if self._thread:
            self._thread.stop()
        self.lbl_status.setText("正在停止...")

    def _done(self, results):
        self.table.setRowCount(len(results))
        for i, (path, size) in enumerate(results):
            self.table.setItem(i, 0, QTableWidgetItem(human_size(size)))
            self.table.setItem(i, 1, QTableWidgetItem(path))
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(f"完成: 共 {len(results)} 个文件")

    def _selected_path(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        return item.text() if item else None

    def _open_selected(self):
        p = self._selected_path()
        if p:
            open_in_explorer(p)

    def _delete_selected(self):
        p = self._selected_path()
        if not p:
            return
        if QMessageBox.question(
            self, "确认删除",
            f"确定要删除该文件吗？此操作不可撤销！\n\n{p}",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        try:
            size = 0
            try:
                size = os.path.getsize(p) if os.path.isfile(p) else 0
            except OSError:
                pass
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
            row = self.table.currentRow()
            self.table.removeRow(row)
            self.lbl_status.setText(f"已删除 {human_size(size)}: {p}")
            win = self.window()
            if size and hasattr(win, 'on_freed'):
                win.on_freed(size)
        except OSError as e:
            QMessageBox.warning(self, "删除失败", str(e))


# ----------------- 空间分析标签页 -----------------
class SpaceAnalyzeTab(QWidget):
    def __init__(self):
        super().__init__()
        self._thread = None
        self._history: List[str] = []
        self._current_root = ""
        self._cache = {}  # {normalized_root: results_list}
        self._build_ui()

    @staticmethod
    def _norm(p: str) -> str:
        return os.path.normpath(p).lower()

    def _invalidate_cache(self, path: str):
        """删除某路径后，作废该路径自身缓存及其所有祖先路径的缓存。"""
        target = self._norm(path)
        keys = list(self._cache.keys())
        for k in keys:
            # k 是祖先（含等于）或 k 是后代，都失效
            if target.startswith(k) or k.startswith(target):
                self._cache.pop(k, None)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.btn_back = QPushButton("← 上一级")
        self.btn_back.setEnabled(False)
        top.addWidget(self.btn_back)
        top.addWidget(QLabel("当前目录:"))
        self.edit_root = QLineEdit("C:\\")
        top.addWidget(self.edit_root, 1)
        self.btn_browse = QPushButton("...")
        self.btn_browse.setMaximumWidth(40)
        top.addWidget(self.btn_browse)
        self.btn_scan = QPushButton("分析")
        self.btn_scan.setToolTip("强制重新扫描当前目录")
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setEnabled(False)
        top.addWidget(self.btn_scan)
        top.addWidget(self.btn_stop)
        layout.addLayout(top)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["类型", "名称", "大小", "占比", "文件数", "风险", "说明"]
        )
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 200)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemDoubleClicked.connect(self._on_double)
        layout.addWidget(self.table)

        bot = QHBoxLayout()
        self.btn_open = QPushButton("在资源管理器中打开")
        self.btn_delete = QPushButton("删除选中（危险）")
        self.btn_delete.setStyleSheet("color:#b00;")
        bot.addWidget(self.btn_open)
        bot.addWidget(self.btn_delete)
        bot.addStretch()
        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet("font-weight:bold;color:#2563eb;")
        bot.addWidget(self.lbl_total)
        layout.addLayout(bot)

        self.lbl_status = QLabel("提示: 双击文件夹可钻进去。大目录（如 C:\\）首次分析需要几分钟。")
        self.lbl_status.setStyleSheet("color:#555;")
        layout.addWidget(self.lbl_status)

        self.btn_scan.clicked.connect(lambda: self.analyze(self.edit_root.text(), force=True))
        self.btn_stop.clicked.connect(self._stop)
        self.btn_browse.clicked.connect(self._pick_dir)
        self.btn_back.clicked.connect(self._go_back)
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_delete.clicked.connect(self._delete_selected)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择目录", self.edit_root.text())
        if d:
            self.edit_root.setText(d.replace("/", "\\"))

    def analyze(self, root: str, push_history=True, force=False):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(
                self, "请稍候",
                "上一次分析尚未完成，请等扫描结束或点击【停止】后再试。"
            )
            return
        self._stopped = False  # 重置停止标志
        root = root.strip()
        if not root or not os.path.isdir(root):
            QMessageBox.warning(self, "提示", "目录不存在")
            return
        if push_history and self._current_root and root != self._current_root:
            self._history.append(self._current_root)
            self.btn_back.setEnabled(True)
        self._current_root = root
        self.edit_root.setText(root)

        # 命中缓存且非强制：直接渲染，不开线程
        cache_key = self._norm(root)
        if not force and cache_key in self._cache:
            results = self._cache[cache_key]
            self._render_rows(results, root, partial=False)
            self.lbl_status.setText(f"已加载缓存: {root}（点【分析】可重新扫描）")
            return

        self.table.setRowCount(0)
        self._items_buffer = []  # 缓存 (name, size, is_dir, count)
        self.btn_scan.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_total.setText("")
        self.lbl_status.setText(f"分析中: {root} ...")

        # 弹出 loading 对话框，阻止重复操作
        self._progress = QProgressDialog(
            f"正在分析: {root}\n\n大目录可能需要数十秒，请勿频繁切换。",
            "停止扫描", 0, 0, self,
        )
        self._progress.setWindowTitle("空间分析中...")
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setMinimumWidth(480)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.canceled.connect(self._stop)
        self._progress.show()

        self._thread = AnalyzeDirThread(root)
        self._thread.progress.connect(self._on_thread_progress)
        self._thread.item_ready.connect(self._on_item)
        self._thread.finished_with.connect(self._done)
        self._thread.start()

    def _on_thread_progress(self, path: str):
        short = path if len(path) <= 80 else "..." + path[-77:]
        self.lbl_status.setText(f"扫描: {short}")
        if hasattr(self, "_progress") and self._progress is not None:
            try:
                self._progress.setLabelText(
                    f"正在分析: {self._current_root}\n\n当前: {short}\n\n"
                    f"已发现 {len(self._items_buffer)} 项，请稍候..."
                )
            except RuntimeError:
                pass

    def _on_item(self, name: str, size: int, is_dir: bool, fcount: int):
        """每来一个一级子项就缓存，渲染节流到 300ms 一次，避免主线程被刷爆。"""
        if getattr(self, "_stopped", False):
            return
        self._items_buffer.append((name, size, is_dir, fcount))
        self._dirty = True
        if not getattr(self, "_render_timer_started", False):
            self._render_timer_started = True
            QTimer.singleShot(300, self._flush_render)

    def _flush_render(self):
        self._render_timer_started = False
        if getattr(self, "_stopped", False):
            return  # 已停止，不再 schedule
        if not getattr(self, "_dirty", False):
            return
        self._dirty = False
        self._items_buffer.sort(key=lambda x: x[1], reverse=True)
        self._render_rows(self._items_buffer, self._current_root, partial=True)
        # 如果扫描还在跑，约下一帧
        if self._thread and self._thread.isRunning():
            self._render_timer_started = True
            QTimer.singleShot(300, self._flush_render)

    def _stop(self):
        if getattr(self, "_stopped", False):
            return
        self._stopped = True  # 立即停止接收新数据
        if self._thread:
            self._thread.stop()
        # 立刻 finalize 当前已扫到的项作为最终结果
        if self._items_buffer:
            self._items_buffer.sort(key=lambda x: x[1], reverse=True)
            self._render_rows(self._items_buffer, self._current_root, partial=False)
        self.lbl_status.setText(f"已停止（部分结果，共 {len(self._items_buffer)} 项）")
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        # 关闭进度对话框
        if hasattr(self, "_progress") and self._progress is not None:
            try:
                self._progress.close()
            except RuntimeError:
                pass
            self._progress = None

    def _go_back(self):
        if not self._history:
            return
        prev = self._history.pop()
        if not self._history:
            self.btn_back.setEnabled(False)
        self.analyze(prev, push_history=False)

    def _render_rows(self, rows: list, root: str, partial: bool):
        total = sum(r[1] for r in rows)
        self.table.setRowCount(len(rows))
        for i, (name, size, is_dir, fcount) in enumerate(rows):
            full = os.path.join(root, name)
            risk, desc = get_info(full, name, is_dir)
            color = QColor(*RISK_COLORS.get(risk, (0, 0, 0)))

            type_item = QTableWidgetItem("📁" if is_dir else "📄")
            type_item.setData(Qt.UserRole, is_dir)
            self.table.setItem(i, 0, type_item)

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.UserRole, full)
            self.table.setItem(i, 1, name_item)

            size_item = QTableWidgetItem(human_size(size))
            size_item.setData(Qt.UserRole, size)
            self.table.setItem(i, 2, size_item)

            pct = (size / total * 100) if total else 0
            pct_item = QTableWidgetItem(f"{pct:.1f}%  {'█' * int(pct / 5)}")
            pct_item.setData(Qt.UserRole, pct)
            self.table.setItem(i, 3, pct_item)

            self.table.setItem(i, 4, QTableWidgetItem(str(fcount)))

            risk_item = QTableWidgetItem(RISK_LABELS.get(risk, "未知"))
            risk_item.setForeground(color)
            f = risk_item.font()
            f.setBold(True)
            risk_item.setFont(f)
            self.table.setItem(i, 5, risk_item)

            desc_item = QTableWidgetItem(desc)
            desc_item.setToolTip(desc)
            desc_item.setForeground(color)
            self.table.setItem(i, 6, desc_item)
        suffix = "（扫描中...）" if partial else f"（{len(rows)} 项）"
        self.lbl_total.setText(f"该目录合计: {human_size(total)} {suffix}")

    def _done(self, root: str, results: list):
        # 如果已停止则 _stop 已 finalize，这里只做清理
        if getattr(self, "_stopped", False):
            self.btn_scan.setEnabled(True)
            self.btn_stop.setEnabled(False)
            return
        # 正常完成：写入缓存
        self._cache[self._norm(root)] = results
        self._render_rows(results, root, partial=False)
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(f"完成: {root}")
        if hasattr(self, "_progress") and self._progress is not None:
            try:
                self._progress.close()
            except RuntimeError:
                pass
            self._progress = None

    def _selected(self):
        row = self.table.currentRow()
        if row < 0:
            return None, None, None
        path = self.table.item(row, 1).data(Qt.UserRole)
        is_dir = self.table.item(row, 0).data(Qt.UserRole)
        size = self.table.item(row, 2).data(Qt.UserRole) or 0
        return path, is_dir, size

    def _on_double(self, item):
        path, is_dir, _ = self._selected()
        if path and is_dir:
            self.analyze(path)
        elif path:
            open_in_explorer(path)

    def _open_selected(self):
        path, is_dir, _ = self._selected()
        if not path:
            return
        if is_dir and os.path.isdir(path):
            os.startfile(path)
        else:
            open_in_explorer(path)

    def _delete_selected(self):
        if hasattr(self, "_del_thread") and self._del_thread and self._del_thread.isRunning():
            QMessageBox.information(self, "提示", "已有删除任务正在进行中，请稍候...")
            return
        path, is_dir, size = self._selected()
        if not path:
            return
        warn = "文件夹及其全部内容" if is_dir else "文件"
        if QMessageBox.question(
            self, "确认删除",
            f"⚠ 将永久删除以下{warn}（不进回收站）：\n\n{path}\n\n大小: {human_size(size)}\n\n"
            f"大目录可能需要数十秒到数分钟，期间按钮会显示\"删除中...\"。继续？",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        self._del_row = self.table.currentRow()
        self.btn_delete.setEnabled(False)
        self.btn_delete.setText("删除中...")
        self.lbl_status.setText(f"删除中: {path}")
        self._del_thread = DeletePathThread(path, bool(is_dir))
        self._del_thread.progress.connect(lambda s: self.lbl_status.setText(s[:120]))
        self._del_thread.finished_with.connect(self._on_delete_done)
        self._del_thread.start()

    def _on_delete_done(self, path: str, ok: bool, freed: int, failed: int, err: str):
        self.btn_delete.setEnabled(True)
        self.btn_delete.setText("删除选中（危险）")
        if ok:
            # 失效自身及所有祖先缓存
            self._invalidate_cache(path)
            # 移除该行
            try:
                self.table.removeRow(self._del_row)
            except Exception:
                pass
            self.lbl_status.setText(
                f"已删除 {human_size(freed)}: {path}"
                + (f"  (失败 {failed} 个文件)" if failed else "")
            )
            win = self.window()
            if freed and hasattr(win, 'on_freed'):
                win.on_freed(freed)
            if failed:
                QMessageBox.information(
                    self, "部分完成",
                    f"已释放 {human_size(freed)}，但有 {failed} 个文件无法删除"
                    f"（通常是被占用或权限不足，可重启或以管理员身份再试）。"
                )
        else:
            self.lbl_status.setText(f"删除失败: {path}")
            QMessageBox.warning(self, "删除失败", err or "未知错误")


# ----------------- 软件管理标签页 -----------------
class SoftwareTab(QWidget):
    def __init__(self):
        super().__init__()
        self._thread = None
        self._apps = []
        self._build_ui()
        QTimer.singleShot(100, self.reload)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.btn_reload = QPushButton("刷新列表")
        self.chk_size = QCheckBox("计算实际安装目录大小（较慢）")
        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText("按名称/发布者筛选...")
        top.addWidget(self.btn_reload)
        top.addWidget(self.chk_size)
        top.addWidget(self.edit_filter, 1)
        layout.addLayout(top)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "版本", "发布者", "大小", "安装位置"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        bot = QHBoxLayout()
        self.btn_uninstall = QPushButton("卸载选中软件")
        self.btn_open = QPushButton("打开安装目录")
        self.lbl_status = QLabel()
        bot.addWidget(self.btn_uninstall)
        bot.addWidget(self.btn_open)
        bot.addStretch()
        bot.addWidget(self.lbl_status)
        layout.addLayout(bot)

        self.btn_reload.clicked.connect(self.reload)
        self.btn_uninstall.clicked.connect(self._uninstall)
        self.btn_open.clicked.connect(self._open)
        self.edit_filter.textChanged.connect(self._apply_filter)

    def reload(self):
        if self._thread and self._thread.isRunning():
            return
        self.btn_reload.setEnabled(False)
        self.lbl_status.setText("加载中...")
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._thread = SoftwareLoadThread(calc_size=self.chk_size.isChecked())
        self._thread.finished_with.connect(self._loaded)
        self._thread.start()

    def _loaded(self, apps):
        self._apps = apps
        self._apply_filter()
        self.btn_reload.setEnabled(True)
        self.lbl_status.setText(f"共 {len(apps)} 个软件")

    def _apply_filter(self):
        kw = self.edit_filter.text().strip().lower()
        self.table.setSortingEnabled(False)
        rows = [a for a in self._apps if not kw or kw in a["name"].lower()
                or kw in (a.get("publisher") or "").lower()]
        self.table.setRowCount(len(rows))
        for i, a in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(a["name"]))
            self.table.setItem(i, 1, QTableWidgetItem(a.get("version", "")))
            self.table.setItem(i, 2, QTableWidgetItem(a.get("publisher", "")))
            size_item = QTableWidgetItem(human_size(a.get("size_bytes") or 0)
                                         if a.get("size_bytes") else "-")
            size_item.setData(Qt.UserRole, a.get("size_bytes") or 0)
            self.table.setItem(i, 3, size_item)
            self.table.setItem(i, 4, QTableWidgetItem(a.get("install_location", "")))
            # 把整个 dict 挂在第 0 列
            self.table.item(i, 0).setData(Qt.UserRole, a)
        self.table.setSortingEnabled(True)

    def _selected_app(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _uninstall(self):
        a = self._selected_app()
        if not a:
            return
        cmd = a.get("uninstall") or a.get("quiet_uninstall")
        if not cmd:
            QMessageBox.warning(self, "提示", "未找到该软件的卸载命令。")
            return
        if QMessageBox.question(
            self, "确认卸载",
            f"将启动卸载程序:\n\n{a['name']}\n{cmd}\n\n继续?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        run_uninstall(cmd)

    def _open(self):
        a = self._selected_app()
        if a and a.get("install_location") and os.path.isdir(a["install_location"]):
            os.startfile(a["install_location"])
        else:
            QMessageBox.information(self, "提示", "未找到安装目录。")


# ----------------- 主窗口 -----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("C 盘清理助手")
        self.resize(1100, 700)
        self._global_freed = 0

        tabs = QTabWidget()
        self.tab_clean = CleanTab()
        self.tab_analyze = SpaceAnalyzeTab()
        self.tab_large = LargeFileTab()
        self.tab_soft = SoftwareTab()
        tabs.addTab(self.tab_clean, "安全清理")
        tabs.addTab(self.tab_analyze, "空间分析")
        tabs.addTab(self.tab_large, "大文件扫描")
        tabs.addTab(self.tab_soft, "已装软件")
        # 大文件删除也计入累计
        self.tab_large.freed_signal = lambda n: self.on_freed(n)
        self.setCentralWidget(tabs)

        self.sb = QStatusBar()
        admin_text = "管理员权限" if is_admin() else "普通用户权限（部分文件可能无法清理）"
        self._admin_text = admin_text
        self._refresh_status()
        self.setStatusBar(self.sb)

    def on_freed(self, n: int):
        self._global_freed += n
        self._refresh_status()

    def _refresh_status(self):
        from cleaner import human_size
        self.sb.showMessage(
            f"运行环境: {self._admin_text}    |    本次运行累计释放: {human_size(self._global_freed)}"
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
