"""安全清理项定义与执行。"""
import os
import shutil
from pathlib import Path
from typing import Callable, List, Tuple

USER_HOME = Path(os.environ.get("USERPROFILE", "C:/Users/Default"))
LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA", USER_HOME / "AppData/Local"))
WINDIR = Path(os.environ.get("WINDIR", "C:/Windows"))


class CleanItem:
    """一个清理项。

    mode:
        'dir_contents' - 删除目录里的文件/子目录，但保留目录本身
        'glob'         - 按通配符删除匹配的文件
    """

    def __init__(self, key: str, name: str, desc: str, paths: List[Path],
                 mode: str = "dir_contents", risk: str = "safe", patterns=None):
        self.key = key
        self.name = name
        self.desc = desc
        self.paths = [Path(p) for p in paths]
        self.mode = mode
        self.risk = risk  # safe / caution
        self.patterns = patterns or ["*"]

    # ---------- 大小统计 ----------
    def calc_size(self, on_progress: Callable[[str], None] = None) -> int:
        total = 0
        for base in self.paths:
            if not base.exists():
                continue
            try:
                if self.mode == "glob":
                    for pat in self.patterns:
                        for f in base.glob(pat):
                            try:
                                if f.is_file():
                                    total += f.stat().st_size
                            except OSError:
                                pass
                else:
                    for root, dirs, files in os.walk(base, topdown=True, onerror=lambda e: None):
                        for fn in files:
                            try:
                                total += os.path.getsize(os.path.join(root, fn))
                            except OSError:
                                pass
                        if on_progress:
                            on_progress(root)
            except (PermissionError, OSError):
                continue
        return total

    # ---------- 执行清理 ----------
    def clean(self, on_progress: Callable[[str], None] = None) -> Tuple[int, int, int]:
        """返回 (释放字节, 已删文件数, 失败数)"""
        freed = 0
        deleted = 0
        failed = 0
        for base in self.paths:
            if not base.exists():
                continue
            if self.mode == "glob":
                for pat in self.patterns:
                    for f in base.glob(pat):
                        try:
                            if f.is_file():
                                size = f.stat().st_size
                                f.unlink()
                                freed += size
                                deleted += 1
                        except OSError:
                            failed += 1
            else:
                # 删除目录下的全部内容（保留目录本身）
                try:
                    for entry in base.iterdir():
                        try:
                            if entry.is_file() or entry.is_symlink():
                                size = 0
                                try:
                                    size = entry.stat().st_size
                                except OSError:
                                    pass
                                try:
                                    entry.unlink()
                                    freed += size
                                    deleted += 1
                                except OSError:
                                    failed += 1
                            elif entry.is_dir():
                                size = _dir_size(entry)
                                try:
                                    shutil.rmtree(entry, ignore_errors=False,
                                                  onerror=_rm_onerror)
                                    freed += size
                                    deleted += 1
                                except OSError:
                                    failed += 1
                            if on_progress:
                                on_progress(str(entry))
                        except OSError:
                            failed += 1
                except OSError:
                    continue
        return freed, deleted, failed


def _dir_size(p: Path) -> int:
    total = 0
    for root, _, files in os.walk(p, onerror=lambda e: None):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


def _rm_onerror(func, path, exc_info):
    """尝试改属性后重试。"""
    try:
        os.chmod(path, 0o777)
        func(path)
    except OSError:
        pass


def build_clean_items() -> List[CleanItem]:
    items: List[CleanItem] = [
        CleanItem(
            "user_temp", "用户临时文件",
            f"{LOCAL_APPDATA}\\Temp 下的所有临时文件",
            [LOCAL_APPDATA / "Temp"], risk="safe",
        ),
        CleanItem(
            "win_temp", "系统临时文件",
            f"{WINDIR}\\Temp 下的所有临时文件",
            [WINDIR / "Temp"], risk="safe",
        ),
        CleanItem(
            "win_update", "Windows Update 缓存",
            "已下载但已安装完毕的更新包",
            [WINDIR / "SoftwareDistribution" / "Download"], risk="safe",
        ),
        CleanItem(
            "prefetch", "预读取文件 (Prefetch)",
            "可加速程序启动的缓存，删后系统会重建",
            [WINDIR / "Prefetch"], risk="safe",
        ),
        CleanItem(
            "thumb_cache", "缩略图缓存",
            "资源管理器缩略图缓存，删后会重建",
            [LOCAL_APPDATA / "Microsoft/Windows/Explorer"],
            mode="glob", patterns=["thumbcache_*.db", "iconcache_*.db"], risk="safe",
        ),
        CleanItem(
            "recent", "最近访问记录",
            "最近打开的文档列表（不删源文件）",
            [USER_HOME / "AppData/Roaming/Microsoft/Windows/Recent"], risk="safe",
        ),
        CleanItem(
            "crash_dump", "系统崩溃转储",
            "MEMORY.DMP / Minidump 文件",
            [WINDIR / "Minidump"], risk="safe",
        ),
        CleanItem(
            "edge_cache", "Edge 浏览器缓存",
            "Microsoft Edge 缓存（不影响登录）",
            [LOCAL_APPDATA / "Microsoft/Edge/User Data/Default/Cache"], risk="safe",
        ),
        CleanItem(
            "chrome_cache", "Chrome 浏览器缓存",
            "Google Chrome 缓存（不影响登录）",
            [LOCAL_APPDATA / "Google/Chrome/User Data/Default/Cache"], risk="safe",
        ),
        CleanItem(
            "delivery_optim", "传送优化文件",
            "Windows 更新点对点分发缓存",
            [WINDIR / "SoftwareDistribution/DeliveryOptimization"], risk="safe",
        ),
        CleanItem(
            "windows_old", "旧系统备份 Windows.old",
            "升级 Windows 后保留的旧系统，确认无回滚需求再删",
            [Path("C:/Windows.old")], risk="caution",
        ),
    ]
    return items


def human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
