---
name: viral-meme-innovation
description: >-
  Guides the 5-step per-episode creative innovation loop (telemetry audit, live Bilibili
  competitor benchmarking, creative_ledger novelty check, beat-synced 60FPS assembly with
  vivid_scene covers, and post-publish retention review) plus idle-cycle workspace Kaizen upgrades.
  Use when designing any brand-new episode or continuously improving the studio workspace.
---

# Per-Episode Viral Innovation & Continuous Kaizen Runbook

本技能规范 ContentFlow「共性工程全自动、每期创意必创新、空闲周期微进化」的完整操作闭环。

## 一、 每期新视频 5 步创新闭环（严禁走老路）

### 第 1 步：线上流水与痛点诊断
* 检查脱敏遥测文件 `/home/mcocdaa/.contentflow/accounts/analytics/bilibili_latest.json`：
  * 识别 `crash_rate_pct`（3秒划走率）、`tm_stars`（封标星级）与 `full_play_ratio_pct`（完播率）的真实瓶颈。
  * 检查是否有未兑现的观众高赞点单评论；兑现后仅在原评论下礼貌单点回复一次，严禁群发 `@股东`。

### 第 2 步：市场调研与爆款横向对标（Benchmarking）
* 运行在线对标拉取 B 站热门赛道头部数据并对比本地指标：
  ```bash
  ./.venv/bin/python cli.py benchmark --project <prev_id> --online
  ```
* 对比爆款关键维度（非只抄话题）：
  * 封面平均明度与暗部面积（高明度亮色、`dark_area < 20%`）
  * 景别切换节奏（`cuts_per_10s >= 1.8`）
  * 情绪声线与节奏峰值（前 3 秒必须出现视觉/听觉强反差钩子）

### 第 3 步：独立构思全新剧场概念与防重检查
* 结合当前全网/B站/抖音最新热梗，确立**全新的角色舞台、反差剧情与音乐节拍**，优选拥有明确非商业同人授权的角色（如 `DeepSeek 蓝色大肥鱼`、`弱音ハク`）。
* 在 `projects/<new_id>/brief.json` 中填写 `creative_spec`（`archetype` / `setting` / `meme_source`），并同步追加到 `library/creative_ledger.json`，确保与近 3 期零重复。
* 检索可灵参考舞步时，必须生成 `1fps` 抽帧联系表并经 `read_file` 确认：单人全身入镜、无镜头跳切、无行人遮挡，且转 16:9 参考时必须等比填充（`force_original_aspect_ratio=decrease`）防止拉伸。

### 第 4 步：共性自动化装配与视觉质检
* 通过可灵 AI 生成 16:9 2K 关键帧锚点与 1080P 动态视频（**严禁并行重负载，调用前检查 `free -m`**；提示词纯视觉描述，不带商业 IP 名）。
* **多景别 60FPS 装配**：配置 `episode_spec.json` 并调用 `./.venv/bin/python cli.py assemble-episode --spec ...`，为中长段落启用 `beat_punch_bpm` 鼓点近景切镜。
* **高明度封面生成**：运行 `./.venv/bin/python cli.py design-cover --project <new_id> --style vivid_scene`。
* **双保险验收**：先跑 `./.venv/bin/python cli.py quality-check --project <new_id> --threshold 90`（`0` Blocker 且 `>= 90` 分），再用 `read_file` 亲自审阅 `diagnostic_contact_sheet.jpg` 与 `*_cover.jpg` / `*_cover_4x3.jpg`。

### 第 5 步：合规投递与下一轮数据回收
* 确认 `bilibili.md` 中零 `@`、借物表与 `GB 45438-2025` 声明完整，然后执行 `cli.py publish`。
* 更新脱敏后的 `bilibili_latest.json`，将已验证的经验写回 `docs/EVOLUTION_BACKLOG.md`。

---

## 二、 空闲时段微进化协议（Idle Kaizen Loop）

当定时排期队列已有 `>= 2` 天未来稿件（或处于空闲巡检窗口）时：
1. 读取 `docs/EVOLUTION_BACKLOG.md`，认领待办队列中的 **1 个小而聚焦的切片**（如 `K1`、`K2`、`K3`）。
2. 在 `core/` 与 `tests/` 中实现该改进，不破坏现有公共 API。
3. 严格串行验证：`ruff format --check .` -> `ruff check .` -> `mypy core cli.py` -> `pytest -q`。
4. 将已完成的改进与实测数据写回 `docs/EVOLUTION_BACKLOG.md`，提交并推送至 `origin main`，确保下一次任意会话自动继承这份进步。
