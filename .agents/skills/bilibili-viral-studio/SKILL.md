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

### B. 前 3 秒钩子与节奏动态密度
4. **首帧直入高能冲突，拒绝站桩 PPT**：前 3 秒直接进入剧场反转、动作特写或爆点问题；严禁复用旧模板走老路（每期立项须写入 `brief.json` 的 `creative_spec` 并在 `library/creative_ledger.json` 登记防重）。
5. **Beat Punch-In 多景别切换**：超过 8 秒的舞蹈或表演片段优先通过 `EpisodeAssembler` (`cli.py assemble-episode`) 开启 `beat_punch_bpm`，每 4 拍在全景群舞与 `1.32x` 上半身特写之间卡点切换，消除单机位疲劳。
6. **技术流与比例铁律**：成片严格保持 `1920x1080`、`SAR=1:1`、`DAR=16:9`（绝不横向拉伸人物）、`60.00fps` (`OpenCV DIS Optical Flow`)、`yuv420p` (`bt709`)、`-14 LUFS` 立体声 `48kHz AAC` 与 `Noto Sans CJK SC` 字幕。

**怎样回答“用了可灵 4 吗，画面流畅吗”**

* 把最终装配清单中的每个镜头对应到生成任务。可灵用 `KLING_NONINTERACTIVE=1` 和 `-q` 提交，省略 `--poll`，记下 `generationId` 后退出，到时用 `query_tasks` 单次回收。私下保留提交时的模型、操作类型（如 `image_to_video`）、分辨率及同一任务的 `COMPLETED` 回执。返工时改记实际采用的版本。报告分别写明哪些镜头由可灵生成、是否另做过整片视频润色，以及母版如何补帧。
* 用 `ffprobe` 分别读生成素材和交付 MP4 的分辨率、帧率及显示比例。用最终视频帧的显示时间戳核对帧数、相邻间隔，再用 `ffmpeg` 的 `freezedetect=n=-50dB:d=0.30` 筛查持续至少 0.30 秒的近静止段。结果结合剧情判断，有意停顿可以保留。
* 原速播放成片，再逐帧复看切镜、手部遮挡和两人交接道具处，检查残影、身份串位，以及口播、字幕和画面指向是否一致。改镜头或台词后重新装配，对同一交付文件复测响度和质量门禁，并重看抽帧表及两版封面。

### C. 礼仪与合规红线（一票否决 / 扣分项）
7. **严禁群发 `@股东`**：简介与置顶评论中严禁使用 `@用户名` 群发打扰观众（由 `QualityGate._eval_compliance` 自动检查扣分）；兑现评论区点单仅可在原评论下礼貌单点回复一次。
8. **完整借物表、真实伴奏致谢与 GB 45438-2025 声明**：简介中以纯文本形式完整致谢角色一创/二设、动作与 BGM 伴奏参考 UP 主（含 BVID）、开源 TTS 与开源字体，并显式标注 `GB 45438-2025` AIGC 生成合成声明；优先通过 `core/bgm_hunter.py`（`cli.py fetch-bgm`）提取 `48kHz` 立体声热门伴奏/二创混音，严禁再用单薄纯正弦波蜂鸣充当热舞主音轨，严禁商用闭源字体或未授权声优克隆。

定时投稿时核对解析后的简介、B 站原生 AI 声明和创作中心的稿件详情。模板、发布入口差异及审核状态见[定时投稿与回读](references/scheduled-release.md)。

---

## 二、 核心自动化命令（共性工程一律走 CLI）

```bash
# 0. 检索并提取 48kHz 立体声B站热门伴奏 / 二创混音片段（输出自动附带借物表致谢行）
./.venv/bin/python cli.py fetch-bgm --query "大展鸿图 机械舞" --limit 8
./.venv/bin/python cli.py fetch-bgm --bvid BV1veMtzGEHf --start 0.0 --duration 14.8 --output track.wav

# 1. 查询分区榜单线索并测量本地成片。竞品节奏和封面另传 --competitor-video 与 --competitor-cover
./.venv/bin/python cli.py benchmark --project 012 --online

# 2. 渲染高明度 vivid_scene 封面（auto 对舞蹈/整活自动选 vivid_scene，科普选 tech_split）
./.venv/bin/python cli.py design-cover --project 012 --style auto

# 3. 运行 O(1) 流式 60FPS 光流补帧 + 鼓点切镜 + -14 LUFS 成片装配器
./.venv/bin/python cli.py assemble-episode --spec projects/012_demo/episode_spec.json

# 4. 运行 100 分制质量门禁（含技术、音频、视觉、封面与礼仪防重检查，自动释放 pyiqa 显存/内存）
./.venv/bin/python cli.py quality-check --project 012 --threshold 90
```

> [!IMPORTANT]
> **旗舰生成模型与低内存纪律**：可灵文生图/图生图锚点一律用 `kling-image-v3_0_omni`（2k+），图生/文生视频一律用 `kling-video-v4_0`（1080p）或 `kling-video-v3_0_omni`，`motion_control` 用 `kling-video-v3_0`（1080p）；严禁降级用 `v2_6`/`v3_0_turbo`/`v4_0_flash`/`720p`。严禁并发重进程，执行前检查 `free -m`。

> [!NOTE]
> 发布前、热更新封面后或写入 `bilibili_latest.json` 时，严禁在终端日志或仓库文件中明文输出账户真实 `uid`、`uname` 或登录 Cookie。
