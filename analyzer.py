"""目录空间分析：列出指定目录下所有一级子项的总占用大小。"""
import os
from typing import Callable, List, Tuple


def analyze_dir(
    root: str,
    on_progress: Callable[[str], None] = None,
    should_stop: Callable[[], bool] = None,
    on_item: Callable[[str, int, bool, int], None] = None,
) -> List[Tuple[str, int, bool, int]]:
    """扫描 root 的一级子项，返回 [(name, size_bytes, is_dir, file_count), ...] 按大小降序。

    file_count: 文件夹包含的文件总数；文件则为 1。
    on_item: 每完成一个一级子项就回调一次，便于 UI 增量显示。
    """
    results: List[Tuple[str, int, bool, int]] = []
    try:
        entries = list(os.scandir(root))
    except OSError:
        return results

    # 先把文件处理掉（很快），再处理目录（耗时）
    entries.sort(key=lambda e: 0 if _safe_is_file(e) else 1)

    for entry in entries:
        if should_stop and should_stop():
            break
        try:
            if entry.is_file(follow_symlinks=False):
                try:
                    sz = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    sz = 0
                item = (entry.name, sz, False, 1)
                results.append(item)
                if on_item:
                    on_item(*item)
            elif entry.is_dir(follow_symlinks=False):
                if on_progress:
                    on_progress(entry.path)
                total, count = _dir_total(entry.path, should_stop)
                item = (entry.name, total, True, count)
                results.append(item)
                if on_item:
                    on_item(*item)
        except OSError:
            continue

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def _safe_is_file(entry) -> bool:
    try:
        return entry.is_file(follow_symlinks=False)
    except OSError:
        return False


def _dir_total(path: str, should_stop=None) -> Tuple[int, int]:
    total = 0
    count = 0
    for cur, dirs, files in os.walk(path, onerror=lambda e: None):
        if should_stop and should_stop():
            break
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(cur, fn))
                count += 1
            except OSError:
                continue
    return total, count
