#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init.py —— 初始化运行目录，让雷达在这台机器上能直接跑。

    python scripts/init.py                 # 缺什么建什么，已有文件一律不覆盖
    python scripts/init.py --force-config   # 连 config.json 一起重置（先备份成 config.json.bak-<ts>）

做的事：
  1. 建状态目录（默认 <仓库根>/state，可用 INTERESTS_DIR 覆盖）+ 子目录 out/ frames/
  2. 拷模板：templates/charter.md → state/charter.md，templates/profile.md → state/profile.md
  3. 写默认 config.json（所有写操作默认 **关**，要开自己在 config 里打开并加 --yes）
  4. 打印解析出来的路径（状态目录 / cookie 路径 / 是否存在），cookie 缺了就提示怎么放

零网络、零凭据：本脚本只碰本地文件。
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bili_radar.core import REPO_ROOT, cookie_path, die, state_dir  # noqa: E402

# 干净起点：所有对外写操作一律关着。要发东西必须自己改 config + 命令行加 --yes。
DEFAULT_CONFIG = {
    "mention": {
        "enabled": False,
        "name": "",
        "mid": 0,
        "per_round": 1,
        "per_hour": 1,
        "per_day": 0,
        "min_score": 17,
        "template": "@{name} {why}",
        "forbid": [],
    },
    "comment_check": {
        "num": 10,
        "warn_ratio": 0.3,
        "name_keywords": [],
        "ai_patterns": [],
    },
    "draft": {
        "enabled": False,
        "per_12h": 1,
        "per_24h": 2,
        "reply_interval_days": 30,
        "forbid": [],
    },
    "write": {
        "cooldown_sec": 120,
        "comment": {"enabled": False, "per_hour": 3, "per_day": 0,
                    "same_video_once": True, "forbid": []},
        "dynamic": {"enabled": False, "per_hour": 1, "per_day": 3, "forbid": []},
        "message": {"enabled": False, "per_day": 5, "allow_mid": [], "forbid": []},
    },
    "budget": {
        "max_subtitles_per_round": 5,
        "max_push_per_round": 3,
        "min_total_score": 14,
    },
}


def _copy_template(d: Path, name: str) -> bool:
    dst = d / name
    if dst.exists():
        return False
    src = REPO_ROOT / "templates" / name
    if not src.is_file():
        print(f"  ! 模板缺失，跳过：{src}")
        return False
    shutil.copyfile(src, dst)
    return True


def main():
    force = "--force-config" in sys.argv[1:]
    d = state_dir()
    (d / "out").mkdir(parents=True, exist_ok=True)
    (d / "frames").mkdir(parents=True, exist_ok=True)
    print(f"状态目录：{d}")

    for name in ("charter.md", "profile.md"):
        print(("  + 新建 " if _copy_template(d, name) else "  = 已存在 ") + name)

    cfg_file = d / "config.json"
    if cfg_file.exists() and not force:
        print("  = 已存在 config.json（要重置加 --force-config）")
    else:
        if cfg_file.exists():
            bak = cfg_file.with_name("config.json.bak-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
            shutil.copyfile(cfg_file, bak)
            print(f"  ~ 旧配置已备份：{bak.name}")
        cfg_file.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print("  + 新建 config.json（写操作全关）")

    ck = cookie_path()
    print(f"cookie  ：{ck}  {'✓ 存在' if ck.is_file() else '✗ 缺失'}")
    if not ck.is_file():
        print("          读字幕/评论必须有它：把小号 B站 cookie 存成一行 "
              "`SESSDATA=…; bili_jct=…; DedeUserID=…` 写进上面的文件。")
        print("          （扫码自救见 scripts/bili_qr_login.py，需要 pip install qrcode）")
    print("下一步：python scripts/radar.py check")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        die("已中断", 130)
