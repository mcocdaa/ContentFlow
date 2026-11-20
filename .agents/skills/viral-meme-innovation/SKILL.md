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

* 用 `./.venv/bin/python cli.py benchmark --project "$PROJECT_ID" --online` 找题材线索。到 B 站稿件详情（`/x/web-interface/view`）核对每条的 BVID、投稿时间和播放量，记下带时区的观测时间。分区榜出现旧稿时，按梗名搜索近期投稿。优先找同角色或同梗作品，再找不同作者把该梗带到其他圈层的作品。判断普遍热度时，也看同期普通投稿的表现。
* 用允许本地分析的竞品 MP4 和封面，实测节奏与明暗。逐条执行下列命令。记录样本清晰度、时长、前 3 秒的动作或声音钩子。片长差异大时，另取与本片等长的开头按同一方法测量。

  ```bash
  ./.venv/bin/python cli.py benchmark --project "$PROJECT_ID" \
    --competitor-video "$PEER_MP4" --competitor-cover "$PEER_COVER" --no-save --json
  ```

* `competitor_metrics.video.cuts_per_10s` 以约 4 fps 采样，大幅推近和构图变化也会计数。`1.8` 是本仓对时长至少 8 秒成片的低节奏告警值。选题时写下本期沿用哪个钩子、改动什么，实际点击和留存等发布后验证。[同梗样本实测](../../../docs/EVOLUTION_BACKLOG.md#trend-case)

### 第 3 步：独立构思全新剧场概念与防重检查
* 结合当前全网/B站/抖音最新热梗，确立**全新的角色舞台、反差剧情与音乐节拍**，优选拥有明确非商业同人授权的角色（如 `DeepSeek 蓝色大肥鱼`、`弱音ハク`）。
* 在 `projects/<new_id>/brief.json` 中填写 `creative_spec`（`archetype` / `setting` / `meme_source`），并同步追加到 `library/creative_ledger.json`，确保与近 3 期零重复。
* 双角色合做一篇时，让两人围绕同一件事互动。已定型的角色从 `library/characters/` 取参考图，新角色先找作者发布的立绘或三视图，分别记下一创、二设署名和使用条件。用两人的参考图生成同一张关键帧，逐镜核对左右站位、发色配饰和关键道具，尤其是换手、遮挡与反打之后。
* 检索可灵参考舞步时，必须生成 `1fps` 抽帧联系表并经 `read_file` 确认：单人全身入镜、无镜头跳切、无行人遮挡，且转 16:9 参考时必须等比填充（`force_original_aspect_ratio=decrease`）防止拉伸。

### 第 4 步：共性自动化装配与视觉质检
* **旗舰模型与纯视觉提示词**：通过可灵 AI 旗舰模型生成素材（锚点 `kling-image-v3_0_omni` 2k、I2V/T2V `kling-video-v4_0` 1080p、`motion_control` `kling-video-v3_0` 1080p；**严禁降级使用 `v2_6`/`v3_0_turbo`/`v4_0_flash`/`720p`**；提示词纯视觉描述，不带商业 IP 名；调用前检查 `free -m`，严禁并发重负载）。
* 选用热门音轨前，核对原曲和实际录音的使用条件，确认允许本次剪辑与投稿。用 `./.venv/bin/python cli.py fetch-bgm` 提取获准使用的片段（48 kHz 立体声 WAV），侧链混音后，在借物表中填入最终使用的曲名、署名和音源链接。只借鉴剧情的热门视频写入梗来源。
* **O(1) 低内存多景别 60FPS 装配**：配置 `episode_spec.json` 并调用 `./.venv/bin/python cli.py assemble-episode --spec ...`（流式两帧滑窗 `< 45 MiB` 内存），为中长段落启用 `beat_punch_bpm` 鼓点近景切镜。
* **高明度封面生成**：运行 `./.venv/bin/python cli.py design-cover --project <new_id> --style vivid_scene`。
* **双保险验收**：先跑 `./.venv/bin/python cli.py quality-check --project <new_id> --threshold 90`（`0` Blocker 且 `>= 90` 分，自动释放 PyTorch 显存与内存），再用 `read_file` 亲自审阅 `diagnostic_contact_sheet.jpg` 与 `*_cover.jpg` / `*_cover_4x3.jpg`。

### 第 5 步：合规投递与下一轮数据回收
* 定时投稿前解析 `delivery/bilibili.md`，核对实际采用的 BGM、角色署名与 AIGC 声明。提交后按创作中心回读的状态和时间记录排期。[定时投稿与回读](../bilibili-viral-studio/references/scheduled-release.md)
* 公开后用脱敏的 `bilibili_latest.json` 回看 3 秒划走率、完播率和封标星级，将与本期选题假设相关的结果写回 `docs/EVOLUTION_BACKLOG.md`。

---

## 二、 空闲时段微进化协议（Idle Kaizen Loop）

当定时排期队列已有 `>= 2` 天未来稿件（或处于空闲巡检窗口）时：
1. 读取 `docs/EVOLUTION_BACKLOG.md`，认领待办队列中的 **1 个小而聚焦的切片**（如 `K1`、`K2`、`K3`）。
2. 在 `core/` 与 `tests/` 中实现该改进，不破坏现有公共 API。
3. 严格串行验证：`ruff format --check .` -> `ruff check .` -> `mypy core cli.py` -> `pytest -q`。
4. 将已完成的改进与实测数据写回 `docs/EVOLUTION_BACKLOG.md`，提交并推送至 `origin main`，确保下一次任意会话自动继承这份进步。
