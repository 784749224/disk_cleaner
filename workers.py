"""后台线程，避免界面卡死。"""
import ctypes
import os
import shutil
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal

from cleaner import CleanItem, build_clean_items
from scanner import scan_large_files
from software import list_installed_software
from analyzer import analyze_dir


class ScanCleanItemsThread(QThread):
    """计算所有清理项的占用大小。"""
    item_done = pyqtSignal(int, 'qlonglong')  # index, size_bytes (64位)
    progress = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, items):
        super().__init__()
        self.items = items

    def run(self):
        for idx, it in enumerate(self.items):
            size = it.calc_size(on_progress=lambda p: self.progress.emit(p))
            self.item_done.emit(idx, size)
        self.finished_all.emit()


class CleanThread(QThread):
    log = pyqtSignal(str)
    item_done = pyqtSignal(str, 'qlonglong', int, int)  # name, freed(64位), deleted, failed
    finished_all = pyqtSignal('qlonglong', int, int)    # total_freed(64位), total_deleted, total_failed

    def __init__(self, items):
        super().__init__()
        self.items = items

    def run(self):
        total_freed = total_deleted = total_failed = 0
        for it in self.items:
            self.log.emit(f"正在清理: {it.name} ...")
            freed, deleted, failed = it.clean(
                on_progress=lambda p: self.log.emit(f"  - {p}")
            )
            total_freed += freed
            total_deleted += deleted
            total_failed += failed
            self.item_done.emit(it.name, freed, deleted, failed)
        self.finished_all.emit(total_freed, total_deleted, total_failed)


class LargeFileScanThread(QThread):
    progress = pyqtSignal(str)
    finished_with = pyqtSignal(list)

    def __init__(self, root: str, min_size_mb: int):
        super().__init__()
        self.root = root
        self.min_size_mb = min_size_mb
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        results = scan_large_files(
            root=self.root,
            min_size_mb=self.min_size_mb,
            on_progress=lambda p: self.progress.emit(p),
            should_stop=lambda: self._stop,
        )
        self.finished_with.emit(results)


class AnalyzeDirThread(QThread):
    progress = pyqtSignal(str)
    item_ready = pyqtSignal(str, 'qlonglong', bool, 'qlonglong')  # name, size(64位), is_dir, file_count(64位)
    finished_with = pyqtSignal(str, list)  # root, results

    def __init__(self, root: str):
        super().__init__()
        self.root = root
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        results = analyze_dir(
            self.root,
            on_progress=lambda p: self.progress.emit(p),
            should_stop=lambda: self._stop,
            on_item=lambda n, s, d, c: self.item_ready.emit(n, s, d, c),
        )
        self.finished_with.emit(self.root, results)


class SoftwareLoadThread(QThread):
    finished_with = pyqtSignal(list)

    def __init__(self, calc_size: bool = False):
        super().__init__()
        self.calc_size = calc_size

    def run(self):
        apps = list_installed_software(calc_size=self.calc_size)
        self.finished_with.emit(apps)


class DeletePathThread(QThread):
    """后台删除单个文件或目录，避免大目录卡死界面。"""
    progress = pyqtSignal(str)
    finished_with = pyqtSignal(str, bool, 'qlonglong', int, str)  # path, ok, freed(64位), failed_count, err_msg

    def __init__(self, path: str, is_dir: bool):
        super().__init__()
        self.path = path
        self.is_dir = is_dir

    def run(self):
        path = self.path
        freed = 0
        failed = 0
        err = ""
        try:
            if self.is_dir or os.path.isdir(path):
                # 先记录大小（粗略），再删
                for root, _, files in os.walk(path, onerror=lambda e: None):
                    for fn in files:
                        try:
                            freed += os.path.getsize(os.path.join(root, fn))
                        except OSError:
                            pass
                self.progress.emit(f"删除中: {path}")
                _failed = [0]

                def onerror(func, p, exc_info):
                    try:
                        os.chmod(p, 0o777)
                        func(p)
                    except OSError:
                        _failed[0] += 1

                shutil.rmtree(path, onerror=onerror)
                failed = _failed[0]
                ok = not os.path.exists(path)
            else:
                try:
                    freed = os.path.getsize(path)
                except OSError:
                    freed = 0
                os.remove(path)
                ok = True
        except OSError as e:
            ok = False
            err = str(e)
        self.finished_with.emit(path, ok, freed, failed, err)


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def open_in_explorer(path: str):
    if os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


def run_uninstall(cmd: str):
    if not cmd:
        return
    try:
        subprocess.Popen(cmd, shell=True)
    except OSError:
        pass
