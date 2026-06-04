"""为空间分析里出现的文件/文件夹提供风险与说明。

risk:
    'safe'    - 可放心删（一般是缓存/临时/日志）
    'caution' - 用户数据或软件目录，需确认后再删
    'danger'  - 系统关键文件，删除可能导致系统不可用
    'unknown' - 未知，自行判断
"""
import os
from typing import Tuple

# 颜色提示 (RGB)
RISK_COLORS = {
    "safe":    (22, 163, 74),    # 绿
    "caution": (217, 119, 6),    # 橙
    "danger":  (220, 38, 38),    # 红
    "unknown": (107, 114, 128),  # 灰
}

RISK_LABELS = {
    "safe": "可删", "caution": "谨慎", "danger": "勿删", "unknown": "未知",
}

# C:\ 根目录下常见名字（小写匹配）
ROOT_KNOWN = {
    "windows":            ("danger",  "Windows 系统核心目录，绝对不要删除"),
    "windows.old":        ("safe",    "升级前的旧系统备份，确认无回滚需要可删，30 天后系统也会自动清理"),
    "program files":      ("caution", "64 位软件安装目录，请通过【已装软件】或控制面板卸载，不要手动删"),
    "program files (x86)":("caution", "32 位软件安装目录，请通过卸载程序删除"),
    "programdata":        ("caution", "软件公共数据/配置，含部分程序的数据库，整体勿删，可进入子目录单独清理"),
    "users":              ("caution", "用户文件（桌面/文档/AppData），整体勿删，进入子目录定位大头"),
    "recovery":           ("danger",  "Windows 系统恢复分区入口，删除后系统重置功能将失效"),
    "perflogs":           ("safe",    "性能监视日志，可安全删除，系统会自动重建"),
    "$recycle.bin":       ("safe",    "回收站，建议在桌面右键回收站→清空，而非直接删此目录"),
    "$getcurrent":        ("safe",    "Windows 升级遗留文件，可删"),
    "$windows.~bt":       ("safe",    "Windows 升级缓存，可删"),
    "$windows.~ws":       ("safe",    "Windows 升级缓存，可删"),
    "system volume information": ("danger", "系统卷影/还原点存储，删除将丢失系统还原能力"),
    "config.msi":         ("safe",    "Windows Installer 临时数据，安装完成后可删"),
    "intel":              ("caution", "Intel 驱动/工具相关数据，一般可保留"),
    "amd":                ("caution", "AMD 驱动相关数据，一般可保留"),
    "nvidia":             ("caution", "NVIDIA 驱动相关数据，一般可保留"),
    "drivers":            ("danger",  "驱动文件，勿删"),
    "boot":               ("danger",  "启动文件，勿删"),
    "msocache":           ("safe",    "Office 安装缓存，可删（重装 Office 时会重新下载）"),
    "drvpath":            ("caution", "驱动相关目录（厂商不一），不确定用途时勿删"),
    "ceofun":             ("caution", "厂商/OEM 预装目录，不确定用途时先在搜索引擎确认"),
}

# 已知文件名（C:\ 根，小写）
ROOT_FILES = {
    "hiberfil.sys":  ("caution", "休眠文件，可通过命令 powercfg /h off 关闭休眠后自动消失（不要手动删）"),
    "pagefile.sys":  ("danger",  "虚拟内存交换文件，由系统管理，请勿手动删除（可在系统设置中调整大小）"),
    "swapfile.sys":  ("danger",  "现代 UWP 应用使用的交换文件，由系统管理，勿手删"),
    "bootmgr":       ("danger",  "Windows 启动管理器，删除后无法开机"),
    "bootnxt":       ("danger",  "启动相关文件，勿删"),
    "ntldr":         ("danger",  "旧版启动加载器，勿删"),
    "dumpstack.log": ("safe",    "系统崩溃栈日志，可删"),
    "dumpstack.log.tmp": ("safe", "系统崩溃栈临时日志，可删"),
    "memory.dmp":    ("safe",    "蓝屏内存转储，可删"),
}

# 用户目录下子文件夹常见名（路径中包含 \Users\xxx\ 时启用）
USER_HOME_KNOWN = {
    "appdata":   ("caution", "应用数据目录，含大量软件缓存与配置，进入子目录定位大头（Local 通常最大）"),
    "desktop":   ("caution", "桌面文件，确认无重要内容再删"),
    "documents": ("caution", "我的文档，含个人文件，确认后再删"),
    "downloads": ("caution", "下载目录，常常堆积大文件，按需清理"),
    "pictures":  ("caution", "图片库，确认后再删"),
    "videos":    ("caution", "视频库，常占大量空间，确认后再删"),
    "music":     ("caution", "音乐库"),
    "onedrive":  ("caution", "OneDrive 同步目录，删除会同步删除云端文件！"),
    ".cache":    ("safe",    "通用缓存目录，可删"),
    ".gradle":   ("safe",    "Gradle 构建缓存，可删（下次构建会重新下载，慢）"),
    ".m2":       ("safe",    "Maven 本地仓库，可删（下次构建会重下）"),
    ".npm":      ("safe",    "npm 缓存，可 npm cache clean 或直接删"),
    ".pip":      ("safe",    "pip 缓存，可删"),
    ".cargo":    ("caution", "Rust cargo 目录（含已安装工具链），删除会需重装"),
    ".conda":    ("caution", "conda 包缓存，删除会影响已建环境"),
    ".vscode":   ("caution", "VSCode 配置/插件，删除会丢配置"),
    ".idea":     ("caution", "JetBrains IDE 项目设置，删除会丢配置"),
}

# AppData\Local 下常见占用
APPDATA_LOCAL_KNOWN = {
    "temp":             ("safe",    "用户临时文件，可全部删除（与【安全清理】里的同源）"),
    "microsoft":        ("caution", "微软系列软件数据（Edge/Office/Teams 缓存等），进入子目录细看"),
    "google":           ("caution", "Chrome 等 Google 软件数据，缓存可删，配置勿删"),
    "package cache":    ("safe",    "软件安装包缓存，可删"),
    "packages":         ("caution", "UWP 应用沙箱数据，删除会重置应用"),
    "pip":              ("safe",    "pip 下载缓存，可删"),
    "npm-cache":        ("safe",    "npm 缓存，可删"),
    "yarn":             ("safe",    "yarn 缓存，可删"),
    "docker":           ("caution", "Docker 数据（镜像、卷），删除会丢失容器/镜像"),
    "programs":         ("caution", "用户级安装的软件（如 Cursor、VS Code 等），通过卸载程序删"),
    "tencent":          ("caution", "腾讯系软件数据（QQ/微信/TIM 等），缓存可删，聊天记录勿删"),
    "baidunetdisk":     ("caution", "百度网盘缓存，可清理"),
    "jetbrains":        ("caution", "JetBrains IDE 缓存与索引，可清理（下次打开会重建索引）"),
    "cursor":           ("caution", "Cursor 编辑器数据，含插件与缓存"),
    "github copilot":   ("caution", "Copilot 缓存"),
    "ms-playwright":    ("safe",    "Playwright 浏览器二进制，可删（下次会重新下载）"),
    "android":          ("caution", "Android SDK/模拟器数据，删除将影响开发环境"),
    "anaconda3":        ("caution", "Anaconda 安装目录，请用 Anaconda 卸载程序"),
    "miniconda3":       ("caution", "Miniconda 安装目录，请用卸载程序"),
}

# 通用关键字（路径或名字中包含）
KEYWORD_HINTS = [
    ("temp",   "safe",    "临时文件目录，通常可清理"),
    ("cache",  "safe",    "缓存目录，通常可清理（程序会重建）"),
    ("logs",   "safe",    "日志目录，可清理（保留近期日志更稳）"),
    ("crashpad", "safe",  "崩溃报告，可删"),
    ("crashes", "safe",   "崩溃报告，可删"),
    ("backup", "caution", "备份数据，确认是否需要后再删"),
    ("dump",   "safe",    "崩溃/内存转储，一般可删"),
]


# 数据盘 (D:/E:/F:...) 常见软件/游戏/下载目录识别
# 采用"包含匹配"（不区分大小写）；规则按顺序匹配，先到先得
# 元组: (匹配关键字, 风险, 说明)
NAME_PATTERNS = [
    # ---- 网盘 / 下载 ----
    ("baidunetdiskdownload", "caution", "百度网盘下载目录，含个人下载内容，按需清理"),
    ("baidunetdisk",  "caution", "百度网盘相关数据"),
    ("百度云",        "caution", "百度云下载/缓存，按需清理"),
    ("xunlei",        "caution", "迅雷下载相关数据"),
    ("thunder",       "caution", "迅雷下载目录，按需清理"),
    ("阿里云盘",      "caution", "阿里云盘相关数据"),
    ("aliyundrive",   "caution", "阿里云盘相关数据"),
    ("download",      "caution", "下载目录，按需清理（确认无重要内容）"),
    ("下载",          "caution", "下载目录，按需清理"),

    # ---- 游戏平台 ----
    ("steamapps",     "caution", "Steam 游戏本体，请通过 Steam 客户端卸载"),
    ("steam",         "caution", "Steam 游戏平台目录"),
    ("epic games",    "caution", "Epic Games 游戏目录，请通过启动器卸载"),
    ("origin games",  "caution", "EA Origin 游戏目录"),
    ("riot games",    "caution", "拳头游戏（英雄联盟等）目录"),
    ("wegame",        "caution", "腾讯 WeGame 游戏目录"),
    ("battle.net",    "caution", "暴雪战网游戏目录"),
    ("warcraft",      "caution", "魔兽争霸游戏目录"),
    ("league of legends", "caution", "英雄联盟"),
    ("perfectworld",  "caution", "完美世界游戏"),
    ("netease",       "caution", "网易游戏/产品目录"),

    # ---- 聊天 / 社交软件文件 ----
    ("xwechat_files", "caution", "微信4.0 聊天记录/文件夹，删除将丢失聊天数据！"),
    ("wechat files",  "caution", "微信聊天记录/文件夹，删除将丢失聊天数据！"),
    ("wechat",        "caution", "微信相关数据"),
    ("tencent files", "caution", "QQ/TIM 聊天记录/接收文件，按需清理"),
    ("qq files",      "caution", "QQ 接收文件，按需清理"),
    ("qq",            "caution", "腾讯 QQ 相关数据"),
    ("dingtalk",      "caution", "钉钉数据"),
    ("feishu",        "caution", "飞书数据"),
    ("lark",          "caution", "飞书海外版数据"),

    # ---- 影音 ----
    ("cloudmusic",    "caution", "网易云音乐目录"),
    ("kugou",         "caution", "酷狗音乐"),
    ("qqmusic",       "caution", "QQ 音乐"),
    ("douyin",        "caution", "抖音相关数据"),
    ("抖音",          "caution", "抖音相关数据"),
    ("bilibili",      "caution", "B站客户端/下载"),
    ("potplayer",     "caution", "PotPlayer 播放器"),

    # ---- 浏览器 ----
    ("qq浏览器",      "caution", "QQ 浏览器数据"),
    ("qqbrowser",     "caution", "QQ 浏览器数据"),
    ("360se",         "caution", "360 浏览器数据"),
    ("sogouexplorer", "caution", "搜狗浏览器"),
    ("firefox",       "caution", "火狐浏览器"),

    # ---- 开发工具 / IDE ----
    ("hbuilderx",     "caution", "HBuilderX IDE 安装目录"),
    ("antigravity",   "caution", "Antigravity 编辑器（Google）"),
    ("cursor",        "caution", "Cursor 编辑器"),
    ("windsurf",      "caution", "Windsurf 编辑器（Codeium）"),
    ("kiro",          "caution", "Kiro IDE（AWS）"),
    ("vscode",        "caution", "VS Code 编辑器或其数据"),
    ("jetbrains",     "caution", "JetBrains IDE 数据"),
    ("intellij",      "caution", "IntelliJ IDEA"),
    ("android studio","caution", "Android Studio"),
    ("eclipse",       "caution", "Eclipse IDE"),
    ("navicat",       "caution", "Navicat 数据库工具"),
    ("apifox",        "caution", "Apifox API 工具"),
    ("postman",       "caution", "Postman API 工具"),
    ("dbeaver",       "caution", "DBeaver 数据库工具"),

    # ---- 开发运行时 / SDK ----
    ("nodejs",        "caution", "Node.js 运行时，卸载会影响相关项目"),
    ("node_modules",  "safe",    "Node 项目依赖目录，可删（npm install 会重建）"),
    ("python",        "caution", "Python 安装目录或项目代码"),
    ("jdk",           "caution", "Java 开发工具包"),
    ("jre",           "caution", "Java 运行时"),
    ("go",            "caution", "Go 语言相关"),
    ("rustup",        "caution", "Rust 工具链管理器"),
    ("fluttersdk",    "caution", "Flutter SDK，卸载会影响 Flutter 项目构建"),
    ("flutter",       "caution", "Flutter 相关"),
    ("dart",          "caution", "Dart SDK"),
    ("gradle",        "caution", "Gradle 工具"),
    ("maven",         "caution", "Maven 工具"),
    ("android-sdk",   "caution", "Android SDK"),

    # ---- AI / 模型 ----
    ("comfyui",       "caution", "ComfyUI 工作流（含已下载的大模型）"),
    ("stable-diffusion", "caution", "Stable Diffusion 相关"),
    ("models",        "caution", "AI 模型目录，下载耗时长，删前请确认"),

    # ---- 远程 / 系统工具 ----
    ("todesk",        "caution", "ToDesk 远程控制软件"),
    ("teamviewer",    "caution", "TeamViewer 远程"),
    ("anydesk",       "caution", "AnyDesk 远程"),
    ("clash",         "caution", "Clash 系列代理软件"),
    ("v2ray",         "caution", "V2Ray 代理"),

    # ---- 项目代码 / 示例 ----
    ("demo",          "caution", "示例/演示项目目录，按需清理"),
    ("workspace",     "caution", "工作区，可能含项目代码，确认后再删"),
    ("project",       "caution", "项目目录，确认后再删"),

    # ---- 沙箱 / 其他 ----
    ("windowsapps",   "danger",  "Windows 应用商店 UWP 应用目录，由系统管理，请通过【设置-应用】卸载"),
    ("deliveryoptimization", "safe", "Windows 更新点对点缓存，可删"),
    ("夸克",          "caution", "夸克网盘/浏览器相关"),
]

# 通用扩展名
EXT_HINTS = {
    ".tmp": ("safe",    "临时文件，可删"),
    ".bak": ("caution", "备份文件，确认后再删"),
    ".old": ("caution", "旧版本备份，确认后再删"),
    ".log": ("safe",    "日志文件，可删"),
    ".dmp": ("safe",    "内存/崩溃转储，可删"),
    ".cab": ("caution", "Windows 更新/驱动包，确认来源后再删"),
    ".iso": ("caution", "光盘镜像，常占大空间，确认不再需要后可删"),
    ".msi": ("caution", "安装包，安装完成后可删"),
    ".exe": ("caution", "可执行/安装程序，确认是否仍需要"),
}


# 祖先目录名 -> 该目录下全部内容的风险继承（小写匹配；带斜杠的代表多级）
ANCESTOR_INHERIT = {
    # 通用缓存/临时
    "temp":             ("safe", "临时文件目录的内容，可删"),
    "tmp":              ("safe", "临时文件目录的内容，可删"),
    "cache":            ("safe", "缓存目录的内容，可删（程序会重建）"),
    ".cache":           ("safe", "缓存目录的内容，可删"),
    "caches":           ("safe", "缓存目录的内容，可删"),
    "logs":             ("safe", "日志目录的内容，可删"),
    "crashpad":         ("safe", "崩溃报告，可删"),
    "crashes":          ("safe", "崩溃报告，可删"),
    "crashdumps":       ("safe", "崩溃转储，可删"),
    # 包管理器缓存
    ".gradle":          ("safe", "Gradle 缓存内容，可删（下次构建会重新下载）"),
    ".m2":              ("safe", "Maven 本地仓库内容，可删（下次构建会重新下载）"),
    ".npm":             ("safe", "npm 缓存内容，可删"),
    ".pip":             ("safe", "pip 缓存内容，可删"),
    ".yarn":            ("safe", "yarn 缓存内容，可删"),
    "pip":              ("safe", "pip 缓存内容，可删"),
    "npm-cache":        ("safe", "npm 缓存内容，可删"),
    "yarn-cache":       ("safe", "yarn 缓存内容，可删"),
    "package cache":    ("safe", "安装包缓存，可删"),
    "ms-playwright":    ("safe", "Playwright 浏览器二进制，可删（重装会重新下载）"),
    # 系统级
    "softwaredistribution": ("safe", "Windows Update 数据，安装完成后多数可删"),
    "prefetch":         ("safe", "预读取缓存，可删（系统会重建）"),
    "minidump":         ("safe", "蓝屏小型转储，可删"),
    # 谨慎类（用户数据）
    "appdata":          ("caution", "应用配置/数据，进入更深层定位再决定是否删"),
    "users":            ("caution", "用户数据范围，请先看清是哪个软件再决定"),
    "documents":        ("caution", "文档目录的内容，确认后再删"),
    "downloads":        ("caution", "下载文件，按需清理"),
    "desktop":          ("caution", "桌面文件，确认后再删"),
    "onedrive":         ("caution", "OneDrive 同步内容，删除会同步删除云端文件！"),
    # 危险类（系统）
    "windows":          ("danger",  "Windows 系统文件，勿删"),
    "system32":         ("danger",  "系统核心，绝对勿删"),
    "syswow64":         ("danger",  "系统核心 (32 位兼容层)，勿删"),
    "winsxs":           ("danger",  "Windows 组件存储，看着大但勿删"),
    "drivers":          ("danger",  "驱动文件，勿删"),
    "boot":             ("danger",  "启动文件，勿删"),
    "recovery":         ("danger",  "系统恢复数据，勿删"),
    "system volume information": ("danger", "系统还原点存储，勿删"),
}


def _check_ancestors(parts):
    """从最近的父目录向根方向找，命中即返回继承风险（最近的优先）。"""
    # parts 已是 normpath 小写的拆分
    for i in range(len(parts) - 1, 0, -1):
        seg = parts[i]
        if seg in ANCESTOR_INHERIT:
            return ANCESTOR_INHERIT[seg]
    return None


def get_info(full_path: str, name: str, is_dir: bool) -> Tuple[str, str]:
    """返回 (risk, desc)。"""
    name_l = name.lower()
    norm = os.path.normpath(full_path).lower()
    parent = os.path.dirname(norm)

    # 1. C:\ 根
    if parent in ("c:\\", "c:"):
        if is_dir and name_l in ROOT_KNOWN:
            return ROOT_KNOWN[name_l]
        if (not is_dir) and name_l in ROOT_FILES:
            return ROOT_FILES[name_l]

    parts = norm.split(os.sep)
    parent_parts = parts[:-1]  # 不包含自身

    # 2. C:\Users\xxx\ 下
    if len(parts) >= 4 and parts[1] == "users":
        if len(parts) == 4 and is_dir and name_l in USER_HOME_KNOWN:
            return USER_HOME_KNOWN[name_l]
        if (len(parts) >= 6 and parts[3] == "appdata" and parts[4] == "local"
                and len(parts) == 6 and name_l in APPDATA_LOCAL_KNOWN):
            return APPDATA_LOCAL_KNOWN[name_l]

    # 3. 扩展名（文件）
    if not is_dir:
        ext = os.path.splitext(name_l)[1]
        if ext in EXT_HINTS:
            return EXT_HINTS[ext]

    # 4. 名字本身的关键字
    for kw, risk, desc in KEYWORD_HINTS:
        if kw in name_l:
            return risk, desc

    # 5. 数据盘软件/游戏/下载目录的"包含匹配"识别
    for pat, risk, desc in NAME_PATTERNS:
        if pat in name_l:
            return risk, desc

    # 6. 祖先目录继承（关键：进入 .cache / Temp / .gradle 等后，子项继承父风险）
    inherited = _check_ancestors(parent_parts)
    if inherited:
        return inherited

    # 7. 默认：非 C 盘默认认为是用户数据（谨慎），C 盘陌生项才标"未知"
    drive = parts[0] if parts else ""
    if drive and drive != "c:":
        if is_dir:
            return "caution", "数据盘的用户文件夹（软件/游戏/项目/下载等），删前请确认用途"
        return "caution", "数据盘的用户文件，删前请确认是否还需要"

    if is_dir:
        return "unknown", "用途未知，建议先在搜索引擎查询该文件夹名再决定"
    return "unknown", "用途未知，建议查询后再删"
