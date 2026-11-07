#!/usr/bin/env python3
"""ContentFlow CLI: Universal Multi-Modal Content and Video Production Suite.

Generates complete, publication-ready multi-platform copywriting and rendered MP4
videos powered by MoneyPrinterTurbo.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from config.settings import (
    CONTENTFLOW_ROOT,
    PROJECTS_DIR,
)
from core.asset_builder import AssetBuilder
from core.copywriting import CopywritingEngine
from core.models import FactSheet
from core.video_engine import VideoEngine


def resolve_project_dir(project_name: str) -> Path:
    """Resolves project directory by exact name, 00x sequence prefix, or substring."""
    direct = PROJECTS_DIR / project_name
    if direct.exists() and direct.is_dir():
        return direct

    if not PROJECTS_DIR.exists():
        return direct

    candidates = [p for p in PROJECTS_DIR.iterdir() if p.is_dir()]

    # If project_name is a number like "5" or "005"
    if project_name.isdigit():
        target_prefix = f"{int(project_name):03d}_"
        for c in candidates:
            if c.name.startswith(target_prefix):
                return c

    # If project_name matches start of directory (e.g. "005")
    for c in candidates:
        if c.name.startswith(f"{project_name}_"):
            return c

    # Substring matching (e.g. "noshiro" -> "005_transformer_noshiro_tutorial")
    matched = [c for c in candidates if project_name.lower() in c.name.lower()]
    if len(matched) == 1:
        return matched[0]
    elif len(matched) > 1:
        for m in matched:
            if m.name.endswith(f"_{project_name.lower()}"):
                return m
        return matched[0]

    return direct


def cmd_init_project(args):
    """Initializes a new project workspace with 00x sequential numbering and a boilerplate brief.json."""
    existing = [p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()] if PROJECTS_DIR.exists() else []
    seq_nums = []
    for name in existing:
        if len(name) >= 4 and name[:3].isdigit() and name[3] == "_":
            seq_nums.append(int(name[:3]))
    next_seq = max(seq_nums, default=0) + 1

    clean_name = args.name.lower().replace(" ", "_").strip()
    if len(clean_name) >= 4 and clean_name[:3].isdigit() and clean_name[3] == "_":
        project_id = clean_name
    else:
        project_id = f"{next_seq:03d}_{clean_name}"

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
            "DevOps and Infrastructure Teams",
        ],
        "pain_points": [
            "Excessive glue code and fragile manual scripts that break silently",
            "Heavyweight enterprise suites with steep learning curves and painful bloat",
            "Lack of end-to-end visibility, audit trails, and deterministic execution",
        ],
        "solutions": [
            "Lightweight single-binary or container deployment with zero external lock-in",
            "Fully deterministic execution pipeline with sub-millisecond coordination",
            "Native extensible protocol and open interoperability",
        ],
        "key_features": [
            {
                "name": "Zero-Overhead Core",
                "headline": "Instant cold starts and minimal resource footprint",
                "detail": "Engineered with modern best practices, consuming under 50MB RAM while handling concurrent pipelines effortlessly.",
            },
            {
                "name": "Deterministic Engine",
                "headline": "Rock-solid reliability with full state snapshotting",
                "detail": "Eliminates random flakiness and provides time-travel inspection of every execution step.",
            },
            {
                "name": "Universal Interop",
                "headline": "Drop-in compatibility with standard tooling and APIs",
                "detail": "Seamlessly integrates into CI/CD, terminals, and webhooks without custom adapters.",
            },
        ],
        "tech_stack": ["Python 3.11+", "FastAPI / Standard Library", "Modern Native Web Components"],
        "highlights": [
            "Zero cloud lock-in: 100% self-hosted & local-first",
            "Production-ready out of the box",
            "Comprehensive test coverage and active open source community",
        ],
        "call_to_action": f"Star {args.name} on GitHub and deploy your first workflow in under 2 minutes!",
        "links": {
            "github": f"https://github.com/example/{project_id}",
            "docs": f"https://example.com/docs/{project_id}",
        },
    }

    with open(brief_file, "w", encoding="utf-8") as f:
        json.dump(boilerplate, f, ensure_ascii=False, indent=2)

    print(f"[+] Initialized project workspace: {proj_dir}")
    print(f"    - Brief:  {brief_file}")
    print(f"    - Assets: {assets_dir}")
    return 0


def cmd_generate_copy(args):
    """Generates complete multi-platform copywriting assets."""
    proj_dir = resolve_project_dir(args.project)
    project_id = proj_dir.name
    brief_file = proj_dir / "brief.json"

    if not brief_file.exists():
        print(f"[-] brief.json not found in: {proj_dir}")
        print(f"    Run: python cli.py init-project {args.project} first.")
        return 1

    with open(brief_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    facts = FactSheet.from_dict(data)
    engine = CopywritingEngine(theme_name=args.theme)
    package = engine.generate_all(facts)

    copy_out = proj_dir / "output" / "copy"
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
    proj_dir = resolve_project_dir(args.project)
    copy_dir = proj_dir / "output" / "copy"
    video_out = proj_dir / "output" / "video"
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
        [p for p in assets_dir.glob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4"}]
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

    print("[*] Invoking MoneyPrinterTurbo Engine...")
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

    print("[+] Video rendered successfully!")
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

    lib = AssetLibrary(root_dir=CONTENTFLOW_ROOT)
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

    lib = AssetLibrary(root_dir=CONTENTFLOW_ROOT)
    asset_id = getattr(args, "asset", None)
    char_id = getattr(args, "char_id", None)
    pose = getattr(args, "pose", None)

    item = None
    if asset_id and asset_id in lib.assets:
        item = lib.assets[asset_id]
    elif char_id or pose:
        matches = []
        for candidate in lib.assets.values():
            if char_id:
                c_match = (
                    candidate.character_id == char_id
                    or (candidate.character_id and char_id.lower() in candidate.character_id.lower())
                    or char_id.lower() in candidate.id.lower()
                )
                if not c_match:
                    continue
            if pose:
                p_match = (
                    candidate.emotion == pose
                    or pose.lower() in candidate.id.lower()
                    or any(pose.lower() in t.lower() for t in candidate.tags)
                )
                if not p_match:
                    continue
            matches.append(candidate)
        if matches:
            matches.sort(
                key=lambda c: (
                    0 if (pose and c.emotion == pose) else 1,
                    1 if "master_reference" in (c.file_path or "") else 0,
                    0 if all(ord(ch) < 128 for ch in Path(c.file_path or "").name) else 1,
                )
            )
            item = matches[0]

    if item is None:
        target_desc = asset_id or f"char_id={char_id}, pose={pose}"
        print(f"[-] Asset '{target_desc}' not found in library.")
        return 1

    proj_dir = resolve_project_dir(args.project) / "assets"
    proj_dir.mkdir(parents=True, exist_ok=True)
    src_file = CONTENTFLOW_ROOT / item.file_path
    dest_file = proj_dir / src_file.name
    shutil.copy2(src_file, dest_file)
    dest_file.touch()
    setattr(args, "_reused_dest_path", str(dest_file))
    project_name = resolve_project_dir(args.project).name
    if project_name not in item.used_in_projects:
        item.used_in_projects.append(project_name)
        lib.save_registry()
    print(f"[+] Reused asset '{item.id}' in project '{args.project}': {dest_file}")
    return 0


def cmd_figure_status(args):
    """Reports status of the 3 figure anime dance video pipelines."""
    from core.figure_orchestrator import FigureVideoOrchestrator

    fo = FigureVideoOrchestrator()
    readiness = fo.get_pipeline_readiness()
    print("\n=== ContentFlow 3D Figure Anime Dance Pipelines Readiness ===")
    for key, info in readiness.items():
        print(f"\n[{key.upper()}] {info['name']}")
        print(f"  • Overall Status: {info['status']}")
        for k, v in info.items():
            if k not in ("name", "status"):
                print(f"    - {k}: {v}")
    print()
    return 0


def cmd_figure_video(args):
    """Executes one of the 3 figure anime dance video pipelines."""
    from core.figure_orchestrator import FigureVideoOrchestrator

    fo = FigureVideoOrchestrator()
    proj_dir = resolve_project_dir(args.project)
    if not proj_dir.exists():
        print(f"[-] Project directory '{args.project}' not found (searched in {PROJECTS_DIR}).")
        return 1

    char_img = proj_dir / "assets" / args.character if getattr(args, "character", None) else None
    audio = proj_dir / "assets" / args.audio if getattr(args, "audio", None) else None

    print(f"[+] Starting Figure Dance Pipeline: {args.pipeline} for project: {args.project}")
    out = fo.run_pipeline(
        mode=args.pipeline,
        project_dir=proj_dir,
        character_image=char_img,
        audio_file=audio,
        prompt=args.prompt,
        model=getattr(args, "model", None),
        motion=getattr(args, "motion", None),
        frames=getattr(args, "frames", 60),
    )
    print(f"[+] Figure video generated successfully: {out}")
    return 0


cmd_init = cmd_init_project


def cmd_format_html(args):
    """Formats a Markdown/text file into standalone inline-CSS HTML."""
    from core.html_formatter import HTMLFormatter

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"[-] Input file not found: {in_path}")
        return 1
    text = in_path.read_text(encoding="utf-8")
    html_out = HTMLFormatter.format_text_to_html(
        text=text,
        title=getattr(args, "title", None),
        theme_name=getattr(args, "theme", "tech_blue"),
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
    print(f"[+] Formatted inline-CSS HTML written to: {out_path}")
    return 0


def cmd_serve(args):
    """Starts the ContentFlow Canonical HTTP JSON API server and Studio WebUI."""
    from core.server import run_server

    return run_server(host=args.host, port=args.port)


def cmd_auth_status(args):
    """Lists all supported platforms, whether logged in, nickname/UID, and session file path."""
    from core.auth_vault import AuthVault

    vault = AuthVault(vault_dir=getattr(args, "vault_dir", None))
    verify_online = bool(getattr(args, "verify", False))
    statuses = vault.get_all_statuses(verify_online=verify_online)

    print("\n=== ContentFlow Social Matrix Auth Vault Status ===")
    for platform, info in statuses.items():
        state_str = "LOGGED IN" if info["logged_in"] else "NOT LOGGED IN"
        ident = f"uname={info.get('uname') or '-'}, uid={info.get('mid') or '-'}"
        if info.get("level") is not None:
            ident += f", Lv.{info['level']}"
        print(f"• [{platform:<12}] {state_str:<15} | {ident}")
        print(f"  Session File: {info['session_file']}")
    print()
    return 0


def cmd_auth_login(args):
    """Initiates QR code generation and polling for platform login (WSL-friendly)."""
    from core.auth_vault import (
        DEFAULT_QR_OUTPUT_PATH,
        SUPPORTED_PLATFORMS,
        AuthVault,
        generate_bilibili_qr,
        poll_bilibili_qr,
    )

    platform = args.platform.lower().strip()
    if platform not in SUPPORTED_PLATFORMS:
        print(f"[-] Unsupported platform '{platform}'. Supported: {', '.join(SUPPORTED_PLATFORMS)}")
        return 1

    vault = AuthVault(vault_dir=getattr(args, "vault_dir", None))
    vault.get_platform_dir(platform, create=True)

    if platform == "bilibili":
        qr_out = Path(args.qr_output) if getattr(args, "qr_output", None) else DEFAULT_QR_OUTPUT_PATH
        qr_info = generate_bilibili_qr(qr_image_path=qr_out, print_terminal=True)
        if getattr(args, "no_poll", False):
            return 0
        print(f"[*] Waiting up to {args.timeout}s for Bilibili mobile app scan & confirmation...")
        poll_res = poll_bilibili_qr(
            qrcode_key=qr_info["qrcode_key"],
            timeout=args.timeout,
            vault=vault,
        )
        if poll_res.get("status") == "confirmed":
            prof = poll_res.get("profile") or {}
            print(f"[+] Bilibili login confirmed! Welcome {prof.get('uname') or ''} (UID: {prof.get('mid') or ''})")
            print(f"    - Cookies saved (0600):       {poll_res['cookies_path']}")
            print(f"    - Storage state saved (0600): {poll_res['storage_state_path']}")
            return 0
        print(f"[-] Bilibili QR login ended with status '{poll_res.get('status')}': {poll_res.get('message', '')}")
        return 1

    print(f"[*] Vault directory initialized for '{platform}': {vault.get_platform_dir(platform)}")
    return 0


def cmd_publish(args):
    """Stages or publishes a project's video & copywriting package and outputs an Advisor Receipt."""
    from core.publisher import MatrixPublisher

    raw_platforms = getattr(args, "platforms", ["bilibili"])
    if isinstance(raw_platforms, str):
        platforms = [p.strip() for p in raw_platforms.split(",") if p.strip()]
    else:
        platforms = []
        for item in raw_platforms:
            platforms.extend([p.strip() for p in str(item).split(",") if p.strip()])
    if not platforms:
        platforms = ["bilibili"]

    vault_dir = getattr(args, "vault_dir", None)
    from core.auth_vault import AuthVault

    vault = AuthVault(vault_dir=vault_dir) if vault_dir else AuthVault()
    publisher = MatrixPublisher(vault=vault, projects_dir=PROJECTS_DIR)

    dry_run = bool(getattr(args, "dry_run", False))
    exec_upload_arg = getattr(args, "execute_upload", False)
    remote_sched_arg = bool(getattr(args, "remote_schedule", False))
    execute_upload = False if dry_run else (True if exec_upload_arg else None)

    try:
        result = publisher.publish_project(
            project=args.project,
            platforms=platforms,
            mode=args.mode,
            schedule_at=getattr(args, "schedule_at", None),
            execute_upload=execute_upload,
            remote_schedule=remote_sched_arg,
        )
    except Exception as exc:
        print(f"[-] Publish failed: {exc}")
        return 1

    print(f"\n=== ContentFlow Advisor Publish Receipt ({result['project_id']}) ===")
    print(
        f"  • Safety Mode: {result['safety_mode']}"
        + (f" @ {result['schedule_at']}" if result.get("schedule_at") else "")
    )
    for plat, manifest in result["platforms"].items():
        receipt = manifest.get("advisor_receipt", {})
        print(f"\n  [{plat.upper()}] Status: {receipt.get('status')}")
        print(f"    - Title:     {manifest['title']}")
        print(f"    - TID/Cat:   {manifest['tid']} ({manifest['category']})")
        print(f"    - Tags:      {', '.join(manifest['tags'])}")
        print(f"    - Video:     {manifest['video_path']}")
        print(f"    - Cover:     {manifest['cover_path']}")
        if receipt.get("bvid"):
            print(f"    - BVID/AID:  {receipt.get('bvid')} (aid={receipt.get('aid')})")
        if receipt.get("dtime_iso"):
            print(f"    - Scheduled: {receipt.get('dtime_iso')} (dtime={receipt.get('dtime')})")
        if receipt.get("manage_url"):
            print(f"    - Creator:   {receipt.get('manage_url')}")
        print(f"    - Manifest:  {manifest['manifest_path']}")
        print(f"    - Receipt:   {manifest['receipt_md_path']}")
    print()
    return 0


def cmd_analytics(args):
    """Fetches Bilibili account stats, submitted archive views, trending radar, and track strategy."""
    from core.analytics import BilibiliAnalytics
    from core.auth_vault import AuthVault

    vault_dir = getattr(args, "vault_dir", None)
    vault = AuthVault(vault_dir=vault_dir) if vault_dir else AuthVault()
    analytics = BilibiliAnalytics(vault=vault)
    report = analytics.generate_report(save_snapshot=not getattr(args, "no_save", False))

    acc = report["account"]
    counts = report["archives_summary"]
    totals = report["totals"]

    print("\n=== ContentFlow Bilibili Autonomous Analytics & Track Radar ===")
    print(
        f"  • Account:   {acc.get('uname')} (UID: {acc.get('uid')}, Lv.{acc.get('level')}) | "
        f"Followers: {acc.get('follower')} | Following: {acc.get('following')}"
    )
    print(
        f"  • Archives:  {counts['pubed']} published | {counts['is_pubing']} auditing/scheduled | "
        f"{counts['not_pubed']} rejected"
    )
    print(
        f"  • Totals:    Views={totals['view']} | Likes={totals['like']} | Coins={totals['coin']} | "
        f"Favs={totals['favorite']} | Danmaku={totals['danmaku']} | Replies={totals['reply']}"
    )

    arcs = report.get("archives") or []
    if arcs:
        print("\n  [Submitted Videos]")
        for a in arcs:
            s = a["stat"]
            sched_str = f" (Scheduled: {a['dtime_iso']})" if a.get("dtime_iso") else ""
            print(
                f"    • {a.get('bvid') or a.get('aid')} [{a.get('state_desc')}]{sched_str}: {a.get('title')}\n"
                f"      Views={s['view']} | Likes={s['like']} | Coins={s['coin']} | Favs={s['favorite']} | "
                f"Danmaku={s['danmaku']} | Replies={s['reply']}"
            )
    else:
        print("\n  [Submitted Videos] None yet.")

    if getattr(args, "radar", False):
        print("\n  [Trending Radar Top 3 per Partition]")
        for part_name, items in (report.get("trending_radar") or {}).items():
            print(f"    - {part_name.upper()}:")
            for item in items[:3]:
                print(
                    f"      * [{item.get('bvid')}] {item.get('title')} "
                    f"(Views={item.get('view')}, Likes={item.get('like')}, Coins={item.get('coin')})"
                )

    print("\n  [Autonomous Viral Track Strategy]")
    for t in report.get("recommended_tracks") or []:
        print(f"    • {t['name']} (tid={t['target_tid']})")
        print(f"      Hook: {t['viral_hook']}")

    if report.get("snapshot_md"):
        print(f"\n  • Saved Snapshot JSON: {report.get('snapshot_json')}")
        print(f"  • Saved Growth Report: {report.get('snapshot_md')}\n")
    return 0


def cmd_quality_check(args):
    """Runs the 100-point objective VideoQualityGate on a project."""
    from core.quality_gate import VideoQualityGate

    gate = VideoQualityGate(
        root_dir=CONTENTFLOW_ROOT,
        pass_threshold=float(getattr(args, "threshold", 80.0)),
    )
    report = gate.evaluate_project(
        project=args.project,
        video_path=getattr(args, "video", None),
        cover_path=getattr(args, "cover", None),
    )
    if getattr(args, "json", False):
        print(report.to_json())
    else:
        print(report.format_terminal_report())
    if getattr(args, "output_json", None):
        out_p = Path(args.output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report.to_json(), encoding="utf-8")
    return 0 if report.passed else 1


def cmd_design_cover(args):
    """Renders a 1920x1080 (16:9) high-CTR Bilibili cover and 1440x1080 (4:3) safe crop."""
    from core.cover_designer import CoverDesigner

    proj_dir = resolve_project_dir(args.project)
    if not proj_dir.exists():
        print(f"[-] Project directory '{args.project}' not found (searched in {PROJECTS_DIR}).")
        return 1

    designer = CoverDesigner(font_path=getattr(args, "font", None))
    raw_tags = getattr(args, "tags", None)
    tags_list = None
    if raw_tags:
        if isinstance(raw_tags, str):
            tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags_list = [str(t).strip() for t in raw_tags if str(t).strip()]

    base_img = getattr(args, "base_image", None)
    out_path = getattr(args, "output", None)
    if base_img:
        b_path = Path(base_img) if Path(base_img).exists() else (proj_dir / base_img)
        target_out = Path(out_path) if out_path else (proj_dir / "delivery" / f"{proj_dir.name}_cover.jpg")
        res = designer.design_cover(
            base_image_path=b_path,
            output_path=target_out,
            hook_line1=getattr(args, "hook_line1", None) or "把B站账号交给AI",
            hook_line2=getattr(args, "hook_line2", None) or "连夜肝出大肥鱼",
            hook_line3=getattr(args, "hook_line3", None) or "60帧纯享热舞！",
            badge_text=getattr(args, "badge", None) or "AI接管账号实录",
            bottom_tags=tags_list,
        )
    else:
        res = designer.design_project_cover(
            project_dir=proj_dir,
            hook_line1=getattr(args, "hook_line1", None),
            hook_line2=getattr(args, "hook_line2", None),
            hook_line3=getattr(args, "hook_line3", None),
            badge_text=getattr(args, "badge", None),
            bottom_tags=tags_list,
            output_path=out_path,
        )

    print(f"[+] Bilibili 16:9 High-CTR Cover rendered for '{proj_dir.name}':")
    print(f"    - Layout Mode:     {res.layout_mode} (from {res.source_size[0]}x{res.source_size[1]})")
    print(f"    - 16:9 Cover JPG:  {res.output_path} ({res.width}x{res.height})")
    print(f"    - 4:3 Safe Crop:   {res.output_4x3_path} (1440x1080)")
    print(f"    - Hook Lines:      {' | '.join(res.hook_lines)}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="ContentFlow: Universal Multi-Modal Content & Video Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-project / init
    p_init = subparsers.add_parser("init-project", aliases=["init"], help="Initialize a new project workspace")
    p_init.add_argument("name", help="Name of the product/topic (e.g. 'DevPulse')")
    p_init.add_argument("--mode", default="hybrid", help="Pipeline mode (default: hybrid)")
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
    p_video.add_argument(
        "--font",
        default="/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        help="Subtitle font path (open-source commercial compliant)",
    )
    p_video.add_argument(
        "--slow-zoom", action="store_true", help="Use MoviePy software zoom instead of fast ffmpeg conversion"
    )
    p_video.add_argument("--theme", default="tech_blue", help="Fallback theme")
    p_video.set_defaults(func=cmd_generate_video)

    # run-all
    p_all = subparsers.add_parser("run-all", help="Generate both copy and video in one go")
    p_all.add_argument("--project", required=True, help="Project ID/name")
    p_all.add_argument("--aspect", default="16:9", choices=["16:9", "9:16", "1:1"], help="Video aspect ratio")
    p_all.add_argument("--voice", default="zh-CN-YunxiNeural", help="TTS Voice Name")
    p_all.add_argument("--bgm", default="random", choices=["random", "none", "custom"], help="Background music mode")
    p_all.add_argument(
        "--font",
        default="/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        help="Subtitle font path (open-source commercial compliant)",
    )
    p_all.add_argument(
        "--slow-zoom", action="store_true", help="Use MoviePy software zoom instead of fast ffmpeg conversion"
    )
    p_all.add_argument("--theme", default="tech_blue", help="HTML theme")
    p_all.set_defaults(func=cmd_run_all)

    # list-assets
    p_assets = subparsers.add_parser("list-assets", help="List reusable assets in central library")
    p_assets.add_argument("--character", default="all", help="Filter by character ID (or 'all')")
    p_assets.add_argument("--emotion", default="all", help="Filter by emotion (or 'all')")
    p_assets.add_argument("--aspect", default="all", help="Filter by aspect ratio ('16:9', '9:16', '1:1', or 'all')")
    p_assets.set_defaults(func=cmd_list_assets)

    # reuse-asset
    p_reuse = subparsers.add_parser("reuse-asset", help="Reuse an asset from central library in a project")
    p_reuse.add_argument("--project", required=True, help="Target project ID/name")
    p_reuse.add_argument("--asset", default=None, help="Asset ID in central library")
    p_reuse.add_argument("--char-id", "--char", dest="char_id", default=None, help="Character ID in central library")
    p_reuse.add_argument("--pose", default=None, help="Pose or emotion tag in central library")
    p_reuse.set_defaults(func=cmd_reuse_asset)

    # format-html
    p_fmt = subparsers.add_parser("format-html", help="Format Markdown/text into inline-CSS WeChat/Whiteboard HTML")
    p_fmt.add_argument("--input", required=True, help="Input Markdown/text file path")
    p_fmt.add_argument("--output", required=True, help="Output HTML file path")
    p_fmt.add_argument("--title", default=None, help="Optional HTML title")
    p_fmt.add_argument("--theme", default="tech_blue", choices=["tech_blue", "emerald"], help="HTML theme")
    p_fmt.set_defaults(func=cmd_format_html)

    # figure-status
    p_fstatus = subparsers.add_parser("figure-status", help="Inspect readiness of 3 figure animation pipelines")
    p_fstatus.set_defaults(func=cmd_figure_status)

    # figure-video
    p_fvideo = subparsers.add_parser("figure-video", help="Generate 3D figure dance video (3d, keyframe, or api)")
    p_fvideo.add_argument(
        "--pipeline", required=True, choices=["3d", "keyframe", "api"], help="Pipeline mode to execute"
    )
    p_fvideo.add_argument("--project", required=True, help="Project name (e.g. transformer_noshiro_tutorial)")
    p_fvideo.add_argument(
        "--character", default="noshiro_reference.jpg", help="Character image filename in project assets"
    )
    p_fvideo.add_argument("--model", default=None, help="PMX model name, keyword (e.g. 'miku', 'luka'), or path")
    p_fvideo.add_argument("--motion", default=None, help="VMD dance motion name or path")
    p_fvideo.add_argument("--frames", type=int, default=60, help="Number of 3D frames to render (default: 60)")
    p_fvideo.add_argument("--audio", default=None, help="Audio/BGM filename in project assets")
    p_fvideo.add_argument(
        "--prompt", default="3D anime figure girl dancing gracefully, studio lighting", help="Prompt description"
    )
    p_fvideo.set_defaults(func=cmd_figure_video)

    # serve
    p_serve = subparsers.add_parser("serve", help="Start ContentFlow Canonical HTTP API & Studio WebUI")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=8090, help="Bind port (default: 8090)")
    p_serve.set_defaults(func=cmd_serve)

    # auth (status / login)
    p_auth = subparsers.add_parser("auth", help="Manage social matrix authentication vault & QR login")
    auth_sub = p_auth.add_subparsers(dest="auth_action", required=True)

    p_auth_status = auth_sub.add_parser("status", help="List login status across all supported platforms")
    p_auth_status.add_argument("--verify", action="store_true", help="Verify active session online via platform API")
    p_auth_status.set_defaults(func=cmd_auth_status)

    p_auth_login = auth_sub.add_parser("login", help="Initiate QR code generation and polling for platform login")
    p_auth_login.add_argument(
        "--platform",
        default="bilibili",
        choices=["bilibili", "douyin", "xiaohongshu", "wechat_mp"],
        help="Target platform (default: bilibili)",
    )
    p_auth_login.add_argument(
        "--timeout", type=int, default=180, help="QR scan polling timeout in seconds (default: 180)"
    )
    p_auth_login.add_argument("--qr-output", default=None, help="Custom path to save QR code PNG")
    p_auth_login.add_argument("--no-poll", action="store_true", help="Generate QR code and exit without polling")
    p_auth_login.set_defaults(func=cmd_auth_login)

    # publish
    p_pub = subparsers.add_parser("publish", help="Stage or publish a project's video & copywriting package")
    p_pub.add_argument("--project", required=True, help="Project ID or name (e.g. 005 or 006)")
    p_pub.add_argument(
        "--platforms",
        "--platform",
        dest="platforms",
        nargs="+",
        default=["bilibili"],
        help="Target platforms (default: bilibili; comma or space separated)",
    )
    p_pub.add_argument(
        "--mode",
        default="draft",
        choices=["draft", "schedule", "direct"],
        help="Advisor safety mode (default: draft)",
    )
    p_pub.add_argument("--schedule-at", default=None, help="Schedule time in HH:MM, +Nh, or ISO format")
    p_pub.add_argument(
        "--execute-upload",
        action="store_true",
        help="Execute real video & cover upload to platform API",
    )
    p_pub.add_argument(
        "--remote-schedule",
        action="store_true",
        help="Upload to Bilibili Creator Center as a scheduled draft (>=4h in future)",
    )
    p_pub.add_argument(
        "--dry-run",
        action="store_true",
        help="Stage locally without making remote upload API calls",
    )
    p_pub.set_defaults(func=cmd_publish)

    # analytics
    p_ana = subparsers.add_parser(
        "analytics", help="Fetch Bilibili account views, archive performance, and viral track radar"
    )
    p_ana.add_argument("--radar", action="store_true", help="Include real-time Bilibili partition trending radar")
    p_ana.add_argument("--no-save", action="store_true", help="Do not write snapshot files to library/analytics/")
    p_ana.set_defaults(func=cmd_analytics)

    # quality-check
    p_qc = subparsers.add_parser("quality-check", help="Run 100-point objective VideoQualityGate on a project")
    p_qc.add_argument("--project", required=True, help="Project ID or name (e.g. 007 or 005)")
    p_qc.add_argument("--video", default=None, help="Optional explicit video file path")
    p_qc.add_argument("--cover", default=None, help="Optional explicit cover file path")
    p_qc.add_argument("--threshold", type=float, default=80.0, help="Passing score threshold (default: 80.0)")
    p_qc.add_argument("--json", action="store_true", help="Output structured JSON report to stdout")
    p_qc.add_argument("--output-json", default=None, help="Save structured JSON report to file")
    p_qc.set_defaults(func=cmd_quality_check)

    # design-cover
    p_dc = subparsers.add_parser(
        "design-cover", help="Render Bilibili 16:9 high-CTR viral cover (1920x1080) & 4:3 safe crop"
    )
    p_dc.add_argument("--project", required=True, help="Project ID or name (e.g. 007 or 005)")
    p_dc.add_argument("--hook-line1", default=None, help="Main hook title line 1 (Gold #FFD700)")
    p_dc.add_argument("--hook-line2", default=None, help="Main hook title line 2 (White #FFFFFF)")
    p_dc.add_argument("--hook-line3", default=None, help="Main hook title line 3 (Cyan #00F0FF)")
    p_dc.add_argument("--badge", default=None, help="Top capsule badge text (e.g. 'AI接管账号实录')")
    p_dc.add_argument("--tags", default=None, help="Comma-separated bottom highlight tags (e.g. '2K重绘,60FPS满帧')")
    p_dc.add_argument("--base-image", default=None, help="Optional explicit base image path")
    p_dc.add_argument("--output", default=None, help="Optional explicit output cover path")
    p_dc.add_argument("--font", default=None, help="Optional path to open-source CJK bold font")
    p_dc.set_defaults(func=cmd_design_cover)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
