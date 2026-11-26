# HTML 动画卡片与可操作演示

第 024 期使用三张可复用版式：带批注的面试照片、透明道具展示、带条件清单的录用通知。它们适合在正片里交代规则、出示证据和揭晓结果。每次绘制只依赖一个以秒计的时间值，拖动进度条与导出视频使用同一画面。

## 用真实操作制作教程

| 示例 | 可复用入口 | 如何核对画面与结果 |
| --- | --- | --- |
| 025　透明 PNG 动画课（180 秒时间线） | [课程画面](../../projects/025_whale_png_motion_lab/design/episode/index.html) · [可独立打开的实验室](../../projects/025_whale_png_motion_lab/delivery/鲸鱼娘透明像素实验室.html) · [取样与动效代码](../../projects/025_whale_png_motion_lab/demo/motion.js) | 切换底色，看半透明发梢和烘进像素的白边；再比较绕脚底与绕图心旋转的差别。课程与工具共同使用 `whaleMotion.sampler`、`pose` 和 `sprite`。 |
| 026　双比例封面裁切（80 秒时间线） | [课程画面](../../projects/026_cover_crop_focus_lab/design/episode/index.html) · [可独立打开的裁图工具](../../projects/026_cover_crop_focus_lab/delivery/双比例封面裁切实验.html) · [共用裁切函数](../../projects/026_cover_crop_focus_lab/demo/crop.js) | 在同一张 1920 × 1080 母图上比较居中起点 240 和示范起点 390。输入焦点 L=460、R=1790，可行起点为 350～460。点导出得到实际 1440 × 1080 PNG。工具可换图。 |
| 027　十分钟专注钟 | [离线单文件与绘制入口](../../projects/027_whale_focus_timer/鲸鱼专注钟.html) · [底图与文字布局数据](../../projects/027_whale_focus_timer/design/clock_layout.json) | 打开 HTML，开始、暂停、继续、重置计时并保存本地速记。`FocusTimer.renderAt(seconds)` 和 `digits(t)` 用于对照指定秒数，`renderBase(i)` 和 `renderCover()` 用于绘制底图和封面。跟练按真实十分钟计时。 |

025、026 都有相同的正片接口。浏览器等待 `window.motionCardsReady` 后，按秒调用 `window.motionCards.draw(t)`。各自的 `design/episode/narration.json` 指定字幕 `text`、起止秒数和可选的读音 `spoken`。画面、语音可分人准备，先冻结同一版台词和时间线。若一句超窗，改写台词并同步更新画面；对照最终音轨抽听开头、数值和结尾。窗内字幕已画进画布时，在装配清单中省略二次烧字幕。

## 素材权利

使用仓库内的演示代码可查 [MIT 协议](../../LICENSE)。作品使用的角色美术、字体和音源各有自己的许可。025、027 的鲸鱼娘角色原案为上善无形，DeepSeek 女仆二设为 ZipZipPipe；桌宠 PNG 来自 pokerface-1224 维护的项目，使用角色相关图片或改编时需遵守 CC BY-NC-SA 4.0，并保留作者、来源、改动说明和许可。026 的同一张面试图还包含 Gemini 娘与弱音ハク，应分别保留各自作者与使用说明。换图、换声音或另作商业用途时，先核对实际使用素材的许可。每期采用的美术、字体、声音和生成方式见该期借物表。[025 借物表](../../projects/025_whale_png_motion_lab/delivery/bilibili.md) · [026 借物表](../../projects/026_cover_crop_focus_lab/delivery/bilibili.md) · [027 借物表](../../projects/027_whale_focus_timer/delivery/bilibili.md)

### 换画幅时保留人物比例

读取图片的原始宽高 `W × H`。完整放入 `w × h` 框时取 `s = min(w/W, h/H)`，以 `W*s × H*s` 绘制，多出的区域留给背景。要铺满时用 `max` 计算统一倍率，再按焦点裁边。比较两种封面时，从同一母图选不同的源矩形。导出后还要看人物或圆形样例，并核对视频的方形像素；仅核对 MP4 的 16:9 标记看不出源图曾被拉宽或拉高。

鲸鱼娘桌宠的 368 × 420 正面全身原稿与 384 × 384 应用图标使用同一张画。对上游两图的眼睛、嘴和头饰做局部纹理匹配，9 处对应点测得横向倍率 1.089、纵向 1.548，图标中的脸被竖向拉长了约 42%。025 在 1920 × 1080 基图上将正面全身原稿等比放大 1.83 倍，人物中心横坐标为 684，再取景排入封面右侧。027 的本地双封面、四张阶段底图和离线工具共用同一原稿与圆形胸像裁框。[正面原稿](https://github.com/pokerface-1224/deepseek-whale-girl-pet/blob/main/art/raw/front.png) · [上游应用图标](https://github.com/pokerface-1224/deepseek-whale-girl-pet/blob/main/icon.png)

复核同一幅画时，先在原稿左右眼与嘴部各选一个能准确重认的像素特征，在两版封面和平台回读图找到同一点。计算两眼间距除以两眼中点到嘴部的距离，再将每张图等比缩放至相同眼距，并排查看嘴部与头饰的位置。025 原稿的比值为 2.171，本地双封面和两张新回读图均为 2.173。需要区分裁边与人物变形时，可再用头饰、衣领等分散位置分别拟合横纵倍率。

026 的原画为 2720 × 1536。上下各取掉 3 像素，再把 2720 × 1530 等比缩放到 1920 × 1080，两个方向倍率均为 12/17。4:3 版本从该母图裁出 1440 × 1080。在窄屏网页中让画布宽度随容器变化，并让高度保持自动。

025 的角色起伏用上下移动和绕支点旋转，绘制宽度由原图宽高比推算。增加呼吸或推进动作时，两个方向始终使用同一缩放倍率。026 的换图检查可用含圆形标记的方图、竖图和超宽图，在开发页与独立工具分别导出两种画幅，量导出 PNG 中同一圆的水平和垂直直径。两者应相等，允许栅格边界取整相差一个像素。

## 更换一期内容

复制 `projects/024_ai_reverse_interview_human_boss/design/interview_cards/` 中的 `index.html` 和 `story.js` 到新项目对应层级。修改网页标题、画布的无障碍描述和 `story.js`。素材地址以 HTML 所在目录为基准。双击 HTML 即可播放。

- `interview` 使用一张完整场景图、两行标题、面试官台词和退回印章。
- `object` 使用带 Alpha 的透明 PNG。不要给素材铺白底，运动轨迹由播放器生成。更换照片、插图或表情时可沿用这个图层。
- `offer` 使用结果图、两项条款和一枚录用印章。三种版式均可重复，卡片时长由 `seconds` 设置。
- `sound` 可省略。有声版指定一条已按时间线剪好的音轨，改变节奏后相应移动声音。片中中文采用 Noto Sans CJK SC，离线机器安装该字体可保持相同排版。

## 导出

导出器需要 Node.js、Playwright 和 FFmpeg。装有 Playwright Chromium 的环境可执行：

```sh
node scripts/render_motion_cards.cjs projects/024_ai_reverse_interview_human_boss/design/interview_cards/index.html output/interview-preview.mp4
```

如复用外部工具环境，可通过 `PLAYWRIGHT_MODULE` 指定已安装的 Playwright 模块，`CHROMIUM_PATH` 指定相应 Chromium 可执行文件。每次输出使用新文件名。导出帧率 60 fps，尺寸 1920×1080。

025、026 的 `episode_spec.json` 给出了项目内画面输入、讲解音轨和最终 MP4 的路径。从仓库根目录核对清单，先生成讲解，再将网页导出到清单指定的画面路径，最后运行 `cli.py assemble-episode --spec <清单路径>`。本机配音、导出、装配和质量门禁串行，启动每项前检查可用内存至少 5000 MiB。[讲解生成器](../../scripts/narrate_motion_cards.py) · [025 装配清单](../../projects/025_whale_png_motion_lab/episode_spec.json) · [026 装配清单](../../projects/026_cover_crop_focus_lab/episode_spec.json)

通用网页导出命令可在输出文件名后追加起帧和结束帧。例如 `0 1800` 覆盖第 0～1799 帧，下一段从 1800 起。两段均用全片帧号计算 `draw(t)`，分别产出无声视频。按帧号顺序拼接、核对总帧数后，再按清单一次装入完整音轨。[网页分段导出器](../../scripts/render_motion_cards.cjs)

027 有四张阶段底图，倒计时用全片帧号计算。仓库根目录执行 `node projects/027_whale_focus_timer/design/render_media.cjs picture`，按每段 30 秒串行编码，600 秒共 20 段，每段 1800 帧。中断后重跑相同命令，脚本核对底图、字体、布局、渲染代码和编码参数的指纹，并逐段检查帧率、包数、时长和色彩参数，通过才复用。纯画面拼成后用同一脚本的 `boundaries` 导出阶段交界帧和首尾帧，核对第 0 帧的 10:00、第 35998 帧的 00:01 和第 35999 帧的 00:00，再按清单配上海浪声。[专注钟媒体脚本](../../projects/027_whale_focus_timer/design/render_media.cjs) · [027 装配清单](../../projects/027_whale_focus_timer/episode_spec.json)

## 本例素材

两张面试场景图来自第 024 期已有关键帧。翻纸、掠过和盖章声为本例制作的立体声拟音。纸飞机为内置 ImageGen 生成，位于 `library/props/folded_resume_plane.png`。生成提示词如下。

> Use case: stylized-concept. Create one reusable transparent PNG prop for an animated graphic-design short: a single beautifully folded ivory paper airplane made from a discarded résumé, flying towards the right with its nose aimed up-right, angled three-quarter top view showing the upper fold and recognisably triangular long wings. A few sparse ultramarine blue thin rule lines printed on the inner wing, a tiny vivid vermilion rectangular ink mark, otherwise unprinted. Crisp warm white paper, delicate folded edges, graphic cel shading with a desaturated pale-blue underside, 1980s Japanese stationery catalogue art direction. The full plane is centered and occupies 78 percent of a landscape canvas with a truly transparent background and generous margin. No floor, no background rectangle, no person, no letters, no legible text, no motion trail, no aura or drop shadow. Cutout subject only.
