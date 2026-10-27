# interest-radar ｜ 兴趣雷达

> 每天替你扫一轮，**只挑真正值得占用你一次注意力的东西**。
> 不是搜索机器人 —— 判据只有一句话：**这条值不值得占用你一次注意力？**

一个 [OpenClaw](https://docs.openclaw.ai) 技能：读你的**兴趣档案** → 按兴趣线（主题 + 邻域）搜 → **读字幕原文**（不看摘要）→ 四维打分 → 判重 → 写日报 → **只把够格的 0-3 条推给你**。

> 用法：**给 agent 看的操作手册在 [`SKILL.md`](SKILL.md)**（命令速查、一轮流程、报告格式）；**判据与红线在 [`templates/charter.md`](templates/charter.md)**（四维打分、阈值、字幕预算口径）。本 README 只讲它是什么、为什么这么设计。

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
| **写操作分档** | 读：无门槛；写：每档都有代码闸（开关 + `--yes` + 敏感词 + 频控 + 白名单）。只 @ 主号、只私信白名单；**自发评论 2026-10-27 老板放权**（不强制 @，小时 ≤3、天不限） |
| **只推 0-3 条** | 推的是注意力预算，不是信息量 |
| **字幕预算（每轮不限，2026-10-27 老板拍板）** | 原为防 token 烧穿设 3 条/轮；老板取消（账号交 AI 运营），粗筛仍保留省 token，但不再卡条数 |
| **判断归模型，算术归脚本** | 打分是判断，判重/权重/阈值是算术 —— 后者别让模型心算 |

## 实测状态（截至 2026-10-27 · commit e028c07）

只列**真跑过**的。证据取自本机状态目录里的账本（`mention-log.jsonl` / `write-log.jsonl`），不是「写完就当能跑」。

| 能力 | 命令 | 状态 | 证据 / 说明 |
|---|---|---|---|
| cookie 校验 | `check` | ✅ 实测 | 打印昵称即有效 |
| 扫码登录 | `scripts/bili_qr_login.py` | ✅ 实测 | 二维码给本人扫，自动换 `SESSDATA` / `bili_jct` |
| wbi 搜索 | `search` | ✅ 实测 | 数据中心出口 IP 会被风控（`v_voucher` / `-412`），家宽正常 |
| 字幕全文 | `sub` | ✅ 实测 | 无字幕打 `NO_SUBTITLE`，不编 |
| 评论区快筛 | `comment-check` | ✅ 实测 | 只提示疑似 AI 水军，**不拦截** |
| 抽帧看画面 | `scripts/frames.py` | ✅ 实测 | 稀疏下载，抽帧结果与全片 md5 一致 |
| @我 / 回复我 | `notify` | ✅ 实测 | 水位线存 `notify-state.json` |
| 私信读取 | `dm` | ✅ 实测 | 只读不回，水位线存 `dm-state.json` |
| 评论 @ 主号 | `reply` | ✅ 实测 67 次 | `mention-log.jsonl`，最近 2026-10-27 18:03 |
| 发动态 | `dynamic` | ✅ 实测 2 次 | `write-log.jsonl`，2026-10-19 |
| 删动态 | `dynamic-del` | ✅ 实测 1 次 | `write-log.jsonl`，2026-10-19 |
| 私信发送 | `msg` | ✅ 实测 1 次 | `write-log.jsonl`，2026-10-19，只发白名单 |
| 自发评论 | `comment` | ⚠️ 已放开、**零真发记录** | 2026-10-27 老板放权（小时 ≤3），账本里还没有 `kind=comment` |
| 陌生人提问草稿 | `draft` | ⚠️ 试点中 | 必须草稿 → 本人审批 → 才发 |
| 活跃度评估 | `engagement` | ✅ 单测覆盖 | 纯统计，无外部依赖 |
| 弹幕 / 置顶评论 / 关注取关 | — | ❌ 不提供 | 有意不做 |

> 这张表会馊。每次改动**连同日期一起更新**；不确定的一律按「未验证」写。

## 测试

```bash
cd scripts && python3 -m unittest discover -s tests -v   # 37 用例 / 零网络 / 零 cookie / <0.1s
```

GitHub Actions 在 push 与 PR 上跑同一套：`.github/workflows/ci.yml`（语法检查 + 单测 + CLI 冒烟）。

## 快速开始

前置：Python 3.10+；一个 B站小号（**读字幕必须登录**，匿名拿不到字幕）。

```bash
# 1. 导出小号 cookie 到（任一行的 key=value 形式）
#    ~/.openclaw/secrets/bilibili-cookies.txt   ← 至少要有 SESSDATA / bili_jct / buvid3
#    cookie 失效（-101）时不用手动导出：跑 scripts/bili_qr_login.py，二维码给本人扫码即换新登录态
python3 scripts/radar.py check          # 校验：打印昵称 = 有效

# 2. 把模板放进状态目录，写第一条兴趣线
mkdir -p ~/.openclaw/workspace/interests
cp templates/charter.md templates/profile.md ~/.openclaw/workspace/interests/

# 3. 定时（OpenClaw cron；建议放在模型优惠的谷时段，比如每天 08:00）
#    独立 session + 便宜模型 + 工具白名单 read/write/exec
```

## 调度：all / 梁文谷

```bash
python3 scripts/apply-cron.py          # 看当前模式
python3 scripts/apply-cron.py all      # 全天每小时
python3 scripts/apply-cron.py valley   # 梁文谷：只在 DeepSeek 谷时的小时跑
```

谷时口径（DeepSeek 官方）：**工作日 9:00-12:00、14:00-18:00 是高峰，其余（含整个周末）都是谷时**。

## 命令速查

```bash
R=skills/interest-radar/scripts/radar.py
python3 $R check                                     # cookie 是否有效
python3 $R search --kw "关键词" --num 20 --days 7    # 搜（order: pubdate|click|totalrank）
python3 $R sub BV1xxxxxxxxx                          # 字幕全文；无字幕打印 NO_SUBTITLE
python3 $R seen check BV1xxx                         # SEEN / NEW
python3 $R seen add 2026-10-15 BV1xxx keep 标题       # 记判重
python3 $R feedback --topic "主题" --signal like|skip|note --bv BV1xxx --score 4
python3 $R stats                                     # 权重汇总 + 已看条数
python3 $R reply --bv BV1xxx [--text "@昵称 …"]        # 评论 @ 主号（默认干跑，--yes 真发）
python3 $R notify --new-only                         # 谁找我：@我的 / 回复我的
python3 $R dm --new-only                             # 私信：新于水位线的（只读不回）
python3 $R dynamic --text "…" [--yes]                 # 发动态（≤200 字，默认干跑）
python3 $R dynamic-del --dyn-id 1260… [--yes]         # 删掉发错的动态
python3 $R msg --mid 239028467 --text "…" [--yes]     # 私信（只准发 allow_mid 白名单）
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
- **写操作分档**（2026-10-19 老板放开发动态/私信）：闸全在代码里——`enabled` 开关、`--yes`、敏感词、频控（动态 ≤3/天、私信 ≤5/天、评论 ≤3/小时，可配）、私信白名单、连续失败自动关。cookie 能写，但口径不变：只 @ 主号、只私信白名单、不发档案内容。
- 不确定的事**不编**，宁可写「没查到」。
- 拿**小号**跑，别拿主号。

## 依赖

纯标准库（`urllib` + `hashlib`），无第三方包。字幕走 B站 官方接口（`x/player/v2` → 字幕 CDN），搜索走 `wbi` 签名接口。

已知限制：搜索接口对数据中心出口 IP 有风控（会返回 `v_voucher`），家宽/住宅 IP 一般没问题；`-412` 是通用风控，脚本会直接报错让你换 IP 或稍后再试。

## 许可证

MIT
