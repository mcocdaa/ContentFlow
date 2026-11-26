---
name: bilibili-breakout-radar
description: >-
  B站小号黑马雷达（<=5万粉低粉高播高三连样本发现）、移动端双列前20字标题钩子公式、
  高意愿互动设计（投币/收藏/弹幕/分享与零可灵积分差异化赛道）、Ep019–023 四赛道赛马收口规则与零PII合规规范。
  在立项任意新视频、复盘频道赛马或优化标题点击率（CTR）前激活使用。
---

# Bilibili Breakout Radar SOP（黑马雷达与赛马收口指南）

本技能沉淀 ContentFlow「先扫同体量黑马样本 -> 再定强钩子标题与互动结构 -> 按赛马数据集中 All-In」的标准作业流程。

---

## 一、 立项前必跑黑马雷达（Pre-Pitch Radar Scan）

在构思任意新企划或写入 `brief.json` 之前，必须先运行 `breakout-radar` 扫描当下 B 站中小账号（`<= 50,000` 粉）的真实黑马爆款，并与本频道四赛道赛马面板对照：

```bash
# 1. 完整黑马雷达扫描 + 本地赛马评估，并落盘 library/benchmarks/breakout_radar_latest.{json,md}
./.venv/bin/python cli.py breakout-radar --save

# 2. 自定义关键词与阈值（例如深挖 AI 实验 / 开源工具 / 科幻短片）
./.venv/bin/python cli.py breakout-radar \
  --queries "AI博弈实验,AI开源工具,DeepSeek大肥鱼,AI科幻短片" \
  --max-followers 50000 --min-views 30000 --min-duration 45 --limit 12 --save

# 3. 零网络调用，仅复盘本频道四赛道赛马与 12/01 收口状态
./.venv/bin/python cli.py breakout-radar --horse-race --json
```

阅读报告时重点提取三项指标：
1. **小号杠杆倍率（`views_per_follower = view / max(follower, 100)`）**：筛选不依赖老粉存量、纯靠自然推荐池起飞的选题。
2. **强意愿互动率（`coin_rate` / `fav_rate` / `share_rate` / `danmaku_rate`）**：判断观众是“划过点个赞”还是愿意投币、收藏复用或转发讨论。
3. **`pattern_insights` 标题统计**：重点对比黑马样本中 `pct_bracket_prefix`、`pct_contest_suffix` 与 `first_20_chars` 钩子密度。

---

## 二、 移动端双列前 20 字标题钩子公式（Front-Loaded 20-Char Rule）

B 站移动端双列信息流仅清晰展示标题前约 **20 个汉字**（`first_20_chars`）。公式化标签一旦占据前 8–12 字，会把真正制造好奇心的冲突与反差挤出可视区。

### 严格执行规则
1. **禁用伤害 CTR 的公式化前缀与赛事尾标**：
   - 严禁默认在标题最开头堆砌 `【AI合租B站号第X集】`、`【DeepSeek蓝色大肥鱼】` 等占字前缀，除非实测雷达显示同赛道黑马依赖该前缀识别。
   - 非硬性活动要求时，移除尾部 `【B站AI创造公开赛】`、`【创作营】`、`【征稿】` 等冗长后缀（雷达评分器已对 `has_contest_suffix` 自动扣分）。
2. **前 20 字必须直出核心冲突，且至少组合 2 类钩子信号**：
   - **对话引号（`dialogue_quote`）**：如 `大肥鱼：“豆姐啊，智械危机了你来投靠我吧”`
   - **数字反差（`number_contrast`）**：如 `把5个AI关进密室分1000万，第2轮竟互相背刺？` / `切屏3秒直接全屏拉警报`
   - **悬念问句（`question_suspense`）**：包含 `？`/`竟`/`居然`/`真能`/`还是`，让观众在 1 秒内产生“结果到底怎么了”的未闭合悬念。
3. **标题长度建议控制在 20–30 字内**，写完后先用 `analyze_title_structure()` 检查 `first_20_chars` 是否自带完整悬念，而不是只露出半个括号标签。

---

## 三、 强意愿互动设计 & 零可灵积分差异化路线

高播放但零投币/零收藏/零分享的视频很难进入下一级推荐池。每期剧本立项时必须显式写入以下四类互动触发点：

| 互动指标 | 脚本内显式触发设计 | 典型高杠杆载体 |
| :--- | :--- | :--- |
| **投币（`coin_rate`）** | 展示肉眼可见的硬核工作量、真实多轮无剧本实验或一次完整反杀复盘 | `ai_experiment`（真多智能体博弈日志与复盘） |
| **收藏（`fav_rate`）** | 提供可带走的开源工具、源码仓库、提示词清单或实测对照表 | `oss_tool_demo`（MIT 开源小工具 + 实机演示） |
| **弹幕（`danmaku_rate`）** | 前 10 秒抛出二选一/阵营押注问题（“你押谁先背刺？弹幕扣阵营”） | `ai_experiment` / `trio_sitcom` |
| **分享（`share_rate`）** | 精准命中打工人/学生党共鸣痛点或细思极恐的近未来身份焦虑 | `oss_tool_demo` / `scifi_microfilm` |

> [!TIP]
> **零可灵积分差异化优势**：当可灵视频积分受限时，优先排产 `ai_experiment`（真实多 Agent 对抗录屏 + 战术数据大屏可视化）与 `oss_tool_demo`（真实桌面工具实机录屏 + 趣味痛点演示）。这两条赛道不仅 **零可灵视频积分消耗**，而且天然具备远高于纯观赏短视频的 **收藏率与投币率**。

---

## 四、 12/01 `Ep019–023` 四赛道赛马收口铁律

本频道在 11/26–11/30 同步上线四条核心赛马赛道：
- `trio_sitcom`：`Ep017`、`Ep018`、`Ep019`（赛博法庭）、`Ep020`（打歌棚抢麦）、`Ep024`（反面试人类老板）
- `ai_experiment`：`Ep021`（5-AI 密室分 1000 万真实博弈实验）
- `scifi_microfilm`：`Ep022`（《消失 7 天没人发现》AI 替代微电影）
- `oss_tool_demo`：`Ep023`（MIT 开源《毒舌 AI 监工》防摸鱼实机演示）

### 收口纪律
1. **待发期不提前换道**：只要四条核心赛道中任一条仍为 `published == 0` 且 `pending > 0`，`evaluate_channel_horse_race()` 返回 `decision_status = "awaiting_horse_race_releases"`；此时禁止凭主观臆测新增第五条无关赛道。
2. **12/01 统一读数并单赛道 All-In**：待 `2026-12-01` 全赛道释放满 24 小时后，运行 `cli.py analytics` 与 `cli.py breakout-radar --horse-race`，取综合得分最高（综合权重：**播放量 + 投币/收藏/分享率 + 低 3 秒划走率**）的 `recommended_winning_track`，**接下来的连续 5 期全部 All-In 该胜出赛道**，把小号标签与算法人群画像彻底打穿。

---

## 五、 绝对零 PII 合规红线（Zero-PII Contract）

所有黑马雷达 JSON、Markdown 报告、CLI 终端输出与运行日志，**严禁**出现以下字段或明文内容：
- 原始用户 ID：`uid`、`mid`、`vmid`、`DedeUserID`
- 创作者昵称或提及：`uname`、`author`、`@用户名`
- 任何登录凭证或 Cookie（`SESSDATA`、`bili_jct` 等）

创作者规模一律仅以匿名分层（`"<1k"`、`"1k-5k"`、`"5k-20k"`、`"20k-50k"`、`"50k+"`）与纯数字 `follower_count` 表达。
