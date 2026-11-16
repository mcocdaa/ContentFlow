---
name: bilibili-viral-studio
description: >-
  B站爆款视频生产铁律、16:9高CTR大字封面排版引擎（tech_split 与娱乐向高明度 vivid_scene）、
  100分制客观质量评判门禁（Quality Gate）、竞品对标基准（benchmark）与社区礼仪/AIGC合规规范。
  当需要制作或审计 B站投稿视频、设计 16:9 爆款封面、运行竞品对标或执行发布前质量门禁时使用。
---

# Bilibili Viral Studio Skill (B站爆款工程与质量门禁规范)

本技能将 ContentFlow 在 B站二次元宅舞、热梗整活与技术科普赛道的实测流水经验，沉淀为 **爆款铁律**、**双模式封面引擎 (`vivid_scene` / `tech_split`)**、**100 分制质量门禁 (`QualityGate`)** 与 **合规礼仪红线**。

---

## 一、 核心创作与运营铁律

### A. 封面与标题（决定信息流点击率 CTR）
1. **娱乐与热梗整活必须使用高明度 `vivid_scene` 模式**：B站百万播放爆款实测封面平均明度在 `172~195`、暗部面积 `< 1%`。严禁给热舞/鬼畜视频套用死黑网格模板；娱乐分类（`宅舞` / `舞蹈` / `鬼畜` / `整活` / `搞笑`）由 `CoverDesigner.design_project_cover` 自动选用 `vivid_scene`，提亮画面并将暗部（`<45`）控制在 `< 20%`（实测 `008/010/011` 仅 `7.1%~9.4%`）。
2. **强制 `1920x1080` (16:9) 横图 + `4:3` 中心安全框**：所有文字、胶囊角标与核心人物重心必须落在 `x: 240..1680` 安全区内；封面渲染与发布后须调用 `read_file` 肉眼复检。
3. **三行撞色粗描边大字 + 叙事反差标题**：首行亮金 `#FFD700`、次行纯白 `#FFFFFF`、末行赛博青 `#00F0FF`，配合 `8~10px` 纯黑描边；标题前置 `【核心IP/身份钩子】` 并带情绪反转标点。

### B. 前 3 秒钩子与节奏动态密度
4. **首帧直入高能冲突，拒绝站桩 PPT**：前 3 秒直接进入剧场反转、动作特写或爆点问题；严禁复用旧模板走老路（每期立项须写入 `brief.json` 的 `creative_spec` 并在 `library/creative_ledger.json` 登记防重）。
5. **Beat Punch-In 多景别切换**：超过 8 秒的舞蹈或表演片段优先通过 `EpisodeAssembler` (`cli.py assemble-episode`) 开启 `beat_punch_bpm`，每 4 拍在全景群舞与 `1.32x` 上半身特写之间卡点切换，消除单机位疲劳。
6. **技术流与比例铁律**：成片严格保持 `1920x1080`、`SAR=1:1`、`DAR=16:9`（绝不横向拉伸人物）、`60.00fps` (`OpenCV DIS Optical Flow`)、`yuv420p` (`bt709`)、`-14 LUFS` 立体声 `48kHz AAC` 与 `Noto Sans CJK SC` 字幕。

### C. 礼仪与合规红线（一票否决 / 扣分项）
7. **严禁群发 `@股东`**：简介与置顶评论中严禁使用 `@用户名` 群发打扰观众（由 `QualityGate._eval_compliance` 自动检查扣分）；兑现评论区点单仅可在原评论下礼貌单点回复一次。
8. **完整借物表与 GB 45438-2025 声明**：简介中以纯文本形式完整致谢角色一创/二设、动作参考 UP 主（含 BVID）、自合成音频/开源 TTS 与开源字体，并显式标注 `GB 45438-2025` AIGC 生成合成声明；严禁商用闭源字体与未经授权的声优声音克隆或版权商业曲库。

---

## 二、 核心自动化命令（共性工程一律走 CLI）

```bash
# 1. 拉取实时榜单并与本地成片/封面做客观对标（检查封面暗部与切镜节奏差距）
./.venv/bin/python cli.py benchmark --project 010 --online

# 2. 渲染高明度 vivid_scene 封面（auto 对舞蹈/整活自动选 vivid_scene，科普选 tech_split）
./.venv/bin/python cli.py design-cover --project 010 --style auto

# 3. 运行统一 60FPS 光流补帧 + 鼓点切镜 + -14 LUFS 成片装配器
./.venv/bin/python cli.py assemble-episode --spec projects/012_demo/episode_spec.json

# 4. 运行 100 分制质量门禁（含技术、音频、视觉、封面与礼仪防重检查）
./.venv/bin/python cli.py quality-check --project 010 --threshold 90
```

> [!NOTE]
> 发布前、热更新封面后或写入 `bilibili_latest.json` 时，严禁在终端日志或仓库文件中明文输出账户真实 `uid`、`uname` 或登录 Cookie。
