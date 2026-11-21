# 可灵 4.0 / Omni 剧场版 2D 番剧质感分镜与提示词圣经（Kling Anime Cinematography Playbook）

> **沉淀日期**：`2026-11-21`  
> **适用范围**：ContentFlow Studio 全部可灵 AI（`kling-image-v3_0_omni` / `kling-video-v4_0` / `kling-video-v3_0_omni` / `element_create` / `omni_ref_video`）动画短片、MMD/2D 动效与喜剧番剧制作。  
> **核心铁律**：只描写纯视觉外观、分镜机位、赛璐珞明暗光影、时间轴微表情与物理动效；**严禁出现商业版权动漫/游戏 IP 专有名词**，**严禁泄露真实 PII / `@用户名`**，**严禁降级调用旧代或 `flash`/`720p` 模型**。

---

## 一、 既有短板复盘诊断（为什么 `016` / `017` “精致但还不够番剧顶流”）

直接对比 `projects/016_yowane_ginkgo_saotui_dance/output/diagnostic_contact_sheet.jpg` 与 `projects/017_dafeiyu_gemini_channel_war_ep1/output/diagnostic_contact_sheet.jpg` 实拍抽帧，我们发现了 5 个导致成片“像会动的精美立绘拼盘，而不像 B 站热门 2D 动画大片”的根本问题：

| 诊断维度 | 过去写法（`016` / `017` 实测现状） | B 站百万级热门 2D AI 动画打法（升级目标） |
| --- | --- | --- |
| **1. 机位与空间纵深** | 几乎全程**水平正面平视中景（人物一字排开看镜头）**，像舞台站桩立绘。 | 强叙事机位交替：**OTS 过肩镜头**、**3/4 侧颜透视**、**低角度仰拍**、**荷兰斜角（Dutch Angle）**、**前景道具大光圈虚化遮挡**（增强电影纵深）。 |
| **2. 光影误区（平涂≠高明度）** | 把“避免黑屏封面”误套用到了全片，导致**背景和人物亮部/暗部缺乏赛璐珞二分阴影与强烈轮廓逆光（Rim Light）**，立体感与空气感不足。 | **高明度氛围下仍保留硬边赛璐珞明暗块（Two-Tone Cel Shading）** + **霓虹/暖阳强边缘光** + **丁达尔体积光柱 / 热气雾霭 / 飘尘粒子**（新海诚 / 剧场版番剧质感，整体依然通透绝不发黑）。 |
| **3. 演技与口型脱节** | 先拍哑剧动画再用外部 TTS 事后强贴台词，人物嘴巴开合与情绪台词对不上，缺乏真正“演戏感”。 | 善用 `kling-video-v4_0` 原生 `enable_audio=true` 音画口型同步，或用 `--audio ./voice.mp3` 驱动 `图片1` 角色精准按音频开口说话；提示词必须写清**秒级微表情演变**（瞳孔颤动→咬牙→汗滴→爆笑）。 |
| **4. 切镜方式单一** | 主要依靠 `EpisodeAssembler` 后期数码裁切放大（`Beat Punch-In`）伪造切换，透视角度其实没变。 | 启用 `omni_ref_video` 的 `prefer_multi_shots=true` **原生多镜头语义切镜（0–3s / 3–7s / 7–10s）**，搭配真实透视变化的分镜锚点。 |
| **5. 工具链只用了 20%** | 仅单调 `kling image_to_video` 喂 1 张首帧图，导致动作幅度一大就容易崩设，不得不克制动作幅度。 | 全面启用本机 CLI 实测高阶武器库：**`element_create` 持久化角色多面锁** + **`omni_ref_video`** + **`first_image + keyframe_1..10 + tail_image`** + **`--video` 运镜/舞蹈参考驱动**。 |

---

## 二、 可灵 CLI 实测高阶武器库（已验证本机参数）

以下参数均经 `./vendor/kling_cli/node_modules/.bin/kling ... --help` 实时服务端声明（`who_am_i`）核验确认：

### 2.1 持久化多角度角色锁：`kling element_create`

告别过去单张正面图硬拐侧脸导致崩坏的问题！先将主力角色（`DeepSeek 蓝色大肥鱼`、`Gemini娘`、`弱音ハク`）用正视图（`--cover`）+ 1–3 张侧面/半身/表情图（`--secondary`）注册为云端复用主体（Element），后续用 `element_list` / `element_get` 读取 `id`：

```bash
KLING_NONINTERACTIVE=1 ./vendor/kling_cli/node_modules/.bin/kling element_create \
  --name "角色名" \
  --description "纯视觉外观描述（不含任何商业版权IP词）" \
  --tag 动漫角色 \
  --cover ./canonical_front.png \
  --secondary ./side_or_expr_1.jpg \
  --secondary ./side_or_expr_2.jpg \
  -q
```

* **大肥鱼无拉伸标准四面参考图（严禁沿用旧版偏宽的 `master_reference.jpg`）**：
  * 正视图：`library/characters/deepseek_dafeiyu/dafeiyu_canonical_front.png`（透明抠图版：`dafeiyu_canonical_front_cutout.png`）
  * 侧视图：`library/characters/deepseek_dafeiyu/dafeiyu_canonical_side.png`
  * 背视图：`library/characters/deepseek_dafeiyu/dafeiyu_canonical_back.png`
  * 特写头肩像：`library/characters/deepseek_dafeiyu/dafeiyu_canonical_portrait.png`
* 说明：也支持 `--voice ./sample.mp3` 绑定角色音色，或在 `omni_ref_video` 中通过 `--elements '[{"id":"<ELEMENT_ID>","bindName":"RoleName","type":"image"}]'` 并在提示词中以 **`<<<ELEMENT_ID>>>`** 引用（`kling-video-v4_0` 最多支持 7 个主体、`elements + image + video + audio <= 15`）。

### 2.2 王牌导演接口：`kling omni_ref_video --model kling-video-v4_0`

实测支持的旗舰能力清单：
* **时长与画质**：`--duration 3..30`（推荐 **10 秒**多镜头段或 5–8 秒爆点段）、`--resolution 1080p`（会员亦支持 `4k`）、`--hdr none|hdr`、`--aspectRatio auto|16:9|9:16|1:1`。
* **原生多镜头分镜（必须保持开启）**：`--prefer_multi_shots true`（`v4_0` 默认开启且必须为 `true`），可在单条提示词中用 `[Shot 1 0-3s]` / `[Shot 2 3-7s]` / `[Shot 3 7-10s]` 直接指挥跨机位连续叙事！
* **原生双声道情绪演戏 vs 外部音频口型驱动**：
  * **方案 A（推荐 · 演技最自然）**：`--enable_audio true --keepOriginalSound false`，在提示词中直接写明清脆中文台词、语气情绪与环境音效（如关东煮沸腾咕嘟声、门铃清脆叮咚声、拍桌砰声），由 `v4_0` 原生同步唇形、胸腔呼吸与声画节奏。
  * **方案 B（需要严格固定配音或对口型唱段时）**：通过 `--audio ./voice.mp3 --audio ./music.mp3`（支持最多 3 轨 `audio_1..3`，`5–30s`、`<=50MB`），在提示词写明 `图片1/<<<id>>> 的角色按音频1说话，使用音频2的环境节奏`。
* **参考素材混排槽位**：
  * `--image`（最多 10 张，`图片1..图片10`）：可用于绑定场景参考图、表情参考图、道具图。
  * `--video`（最多 5 段，`视频1..视频5`，每段 `3–30s`）：可用于传入经典 MMD 运镜或 2D 手书节奏参考视频（注意计费按秒叠加输入视频时长，使用前务必精算必要性）。

### 2.3 严控起止帧与关键节拍转场：`kling image_to_video --model kling-video-v4_0`

当某个高难变身、特定手势指认或绝对不能跑偏的首尾转场画面需要精准掌控时，不再只传一张 `--image`，可组合：
* `--image ./start.jpg`（`first_image`）
* `--input keyframe_1=./mid.jpg`（最多支持 `keyframe_1..10`）
* `--tailImage ./end.jpg`（`tail_image`，总图数 `<= 10`，**严禁在 Flash 模型调用**）

---

## 三、 剧场版 2D 动画提示词 6 层黄金公式与词库

放弃“好看、高质量、杰作”这类无效虚词，以及“8K photorealistic”等会毁掉二次元画风的写实词！每条提示词严格按以下 **6 层结构** 与 **时间顺序** 编写（单镜建议 `45–100` 词，多镜连续剧本建议 `100–220` 词）：

```text
[1. 画幅与剧场版2D赛璐珞定调]
+ [2. 景别与单运镜法则 (One-Move Rule / 分镜时间轴)]
+ [3. 空间纵深与通透电影光影 (前景虚化 + 赛璐珞硬边明暗 + 彩色轮廓逆光)]
+ [4. 角色主体 (<<<id>>>/图片X) 与 秒级微表情/肢体演技演变]
+ [5. 次级物理动效 (发丝甩动、衣褶惯性、鱼尾摆动、热气/火花/粉尘粒子)]
+ [6. 原生音频/台词口型提示 + 反塑料/无水印/无字幕洁净约束]
```

### 3.1 必背质感关键词库（压制大模型 3D 塑料偏置）

| 目标维度 | 正向高权重写法（按需组合 2–4 组） | 严禁写入（会破坏 2D 质感） |
| --- | --- | --- |
| **纯粹 2D 番剧质感** | `2D Japanese theatrical cel-shaded anime film`, `crisp clean ink linework`, `expressive Kyoto/Shinkai-inspired anime film aesthetic`, `hand-drawn keyframe animation sakuga`, `distinct two-tone cel shadow blocks` | `photorealistic`, `hyperrealistic`, `3D render`, `Unreal Engine 5`, `CGI`, `Octane`, `wax skin` |
| **明亮但有立体光影** | `bright warm daylight interior balanced with crisp cel-shaded contact shadows`, `luminous cyan and amber rim light tracing silhouettes`, `cinematic shallow depth of field`, `volumetric sunlight shafts and floating dust motes` | `flat white void`, `dark pitch-black scene`, `overexposed washed-out lighting` |
| **动态张力与作画感** | `snappy animation timing with subtle smear frames on fast motion`, `impact shockwave air ripple`, `recoil momentum shifting shoulders`, `comic anime sweat drop and wide startled eyes` | `moving naturally`, `good animation`, `fast erratic camera shaking wildly` |
| **构图洁净护栏（必附文末）** | `Pure 2D cel animation look, zero 3D plastic CGI texture, no on-screen subtitles, no dialogue text boxes, no UI overlays, no logos or watermarks.` | （不可遗漏无字幕/无UI约束，否则带台词提示时模型极易自造乱码字幕条） |

### 3.2 机位与运镜铁律：**One-Move Rule（单镜一运镜）**

1. **禁止在同一镜头混写两个冲突大运镜**（如同时写 `360度环绕 + 急速拉远 + 摇晃` 会直接引发背景融化与五官崩坏）。
2. **多机位必须显式切片**（搭配 `prefer_multi_shots=true`）：
   * **情感积蓄/惊愕特写**：`Continuous slow dolly push-in from medium over-the-shoulder shot to tight close-up on her widening pupils.`
   * **冲突吐槽/喜剧反打**：`Sharp dynamic Dutch-angle snap push toward the gesturing character, foreground prop softly blurred.`
   * **人物气场空降/变身定格**：`Low-angle hero shot tilting upward as morning backlight flares behind her silver hair.`
   * **高燃动作/追逐**：`Smooth lateral tracking shot keeping profile framing crisp as coats and long hair whip backward.`
   * **纯局部作画细节（最像手绘番剧）**：`Locked-off cinematic wide frame; only hair, steam wisps, falling petals, and expressive hand gestures animate crisply.`

### 3.3 秒级演技演变写法（让纸片人“活过来”）

* ❌ **坏写法**：“A 和 B 在便利店吵架，表现得很生气。”（AI 只会僵硬张嘴挥手）
* ✅ **好写法**（按时间点逐拍拆解）：
  * `0.0-1.5s`: `<<<dafeiyu>>> narrows her eyes suspiciously, leans slightly forward over the steaming oden counter, shielding the paper cup with both hands as hot broth steam drifts across the lens.`
  * `1.5-3.0s`: `She widens her pupils in comic shock with a tiny anime sweat drop, shouting in disbelief while tapping the counter twice.`
  * `Physical inertia`: `Long dark-blue twin-tail strands and whale tail sway with delayed overlapping weight when she halts sharply.`

---

## 四、 剧场版 2D 样片实战示范（可直接提交的 `10s` 多镜头样板）

以 `018-B`（24 小时暖白便利店关东煮吧台 · 铁三角冲突反转）为例，以下模板可直接配合 `kling omni_ref_video --model kling-video-v4_0 --resolution 1080p --duration 10 --prefer_multi_shots true --enable_audio true --aspectRatio 16:9` 异步提交测试：

```text
16:9 2D Japanese theatrical cel-shaded anime comedy film, crisp ink linework, distinct two-tone cel shadows and bright luminous rim lighting, hand-painted bright 24h convenience store interior bathed in warm morning sunbeams through floor-to-ceiling windows, zero 3D plastic CGI texture, no subtitles, no UI overlays, no watermarks.

[Shot 1: 0-3s] Over-the-shoulder close-up with shallow depth of field framing a steaming paper cup of oden with one last fishcake in sharp foreground focus while rising white steam curls upward. Camera move: slow continuous dolly push-in past the steam toward <<<dafeiyu>>> clutching the cup protectively, comic panic tightening her eyebrows as her long dark-blue hair and whale tail sway slightly. Stereo audio: bubbling oden broth sound, followed by her panicked crisp Chinese female voice shouting: "只剩四毛经费了，最后一颗鱼丸归我！"

[Shot 2: 3-7s] Sharp snap-cut to a dynamic Dutch-angle medium two-shot across the wooden counter. <<<gemini_neko>>> bursts forward from the side, her heterochromatic pink-and-gold eyes gleaming mischievously as she thrusts a glowing holographic tablet receipt right between them, pointing dramatically while teasing; <<<dafeiyu>>> flinches backward in exaggerated anime shock with dilated pupils and flared fin-ears. Smooth overlapping hair whip and crisp cel-shaded clothes folds. Stereo audio: bright electronic screen chime, followed by her playful teasing Chinese voice: "就这点预算，还偷跑去海边度假呀？"

[Shot 3: 7-10s] Cut to a crisp low-angle doorway shot backlit by radiant pale-blue morning sunlight; a silver-haired woman with red-rimmed glasses (<<<yowane_haku>>>) pushes open the glass convenience store door, silhouetted briefly by golden sun flare before crisp two-tone shading reveals her cool, unimpressed smirk as she holds up an iced drink and long white paper receipt. Camera move: subtle upward hero tilt as sunlight sparkles on glass and dust motes drift. Stereo audio: crisp glass-door chime 'ding-dong', calm low-key Chinese voice: "吵什么，今天起经费全归我管。"
```

> **提示**：实操前先将 `<<<dafeiyu>>>`、`<<<gemini_neko>>>`、`<<<yowane_haku>>>` 替换为 `kling element_create` 返回的真实 `element_id` 并通过 `--elements '[...]'` 绑定；或若暂未建库，亦可用多张定型参考图 `--image ... --image ...` 并改为 `图片1 / 图片2 / 图片3` 对应指代。

---

## 五、 交付验收联动铁律

1. **先跑 10 秒样片再批产**：新剧目开全集前，先用上述模板只生成 **1 条 10 秒多镜头样片**，用 `ffmpeg` 抽 4 帧或 `read_file` 看清人物一致性、口型演戏和 2D 赛璐珞阴影光效后再批量生产其余片段。
2. **严控防崩护栏**：若发现某段原生音频杂音或口型偏差，可立即切换同结构 `omni_ref_video --audio ./line.mp3 --enable_audio false`（外部配音驱动）或退回 `EpisodeAssembler` 精剪配音；成片最终仍必须满足 `1920x1080`、`SAR=1:1`、`DAR=16:9`、`60.00fps`、`yuv420p`、`bt709`、`-14 LUFS` 及 `cli.py quality-check --threshold 90`（`0` 阻断）。
