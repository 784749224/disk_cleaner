"""读取已安装软件列表（从 Windows 注册表）。"""
import os
from typing import List, Dict

try:
    import winreg
except ImportError:
    winreg = None

UNINSTALL_KEYS = [
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM", 0),
    (r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM", 0),
    (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU", 0),
]


def _open_root(name: str):
    return winreg.HKEY_LOCAL_MACHINE if name == "HKLM" else winreg.HKEY_CURRENT_USER


def _folder_size(path: str) -> int:
    if not path or not os.path.isdir(path):
        return 0
    total = 0
    for root, _, files in os.walk(path, onerror=lambda e: None):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total


def list_installed_software(calc_size: bool = False) -> List[Dict]:
    if winreg is None:
        return []
    seen = set()
    apps: List[Dict] = []

    for sub, root_name, _flags in UNINSTALL_KEYS:
        try:
            root = _open_root(root_name)
            with winreg.OpenKey(root, sub) as hkey:
                i = 0
                while True:
                    try:
                        sk = winreg.EnumKey(hkey, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(hkey, sk) as item:
                            info = _read_app(item)
                            if not info.get("name"):
                                continue
                            sig = (info["name"], info.get("version", ""))
                            if sig in seen:
                                continue
                            seen.add(sig)
                            if calc_size and not info.get("size_bytes"):
                                info["size_bytes"] = _folder_size(info.get("install_location", ""))
                            apps.append(info)
                    except OSError:
                        continue
        except OSError:
            continue

    apps.sort(key=lambda a: (a.get("size_bytes") or 0), reverse=True)
    return apps


def _read_app(item) -> Dict:
    def get(name, default=""):
        try:
            return winreg.QueryValueEx(item, name)[0]
        except OSError:
            return default

    sys_comp = get("SystemComponent", 0)
    parent = get("ParentKeyName", "")
    if sys_comp or parent:
        return {}

    name = get("DisplayName", "")
    if not name:
        return {}

    size_kb = get("EstimatedSize", 0)
    try:
        size_bytes = int(size_kb) * 1024 if size_kb else 0
    except (TypeError, ValueError):
        size_bytes = 0

    return {
        "name": name,
        "version": get("DisplayVersion", ""),
        "publisher": get("Publisher", ""),
        "install_location": get("InstallLocation", ""),
        "install_date": get("InstallDate", ""),
        "uninstall": get("UninstallString", ""),
        "quiet_uninstall": get("QuietUninstallString", ""),
        "size_bytes": size_bytes,
    }
