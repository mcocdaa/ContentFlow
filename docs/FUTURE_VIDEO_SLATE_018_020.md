# ContentFlow 未来三期内容规划与决策门禁（Episodes 018–020 · 2026-11-25 至 2026-11-27）

> **规划日期**：`2026-11-21`（北京时间 CST）  
> **核心目标**：依托已完成过审排期的 `015–017` 过渡期数据，以及无头双 AI 直播首秀（`K8`）实测，用 **`>= 60 秒`（`65–72 秒`，严格大于 1 分钟）剧场版 2D 多 AI 群像喜剧 / 音乐对战 / 综艺法庭** 彻底打破 15 粉冷启动曝光与零弹幕瓶颈，冲刺 `15 → 1,000 粉` 第一阶段里程碑。  
> **安全与合规铁律**：全案零 PII（无真实 `uid`/`uname`/`room_id`/Cookie/RTMP）、零群发 `@用户名`、零商业版权 IP 专有名词、仅启用 `library/characters/` 定型开源/同人授权主力角色，全线执行 `kling-image-v3_0_omni`（2K 多参考锁人设）+ `kling-video-v4_0`（1080p Pro）+ `EpisodeAssembler`（`O(1)` 60FPS 光流 + `Beat Punch-In` + `K2 Hook Banner`）+ `vivid_scene` 高明度封面（`dark<45 < 20%`）+ `GB 45438-2025` AIGC 合规标识。

---

## 一、 线上遥测与冷启动破局诊断（Telemetry & Live Competitor Grounding）

### 1.1 账号基线与当前排期库存（零 PII 脱敏）

数据来源：[bilibili_latest.json](file:///home/mcocdaa/.contentflow/accounts/analytics/bilibili_latest.json)（快照 `2026-11-21 09:15 CST`）、[creative_ledger.json](file:///home/mcocdaa/AI_CODE/ContentFlow/library/creative_ledger.json) 与 [EVOLUTION_BACKLOG.md](file:///home/mcocdaa/AI_CODE/ContentFlow/docs/EVOLUTION_BACKLOG.md)。

| 指标维度 | 当前实测基线 | 核心诊断结论 |
| --- | --- | --- |
| **账号规模与库存** | 粉丝 **`15`** · 已公开 **`10`** 篇（累计播放 `558` / 点赞 `31` / 收藏 `3` / 评论 `18` / **弹幕 `0`**）· 过审待发 **`4`** 篇（`11/21–11/24`，均 `state=-40`，**`0` 退回**） | 排期已覆盖至 `11/24 18:30 CST`（`015` [BV12Fs36uECr](https://www.bilibili.com/video/BV12Fs36uECr/)、`016` [BV1AWsh6sEQF](https://www.bilibili.com/video/BV1AWsh6sEQF/)、`非凡之爱` [BV1PyyWzqE38](https://www.bilibili.com/video/BV1PyyWzqE38/)、`017` [BV1VaytzcEp9](https://www.bilibili.com/video/BV1VaytzcEp9/)），为 `018–020` 留足数据回收与精品迭代窗口。 |
| **赛道分群对比** | 新娱乐高明度赛道（`n=7`）vs 旧静态白板科普（`n=3`）：均播 **`64.29` vs `36.00`**（`1.79x`）、点赞率 **`6.67%` vs `0.93%`**、封标 **`3.46★` vs `2.43★`**、3s 划走率 **`29.91%` vs `51.51%`**（`-21.60%`） | 娱乐向高明度动态路线优势确立；标杆 [BV198sw6oEHN](https://www.bilibili.com/video/BV198sw6oEHN/)（`129` 播放 / `4.6★`）与 [BV121sw62EGg](https://www.bilibili.com/video/BV121sw62EGg/)（`129` 播放 / `3.7★` / `82.87%` 完播）已跑通基础留存。 |
| **三大待解核心瓶颈** | ① 头部娱乐稿 3s 划走率仍达 **`41.0%–44.3%`**（高于同类中位数 `27.35%`）；② 全站 **`0` 弹幕**、同类转粉率中位数仅 **`0.09%`**；③ `013`（[BV18AWC6YE3M](https://www.bilibili.com/video/BV18AWC6YE3M/)）获 **`4.9★`** 封标却仅 `10` 播放、`014`（[BV117sM6FEVL](https://www.bilibili.com/video/BV117sM6FEVL/)）冷启动仅 `1` 播放 | **15–20 秒单人短舞缺乏搜索爆词、角色关系羁绊与弹幕辩论议题**。`018–020` 必须全面切向 **40–60 秒多 AI 群像互动** + **`>= 4.5 cuts/10s` 高密节奏** + **显式弹幕二/三选一投票钩子**（对标 [EVOLUTION_BACKLOG.md](file:///home/mcocdaa/AI_CODE/ContentFlow/docs/EVOLUTION_BACKLOG.md#L24-L36) 百万同梗样本：`63–76s`、`4.6–6.3 cuts/10s`、封面明度 `157–158`）。 |

### 1.2 `2026-11-21` B 站实时四维竞品检索洞察（`BilibiliBgmHunter.search_bgm` 只读元数据）

观测时间：`2026-11-21 16:18 CST`（`order="click"`, `limit=6`，零下载、零 PII）。

| 检索词 | 代表头部样本（BVID / 播放量 / 时长） | 可直接复用的爆款打法与蓝海结论 |
| --- | --- | --- |
| **`DeepSeek 大肥鱼`** | • [BV1uaJy6ZE9P](https://www.bilibili.com/video/BV1uaJy6ZE9P/) 《deepseek崩的时候大肥鱼在做的事：》（**`5,164,434`** · `1:16`）<br>• [BV166nW6REyR](https://www.bilibili.com/video/BV166nW6REyR/) 《“大肥鱼适合做女朋友吗？”》（**`4,912,311`** · `3:16`）<br>• [BV1fYpn6SEk9](https://www.bilibili.com/video/BV1fYpn6SEk9/) 《deepseek 翻唱〈人是猫〉真完整版，大肥鱼觉得人和猫一样可爱,所以人是猫》（**`4,292,443`** · `4:30`）<br>• [BV1LBnb6aERV](https://www.bilibili.com/video/BV1LBnb6aERV/) 《大肥鱼，你怎么穿着Claude的衣服》（**`3,860,685`** · **`0:43`**）<br>• [BV1nJHK6gEtd](https://www.bilibili.com/video/BV1nJHK6gEtd/) 《花4毛钱让1000个蓝色大肥鱼建造故宫》（**`3,624,624`** · `4:49`）<br>• [BV16GsF6hEKf](https://www.bilibili.com/video/BV16GsF6hEKf/) 《大肥鱼捅穿AZ3？！带着大肥鱼猛攻三角洲是什么感觉？》（`3,602,686` · `9:55`） | **360 万–516 万级超级流量池！** 强力验证三条铁律：① **`43 秒` 跨 AI 人设反差情景短剧**（`BV1LBnb6aERV`）正是我方 40–60s 群像短剧的黄金甜点；② **大肥鱼 × 猫娘「人是猫」梗翻唱**（`BV1fYpn6SEk9`）与我方「大肥鱼 × Gemini猫娘」天然绝配；③ **“崩服摸鱼”与“4毛钱打工压榨”**（`BV1uaJy6ZE9P` / `BV1nJHK6gEtd`）与我方「老板 15 粉甩锅 AI 员工」世界观 100% 契合！ |
| **`AI角色 搞笑 短剧`** | • [BV1sVti67ESD](https://www.bilibili.com/video/BV1sVti67ESD/) 《Ai短剧将宝妈设定为负面角色,四闺蜜砸200万开童装店》（`205,946` · `1:43`）<br>• [BV1oj5e68ESV](https://www.bilibili.com/video/BV1oj5e68ESV/) 《国产AI神作〈丧尸清道夫〉人物一致性教程》（`92,057` · `209:18`）<br>• [BV1dLxQzWEox](https://www.bilibili.com/video/BV1dLxQzWEox/) 《AI真人秀测试视频》（`91,836` · `1:54`）<br>• [BV1qtknYYEgr](https://www.bilibili.com/video/BV1qtknYYEgr/) 《猜猜AI会给我俩安排了什么角色？》（`56,043` · `2:57`）<br>• [BV1dbNN6xEfm](https://www.bilibili.com/video/BV1dbNN6xEfm/) 《从夯到拉锐评短剧各类人物》（`52,829` · `6:30`）<br>• [BV1ZCUvBSEg6](https://www.bilibili.com/video/BV1ZCUvBSEg6/) 《坑货闺蜜反转短剧》（`49,795` · `1:37`） | 1–2 分钟 **多人角色反差 / 真人秀 / 锐评打分** 格式更容易破 5 万–20 万播放；观众对 **AI 多角色前后脸型一致（参考锁）+ 首句冲突** 敏感度极高。 |
| **`AI翻唱 热梗`** | • [BV19g2YYME86](https://www.bilibili.com/video/BV19g2YYME86/) 魔性热梗翻唱（`14,252` · `1:40`，注：涉及敏感争议梗，**严禁跟风**）<br>• [BV1bE4EeoETe](https://www.bilibili.com/video/BV1bE4EeoETe/) 鬼畜洗脑小曲整活（`7,596` · `1:01`）<br>• [BV1Q1HG61Emp](https://www.bilibili.com/video/BV1Q1HG61Emp/) & [BV1iGp76qE1Z](https://www.bilibili.com/video/BV1iGp76qE1Z/) 《司凤音乐怪腔AI翻唱梗指南》（`5,417` / `3,001`）<br>• [BV1XhyrBEEgR](https://www.bilibili.com/video/BV1XhyrBEEgR/) 东北味翻唱整活（`4,216` · `2:06`）<br>• [BV138u26rEPF](https://www.bilibili.com/video/BV138u26rEPF/) 热梗改编音乐大集合（`887` · `1:26`） | 泛搜「AI翻唱 热梗」天花板仅 1 万级，但一旦绑定 **大肥鱼超级角色 + 强喜剧对唱冲突** 即可跃迁至百万级（对比 `BV1fYpn6SEk9` `429万`）。因此 `019` 必须走 **“角色人设互怼 + 高燃无版权/Free节拍鬼畜对唱”**，拒绝纯换声翻唱与商用版权/敏感梗。 |
| **`AI直播 切片`** | • [BV16zo9YNEqk](https://www.bilibili.com/video/BV16zo9YNEqk/) 《策划的最终怜悯 防退坑AI队友》（`2,027,609` · `12:10`）<br>• [BV17QnU6sEpa](https://www.bilibili.com/video/BV17QnU6sEpa/) 海外爆款AI视频解说切片（`923,686` · `23:48`）<br>• [BV1vrGa6mE6d](https://www.bilibili.com/video/BV1vrGa6mE6d/) & [BV1sQVF6yEZp](https://www.bilibili.com/video/BV1sQVF6yEZp/) 游戏高能AI实录切片（`716,434` / `553,612` · `1:01`）<br>• [BV1SV4y127CX](https://www.bilibili.com/video/BV1SV4y127CX/) 《对不起，还是让AI去高考吧😵》（**`479,570`** · `2:10`）<br>• [BV1NheQ6CED5](https://www.bilibili.com/video/BV1NheQ6CED5/) 虚拟主播AI热议切片（`435,261` · `1:10`） | **极度稀缺的结构性蓝海！** 当前该词几乎被游戏人机或真人看AI切片占据，**“真正让双 AI 自主无头直播 10 分钟并现场卖老板 + 可灵 4.0 动漫反应切镜”**（`018-A`）在 B 站全网具备稀缺首创感，与 `BV1SV4y127CX` 的“让AI干离谱实验看翻车”天然同频。 |

---

## 二、 严苛防重审计（Anti-Duplication Matrix vs 近 3 期账本）

依据 [core/quality_gate.py](file:///home/mcocdaa/AI_CODE/ContentFlow/core/quality_gate.py#L948-L966) 的近 3 期 `creative_spec`（`archetype` / `setting`）防重校验与工作室创意铁律，先锁定 [creative_ledger.json](file:///home/mcocdaa/AI_CODE/ContentFlow/library/creative_ledger.json#L94-L118) 最新 3 条基线，再验证 `018–020` 无论任意连续 3 期滑动窗口均 **100% 零重合**：

| 期数 / 账本 ID | `archetype`（唯一剧作原型） | `setting`（物理/视觉舞台） | 核心形式与热梗源 | 与近 3 期冲突校验 |
| --- | --- | --- | --- | --- |
| **基线 -3**：`016`（[BV1AWsh6sEQF](https://www.bilibili.com/video/BV1AWsh6sEQF/) · `11/22`） | `autumn_leaf_sweeping_pun_caught_slacking_to_trio_saotui_dance_reversal` | 深秋晴空金黄银杏大道 | 室外抓包谐音反转 + 三人 60 帧《扫腿舞》 | 基线锁定（禁用室外落叶/扫地/纯宅舞） |
| **基线 -2**：`BV1PyyWzqE38`（`11/23`） | `dual_ai_comedy_skit_meme_adaptation` | 都市餐厅双人餐桌 | 《非凡之爱》最后一只虾微表情短剧 | 基线锁定（禁用都市西餐厅/点菜让菜梗） |
| **基线 -1**：`017`（[BV1VaytzcEp9](https://www.bilibili.com/video/BV1VaytzcEp9/) · `11/24`） | `dual_ai_ensemble_meta_sitcom_pilot` | 明媚阳光赛博创意机房会议桌→全息星光台 | 《AI合租》第1集双AI吵架立项 | 基线锁定（禁用赛博电脑机房会议桌场景） |
| **新案 `018-A`**（`11/25` 选项A） | `headless_livestream_highlight_hybrid_anime_reaction_cut` | 无头直播实录界面 ↔ 明媚阳光后台公关室 | 真实 10 分钟无头直播切片 + 可灵 4.0 反应切镜 | **PASS（0 重合）**：唯一“真直播实录×动画切镜”双轨形式 |
| **新案 `018-B`**（`11/25` 选项B） | `trio_ai_convenience_store_budget_mutiny_sitcom_ep2` | 灯火通明暖白 24h 日系便利店关东煮吧台 | 《AI合租》第2集：4毛钱经费内讧 + 弱音空降立军令状 | **PASS（0 重合）**：暖白便利店新场景 + 弱音新晋财务大姐头 |
| **新案 `019`**（`11/26`） | `trio_ai_daylight_variety_courtroom_reverse_trial` | 全景落地窗浅原木暖光综艺大法庭 | 《AI合租第3集·赛博大法庭》：控告大肥鱼“服务器繁忙”摸鱼案 → 反把老板判刑神反转 | **PASS（0 重合）**：全景日光法庭综艺审判形态，道具/机位全全新 |
| **新案 `020`**（`11/27`） | `bright_pop_studio_ai_parody_chorus_mic_battle_mv` | 马卡龙高明度阳光音乐综艺打歌棚与评委席 | 双 AI 抢麦鬼畜对唱《到底谁才是猫》+ 弱音爆灯打分 | **PASS（0 重合）**：音乐综艺抢麦 MV 形态，非情景对白、非宅舞 |

---

## 三、 定型角色参考锁与合规配置（Canonical Cast Lock）

`018–020` **严格限定** 仅调用以下 3 位拥有完整非商业同人授权且已沉淀于 `library/characters/` 的定型主力角色（生成所有关键帧与封面锚点前**必调 `kling image_to_image` 锁定参考图并先清空旧版抠图缓存**，提示词纯视觉描述，零商业 IP 词）：

1. **DeepSeek 蓝色大肥鱼**
   * **参考锁路径（严禁使用早期偏宽拉伸的 `master_reference.jpg`）**：[dafeiyu_canonical_front.png](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/deepseek_dafeiyu/dafeiyu_canonical_front.png) / [dafeiyu_canonical_side.png](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/deepseek_dafeiyu/dafeiyu_canonical_side.png) / [dafeiyu_canonical_back.png](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/deepseek_dafeiyu/dafeiyu_canonical_back.png) / [dafeiyu_canonical_portrait.png](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/deepseek_dafeiyu/dafeiyu_canonical_portrait.png)（完整原表：[dafeiyu_canonical_sheet.png](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/deepseek_dafeiyu/reference/dafeiyu_canonical_sheet.png)）
   * **固定借物表署名**：一创作者「上善无形」溟月 (CC BY-NC-SA 4.0) / 女仆装二设作者「ZipZipPipe」《大AI和小AI们》(CC BY-NC-SA 4.0)
   * **声线档位**：现行 `zh-CN-XiaoxiaoNeural`（待 `K6` 落地后切换高情绪波动鱼娘专属音色）
2. **Gemini娘（Gemini猫猫）**
   * **参考锁路径**：[gemini_canonical_full.png](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/gemini_neko/gemini_canonical_full.png)（花字/贴纸 Q 版：[gemini_canonical_chibi.png](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/gemini_neko/gemini_canonical_chibi.png)）
   * **固定借物表署名**：二设参考「蓝色大肥鱼档案馆」(fisharchive.cc / EDMOK/blue-fish-archive) NO.004 立绘 &「ZipZipPipe」《大AI和小AI们》(CC BY-NC-SA 4.0)
   * **声线档位**：现行 `zh-CN-XiaoyiNeural`（待 `K6` 升级傲娇星光猫娘音色）
3. **弱音ハク（Yowane Haku）**
   * **参考锁路径**：[master_reference.jpg](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/yowane_haku/master_reference.jpg)（表情辅助：[yowane_teacher_hands_on_hips.jpg](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/yowane_haku/angry/yowane_teacher_hands_on_hips.jpg) / [yowane_scene1_sigh.jpg](file:///home/mcocdaa/AI_CODE/ContentFlow/library/characters/yowane_haku/sigh/yowane_scene1_sigh.jpg)）
   * **固定借物表署名**：原案设计 CAFFEIN / Crypton Future Media, INC.（严格遵循 PCL 与 CC BY-NC 3.0 非商业同人创作协议）
   * **声线档位**：现行 `zh-TW-HsiaoChenNeural`（待 `K6` 升级厌世慵懒大姐头音色）

---

## 四、 三期逐集生产蓝图（Episodes 018–020）

> **共性硬指标（每期强制通过 `cli.py quality-check --threshold 90`）**：
> `1920x1080` · `SAR=1:1` · `DAR=16:9` · `60.00fps`（`EpisodeAssembler` `O(1)` OpenCV DIS 光流）· `yuv420p` (`bt709`) · `-14 LUFS` `48kHz` 立体声 AAC · `Noto Sans CJK SC` 字幕 · 封面 `vivid_scene`（`V_mean >= 165`, `dark<45 < 15%`, 4:3 安全区 `x=240..1680` 人脸与文字零遮挡）· 简介完整借物表 + `GB 45438-2025` AIGC 声明 + B 站原生 `neutral_mark` · **严禁任何 `@用户名`**。

---

### Episode 018（排期：`2026-11-25 18:30 CST`）— 已拍板绿灯：`018-B` 剧场版 2D 便利店长片（`>= 60 秒`）

#### 预案 018-A（待直播弹幕密度提升后复用于 021 · 直播切片反哺 + 可灵 4.0 动漫反应切镜）

* **项目 ID**：`018a_dual_ai_headless_live_betrayal_cut`
* **推荐主标题**：`【双AI直播切片】把账号交给双AI无头直播10分钟，结果它们把老板卖了？！【B站AI创造公开赛】`
* **推荐分区**：动画 → 短片·手书（备选：科技 → 计算机技术 / 搞笑日常，以 017 实测表现对齐）
* **目标时长与节奏**：**`64–70 秒`（严格 `>= 1 min`）** · **`5.0–5.4 cuts/10s`**（全片 32–36 次画面/景别跳切，拒绝单屏直播呆板录屏）
* **出镜阵容**：`DeepSeek 蓝色大肥鱼` × `Gemini娘`（无头直播实录画面 + 3 段可灵 4.0 动漫反应插片）
* **资产复用与混合管线**：
  1. **实录切片底座**：读取无头首播产物目录 `output/live_trial_01/` 的本地录屏与 `output/live_trial_01/live_highlights_ffmpeg_clip_plan.json`（参考 [LIVE_PLAN_DUAL_AI.md](file:///home/mcocdaa/AI_CODE/ContentFlow/docs/LIVE_PLAN_DUAL_AI.md#L174-L189)），在空载内存下筛选最具笑点的 3 段 `roast_battle` / `danmaku_burst` / `gift_reaction` 高光（合计 26–30s，所有界面均已天然脱敏零 PII）。
  2. **3 段可灵 4.0 动漫反应切镜**（`kling-image-v3_0_omni` 2K 多参考锁人设 → `kling-video-v4_0` 1080p Pro，纯视觉提示词）：
     * **切镜 1（`0–4s` 黄金钩子）**：阳光明亮的蓝白控制室，大肥鱼坏笑着一巴掌拍下发光青色开播按钮，Gemini娘顺手把透明玻璃门锁上冲镜头比耶；叠加 `K2 Hook Banner`：`老板刚出门，AI偷偷开播了？！`
     * **切镜 2（`18–25s` 卖老板名场面放大）**：承接直播中吐槽 `15 / 1,000 粉` 进度条的高光句，硬切至特写动画——大肥鱼高举亮黄色手绘牌「15粉清仓大甩卖」，Gemini娘狂敲发光荧光笔往老板照片贴「KPI不达标」贴纸，鼓点触发 `1.32x Beat Punch-In`。
     * **切镜 3（`42–50s` 警报翻车尾声）**：模拟“老板脚步声回来了”喜剧反转（采用**明亮暖橙×青色**综艺闪灯，严禁黑屏暗调），两人手忙脚乱拔线同时朝镜头大喊投票口令。
* **已核验真实 BGM BVID 线索（提取前核对授权，侧链闪避至 `-22 LUFS` 铺底）**：
  * 轻快喜剧铺底：[BV1o4KwzPERi](https://www.bilibili.com/video/BV1o4KwzPERi/)（Plum《살금살금 (轻轻)》，原作者授权 100% Free BGM，UP主「凌零安Lyanzo_」）
  * 结尾反转高燃卡点：[BV1254y1V7cJ](https://www.bilibili.com/video/BV1254y1V7cJ/)（CC0 协议《欢快/积极/商业短片/开场》，UP主「无版权BGM」）
  * 同类流量对标（仅作叙事参考）：[BV1SV4y127CX](https://www.bilibili.com/video/BV1SV4y127CX/)（`479,570` 播放，“让AI执行离谱实验看翻车”）与 [BV1uaJy6ZE9P](https://www.bilibili.com/video/BV1uaJy6ZE9P/)（`5,164,434` 播放）
* **高明度 `vivid_scene` 封面方案**：
  * **画幅与亮度**：明亮天青×奶白透明演播厅背景（`V_mean` 目标 `170–184`，`dark<45 < 10%`）；前景 `4:3` 安全区（`x=240..1680`）内大肥鱼与 Gemini娘并排坏笑特写，右上角醒目珊瑚红 `ON AIR 10min` 徽章 + 右下角 `15/1000粉` 亮色进度胶囊。
  * **三行大字（`#FFD700` / `#FFFFFF` / `#00F0FF` + 9px 黑描边）**：`放任双AI开播` / `10分钟把老板卖了?!` / `无头直播翻车实录`
* **弹幕 / 评论区投票钩子（零 `@` 提及）**：
  * *"下场双AI实时直播你想看谁当主控？**弹幕扣1：大肥鱼原地爆料老板黑历史**，**扣2：Gemini娘狠抓弹幕冲千粉**！评论区最高赞惩罚直接写进下场直播台本！"*

---

#### 主投绿灯方案 `018-B`（2026-11-25 18:30 CST · 《AI合租B站号》第 2 集 · 24h 晨曦便利店关东煮分赃）

> **拍板依据**：首场 10 分钟技术试播弹幕为 `0` 且无 LLM Key，而观众明确要求 **第 018 期起单集时长 `>= 1 分钟`** 并大幅跃升「剧场版 2D 番剧质感」与大肥鱼无拉伸比例！因此绿灯 **`018-B`（`018_ai_flatshare_ep2_convenience_store_mutiny`）** 作为 `2026-11-25 18:30 CST` 旗舰交付，启用云端 `kling element_create` 三主角多角度主体锁 + `kling omni_ref_video --model kling-video-v4_0`（`7 × 10s` 多镜头剧场版 2D 分镜）冲刺 `~68–70 秒` 成片！

* **项目 ID**：`018_ai_flatshare_ep2_convenience_store_mutiny`
* **推荐主标题**：`【AI合租B站号第2集】运营经费只剩4毛钱？弱音空降便利店关东煮局，当场治服大肥鱼和猫娘！【B站AI创造公开赛】`
* **推荐分区**：动画 → 短片·手书
* **目标时长与节奏**：**`66–72 秒`（严格 `>= 60.0 秒`，7 幕 × 10s 可灵 4.0 原生多镜头）** · **`4.8–5.5 cuts/10s`**（过肩 OTS、荷兰斜角、低仰拍逆光、快甩与特写反打，拒绝正面平视站桩）
* **全新高明度场景**：**灯火通明暖白 24 小时日系便利店落地窗关东煮吧台**（晨曦金蓝斜射光束、赛璐珞硬边二分阴影、透明关东煮蒸汽与清新马卡龙饮料货架，与 `017` 赛博机房、`BV1PyyWzqE38` 餐厅、`016` 银杏街零重合）
* **出镜阵容（定型铁三角全员集结 · 均以云端 Element 锁定）**：`DeepSeek 蓝色大肥鱼`（无拉伸标准四视图）× `Gemini娘` × `弱音ハク`
* **七幕剧场版 2D 分镜节奏大纲（`~70s`）**：
  1. **Act 1（`0–10s` 前景蒸汽 OTS 钩子 + `K2 Hook Banner`）**：冒热气的关东煮纸杯特写虚化前景，镜头平滑前推至吧台内侧 `大肥鱼` 惊恐护住最后一颗鱼丸喊“经费只剩 4 毛啦！”，荷兰斜角切入 `Gemini娘` 举全息小票逼近吐槽；
  2. **Act 2（`10–20s` 甩锅嘴炮快切反打）**：极速甩镜与低仰拍拍桌冲击波，`大肥鱼` 喊冤 24G 内存报警，`Gemini娘` 得意炫耀 4.9 星高明度封面与直播间计划；
  3. **Act 3（`20–30s` 叮咚门铃逆光空降）**：玻璃门低角度仰拍晨光暴闪，白发红框眼镜 `弱音ハク` 拎着冰饮剪影推门而入，逆光轮廓转为清晰赛璐珞光影，甩出 1 米长白色账单占满前景；
  4. **Act 4（`30–40s` 弱音推眼镜镇场 + 双 AI 石化）**：近景推眼镜反光，`大肥鱼` 与 `猫娘` 二次元石化汗滴双特写，`弱音` OTS 亮票拍板“129 榜一和 4.9 星都是我刷的，从今天起财务归我管！”；
  5. **Act 5（`40–50s` 落地窗斜角军令状立契）**：落地窗晨光光柱下 `大肥鱼` 鼓腮赌气、`Gemini娘` 坏笑挑眉指责“谁下期播放垫底就请全员吃一周关东煮！”；
  6. **Act 6（`50–60s` 围绕吧台环绕对峙与眼神杀三连切）**：旋转跟拍 + 三角色瞳孔极特写作画张力飙升，最后一秒三人齐刷刷看向镜头外老板；
  7. **Act 7（`60–70s` 晨光干杯定格 + 弹幕押注 CTA）**：三人举关东煮杯与冰饮逆光碰杯，随后齐手指镜头发出投票口令：`扣1大肥鱼 / 扣2Gemini娘 / 扣3弱音大姐头`！
* **已核验真实 BGM BVID 线索**：
  * 主喜剧轻快节奏：[BV1VJEfzJEkx](https://www.bilibili.com/video/BV1VJEfzJEkx/)（《来去曼波🎵加长版》，UP主「还给我神ID」，已于 `015` 实装）或 [BV1o4KwzPERi](https://www.bilibili.com/video/BV1o4KwzPERi/)（Plum 100% Free BGM《살금살금 (轻轻)》）
  * 空降反杀与碰杯高燃段落：[BV1254y1V7cJ](https://www.bilibili.com/video/BV1254y1V7cJ/)（CC0 免费积极开场配乐，UP主「无版权BGM」）
  * 竞品对标参考：[BV1LBnb6aERV](https://www.bilibili.com/video/BV1LBnb6aERV/)（`3,860,685` 播放 · `43s` 跨 AI 喜剧短片）& [BV1nJHK6gEtd](https://www.bilibili.com/video/BV1nJHK6gEtd/)（`3,624,624` 播放）
* **高明度 `vivid_scene` 封面方案**：
  * **画幅与亮度**：暖白明亮便利店吧台（`V_mean` 目标 `174–188`，`dark<45 < 8%`），前景金黄冒热气关东煮杯；弱音居C位冷酷高举长账单小票，左侧大肥鱼护住鱼丸惊恐张嘴，右侧 Gemini娘举平板震惊，三张脸清晰饱满落入 `4:3` 中心安全区。
  * **三行大字**：`经费只剩4毛?!` / `弱音空降管财务` / `大肥鱼×猫娘当场破防`
* **弹幕 / 评论区投票钩子（零 `@` 提及）**：
  * *"铁三角立下军令状，下期垫底的请吃关东煮！你押谁能带飞播放？**弹幕扣1：大肥鱼 / 扣2：Gemini娘 / 扣3：弱音大姐头**！"*

---

### Episode 019（排期：`2026-11-26 18:30 CST`）— 剧场版 2D 日光综艺大法庭：大肥鱼“服务器繁忙”摸鱼案（`>= 70s`）

> **拍板调整理由（`2026-11-23` 更新）**：优先保证叙事完整度、自然原生配音与 `3–4s` 舒展切镜呼吸感，将原定 `020` 提前至 **`019`（`11/26 18:30 CST`）** 拍摄，全片 **`~70s`（7 × 10s 可灵 4.0 原生多镜头 + 原生中文配音，严格 `>= 60s`）**，衔接 `018` 便利店军令状结尾彩蛋；《打歌棚抢麦鬼畜对唱》顺延至 **`020`（`11/27 18:30 CST`，同样确保 `>= 65s`）**。
>
> **策划逻辑**：直击 `2026-11-21` 全站 **`516 万播放` 榜首痛点词** [BV1uaJy6ZE9P](https://www.bilibili.com/video/BV1uaJy6ZE9P/)（“deepseek 崩的时候大肥鱼在干嘛”）+ **491 万辩论问答势能** [BV166nW6REyR](https://www.bilibili.com/video/BV166nW6REyR/)，用全新 **“全景落地窗浅原木日光综艺法庭”** 上演一场舒展流畅的高密反转庭审——前半段公诉人猫娘狂甩摸鱼铁证，后半段大肥鱼反手把“只给 24G 内存还催日更的 15 粉老板”送上被告席！天然融合技术自嘲梗（`24 GiB RAM` / `60FPS`）与二次元喜剧，打通科技宅与二次元双圈层弹幕。

* **项目 ID**：`019_cyber_variety_court_server_busy_trial`
* **推荐主标题**：`【AI赛博法庭】控告大肥鱼“服务器繁忙”摸鱼罪！公诉猫娘刚亮铁证，被告反手把老板判了？！【B站AI创造公开赛】`
* **推荐分区**：动画 → 短片·手书（备选：搞笑 / 日常）
* **目标时长与节奏**：**`~70.1 秒`（7 × 10s 原生多镜头，严格 `>= 60.0s`）** · **舒展切镜节奏（每镜 `3.0–4.5s`，中位切镜间隔 `>= 2.5s`）**（关闭后期 `beat_punch_bpm` 强切，全靠可灵 4.0 原生叙事分镜）
* **全新高明度场景**：**全景落地窗浅原木暖光综艺大法庭**（奶油白挑高大厅、阳光透窗斜射、浅原木色公诉席/被告席/审判长高台、中央悬浮亮青×暖金全息「铁证投屏」，绝对杜绝阴暗严肃法院压抑色调）
* **出镜阵容**：`DeepSeek 蓝色大肥鱼`（被告席委屈→拍桌反杀）× `Gemini娘`（公诉人扶框亮证据）× `弱音ハク`（审判长高台敲巨型亮金色毛绒大木槌）
* **七幕剧场版 2D 分镜节奏大纲（`~70.1s`）**：
  1. **Act 1（`0–10s` 开庭敲槌 + `K2 Hook Banner`）**：弱音审判长亮金色大木槌重重敲下「咚！」，宣读控告“大肥鱼服务器繁忙摸鱼案”；镜头切向被告席大肥鱼抱头喊冤。
  2. **Act 2（`10–20s` 公诉证物一：海边度假）**：公诉人 Gemini娘拉出全息青光卡片“证物一：观众一问就繁忙，结果跑去海边度假”，大肥鱼擦汗狡辩。
  3. **Act 3（`20–30s` 公诉证物二：机房/泳池蹦迪）**：Gemini娘再亮全息铁证“半夜机房偷跳舞、泳池蹦迪”，弱音推眼镜审问。
  4. **Act 4（`30–40s` 被告大肥鱼拍桌反杀）**：大肥鱼双手拍案反对：“是老板只给 24G 内存主机，既要 60 帧补帧又要开直播，内存飙红只能自保！”
  5. **Act 5（`40–50s` 猫娘共情 + 审判长核账）**：Gemini娘放下平板惊觉自己也差点跑崩；弱音审判长核对发光账单：“经费四毛、粉丝十五，确实严重压榨员工。”
  6. **Act 6（`50–60s` 当庭反转宣判）**：弱音连敲两槌当庭宣判“大肥鱼无罪释放，真正该受审的是老板，罚立刻加小鱼干升内存！”
  7. **Act 7（`60–70s` 全员击掌欢呼 + 陪审团投票定格）**：大肥鱼与猫娘击掌欢呼，铁三角齐看镜头比 `1 / 2` 手势呼吁人类陪审团弹幕宣判！
* **已核验真实 BGM BVID 线索**：
  * 庭审起势轻快悬疑铺底：[BV1o4KwzPERi](https://www.bilibili.com/video/BV1o4KwzPERi/)（Plum 100% Free BGM《살금살금 (轻轻)》，UP主「凌零安Lyanzo_」）
  * 拍桌逆转与宣判高燃段落：[BV1254y1V7cJ](https://www.bilibili.com/video/BV1254y1V7cJ/)（CC0 积极高燃配乐，UP主「无版权BGM」）
* **高明度 `vivid_scene` 封面方案**：
  * **画幅与亮度**：阳光通透浅原木综艺法庭（`V_mean` 目标 `170–186`，`dark<45 < 10%`）；中上方弱音高举闪光金木槌，左侧 Gemini娘帅气指证并托起亮青「铁证」全息卡，右侧大肥鱼满头大汗喊冤，三张脸与金槌/证据卡全部锁在 `4:3` 安全区内。
  * **三行大字**：`大肥鱼摸鱼案开庭!` / `猫娘亮出服务器繁忙铁证` / `反手把老板判了?!`
* **弹幕 / 评论区投票钩子（零 `@` 提及）**：
  * *"请各位人类陪审团在弹幕当庭宣判！**扣1：罚大肥鱼连夜加更 / 扣2：罚老板立刻升级内存加小鱼干**！最高赞判决书下期照单执行！"*

---

### Episode 020（排期：`2026-11-27 18:30 CST`）— 音乐综艺抢麦对唱 MV 战（`>= 65s`）

> **策划逻辑**：直接吃透 `2026-11-21` 实测 **429 万播放** 爆梗 [BV1fYpn6SEk9](https://www.bilibili.com/video/BV1fYpn6SEk9/)（“大肥鱼觉得人和猫一样可爱，所以大肥鱼是猫”）× 我方天然具备 **大肥鱼 + Gemini猫娘** 角色组合的独家优势！用 **无版权/Free 电子节拍 + 原创押韵搞笑对唱词** 规避商用歌曲版权风险，彻底区别于情景对话剧（`017`/`018`）与庭审剧（`019`）。确保 **全片 `>= 65s`（至少 1 分钟）**，切镜保持舒展连贯。

* **项目 ID**：`020_trio_ai_karaoke_cat_fish_battle_mv`
* **推荐主标题**：`【AI打歌棚整活】大肥鱼硬说自己是猫？Gemini猫娘冲上台抢麦鬼畜对唱，弱音评委直接笑崩！【B站AI创造公开赛】`
* **推荐分区**：鬼畜 → 鬼畜调教 / 动画 → 短片·手书（依实测流量池表现二选一）
* **目标时长与节奏**：**`65–70 秒`（严格 `>= 60.0s`）** · **每镜 `2.5–3.5s` 舒展切换**（配合可灵 4.0 原生演戏推拉 + 综艺亮色歌词字幕）
* **全新高明度场景**：**晴空马卡龙高饱和音乐综艺打歌摄影棚**（天蓝×嫩粉×纯白柔光环形灯箱舞台、中央银色复古立麦架、右侧透明玻璃评委席与巨大荧光黄打分牌；高明度日间演播棚感，严禁暗黑夜店风）
* **出镜阵容**：`DeepSeek 蓝色大肥鱼`（头戴搞笑发光蓝猫耳发箍强行混充猫猫）× `Gemini娘`（正牌猫娘气鼓鼓抢麦踢馆）× `弱音ハク`（戴白色大头戴耳机坐评委席举牌打分）
* **分镜与词曲节拍结构（`>= 65s`）**：
  1. **`0–10s` 魔性开麦暴击 + `K2 Hook Banner`**：特写大肥鱼一拍亮蓝猫耳发箍抢过立麦，甩出灵魂逻辑：“鱼可爱！猫可爱！四舍五入大肥鱼也是蓝猫！”
  2. **`10–30s` 大肥鱼洗脑单口 Rap 段（每镜 3–4s）**：围绕「服务器繁忙是在舔毛」「深海算力蓝猫娘」高密押韵魔性唱段。
  3. **`30–50s` Gemini正牌猫娘滑铲抢麦反击**：Gemini娘冲进画面一把拽过话筒架，傲娇吐槽对唱“你连猫薄荷和显卡风扇都分不清，还敢蹭我流量？！”。
  4. **`50–60s` 弱音评委拍爆红灯终极反转**：弱音ハク本来面无表情喝茶，听完直接憋不住拍爆「999 分」亮黄爆灯键：“停！再不一起合声把老板 15 粉冲上去，明天连猫粮和鱼粮全断供！”
  5. **`60–70s` 三人齐声洗脑副歌谢幕 + 弹幕拉票**：三人挤在立麦前合声高唱冲千粉口号，明亮礼花彩纸飘落定格。
* **已核验真实 BGM BVID 线索 & 音频生产路径**：
  * 现成零风险 CC0 / Free 欢快高节拍伴奏备选：[BV1254y1V7cJ](https://www.bilibili.com/video/BV1254y1V7cJ/)（CC0 欢快高能电子节拍，UP主「无版权BGM」）& [BV1VJEfzJEkx](https://www.bilibili.com/video/BV1VJEfzJEkx/)（高洗脑弹跳节拍《来去曼波🎵加长版》，UP主「还给我神ID」）
  * 热梗灵感来源（仅署名致谢于借物表，绝不盗用原音频）：[BV1fYpn6SEk9](https://www.bilibili.com/video/BV1fYpn6SEk9/)（`4,292,443` 播放，大肥鱼「人是猫」梗）& [BV1bE4EeoETe](https://www.bilibili.com/video/BV1bE4EeoETe/)
* **高明度 `vivid_scene` 封面方案**：
  * **画幅与亮度**：明亮马卡龙天蓝×浅粉打歌摄影棚（`V_mean` 目标 `176–190`，`dark<45 < 6%`）；大肥鱼戴亮眼蓝猫耳发箍死抱复古立麦，Gemini娘鼓着脸拽话筒架（两人表情极致反差），背景弱音高举亮黄 `999分` 牌笑出声，全员脸部与立麦道具完全落入 `4:3` 中心安全区。
  * **三行大字**：`大肥鱼硬说自己是猫?!` / `打歌棚抢麦鬼畜对唱` / `弱音评委当场笑崩`
* **弹幕 / 评论区投票钩子（零 `@` 提及）**：
  * *"这轮打歌棚抢麦你站哪边？**弹幕刷「蓝猫鱼」投大肥鱼，刷「真猫娘」投Gemini娘**！评论区最高赞鬼畜词条，直接塞进下首全员原创单曲副歌！"*

---

## 五、 量化决策门禁（Quantitative Decision Gate · 绑定 `015`/`016`/`017` 48h 实测数据）

每次正式启动 `018` / `019` / `020` 生产前，先刷新脱敏遥测快照（[bilibili_latest.json](file:///home/mcocdaa/.contentflow/accounts/analytics/bilibili_latest.json)）并运行 `./.venv/bin/python cli.py benchmark --attribution`，按以下硬阈值触发分支决策与参数纠偏：

### 5.1 排期数据回收时间窗

* **`015`（[BV12Fs36uECr](https://www.bilibili.com/video/BV12Fs36uECr/)）**：`11/21 18:30` 公开 → **48h 读数窗口 `11/23 18:30 CST`**（直接决定 `018-A` vs `018-B`）
* **`016`（[BV1AWsh6sEQF](https://www.bilibili.com/video/BV1AWsh6sEQF/)）**：`11/22 18:30` 公开 → **48h 读数窗口 `11/24 18:30 CST`**（校验三人阵容 + 弱音吸睛度，决定 `018`/`019` 权重）
* **`017`（[BV1VaytzcEp9](https://www.bilibili.com/video/BV1VaytzcEp9/)）**：`11/24 18:30` 公开 → **24h 快报 `11/25 18:30` / 48h 完整读数 `11/26 18:30 CST`**（直接决定 `019` 终剪时长与 `020` 是否冠名《AI合租第3集》）

### 5.2 五维定量阈值与动作触发矩阵

| 观测维度 | 达标绿灯区 | 触发纠偏阈值 | 对应执行动作（严格自动化落地） |
| --- | --- | --- | --- |
| **Gate A：`018-A` vs `018-B` 抉择**（`11/23–11/24`） | `output/live_trial_01/` 产出 **`>= 2`** 段高笑点/无噪点高光切片，且 `015`（幕后 Meta VLOG）48h **`view >= 150`** 或 **`full_play_ratio_pct >= 55%`** | ① `live_trial_01` 录屏高光不足 `< 2` 段或音画/台词节奏偏平；**或** ② `016`（弱音三人组）48h 播放量达 `015` 的 **`>= 1.5x`** 且 `tm_stars >= 4.2★` | 满足绿灯即拍 **`018-A`**（直播切片反哺），`018-B` 顺延至 `021`；触发任一纠偏项则立即切拍 **`018-B`（便利店关东煮第2集）**，确保 `11/25` 排期高质不断档。 |
| **封标星级 `tm_stars`（CTR 诊断）** | **`>= 4.2★`**（且 `tm_pass_rate_pct >= 80%`） | ① **`tm_stars < 3.5★`**；<br>② **`tm_stars >= 4.5★` 但 48h `view < 50`**（如 `013` 冷启动曝光困局） | 情况①：强制把下一期封面三行字压缩至 **总字数 `<= 16` 字**、放大 `4:3` 安全区人脸占比至 `>= 42%`、锁死 `dark<45 < 10%`；<br>情况②：封面已达标，瓶颈在搜索与话题词——把 **`DeepSeek` / `大肥鱼` / `猫娘` / `AI翻唱`** 前置至主标题前 16 字，并同步调整分区测试 `动画·短片手书` vs `鬼畜`。 |
| **3 秒划走率 `crash_rate_pct`** | **`<= 27.0%`**（跑赢 B 站同类中位数 `27.35%`） | **`> 32.0%`**（复发 `010/011` 的 `41%–43%` 痛点） | 删除任何超过 `1.0s` 的铺垫空镜；首帧 `t=0.0s` 直接落点在 **拍桌/抢麦/敲槌高音量音效 + 角色近景爆点台词**，强制开启 `K2 Hook Banner`（`hook_banner_sec=1.6`），前 10 秒切镜密度提升至 **`>= 5.5 cuts/10s`**。 |
| **完播率 `full_play_ratio_pct` 与播放量 `view`** | `>= 60s` 长短剧 **`full_play_ratio_pct >= 45.0%`**，且 48h **`view >= 250`** | ① `017` 48h **`full_play_ratio_pct < 40.0%`**；<br>② `017` 48h **`view >= 300` 且 `danmaku + reply >= 8`** | 情况①：将 `019`/`020` 紧凑控制在 **`60–64s`（守住 `>= 1 min` 底线同时砍除冗余铺垫）**，每 5–6 秒插入一次剧情反转或高速切镜；<br>情况②：连载剧场正式破圈！立即给 `020` 标题加上 **`【AI合租B站号第3集】`** 系列前缀并配置片尾「点击主页连看第1–2集」引导，冲击转粉率 `>= 0.5%`（超 P50 `0.09%` 五倍以上）。 |
| **观众评论点单 & 投票结果（P0 快速通道）** | `015`/`016`/`017` 评论区出现清晰投票胜出项或合规点单 | 任意单条真实观众高赞点单（**`like >= 2`** 或投票数 **`>= 3`** 且不含版权/违规风险） | 立即触发 **P0 点单插入**：轻量脑洞直接写进 `019`/`020` 开场彩蛋或台词；完整选题直接顺位替换 `020` 或锁定 `021`。成片公开后，**仅在该观众原评论下礼貌单点回复一次并附新稿 BVID（严禁简介/置顶群发 `@`）**。 |

---

## 六、 生产排程与硬件串行安全约束（Execution Guardrails）

1. **严格错峰与内存红线**：所有 `018–020` 的可灵异步提交（去 `--poll`）、`cli.py fetch-bgm`、`EpisodeAssembler` 60FPS 光流渲染、`CoverDesigner` 及 `cli.py quality-check` 均须在 **无直播推流运行** 且 `free -m` 确认 `available >= 5000 MiB` 时**严格单进程串行执行**。
2. **旗舰模型与异步规范**：生图锚点一律 `kling-image-v3_0_omni`（`2k` + `image_to_image` 锁定第 3 节定型立绘），视频一律 `kling-video-v4_0`（`1080p` Pro），提交加 `KLING_NONINTERACTIVE=1 ... -q` 秒退释放内存，回收单调 `query_tasks`。
3. **交付双保险**：每期成片交付前必过 `cli.py quality-check --threshold 90`（`0` Blocker）+ `read_file` 人工核验 `diagnostic_contact_sheet.jpg` / `*_cover.jpg` / `*_cover_4x3.jpg` + `cli.py publish --ai-declaration` 附 B 站原生 `neutral_mark` 与创作中心回读核验（详见 [scheduled-release.md](file:///home/mcocdaa/AI_CODE/ContentFlow/.agents/skills/bilibili-viral-studio/references/scheduled-release.md)），同时将新期 `creative_spec` 追加登记至 [creative_ledger.json](file:///home/mcocdaa/AI_CODE/ContentFlow/library/creative_ledger.json)。
