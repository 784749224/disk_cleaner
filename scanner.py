"""大文件扫描。"""
import os
from pathlib import Path
from typing import Callable, List, Tuple

DEFAULT_EXCLUDES = {
    "C:\\Windows\\WinSxS",
    "C:\\Windows\\System32",
    "C:\\Windows\\SysWOW64",
    "C:\\Windows\\Installer",
    "C:\\$Recycle.Bin",
    "C:\\System Volume Information",
}


def scan_large_files(
    root: str = "C:\\",
    min_size_mb: int = 100,
    on_progress: Callable[[str], None] = None,
    should_stop: Callable[[], bool] = None,
    excludes=None,
) -> List[Tuple[str, int]]:
    """扫描指定目录下大于 min_size_mb 的文件，按大小降序返回 [(path, size_bytes), ...]"""
    excludes = set(excludes) if excludes else set(DEFAULT_EXCLUDES)
    threshold = min_size_mb * 1024 * 1024
    results: List[Tuple[str, int]] = []
    counter = 0

    for cur, dirs, files in os.walk(root, onerror=lambda e: None):
        if should_stop and should_stop():
            break
        # 跳过排除目录
        cur_norm = os.path.normpath(cur).lower()
        if any(cur_norm.startswith(ex.lower()) for ex in excludes):
            dirs[:] = []
            continue

        for fn in files:
            if should_stop and should_stop():
                break
            full = os.path.join(cur, fn)
            try:
                size = os.path.getsize(full)
                if size >= threshold:
                    results.append((full, size))
            except OSError:
                continue

        counter += 1
        if on_progress and counter % 50 == 0:
            on_progress(cur)

    results.sort(key=lambda x: x[1], reverse=True)
    return results
