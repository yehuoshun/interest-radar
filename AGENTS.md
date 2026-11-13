# AGENTS.md — interest-radar 项目约定

> 本文件由 DSH 每轮自动注入（`AGENTS.md` 复数才会被加载；`AGENT.md` 单数是代码地图，需要主动读）。

## 这是什么仓库

B 站「兴趣雷达」：读兴趣档案 → 按兴趣线搜 → 读字幕原文 → 判重 → 写日报 → 挑值得看的东西 `@` 主号。本机 DSH 直接可用，也能当纯 CLI 跑。

| 想知道 | 去哪 |
|---|---|
| 代码在哪（文件 → 函数 → 行号） | [`AGENT.md`](AGENT.md) —— 改代码前先查，**别全仓 grep** |
| 怎么用、判据、作息 | [`SKILL.md`](SKILL.md) |
| 哪些参数真生效 / 哪些是死配置 | [`PARAMETERS.md`](PARAMETERS.md) |
| 判断口径与红线 | `templates/charter.md`（判据）、`templates/schedule-prompt.md`（一巡怎么走） |

## 提交与推送纪律（老板 2026-11-13 定，铁律）

- 中文提交信息，格式 `范围: 改了什么(为什么)`，范围取 `check` / `scripts` / `prompts` / `video` / `docs` / `chore`。
- **一修改一 push（铁律）**：每完成一处改动就 `git commit` + `git push origin main`，立刻推到远端，不许攒着、不留「等攒多点再一起推」。本地历史一次 `reset` 就没了，远端是唯一能追溯的底。中途干了多件事要拆成多个 commit 分别推，**一个 commit 只说一件事**，这样回溯时能精确 revert 单个改动。
- push 失败（网络 / 凭据 / 远端拒绝）必须**当场报出原文错误**并停下，不许静默跳过、不许改成本地攒着；确认远端真推上去了再继续下一步。
- **怎么判断 push 成功**：PowerShell 5.1 会把 `git push` 的进度行（`To github.com:...`）当 NativeCommandError、即使成功也返回 exit 1，别被退出码骗了。以 `git status -sb` 显示 `## main...origin/main`（无 `ahead`）或 `git log --oneline -1 origin/main` 等于本地 HEAD 为准。
- **动仓库前先看状态**：`git status` + `git log --oneline -3` + `git remote -v`。2026-11-12 出现过另一个会话在同一仓库并行改文件（根 README 被整体重写并单独提交），`git add -A` 会把别人的改动一起卷进你的 commit —— 发现工作区有不是你改的东西，先问，别一键全加。
- **禁止**替用户执行 `git reset --hard` / `git checkout -- .` / `git clean -fd`；也不要 `git push --force`。需要回退只做 `git revert`（留痕）或先问。
- git 操作只在项目目录内做，不跨仓库 `git add`。

## 本项目的红线（代码里已实现，别绕过）

- 写操作默认**干跑**，加 `--yes` 才真发；写完冷却 `write.cooldown_sec`（60 秒）会挡住「点完赞立刻评论」。
- `@` 老板**只走 `radar.py reply`**：`comment` 是自发评论路径，不记 `mention-log.jsonl`、不查 seen 的 `mentioned`（2026-11-13 踩过，SKILL.md 有标注）。
- 同一视频只发一次（`same_video_once`）；每小时上限（like 2 / comment 1 / mention 2）是**防封号安全阀**，不是内容标准，别拿它当审美去卡自己，也别绕。
- 分数阈值已作废：`budget.min_total_score = 0`、`mention.min_score = 0`（老板「不要设定阈值」）。判断交回模型，闸只防爆号。
- **凭据与运行态不进仓库**：cookie 在工作区 `config/bilibili_cookies.txt`（`core.py:12-15` 的候选顺序：工作区 config → 仓库 config → 旧 OpenClaw）；运行数据全在 `state/`（`.gitignore` 已挡：`config.json`、`seen.md`、`out/`、`jitter-log.jsonl`、`write-log.jsonl`、`mention-log.jsonl`）。不要把 `state/` 内容、cookie、头像缓存贴进提交或对话。

## 改完要做的

- 跑单测：`cd scripts; python -m unittest discover -s tests`（当前 **151 例**）。
- 动代码顺手更新 `AGENT.md` 的行号与符号表（它自己写着「行号会漂」），用例数变了同步 `SKILL.md` / `PARAMETERS.md` / `README.md` / `.github/workflows/ci.yml`。
- 临时文件写项目 `tmp/`（已 ignore），收尾删掉。
