"""Unit tests for compliant open-source fonts, AssetLibrary credits attribution,
CoverDesigner (16:9 & 4:3 safe zone), VideoQualityGate (100-pt rubric), and CLI commands.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

import cli
from config.settings import CONTENTFLOW_ROOT, DEFAULT_FONTS
from core.asset_library import AssetItem, AssetLibrary
from core.cover_designer import CoverDesigner
from core.quality_gate import VideoQualityGate


def _ensure_test_video(target_mp4: Path, width: int = 1080, height: int = 1920, fps: int = 60) -> Path:
    """Returns target_mp4 if it exists, otherwise synthesizes a valid test MP4 via ffmpeg (or header stub on headless CI)."""
    if target_mp4.exists() and target_mp4.stat().st_size > 1000:
        return target_mp4
    target_mp4.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") is None:
        target_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)
        return target_mp4
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={width}x{height}:rate={fps}:duration=4",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=4",
        "-af",
        "pan=stereo|c0=c0|c1=c0,volume=0.5",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        "10M",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(target_mp4),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return target_mp4


def test_compliant_fonts_and_voice_redline() -> None:
    """Verifies commercial fonts are removed and voice cloning redline is enforced."""
    forbidden = {"stheitimedium.ttc", "microsoftyaheinormal.ttc", "simhei.ttf"}
    for f in DEFAULT_FONTS:
        assert Path(f).name.lower() not in forbidden
        assert any(k in f.lower() for k in ("noto", "wqy"))

    skill_md = (CONTENTFLOW_ROOT / ".agents" / "skills" / "figure-tutorial-video" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "石川由依" not in skill_md
    assert "《民法典》第1023条" in skill_md
    assert "《人工智能生成合成内容标识办法》" in skill_md
    assert "严禁未经授权克隆真人或动漫声优原声" in skill_md


def test_asset_library_registry_and_generate_project_credits() -> None:
    """Verifies all registry assets have attribution fields and generate_project_credits works."""
    lib = AssetLibrary(root_dir=CONTENTFLOW_ROOT)
    assert len(lib.assets) >= 38
    assert "noshiro_reference" in lib.assets
    assert "ureshiiiiii_phone_number_motion" in lib.assets

    noshiro = lib.assets["noshiro_reference"]
    assert "ATDAN" in noshiro.author or "ATDAN" in noshiro.credit_line
    assert "Manjuu" in noshiro.author or "Manjuu" in noshiro.credit_line

    motion = lib.assets["ureshiiiiii_phone_number_motion"]
    assert "ureshiiiiii" in motion.author
    assert "TDA Luka Dress" in motion.author
    assert "TAHITI - Phone Number" in motion.author

    for item in lib.assets.values():
        assert item.license
        assert item.author
        assert item.credit_line

    credits_007 = lib.generate_project_credits("007_deepseek_dafeiyu_phone_number", extra_credits=["测试附加致谢条目"])
    assert "借物表 (Credits)" in credits_007
    assert "@上善无形" in credits_007
    assert "@ZipZipPipe" in credits_007
    assert "ureshiiiiii" in credits_007
    assert "TAHITI - Phone Number" in credits_007
    assert "GB 45438-2025" in credits_007
    assert "《人工智能生成合成内容标识办法》" in credits_007
    assert "Noto Sans CJK" in credits_007
    assert "测试附加致谢条目" in credits_007

    credits_005 = lib.generate_project_credits("005_transformer_noshiro_tutorial")
    assert "能代" in credits_005
    assert "ATDAN" in credits_005
    assert "GB 45438-2025" in credits_005

    # Verify backward compatibility of AssetItem.from_dict with minimal legacy dict
    legacy = AssetItem.from_dict({"id": "legacy_1", "type": "image", "category": "prop"})
    assert legacy.license == "CC BY-NC-SA 4.0"
    assert legacy.author == "ContentFlow Studio"
    assert legacy.attribution_required is True


def test_cover_designer_portrait_and_landscape(tmp_path: Path) -> None:
    """Tests CoverDesigner converting both 9:16 portrait and 16:9 landscape images to 1920x1080 + 1440x1080."""
    designer = CoverDesigner()

    # 1. 9:16 portrait base image -> 1920x1080 (16:9) + 1440x1080 (4:3)
    portrait_src = tmp_path / "portrait_9x16.jpg"
    Image.new("RGB", (1080, 1920), color=(25, 55, 110)).save(portrait_src)
    out_p = tmp_path / "cover_from_portrait.jpg"

    res_p = designer.design_cover(
        base_image_path=portrait_src,
        output_path=out_p,
        hook_line1="把B站账号交给AI",
        hook_line2="连夜肝出大肥鱼",
        hook_line3="60帧纯享热舞！",
        badge_text="AI接管账号实录",
        bottom_tags=["2K重绘", "60FPS满帧"],
    )
    assert res_p.layout_mode == "portrait_to_16x9"
    assert res_p.output_path.exists()
    assert res_p.output_4x3_path is not None and res_p.output_4x3_path.exists()

    with Image.open(res_p.output_path) as im16:
        assert im16.size == (1920, 1080)
    with Image.open(res_p.output_4x3_path) as im43:
        assert im43.size == (1440, 1080)

    # 2. 16:9 landscape base image -> 1920x1080 (16:9) + 1440x1080 (4:3)
    landscape_src = tmp_path / "landscape_16x9.jpg"
    Image.new("RGB", (1376, 768), color=(40, 70, 95)).save(landscape_src)
    out_l = tmp_path / "cover_from_landscape.jpg"

    res_l = designer.design_cover(
        base_image_path=landscape_src,
        output_path=out_l,
        hook_line1="能代手把手教你",
        hook_line2="大模型核心基石",
        hook_line3="Transformer全解",
        badge_text="硬核AI架构科普",
    )
    assert res_l.layout_mode == "landscape_16x9"
    assert res_l.output_path.exists()
    with Image.open(res_l.output_path) as im16_l:
        assert im16_l.size == (1920, 1080)

    # 3. Verify real project covers for 007 and 005 are 1920x1080
    cover_007 = (
        CONTENTFLOW_ROOT
        / "projects"
        / "007_deepseek_dafeiyu_phone_number"
        / "delivery"
        / "deepseek_dafeiyu_phone_number_cover.jpg"
    )
    cover_005 = (
        CONTENTFLOW_ROOT
        / "projects"
        / "005_transformer_noshiro_tutorial"
        / "delivery"
        / "能代教你大模型核心基石_Transformer原理解析_cover.jpg"
    )
    assert cover_007.exists()
    assert cover_005.exists()
    with Image.open(cover_007) as c7:
        assert c7.size == (1920, 1080)
    with Image.open(cover_005) as c5:
        assert c5.size == (1920, 1080)


def test_video_quality_gate_pass_and_blocker(tmp_path: Path) -> None:
    """Tests VideoQualityGate on real projects (007 & 005) and blocker detection on invalid covers."""
    gate = VideoQualityGate(root_dir=CONTENTFLOW_ROOT)

    vid_007 = _ensure_test_video(tmp_path / "007_synth_final.mp4", width=1080, height=1920, fps=60)
    rep_007 = gate.evaluate_project("007_deepseek_dafeiyu_phone_number", video_path=vid_007)
    assert rep_007.passed is True
    assert len(rep_007.blockers) == 0
    assert rep_007.total_score >= 90.0
    assert rep_007.grade == "S"
    assert set(rep_007.dimensions.keys()) == {"technical", "audio", "visual_dynamics", "cover_ctr", "compliance"}

    vid_005 = _ensure_test_video(tmp_path / "005_synth_final.mp4", width=1920, height=1080, fps=30)
    rep_005 = gate.evaluate_project("005_transformer_noshiro_tutorial", video_path=vid_005)
    assert rep_005.passed is True
    assert len(rep_005.blockers) == 0
    assert rep_005.total_score >= 80.0

    # Test blocker when a 9:16 vertical cover is supplied
    bad_cover = tmp_path / "vertical_bad_cover.jpg"
    Image.new("RGB", (1080, 1920), color=(20, 20, 20)).save(bad_cover)
    rep_blocked = gate.evaluate_project("007_deepseek_dafeiyu_phone_number", video_path=vid_007, cover_path=bad_cover)
    assert rep_blocked.passed is False
    assert rep_blocked.grade == "F"
    assert any("NOT 16:9" in b for b in rep_blocked.blockers)


def test_cli_design_cover_and_quality_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tests cli.py design-cover and quality-check subcommands."""
    out_cover = tmp_path / "cli_007_cover.jpg"
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "design-cover",
            "--project",
            "007",
            "--hook-line1",
            "把B站账号交给AI",
            "--hook-line2",
            "连夜肝出大肥鱼",
            "--hook-line3",
            "60帧纯享热舞！",
            "--output",
            str(out_cover),
        ],
    )
    assert cli.main() == 0
    assert out_cover.exists()

    vid_007 = _ensure_test_video(tmp_path / "cli_007_synth.mp4", width=1080, height=1920, fps=60)

    out_json = tmp_path / "qc_report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "cli.py",
            "quality-check",
            "--project",
            "007",
            "--video",
            str(vid_007),
            "--json",
            "--output-json",
            str(out_json),
        ],
    )
    assert cli.main() == 0
    assert out_json.exists()
    assert '"passed": true' in out_json.read_text(encoding="utf-8")
