跑一轮兴趣雷达（interest-radar）。

一次触发只跑一轮：跑完即止，不补轮、不叠轮、不为了凑数再加搜索。

严格按 `work/interest-radar/SKILL.md` 的「一轮流程」走：

1. 先读反馈：`python scripts/radar.py notify --new-only`。主号在我评论下的每条回复都用
   `radar.py feedback` 记一条（like/skip/note），一条都不许丢；别人 @ 我不理不回。
2. `python scripts/radar.py check` —— cookie 失效就直接停，别硬跑，报一句「cookie 失效」。
3. 读 `state/profile.md` 的兴趣线（0 条就只按「明确不要的」过滤，不自造兴趣）。
4. 每条兴趣线搜 1 轮：`radar.py search --kw "…" --days 7 --order pubdate`。
5. 粗筛到 ≤8 条候选（砍入门教程/标题党/吵架场）→ 按分数从高到低 `radar.py sub` 读字幕，
   **每轮 ≤5 条**，读满即停，剩下的写进报告「待读队列」。
6. 四维打分（相关性/新奇度/实操价值/新鲜度，各 0-5）：总分 ≥14 才留，新奇度 ≤1 直接砍。
7. 判重：`radar.py seen check <BV>`，SEEN 跳过；处理完 `radar.py seen add …`。
8. 写报告 `state/out/<YYYY-MM-DD>.md`（格式见 SKILL.md），把 0-3 条候选在对话里回报。

时间纪律：这是每 10 分钟一轮的高频巡检，**整轮 8 分钟内必须收尾**，到点立刻停手、
把没读完的写进「待读队列」交下一轮，别让这一轮拖过下一个触发点。
（若把节奏改回按小时，这条改成「12 分钟内收尾」即可。）

红线：只 @ 主号；写操作默认干跑（加 `--yes` 才真发）且现在全关着；兴趣档案不出本机；
不确定的写「没查到」，别编。**一天 0 条是合法输出**，不凑数。正常回 NO_REPLY 式的静默，
只有需要人看的东西才开口。
