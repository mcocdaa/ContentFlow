---
name: bilibili-viral-studio
description: >-
  B站爆款视频生产铁律、16:9高CTR大字封面排版引擎（tech_split 与娱乐向高明度 vivid_scene）、
  100分制客观质量评判门禁（Quality Gate）、竞品对标基准（benchmark）与社区礼仪/AIGC合规规范。
  用于制作或审计 B 站视频、设计封面、对标热门、核验可灵素材与成片流畅度，以及核对定时投稿的创作中心回执。
---

# Bilibili Viral Studio Skill (B站爆款工程与质量门禁规范)

本技能将 ContentFlow 在 B站二次元宅舞、热梗整活与技术科普赛道的实测流水经验，沉淀为 **爆款铁律**、**双模式封面引擎 (`vivid_scene` / `tech_split`)**、**100 分制质量门禁 (`QualityGate`)** 与 **合规礼仪红线**。

---

## 一、 核心创作与运营铁律

### A. 封面与标题（决定信息流点击率 CTR）
1. 娱乐与热梗整活使用高明度 `vivid_scene`。本仓把近黑像素（RGB 最大值小于 45）占比控制在 20% 以下。用同题材近期样本校准平均明度（HSV 的 V 通道，0–255）。历史分区榜样本曾测得 172–195，另两条百万播放同梗样本分别为 157.57 和 158.42。[封面与节奏实测](../../../docs/EVOLUTION_BACKLOG.md#trend-case)
2. 使用 `1920x1080`（16:9）主封面，关键内容放在 4:3 中心安全区（横坐标 240–1680）。打开两种比例的实图，双人片尤其要看两张脸、标题和影响剧情的道具。上传后再看平台返回的封面。
3. 标题点明角色与剧情反差。三行模板用亮金 `#FFD700`、纯白 `#FFFFFF`、赛博青 `#00F0FF` 配 8–10 px 黑描边。双人封面若文字挡脸或遮住关键道具，先缩短文案，再看 4:3 缩略图能否读清。

### B. 前 3 秒钩子、成片时长与舒展镜头节奏
4. **立项黑马预检与时长硬红线（`>= 60.0s`）**：立项前先用 `cli.py breakout-radar`（详见 [bilibili-breakout-radar](../bilibili-breakout-radar/SKILL.md)）扫描 B 站低粉爆款与高留存切口，再结合 `cli.py benchmark --online` 校准题材。自 `018` 期起所有新视频必须按 **`>= 60.0 秒`**（至少 1 分钟）设计剧本与分镜，`VideoQualityGate` 自动拦截 `< 60.0s` 的短片。前 3 秒直接进入剧场反转、动作特写或爆点问题，拒绝站桩 PPT；每期立项须写入 `brief.json` 的 `creative_spec` 并在 `library/creative_ledger.json` 登记防重。
5. **舒展镜头节奏与选择性 Beat Punch-In**：2D 剧场/叙事动画优先采用可灵 4.0 原生多镜头（`prefer_multi_shots=true`，每镜 `3.0–4.0s` 完整表演），默认关闭 `beat_punch_bpm` 数码跳切与高频闪白，确保全片切镜间隔中位数 **`>= 2.5s`**；仅对长于 8 秒且无原生切镜的纯热舞段落，通过 `EpisodeAssembler` (`cli.py assemble-episode`) 适度启用 `beat_punch_bpm` 消除单机位疲劳。
6. **技术流与比例**。交付 `1920x1080`、`SAR=1:1`、`DAR=16:9`、`60.00fps`、`yuv420p`（BT.709）、`-14 LUFS` 立体声 `48kHz AAC` 与 `Noto Sans CJK SC` 字幕。原生程序动画按时间戳逐帧导出；低帧率素材需要补帧时用标准装配器。技术教程按完整操作来定时长，给观众看清失败现象、复现步骤和可保存的结果。实际跟练按墙钟时间走完一轮。可以复用 [025–027 的浏览器演示与素材说明](../../../library/motion_cards/README.md)。

人物封面和动效从画师未变形的原稿取景。两个方向使用同一缩放倍率，换画幅时裁切或留白。桌宠仓的方形应用图标曾在上游把鲸鱼娘脸部纵向拉长约 42%，025 封面与 027 计时器已改用 `art/raw/front.png` 正面全身原画。验收时在同一幅原稿、交付封面和平台回读图上对应双眼与嘴部，比较眼距除以两眼中点到嘴部的距离，再把脸放到相同尺度目检。窄屏网页、独立 HTML 和节目内的小头像也要抽查。[源图与实测方法](../../../library/motion_cards/README.md#换画幅时保留人物比例)

长时间线按全片帧号分段，逐段核对后再装配音轨。[分段导出示例](../../../library/motion_cards/README.md#导出)

**怎样回答“用了可灵 4 吗，画面流畅吗”**

* 把最终装配清单中的每个镜头对应到生成任务。可灵用 `KLING_NONINTERACTIVE=1` 和 `-q` 提交，省略 `--poll`，记下 `generationId` 后退出，到时用 `query_tasks` 单次回收。私下保留提交时的模型、操作类型（如 `image_to_video`）、分辨率及同一任务的 `COMPLETED` 回执。返工时改记实际采用的版本。报告分别写明哪些镜头由可灵生成、是否另做过整片视频润色，以及母版如何补帧。
* 用 `ffprobe` 分别读生成素材和交付 MP4 的分辨率、帧率及显示比例。用最终视频帧的显示时间戳核对帧数、相邻间隔，再用 `ffmpeg` 的 `freezedetect=n=-50dB:d=0.30` 筛查持续至少 0.30 秒的近静止段。结果结合剧情判断，有意停顿可以保留。
* 原速播放成片，再逐帧复看切镜、手部遮挡和两人交接道具处，检查残影、身份串位，以及口播、字幕和画面指向是否一致。改镜头或台词后重新装配，对同一交付文件复测响度和质量门禁，并重看抽帧表及两版封面。

### C. 礼仪与合规红线（一票否决 / 扣分项）
7. **严禁群发 `@股东`**：简介与置顶评论中严禁使用 `@用户名` 群发打扰观众（由 `QualityGate._eval_compliance` 自动检查扣分）；兑现评论区点单仅可在原评论下礼貌单点回复一次。
8. **完整借物表、真实伴奏致谢与声画合规声明**：依据《民法典》第1023条及《人工智能生成合成内容标识办法》，严禁未经授权克隆真人或动漫声优原声，严禁使用商用闭源字体；简介中须以纯文本形式完整致谢角色一创/二设、动作与 BGM 伴奏参考 UP 主（含 BVID）、开源 TTS 与开源字体（`Noto Sans CJK SC`），并显式标注 `GB 45438-2025` AIGC 生成合成声明。优先通过 `core/bgm_hunter.py`（`cli.py fetch-bgm`）提取 `48kHz` 立体声热门伴奏/二创混音，严禁再用单薄纯正弦波蜂鸣充当主音轨。

定时排期先读完创作中心待发队列，以明确日期和时区接在队尾。由一人负责提交和按 BVID 回读，其他人可并行编写脚本、制作封面和校对署名。把本机配音、编码、装配、质量门禁及测试交给同一位成员串行执行。每项重任务启动前检查 `free -m` 中的 `available >= 5000` MiB；本地 TTS 用完即 `close()`。回读时核实排期、审核状态和原生 AI 声明。遇平台返回 `-412` 或 HTTP 412，保留回执，停止脚本提交，转官方创作中心查重并按页面指引处理。[定时投稿与回读](references/scheduled-release.md)

---

## 二、 核心自动化命令（共性工程一律走 CLI）

```bash
# 0. 立项前扫描 B 站低粉爆款 / 黑马赛道（详见 ../bilibili-breakout-radar/SKILL.md）
./.venv/bin/python cli.py breakout-radar --limit 15

# 1. 检索并提取 48kHz 立体声B站热门伴奏 / 二创混音片段（输出自动附带借物表致谢行）
./.venv/bin/python cli.py fetch-bgm --query "大展鸿图 机械舞" --limit 8
./.venv/bin/python cli.py fetch-bgm --bvid BV1veMtzGEHf --start 0.0 --duration 62.0 --output track.wav

# 2. 查询分区榜单线索并测量本地成片。竞品节奏和封面另传 --competitor-video 与 --competitor-cover
./.venv/bin/python cli.py benchmark --project 012 --online

# 3. 渲染高明度 vivid_scene 封面（auto 对舞蹈/整活自动选 vivid_scene，科普选 tech_split）
./.venv/bin/python cli.py design-cover --project 012 --style auto

# 4. 装配 026 的原生 60 FPS 画面与讲解音轨，本期清单采用视频流复制和 -14 LUFS 音频归一化
./.venv/bin/python cli.py assemble-episode --spec projects/026_cover_crop_focus_lab/episode_spec.json

# 5. 运行 100 分制质量门禁（含 >= 60s 时长、技术、音频、视觉、封面与礼仪防重检查，自动释放 pyiqa 显存/内存）
./.venv/bin/python cli.py quality-check --project 012 --threshold 90
```

> [!IMPORTANT]
> **旗舰生成模型与低内存纪律**：可灵文生图/图生图锚点一律用 `kling-image-v3_0_omni`（2k+），图生/文生视频一律用 `kling-video-v4_0`（1080p）或 `kling-video-v3_0_omni`，`motion_control` 用 `kling-video-v3_0`（1080p）；严禁降级用 `v2_6`/`v3_0_turbo`/`v4_0_flash`/`720p`。严禁并发重进程，执行前检查 `free -m`。

> [!NOTE]
> 发布前、热更新封面后或写入 `bilibili_latest.json` 时，严禁在终端日志或仓库文件中明文输出账户真实 `uid`、`uname` 或登录 Cookie。
