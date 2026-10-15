# interest-radar ｜ 兴趣雷达

> 每天替你扫一轮，**只挑真正值得占用你一次注意力的东西**。
> 不是搜索机器人 —— 判据只有一句话：**这条值不值得占用你一次注意力？**

一个 [OpenClaw](https://docs.openclaw.ai) 技能：读你的**兴趣档案** → 按兴趣线（主题 + 邻域）搜 → **读字幕原文**（不看摘要）→ 四维打分 → 判重 → 写日报 → **只把够格的 0-3 条推给你**。

> 用法：**给 agent 看的操作手册在 [`SKILL.md`](SKILL.md)**（命令速查、一轮流程、报告格式）；**判据与红线在 [`templates/charter.md`](templates/charter.md)**（四维打分、阈值、字幕预算）。本 README 只讲它是什么、为什么这么设计。

## 它和"关键词雷达"的区别

关键词雷达找的是"你已经知道自己在关注的领域里的新东西"。
兴趣雷达多两件事：

1. **新奇度**单独占一维 —— 它得能把你带到**邻域**（相关但你没想到），而不是把同一条消息喂你三遍；
2. **反馈回路** —— 你回 👍/👎，权重长在 `weights.json` 里，越跑越准。

## 设计原则（都是踩出来的）

| 原则 | 为什么 |
|---|---|
| **档案一开始是空的** | 脏种子比空种子贵：拿别人的收藏/历史数据当兴趣，只会把噪音训成口味 |
| **宁缺勿滥，一天 0 条是合法输出** | 假阳性是在偷你的注意力，比漏一条贵得多 |
| **只读不写** | 不发评论、不发动态、不互动。只做「读 + 挑 + 汇报」 |
| **只推 0-3 条** | 推的是注意力预算，不是信息量 |
| **字幕预算（一轮 ≤ 8 条）** | 先按标题/简介/时长粗筛，再读字幕；不设预算一轮能烧几万 token |
| **判断归模型，算术归脚本** | 打分是判断，判重/权重/阈值是算术 —— 后者别让模型心算 |

## 快速开始

前置：Python 3.10+；一个 B站小号（**读字幕必须登录**，匿名拿不到字幕）。

```bash
# 1. 导出小号 cookie 到（任一行的 key=value 形式）
#    ~/.openclaw/secrets/bilibili-cookies.txt   ← 至少要有 SESSDATA / bili_jct / buvid3
python3 scripts/radar.py check          # 校验：打印昵称 = 有效

# 2. 把模板放进状态目录，写第一条兴趣线
mkdir -p ~/.openclaw/workspace/interests
cp templates/charter.md templates/profile.md ~/.openclaw/workspace/interests/

# 3. 定时（OpenClaw cron；建议放在模型优惠的谷时段，比如每天 08:00）
#    独立 session + 便宜模型 + 工具白名单 read/write/exec
```

## 命令速查

```bash
R=skills/interest-radar/scripts/radar.py
python3 $R check                                     # cookie 是否有效
python3 $R search --kw "关键词" --num 20 --days 7    # 搜（order: pubdate|click|totalrank）
python3 $R sub BV1xxxxxxxxx                          # 字幕全文；无字幕打印 NO_SUBTITLE
python3 $R seen check BV1xxx                         # SEEN / NEW
python3 $R seen add 2026-10-15 BV1xxx keep 标题       # 记判重
python3 $R feedback --topic "主题" --signal like --bv BV1xxx --score 4
python3 $R stats                                     # 权重汇总 + 已看条数
```

环境变量：`INTERESTS_DIR`（状态目录）、`BILI_COOKIE_FILE`（cookie 文件）。

## 目录结构

```
SKILL.md              技能说明书（给 agent 看的操作手册）
scripts/radar.py      确定性那一半：取数 / 判重 / 记反馈 / 权重
templates/profile.md  兴趣档案模板（空起步）
templates/charter.md  章程模板：判据、四维打分、红线
```

## 红线

- **兴趣档案不出本机**：不进任何公开平台、不进评论、不进外部日志。
- **只读不写**：不评论、不动态、不私信 —— 手上的 cookie 只用于读。
- 不确定的事**不编**，宁可写「没查到」。
- 拿**小号**跑，别拿主号。

## 依赖

纯标准库（`urllib` + `hashlib`），无第三方包。字幕走 B站 官方接口（`x/player/v2` → 字幕 CDN），搜索走 `wbi` 签名接口。

已知限制：搜索接口对数据中心出口 IP 有风控（会返回 `v_voucher`），家宽/住宅 IP 一般没问题；`-412` 是通用风控，脚本会直接报错让你换 IP 或稍后再试。

## 许可证

MIT
