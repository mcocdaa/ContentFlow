"""Universal Multi-Platform Copywriting Generator.
Generates tailored, high-converting, and technically accurate copy packages
for WeChat, Xiaohongshu, Zhihu, V2EX, Release Notes, and Video Scripts.
"""

from typing import List
from .models import FactSheet, ContentPackage, StoryboardScene
from .html_formatter import markdown_to_wechat_html


class CopywritingEngine:
    """Universal copywriting generator driven by structured FactSheets."""

    def __init__(self, theme_name: str = "tech_blue"):
        self.theme_name = theme_name

    def generate_all(self, facts: FactSheet) -> ContentPackage:
        """Generates all channel copy assets for a given FactSheet."""
        wechat_md = self.generate_wechat(facts)
        wechat_html = markdown_to_wechat_html(wechat_md, self.theme_name)
        xhs = self.generate_xiaohongshu(facts)
        zhihu = self.generate_zhihu(facts)
        v2ex = self.generate_v2ex(facts)
        release = self.generate_release_notes(facts)
        video_script, scenes = self.generate_video_script_and_scenes(facts)

        return ContentPackage(
            project_id=facts.project_id,
            wechat_md=wechat_md,
            wechat_html=wechat_html,
            xiaohongshu=xhs,
            zhihu=zhihu,
            v2ex=v2ex,
            release=release,
            video_script=video_script,
            scenes=scenes,
        )

    def generate_wechat(self, f: FactSheet) -> str:
        """Generates a deep, narrative-driven WeChat Official Account article."""
        pain_list = "\n".join(f"- **痛点 {i + 1}**：{p}" for i, p in enumerate(f.pain_points))
        sol_list = "\n".join(f"- **方案 {i + 1}**：{s}" for i, s in enumerate(f.solutions))
        feat_blocks = []
        for i, feat in enumerate(f.key_features):
            feat_blocks.append(f"### {i + 1}. {feat.name} —— {feat.headline}\n\n{feat.detail}\n")
        features_str = "\n".join(feat_blocks)
        tech_str = "、".join(f.tech_stack) if f.tech_stack else "现代云原生架构"
        target_str = "、".join(f.target_audience) if f.target_audience else "技术开发者与产品团队"
        cta_str = f.call_to_action or "欢迎在 GitHub 关注项目最新动态，或在评论区留下你对这一方案的看法与建议！"

        doc = f"""# 告别繁琐与失控：{f.name} 如何重塑 {f.category} 生产力

> 核心导读：在当今快节奏的研发与业务环境中，{f.tagline} 已不仅是一个工具升级，而是一次工作范式的系统性解耦与重构。

---

## 一、 为什么传统的方案总让人疲惫不堪？

在实际业务场景中，我们经常能看到这样的景象：

{pain_list}

很多团队不是没有尝试过现有工具，但往往陷入“要么过于沉重难以维护，要么功能残缺无法落地”的尴尬境地。当工具本身的维护成本超过了它创造的价值，开发者和业务人员就不得不将大量精力浪费在低价值的胶水代码和重复手工操作上。

## 二、 {f.name} 的核心破局思路

面对上述顽疾，**{f.name}** 给出的解法不是简单的修修补补，而是从第一性原理出发，提供确定性、高复用与轻量化的整体方案：

{sol_list}

不同于市面上盲目堆砌概念的产品，{f.name} 坚持**“把简单做到极致，把确定性留给用户”**。技术底座选用 `{tech_str}`，既保障了毫秒级的响应与极低资源消耗，又具备极致的扩展能力。

---

## 三、 深度拆解：{f.name} 的核心特性与实战表现

{features_str}

## 四、 谁能从中获得最大收益？

{f.name} 专为以下群体与场景深度打磨：
- **适用人群**：{target_str}
- **典型收益**：
  1. **零心智负担**：告别繁琐的前置依赖，开箱即用；
  2. **高保真可追溯**：全流程可观测、可回溯、可干预；
  3. **生态兼容**：无缝融入现有流水线与技术基础设施。

---

## 五、 结语与未来演进

工具的终极价值，是让创造者专注于创造本身。{f.description}

{cta_str}

**互动话题**：你在当前场景中遇到过最棘手的问题是什么？欢迎在留言区与我们深入交流。
"""
        return doc.strip()

    def generate_xiaohongshu(self, f: FactSheet) -> str:
        """Generates punchy, highly engaging Xiaohongshu card script."""
        pains_summary = " / ".join(f.pain_points[:3]) if f.pain_points else "效率低下、手工繁琐"
        pain_items = "".join(f"❌ {p}\n" for p in f.pain_points[:3])
        audience_items = "".join(f"👉 {a}\n" for a in f.target_audience[:3])
        features = "\n".join(f"✨ **{item.name}**：{item.headline}" for item in f.key_features[:4])
        cta = f.call_to_action or "收藏起来防走丢，需要的宝子留言或者点个赞吧~"

        doc = f"""📌 建议标题候选：
1. 狠狠吹爆！这才是降维打击的 {f.name} 生产力神器 🚀
2. 被繁琐工作折磨疯了？试试这个开源解法，直接起飞！
3. 程序员/效率控必看：{f.tagline}，彻底告别加班

---

【视觉首图排版建议】
- 风格：极简深色背景 + 亮色大标题字
- 核心大字：“告别 {pains_summary}！”
- 副标题：“{f.name} | {f.tagline}”

---

【笔记正文】
谁懂啊家人门！😭 之前做项目一直被折磨：
{pain_items}

直到挖到了这个神仙项目 **{f.name}**，简直是把痛点按在地上摩擦！体验直接拉满 👇

💡 **核心杀手锏盘点**：
{features}

🎯 **适合谁用？**
{audience_items}

🛠️ **上手门槛**：
不仅完全开源，而且架构极其轻量，支持一键开箱即用，拒绝笨重繁杂配置！

{cta}

---
#效率工具 #程序员日常 #开源分享 #独立开发 #{f.category} #{f.name}
"""
        return doc.strip()

    def generate_zhihu(self, f: FactSheet) -> str:
        """Generates analytical, technically rigorous Zhihu article/answer."""
        pains_str = "".join(
            f"{i + 1}. **{p}**：在传统方案中往往难以兼顾开发成本与运维可靠性；\n" for i, p in enumerate(f.pain_points)
        )
        sols_str = "".join(f"- **{s}**\n" for s in f.solutions)
        tech_str = ", ".join(f.tech_stack)
        aud_str = ", ".join(f.target_audience)
        feat_rows = "".join(
            f"| **{item.name}** | {item.headline} | {item.detail[:40]}... |\n" for item in f.key_features
        )

        doc = f"""# 如何评价 {f.name}？它解决了 {f.category} 领域的哪些核心痛点？

在当前的技术与工程实践中，{f.tagline} 正在成为很多研发团队与独立开发者的刚需。本文将从**设计理念、技术选型、核心机制与落地边界**四个维度展开客观评析。

---

### 一、 核心痛点与问题本质

在谈论 {f.name} 之前，我们必须厘清该领域长期存在的本质矛盾：

{pains_str}

很多所谓的“一站式平台”往往存在严重的过度设计问题，引入了海量外部服务与重型依赖，导致中小型团队在冷启动和定制扩展时不堪重负。

---

### 二、 {f.name} 的架构设计与核心解法

{f.name} 的核心定位是：**{f.description}**。

在架构设计上，它采取了务实的工程策略：
{sols_str}

在技术底座方面，选用 `{tech_str}`，保障了高效的本地执行与确定性行为。

---

### 三、 核心特性矩阵

| 特性模块 | 核心能力 | 实际收益 |
| :--- | :--- | :--- |
{feat_rows}

---

### 四、 客观评价与适用边界

没有银弹工具。{f.name} 的核心优势在于**轻量、确定性、高可用与直观体验**。
- **最佳适用场景**：{aud_str}，追求敏捷、可自托管、可深度定制的场景。
- **不适用场景**：如果团队需要极其沉重的超大型多租户分布式审批流，则需要结合具体企业基础设施做二次扩展。

**总结**：{f.name} 是一个目标非常纯粹、实用主义导向的优秀实践。推荐受困于传统复杂方案的开发者动手体验。
"""
        return doc.strip()

    def generate_v2ex(self, f: FactSheet) -> str:
        """Generates candid, geek-friendly V2EX sharing post."""
        pains_str = "".join(f"- {p}\n" for p in f.pain_points)
        sols_str = "".join(f"- {s}\n" for s in f.solutions)
        tech_str = ", ".join(f.tech_stack)
        feat_str = "".join(
            f"{i + 1}. **{item.name}**：{item.headline}。{item.detail}\n" for i, item in enumerate(f.key_features[:3])
        )
        github_link = f.links.get("github", "GitHub 项目主页已公开")

        doc = f"""[分享创造] 做了个面向 {f.category} 的轻量开源项目：{f.name}，求 V 友真实反馈

大家好，最近几个月业余时间折腾了一个新项目：**{f.name}**。

### 背景痛点
平时在开发和业务协作时，深感现有的一些方案实在太重或者太不顺手了：
{pains_str}

很多时候我就想要一个轻量、稳定、可预期、能开箱即用的工具，而不是为了喝口水先搭一套水厂。

### 做了什么
项目定位：**{f.tagline}**。
核心实现：
{sols_str}

技术选型上尽量克制：`{tech_str}`，尽量不引入不必要的重型外部常驻服务，单机或单镜像即可轻松搞定。

### 核心亮点
{feat_str}

### 项目地址与反馈
目前第一版核心功能已经跑通且在持续迭代，欢迎各位 V 友试用或提 Issue / PR！
{github_link}

想听听大家平时在这个场景下是怎么解决的，有什么建议欢迎直接拍砖！感谢！
"""
        return doc.strip()

    def generate_release_notes(self, f: FactSheet) -> str:
        """Generates clean release announcement."""
        feat_str = "".join(f"- **{item.name}**：{item.headline}\n" for item in f.key_features)
        tech_str = ", ".join(f.tech_stack)
        cta_str = f.call_to_action or "立即部署并体验全新工作流！"

        doc = f"""# 🚀 {f.name} v1.0.0 发布说明：{f.tagline}

我们很高兴地宣布 **{f.name}** 正式发布！

## 🌟 核心亮点
{feat_str}

## 🛠️ 技术基石
- 技术栈：`{tech_str}`
- 开箱即用，高内聚低耦合设计

## 📦 快速开始
欢迎查阅官方文档与仓库开始体验：
{cta_str}
"""
        return doc.strip()

    def generate_video_script_and_scenes(self, f: FactSheet) -> tuple[str, List[StoryboardScene]]:
        """Generates a cohesive video script and structured storyboard scenes."""
        scenes: List[StoryboardScene] = []

        # Scene 1: Hook
        pains = "、".join(f.pain_points[:2]) if f.pain_points else "繁琐的手工配置与失控的流程"
        s1 = StoryboardScene(
            scene_id=1,
            title="痛点共鸣与破局引入",
            narration=f"在日常开发中，你是否也经常被{pains}所折磨？今天为你介绍一个全新的破局方案：{f.name}。",
            visual_description=f"展示开发中遇到的困境与痛点对比，随后呈现 {f.name} 的醒目Logo与核心主标",
            duration_estimate=4.5,
        )
        scenes.append(s1)

        # Scene 2: Definition & Value
        s2 = StoryboardScene(
            scene_id=2,
            title="核心定位与架构理念",
            narration=f"{f.name} 主打{f.tagline}。从第一性原理出发，告别过度设计，带来极致的确定性与敏捷体验。",
            visual_description="简洁的架构图或核心价值三要素，高亮展示核心理念",
            duration_estimate=5.0,
        )
        scenes.append(s2)

        # Scene 3: Key Features in Action
        feat_narrations = []
        for feat in f.key_features[:3]:
            feat_narrations.append(f"{feat.name}，{feat.headline}。")
        feat_text = "".join(feat_narrations)
        s3 = StoryboardScene(
            scene_id=3,
            title="核心功能亮点实战",
            narration=f"在实际功能上，{f.name} 提供了四大核心特性：{feat_text}",
            visual_description="动态演示产品界面与核心特性运行时的交互反馈",
            duration_estimate=6.0,
        )
        scenes.append(s3)

        # Scene 4: Audience & Summary
        audience_str = "和".join(f.target_audience[:2]) if f.target_audience else "技术团队"
        s4 = StoryboardScene(
            scene_id=4,
            title="适用对象与行动呼吁",
            narration=f"无论你是{audience_str}，{f.name} 都能大幅缩短交付路径。让工具回归本质，让创造更加高效！",
            visual_description="展示支持的终端设备与生态互通，呈现开源地址与互动引导",
            duration_estimate=4.5,
        )
        scenes.append(s4)

        full_script = " ".join(s.narration for s in scenes)
        return full_script, scenes
