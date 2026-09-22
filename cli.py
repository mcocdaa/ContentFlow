#!/usr/bin/env python3
"""ContentFlow CLI: Universal Multi-Modal Content and Video Production Suite.

Generates complete, publication-ready multi-platform copywriting and rendered MP4
videos powered by MoneyPrinterTurbo.
"""

import argparse
import sys
import json
import os
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config.settings import (
    CONTENTFLOW_ROOT,
    PROJECTS_DIR,
    OUTPUT_DIR,
    DEFAULT_VOICES,
    DEFAULT_ASPECT_RATIOS,
)
from core.models import FactSheet
from core.copywriting import CopywritingEngine
from core.asset_builder import AssetBuilder
from core.video_engine import VideoEngine


def cmd_init_project(args):
    """Initializes a new project workspace with a boilerplate brief.json."""
    project_id = args.name.lower().replace(" ", "_")
    proj_dir = PROJECTS_DIR / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = proj_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    brief_file = proj_dir / "brief.json"
    if brief_file.exists() and not args.force:
        print(f"[-] Project '{project_id}' already exists at: {proj_dir}")
        print("    Use --force to overwrite boilerplate.")
        return 0

    boilerplate = {
        "project_id": project_id,
        "name": args.name,
        "tagline": "A revolutionary open-source platform that eliminates manual toil",
        "category": "Developer Tools & AI",
        "description": f"{args.name} is a high-performance system engineered for reliable automation and seamless developer experience.",
        "target_audience": [
            "Software Engineers and Architects",
            "Indie Hackers and Technical Founders",
            "DevOps and Infrastructure Teams"
        ],
        "pain_points": [
            "Excessive glue code and fragile manual scripts that break silently",
            "Heavyweight enterprise suites with steep learning curves and painful bloat",
            "Lack of end-to-end visibility, audit trails, and deterministic execution"
        ],
        "solutions": [
            "Lightweight single-binary or container deployment with zero external lock-in",
            "Fully deterministic execution pipeline with sub-millisecond coordination",
            "Native extensible protocol and open interoperability"
        ],
        "key_features": [
            {
                "name": "Zero-Overhead Core",
                "headline": "Instant cold starts and minimal resource footprint",
                "detail": "Engineered with modern best practices, consuming under 50MB RAM while handling concurrent pipelines effortlessly."
            },
            {
                "name": "Deterministic Engine",
                "headline": "Rock-solid reliability with full state snapshotting",
                "detail": "Eliminates random flakiness and provides time-travel inspection of every execution step."
            },
            {
                "name": "Universal Interop",
                "headline": "Drop-in compatibility with standard tooling and APIs",
                "detail": "Seamlessly integrates into CI/CD, terminals, and webhooks without custom adapters."
            }
        ],
        "tech_stack": ["Python 3.11+", "FastAPI / Standard Library", "Modern Native Web Components"],
        "highlights": [
            "Zero cloud lock-in: 100% self-hosted & local-first",
            "Production-ready out of the box",
            "Comprehensive test coverage and active open source community"
        ],
        "call_to_action": f"Star {args.name} on GitHub and deploy your first workflow in under 2 minutes!",
        "links": {
            "github": f"https://github.com/example/{project_id}",
            "docs": f"https://example.com/docs/{project_id}"
        }
    }

    with open(brief_file, "w", encoding="utf-8") as f:
        json.dump(boilerplate, f, ensure_ascii=False, indent=2)

    print(f"[+] Initialized project workspace: {proj_dir}")
    print(f"    - Brief:  {brief_file}")
    print(f"    - Assets: {assets_dir}")
    return 0


def cmd_generate_copy(args):
    """Generates complete multi-platform copywriting assets."""
    project_id = args.project
    proj_dir = PROJECTS_DIR / project_id
    brief_file = proj_dir / "brief.json"

    if not brief_file.exists():
        print(f"[-] brief.json not found in: {proj_dir}")
        print(f"    Run: python cli.py init-project {project_id} first.")
        return 1

    with open(brief_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    facts = FactSheet.from_dict(data)
    engine = CopywritingEngine(theme_name=args.theme)
    package = engine.generate_all(facts)

    copy_out = OUTPUT_DIR / project_id / "copy"
    copy_out.mkdir(parents=True, exist_ok=True)

    # Save WeChat MD & HTML
    with open(copy_out / "wechat.md", "w", encoding="utf-8") as f:
        f.write(package.wechat_md)
    with open(copy_out / "wechat.html", "w", encoding="utf-8") as f:
        f.write(package.wechat_html)

    # Save XHS
    with open(copy_out / "xiaohongshu.md", "w", encoding="utf-8") as f:
        f.write(package.xiaohongshu)

    # Save Zhihu
    with open(copy_out / "zhihu.md", "w", encoding="utf-8") as f:
        f.write(package.zhihu)

    # Save V2EX
    with open(copy_out / "v2ex.md", "w", encoding="utf-8") as f:
        f.write(package.v2ex)

    # Save Release
    with open(copy_out / "release.md", "w", encoding="utf-8") as f:
        f.write(package.release)

    # Save Video Script & Storyboard
    with open(copy_out / "video_script.txt", "w", encoding="utf-8") as f:
        f.write(package.video_script)

    storyboard_data = [
        {
            "scene_id": s.scene_id,
            "title": s.title,
            "narration": s.narration,
            "visual_description": s.visual_description,
            "duration_estimate": s.duration_estimate,
        }
        for s in package.scenes
    ]
    with open(copy_out / "storyboard.json", "w", encoding="utf-8") as f:
        json.dump(storyboard_data, f, ensure_ascii=False, indent=2)

    print(f"[+] Multi-platform copywriting generated successfully for '{project_id}':")
    print(f"    - WeChat Article (MD):   {copy_out / 'wechat.md'}")
    print(f"    - WeChat Inline HTML:    {copy_out / 'wechat.html'}")
    print(f"    - Xiaohongshu Card:      {copy_out / 'xiaohongshu.md'}")
    print(f"    - Zhihu Technical Post:  {copy_out / 'zhihu.md'}")
    print(f"    - V2EX Community Post:   {copy_out / 'v2ex.md'}")
    print(f"    - Release Announcement:  {copy_out / 'release.md'}")
    print(f"    - Video Script & Board:  {copy_out / 'storyboard.json'}")
    return 0


def cmd_generate_video(args):
    """Generates rendered video using MoneyPrinterTurbo engine."""
    project_id = args.project
    proj_dir = PROJECTS_DIR / project_id
    copy_dir = OUTPUT_DIR / project_id / "copy"
    video_out = OUTPUT_DIR / project_id / "video"
    video_out.mkdir(parents=True, exist_ok=True)

    # Load brief
    brief_file = proj_dir / "brief.json"
    if not brief_file.exists():
        print(f"[-] brief.json not found in: {proj_dir}")
        return 1

    with open(brief_file, "r", encoding="utf-8") as f:
        facts = FactSheet.from_dict(json.load(f))

    # Ensure storyboard and script exist
    storyboard_file = copy_dir / "storyboard.json"
    script_file = copy_dir / "video_script.txt"
    if not storyboard_file.exists() or not script_file.exists():
        print("[*] Copy assets not found. Generating copywriting & storyboard first...")
        cmd_generate_copy(args)

    custom_script_file = proj_dir / "script.txt"
    if custom_script_file.exists():
        with open(custom_script_file, "r", encoding="utf-8") as f:
            script_text = f.read().strip()
    else:
        with open(script_file, "r", encoding="utf-8") as f:
            script_text = f.read().strip()

    with open(storyboard_file, "r", encoding="utf-8") as f:
        scenes = json.load(f)

    # Collect materials: check storyboard scene asset mappings first
    storyboard_materials = []
    for sc in scenes:
        ap = sc.get("asset_path")
        if ap:
            p = CONTENTFLOW_ROOT / ap
            if p.exists():
                storyboard_materials.append(p)

    assets_dir = proj_dir / "assets"
    existing_materials = sorted(
        [
            p
            for p in assets_dir.glob("*")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4"}
        ]
    )

    final_materials = []
    aspect = args.aspect or "16:9"
    size = (1920, 1080) if aspect == "16:9" else ((1080, 1920) if aspect == "9:16" else (1080, 1080))

    if storyboard_materials:
        print(f"[*] Found {len(storyboard_materials)} storyboard scene assets mapped in order from storyboard.json")
        final_materials.extend(storyboard_materials)
    elif existing_materials:
        print(f"[*] Found {len(existing_materials)} user materials in {assets_dir}")
        final_materials.extend(existing_materials)
    else:
        print(f"[*] No raw media in assets/. Auto-generating {len(scenes)} visual slides...")
        builder = AssetBuilder(video_out / "slides")
        for sc in scenes:
            slide_path = builder.create_scene_slide(
                scene_id=sc["scene_id"],
                title=sc["title"],
                subtitle=sc["narration"][:35] + "...",
                bullets=[facts.tagline, *facts.highlights[:2]],
                size=size,
            )
            final_materials.append(slide_path)

    print(f"[*] Invoking MoneyPrinterTurbo Engine...")
    print(f"    - Aspect:     {aspect}")
    print(f"    - Voice:      {args.voice}")
    print(f"    - BGM:        {args.bgm}")
    print(f"    - Materials:  {len(final_materials)} items")

    engine = VideoEngine()
    result = engine.render(
        subject=facts.name,
        script=script_text,
        materials=final_materials,
        output_dir=video_out,
        aspect=aspect,
        voice_name=args.voice,
        bgm_type=args.bgm,
        font_name=args.font,
        fast_image_convert=not args.slow_zoom,
    )

    if not result.success:
        print(f"[-] Video rendering failed: {result.error}")
        return 1

    print(f"[+] Video rendered successfully!")
    print(f"    - Task ID:    {result.task_id}")
    print(f"    - Video MP4:  {result.video_path}")
    print(f"    - Audio MP3:  {result.audio_path}")
    print(f"    - Subtitle:   {result.subtitle_path}")
    print(f"    - Cover JPG:  {result.cover_path}")
    return 0


def cmd_run_all(args):
    """Generates all copy and renders video in a single command."""
    ret = cmd_generate_copy(args)
    if ret != 0:
        return ret
    return cmd_generate_video(args)


def cmd_list_assets(args):
    """Lists all cataloged reusable assets in the central library."""
    from core.asset_library import AssetLibrary
    lib = AssetLibrary()
    assets = lib.search_assets(
        character_id=args.character if args.character != "all" else None,
        emotion=args.emotion if args.emotion != "all" else None,
        aspect_ratio=args.aspect if args.aspect != "all" else None,
    )
    print(f"\n=== ContentFlow Asset Library ({len(assets)} assets found) ===")
    for a in assets:
        char_tag = f"[{a.character_id}] " if a.character_id else ""
        emo_tag = f"({a.emotion}) " if a.emotion else ""
        print(f"• ID: {a.id:<32} {char_tag}{emo_tag}| {a.aspect_ratio} ({a.resolution}) | Tags: {','.join(a.tags)}")
        print(f"  Path: {a.file_path}")
    print()
    return 0


def cmd_reuse_asset(args):
    """Imports an asset from the central library into a project workspace."""
    from core.asset_library import AssetLibrary
    import shutil
    lib = AssetLibrary()
    if args.asset not in lib.assets:
        print(f"[-] Asset '{args.asset}' not found in library.")
        return 1
    item = lib.assets[args.asset]
    proj_dir = PROJECTS_DIR / args.project / "assets"
    proj_dir.mkdir(parents=True, exist_ok=True)
    src_file = CONTENTFLOW_ROOT / item.file_path
    dest_file = proj_dir / src_file.name
    shutil.copy2(src_file, dest_file)
    if args.project not in item.used_in_projects:
        item.used_in_projects.append(args.project)
        lib.save_registry()
    print(f"[+] Reused asset '{args.asset}' in project '{args.project}': {dest_file}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="ContentFlow: Universal Multi-Modal Content & Video Engine"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-project
    p_init = subparsers.add_parser("init-project", help="Initialize a new project workspace")
    p_init.add_argument("name", help="Name of the product/topic (e.g. 'DevPulse')")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing brief")
    p_init.set_defaults(func=cmd_init_project)

    # generate-copy
    p_copy = subparsers.add_parser("generate-copy", help="Generate all copywriting packages")
    p_copy.add_argument("--project", required=True, help="Project ID/name")
    p_copy.add_argument("--theme", default="tech_blue", choices=["tech_blue", "emerald"], help="HTML theme")
    p_copy.set_defaults(func=cmd_generate_copy)

    # generate-video
    p_video = subparsers.add_parser("generate-video", help="Render video using MoneyPrinterTurbo")
    p_video.add_argument("--project", required=True, help="Project ID/name")
    p_video.add_argument("--aspect", default="16:9", choices=["16:9", "9:16", "1:1"], help="Video aspect ratio")
    p_video.add_argument("--voice", default="zh-CN-YunxiNeural", help="TTS Voice Name")
    p_video.add_argument("--bgm", default="random", choices=["random", "none", "custom"], help="Background music mode")
    p_video.add_argument("--font", default="STHeitiMedium.ttc", help="Subtitle font filename")
    p_video.add_argument("--slow-zoom", action="store_true", help="Use MoviePy software zoom instead of fast ffmpeg conversion")
    p_video.add_argument("--theme", default="tech_blue", help="Fallback theme")
    p_video.set_defaults(func=cmd_generate_video)

    # run-all
    p_all = subparsers.add_parser("run-all", help="Generate both copy and video in one go")
    p_all.add_argument("--project", required=True, help="Project ID/name")
    p_all.add_argument("--aspect", default="16:9", choices=["16:9", "9:16", "1:1"], help="Video aspect ratio")
    p_all.add_argument("--voice", default="zh-CN-YunxiNeural", help="TTS Voice Name")
    p_all.add_argument("--bgm", default="random", choices=["random", "none", "custom"], help="Background music mode")
    p_all.add_argument("--font", default="STHeitiMedium.ttc", help="Subtitle font filename")
    p_all.add_argument("--slow-zoom", action="store_true", help="Use MoviePy software zoom instead of fast ffmpeg conversion")
    p_all.add_argument("--theme", default="tech_blue", help="HTML theme")
    p_all.set_defaults(func=cmd_run_all)

    # list-assets
    p_assets = subparsers.add_parser("list-assets", help="List reusable assets in central library")
    p_assets.add_argument("--character", default="all", help="Filter by character ID (or 'all')")
    p_assets.add_argument("--emotion", default="all", help="Filter by emotion (or 'all')")
    p_assets.add_argument("--aspect", default="all", help="Filter by aspect ratio ('16:9', '9:16', '1:1', or 'all')")
    p_assets.set_defaults(func=cmd_list_assets)

    # reuse-asset
    p_reuse = subparsers.add_parser("reuse-asset", help="Import an asset from central library into project")
    p_reuse.add_argument("--asset", required=True, help="Asset ID from registry")
    p_reuse.add_argument("--project", required=True, help="Target Project ID")
    p_reuse.set_defaults(func=cmd_reuse_asset)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
