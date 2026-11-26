# B 站定时投稿与创作中心回读

## 1. 预览实际会进入简介的文字

在项目的 `delivery/bilibili.md` 中使用以下格式。示例分区适用于动画短片，其他题材按实际内容选择。两个方括号小标题都属于简介正文。`## ` 标题会结束当前简介段，投稿器随后可能补上通用致谢，导致具体署名丢失。

```markdown
**主标题**：填写本片标题
**主选分区**：动画 → 短片·手书
**标签**：动画短片，原创动画，剧情，角色互动
**简介**：
填写本片简介。

【借物表 (Credits)】
角色与参考图｜分别填写一创、二设作者的公开署名、原始作品链接及使用条件。
音乐｜填写实际混入成片的曲名、作曲或演奏者、音源发布者、来源链接或 BVID 及使用条件。
梗或动作参考｜填写参考作品、作者与 BVID。如只借鉴动作或构思，说明采用了哪一部分。
配音与字体｜填写实际使用的音源及字体，如 Noto Sans CJK SC。

【AIGC 标识】
本片包含 AI 生成合成画面。按实际情况补充合成声音等内容，并注明 GB 45438-2025。

**置顶评论草稿**：填写供公开后使用的互动问题。
```

将示例内容替换为本片的真实信息。参考图下载站和原作者分别署名，使用条件以原作品为准。提交器会把标题截到 80 字符、标签取前 10 项、简介截到 2000 字符。检查截取后的内容仍含完整借物表与声明，并且简介、标签和评论没有点名打扰观众。

在仓库根目录运行以下离线预览。把参数换成本片的 Markdown 文件。它直接使用投稿器的解析器，输出进入提交范围的字段统计，无需登录。

```bash
./.venv/bin/python - projects/007_deepseek_dafeiyu_phone_number/delivery/bilibili.md <<'PY'
import sys
from pathlib import Path
from core.publisher import MatrixPublisher

source = Path(sys.argv[1]).read_text(encoding="utf-8")
draft = MatrixPublisher.parse_bilibili_markdown(source)
description = draft["description"][:2000]
print("分区 tid", draft["tid"], "标题字数", len(draft["title"]), "提交标签数", len(draft["tags"][:10]))
print("简介字数", len(description), "借物表", "【借物表" in description, "AIGC", "【AIGC" in description)
PY
```

命令自带的 007 稿件属于 MMD·3D，输出 `tid=25`。换用上面的「短片·手书」模板，预期得到 `tid=47` 和 4 个标签。两个布尔值只能确认小标题存在，具体曲名、署名、链接和声明末行还需在私有编辑器中逐项核对。

## 2. 查明队尾，分配北京时间档期

从已登录的创作中心查完整稿件列表，含审核中、定时待发和公开稿。按已有 BVID 查同一项目，再按完整标题查重。列表需翻页，程序入口为 `BilibiliAnalytics.fetch_creator_archives(pn=…, ps=…)`。首屏和本地快照都可能只含部分稿件。核对平台计数、翻至末页，并从稿件详情取未来有效的 `dtime`。查询失败或有已提交稿件的档期未查明时，先完成只读核对。

按每日一稿续排时，以已有排期中最晚的北京时间日期为准，从下一自然日开始依次安排。使用 `YYYY-MM-DDTHH:MM:SS+08:00`，逐稿记录目标时刻和平台实际保存的时刻。单独的 `18:30` 由主机时区解释。当前投稿器对过近的时间保留至少 4 小时 10 分钟提前量。以预演计算的 `dtime` 核对档期，避免无意顺延或同日重叠。

## 3. 预演后提交一次

在仓库根目录设置 `project` 为本期项目标识，`slot` 为已核实的新档期，再做本地预演。

```sh
./.venv/bin/python cli.py publish --project "$project" --platforms bilibili --mode schedule --schedule-at "$slot" --dry-run
```

在本仓 B 站入口，`--dry-run` 对 `--execute-upload` 和 `--remote-schedule` 均有优先级，只在本地写 staging 清单和回执。已提交的项目如只需查看稿件，用第 4 节的只读回查，避免用预演覆盖本地清单。核对清单中的 MP4、两版封面、标题、分区、标签、最终简介及实际选中的上传封面。含 AI 的投稿默认启用 `--ai-declaration`，写入平台原生 `neutral_mark`。简介中的借物表、AIGC 标识和原生声明三项分别检查。[B 站关于 AI 生成内容有序标识的公告](https://www.bilibili.com/opus/1106496554576904197)

确认本次交付已经获得投稿授权，由发布负责人对通过门禁和目检的同一文件、同一档期执行一次：在上面命令中去掉 `--dry-run`。当前 `--mode schedule` 默认尝试真实上传。拿到 BVID 后切换至只读回查；遇到提交超时或空回包，以已有 BVID 或完整标题到创作中心逐页查证。仍无法区分“未受理”和“已受理但回执缺失”时保留待核实状态。回执里的 `one_click_verify_cmd` 包含上传参数，不能将其用作只读核验。

## 4. 以创作中心记录确认排期

| 看到的结果 | 可以确认的进度 |
| --- | --- |
| `scheduled_in_staging_queue` | 文件已在本地排队，平台排期仍待核实 |
| `rejected`、`code=-412` | 平台拒绝本次提交。保留回执并在官方创作中心查同稿，目标档期仍待核实 |
| `scheduled_on_bilibili` 且返回 BVID | 平台已受理，审核和定时时间需回读 |
| 创作中心显示「审核中」 | 已进审核，按页面显示的状态报告 |
| `state=-40` 且显示「通过审核，等待发布」 | 已过审，可按平台的 `dtime` 确认待发时刻 |
| `state=0` 且显示「开放浏览」 | 稿件已公开，可开始跟踪播放与留存 |

在稿件管理中确认只有一条对应投稿。程序化只读检查可用 `BilibiliUploader.verify_archive_submission(aid)`。核对 `code=0`、BVID、`state`、`state_desc`、`dtime_cst`、分区与原生 AI 声明。旧接口曾返回声明 ID `101`，新版网页在 025 上返回 `creation_statement={id:1,content:"含AI生成内容"}`。新版按 ID 和平台保存的声明文本共同核对。审核中按原 BVID 后续回读。

官网投稿成功后，将经过脱敏的单次受理回包证据保留在项目 `output/creator-reconciliation/official-form.json`，记录 `status=accepted`、HTTP 状态 `http`、平台 `code`、`aid`、`bvid`、`requested_dtime`、提交时的 `category`（旧 tid）和 `human_type2`（网页一级分类 ID）。在 `brief.json` 中写明制作意图对应的 `bilibili_web_category`。例如 025 为“知识”，026/027 为“科技数码”。持有实际 BVID 后，在仓库根目录运行以下只读回验，会在本地保存回执和用于目检的线上主封面。

```sh
flock -x /tmp/cf-operations.lock ./.venv/bin/python .agents/skills/bilibili-viral-studio/scripts/schedule_after_queue.py \
  --project "$project" --bvid "$bvid" --schedule-at "$slot" --record-readback
```

守护先查全队列，再按 AID 读取详情。标题逐字核对，标签允许换序，简介只归一空白。新版分类按详情的 `human_type2.name` 对制作意图、`human_type2.id` 对提交值，旧 `tid` 与提交时的兼容字段单独核对。025 详情为“知识”/1010、旧 tid 47，原本地映射为 231。充电看 `data.arc_elec.state`，转载看 `data.archive.no_reprint`。脚本从公开 CDN 取两版封面，与交付图逐一比对宽高比和 RGB 像素差，并记录各自的哈希。打开 `output/creator-reconciliation/online-cover.jpg` 和 `online-cover-4x3.jpg` 目检标题与主体后，按 `delivery/bilibili_verify_receipt.json` 的回读时间和状态交接。

使用队尾守护投递新稿件时，含 `bilibili_web_category` 的企划会先从官网现行分区与声明菜单核对名称、ID，再将 `human_type2`、`creation_statement.id` 和独立的 `cover43` 补入同一个定时请求。旧 `tid` 保留制作稿映射，非商业稿件仍显式设置 `open_elec=0`、`no_reprint=0`。2026-11-26 实测“科技数码”为 1012，“含AI生成内容”为 1。平台只回通用参数错误 21001 时，不据此认定具体字段是拒绝原因。

投稿器会把 staging 清单 `auth_status` 中的账号标识和回执中的 `dede_userid` 脱敏；遥测快照会脱敏本账号标识。该处理仅覆盖指定字段。原始平台响应、评论作者和自由文本可能仍含个人信息。向日志、仓库或对话输出时只取所需字段，例如 BVID、回读时刻、排期、状态和核对结果，跳过登录凭据、账户身份及原始回包。

需要接在现有队尾时，从仓库根目录执行 `./.venv/bin/python .agents/skills/bilibili-viral-studio/scripts/schedule_after_queue.py --project 项目ID --schedule-at YYYY-MM-DDTHH:MM:SS+08:00` 只读核对完整队列与门禁。获准提交后追加 `--submit`。已知稿号可用 `--project 项目ID --bvid BV号` 单独回读。非商业同人会从借物表中的非商声明或 BY-NC 许可识别，也可显式传 `--noncommercial`。受理不明时保留项目 `delivery/bilibili_schedule_receipt.json`，再次运行会按原记录查证。[队尾排期与回读脚本](../scripts/schedule_after_queue.py)

回执为 `pending` 时，只用同一项目参数回查创作中心「稿件管理」的全部状态，以及已知稿号的详情。较早版本的 pending 回执缺少首轮平台返回码，保留原件。上传文件、待转码素材或浏览器草稿本身均不足以认定稿件受理。

### 平台返回 -412 或 HTTP 412

025 的首次脚本请求因 `code=-412` 被拒。后续独立官网投稿才取得 BVID 和排期，最终回执保留了前次拒绝结果。遇同类错误时保留原回执与提交时刻，停止脚本投稿，由发布负责人按完整标题和已有 BVID 查所有状态，并查看草稿。[官方创作中心稿件管理](https://member.bilibili.com/platform/upload-manager/article)

已有对应稿件时，只打开原稿详情核对审核、排期和 AI 声明。只有草稿时，继续该草稿。确认没有对应稿件或草稿，且仍有投稿授权时，在官方网页选择已验收的视频和封面、核对最新队尾、设置带时区的目标档期并填写原生声明。按页面提示完成验证、提交一次，随后回到稿件管理按新 BVID 核对。一时无法登录、验证或查清是否同稿时，保留当前状态，留给有权限的账号操作者处理。

026 实测，等到页面显示「点击上传或将视频拖拽到此区域」再拖入 MP4，出现标题与创作声明输入框后即可编辑。在封面窗口分别上传推荐位 4:3 和个人空间 16:9。打开独立的定时开关，核对日期和时分再点击「立即投稿」，该按钮用于交稿。返回稿件管理，分别核对平台保存的 `dtime` 和审核状态，按两个展示位回看线上封面。

其他明确的参数错误可按脱敏的 `code` 和 `reason` 修正。若原回执为 `rejected`、已修正原因并再次只读确认平台无同稿，才使用 `--submit --retry-rejected` 显式发起一次提交。该参数不适用于上述 412 流程。

### 编辑已排期稿件的双封面

先把新封面中的角色与未变形原画量比，分别查看 16:9 和 4:3。再在稿件管理找到原 BVID 的「编辑」，对应官网路径 `/platform/upload/video/frame?type=edit&bvid=原BVID`。已登录创作中心的 Playwright 页面可在打开编辑器前安装仓库守护。由同一发布负责人持有操作锁，并在已获授权的编辑操作中启用 `execute:true`。[官网双封面编辑守护](../scripts/official_cover_edit.cjs)

```js
const { installCoverEditGuard } = require(scriptPath);
const guard = await installCoverEditGuard(page, projectDirectory, bvid, { execute: true });
await page.goto(guard.editUrl);
```

在原稿编辑器更换首页 4:3 和个人空间 16:9 两个封面，只提交一次「提交修改」。脚本核对原排期、分 P、标题、简介、标签、平台新旧分类、原生创作声明、版权、充电与转载，并从公开 CDN 分别比对提交候选与两张已验收本地图。同步修正同一素材的来源时，可以显式提供 `revisedCredits: {from, to}`，分别为借物表中唯一的原整行和替换整行。此时会逐字符核对其它简介文字，保存完整新简介的哈希。接口受理后运行 `await guard.verify()` 对账。平台尚未回显新图时只做回读，保留 `output/creator-reconciliation/official-cover-edit.json`。随后重新执行既有 BVID 的只读回验并逐张目检。
