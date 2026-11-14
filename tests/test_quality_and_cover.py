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
from core.asset_library import DEFAULT_ATTRIBUTION_RULES, AssetItem, AssetLibrary
from core.cover_designer import CoverDesigner
from core.quality_gate import VideoQualityGate


def _ensure_test_video(
    target_mp4: Path, width: int = 1080, height: int = 1920, fps: int = 60, duration: int = 4
) -> Path:
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
        f"testsrc2=size={width}x{height}:rate={fps}:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:sample_rate=48000:duration={duration}",
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
    assert "小咩先生" in noshiro.author
    assert "小咩先生" in noshiro.credit_line
    assert "小咩先生" in DEFAULT_ATTRIBUTION_RULES["noshiro"]["author"]
    assert "小咩先生" in DEFAULT_ATTRIBUTION_RULES["noshiro"]["credit_line"]

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
    assert "小咩先生" in credits_005
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
    real_005_dir = CONTENTFLOW_ROOT / "projects" / "005_transformer_noshiro_tutorial"
    real_005_cover = real_005_dir / "delivery" / "能代教你大模型核心基石_Transformer原理解析_cover.jpg"
    real_005_md = (real_005_dir / "delivery" / "bilibili.md").read_text(encoding="utf-8")

    # Setup compliant 005 fixture with @小咩先生 reference attribution
    proj_005_ok = tmp_path / "005_transformer_noshiro_tutorial"
    (proj_005_ok / "assets").mkdir(parents=True, exist_ok=True)
    (proj_005_ok / "delivery").mkdir(parents=True, exist_ok=True)
    (proj_005_ok / "assets" / "noshiro_reference.jpg").write_bytes(b"REF")
    md_with_ref = real_005_md if "小咩先生" in real_005_md else (real_005_md + "\n- 3D渲染参考：B站UP主 @小咩先生\n")
    (proj_005_ok / "delivery" / "bilibili.md").write_text(md_with_ref, encoding="utf-8")

    rep_005 = gate.evaluate_project(proj_005_ok, video_path=vid_005, cover_path=real_005_cover)
    assert rep_005.passed is True
    assert len(rep_005.blockers) == 0
    assert rep_005.total_score >= 80.0
    assert rep_005.dimensions["visual_dynamics"]["details"]["upper_frame_motion_delta"] > 0.15
    if shutil.which("ffprobe") is not None:
        assert any("帧率为 30fps" in iss for iss in rep_005.dimensions["technical"]["issues"])

    # Test blocker when @小咩先生 reference attribution is missing in bilibili.md
    proj_005_missing_ref = tmp_path / "005_noshiro_missing_ref"
    (proj_005_missing_ref / "assets").mkdir(parents=True, exist_ok=True)
    (proj_005_missing_ref / "delivery").mkdir(parents=True, exist_ok=True)
    (proj_005_missing_ref / "assets" / "noshiro_reference.jpg").write_bytes(b"REF")
    md_without_ref = real_005_md.replace("小咩先生", "")
    (proj_005_missing_ref / "delivery" / "bilibili.md").write_text(md_without_ref, encoding="utf-8")

    rep_missing_ref = gate.evaluate_project(proj_005_missing_ref, video_path=vid_005, cover_path=real_005_cover)
    assert rep_missing_ref.passed is False
    assert any("Missing reference attribution for @小咩先生" in b for b in rep_missing_ref.blockers)
    assert any(
        "缺少对参考素材作者 @小咩先生 的致谢说明" in iss for iss in rep_missing_ref.dimensions["compliance"]["issues"]
    )

    # Test upper_frame_motion_delta penalty when upper 78% of frame is static (only bottom subtitle bar changes)
    if shutil.which("ffmpeg") is not None:
        static_upper_mp4 = tmp_path / "static_upper_only_sub_changes.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x1e293b:s=640x360:r=30:d=3",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=3",
                "-vf",
                "drawbox=x=20:y=300:w=600:h=45:color=yellow@0.9:t=fill:enable='between(t,1.0,2.5)'",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(static_upper_mp4),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        rep_static = gate.evaluate_project(proj_005_ok, video_path=static_upper_mp4, cover_path=real_005_cover)
        assert rep_static.dimensions["visual_dynamics"]["details"]["upper_frame_motion_delta"] < 0.15
        assert rep_static.dimensions["visual_dynamics"]["score"] <= 12.0
        assert any(
            "画面主体(除底部字幕外)缺乏连续动态变化" in iss
            for iss in rep_static.dimensions["visual_dynamics"]["issues"]
        )

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


def test_local_aesthetic_evaluator_camera_and_contact_sheet(tmp_path: Path) -> None:
    """Tests LocalAestheticEvaluator camera stability analysis and 12-frame contact sheet generation."""
    from core.aesthetic_evaluator import LocalAestheticEvaluator

    evaluator = LocalAestheticEvaluator(allow_weight_download=False)
    vid = _ensure_test_video(tmp_path / "eval_test.mp4", width=1920, height=1080, fps=60)
    cov = Path("projects/004_ai_api_tutorial_2b/delivery/2B小姐姐教你大模型API核心三要素_cover.jpg")
    sheet = tmp_path / "diagnostic_contact_sheet.jpg"

    cam_rep_dance = evaluator.analyze_camera_and_motion(vid, is_tutorial=False)
    assert cam_rep_dance.camera_wobble_detected is False
    assert cam_rep_dance.ghosting_detected is False
    assert cam_rep_dance.stability_score_10 >= 8.0

    if vid.stat().st_size > 8192:
        cam_rep_tut = evaluator.analyze_camera_and_motion(vid, is_tutorial=True)
        assert cam_rep_tut.camera_wobble_detected is True

    aes_rep = evaluator.evaluate_aesthetics_and_contact_sheet(
        video_path=vid,
        cover_path=cov,
        output_contact_sheet=sheet,
        allow_download=False,
    )
    assert aes_rep.cover_split_hierarchy_ok is True
    assert aes_rep.cover_aesthetic_10 >= 6.0
    if vid.stat().st_size > 8192:
        assert sheet.exists()
        with Image.open(sheet) as im:
            assert im.size == (1920, 874)


def test_cover_designer_002_preset_and_qc_contact_sheet_path(tmp_path: Path) -> None:
    """Verifies 002 cover preset (16:9 + 4:3) and non-nested output/diagnostic_contact_sheet.jpg placement."""
    proj_002 = CONTENTFLOW_ROOT / "projects" / "002_yowane_cicd"
    out_cover = tmp_path / "002_cover.jpg"
    res = CoverDesigner().design_project_cover(proj_002, output_path=out_cover)

    out_16x9 = res.output_path
    assert res.output_4x3_path is not None
    out_4x3 = res.output_4x3_path
    assert out_16x9.exists()
    assert out_4x3.exists()
    with Image.open(out_16x9) as im:
        assert im.size == (1920, 1080)
    with Image.open(out_4x3) as im43:
        assert im43.size == (1440, 1080)

    real_cover = proj_002 / "delivery" / "3D手办弱音的CI_CD避坑指南_cover.jpg"
    assert real_cover.exists()
    with Image.open(real_cover) as rim:
        assert rim.size == (1920, 1080)

    proj = tmp_path / "099_test_proj"
    vid = _ensure_test_video(proj / "output" / "video" / "demo.mp4", width=1920, height=1080, fps=60, duration=6)
    cov = proj / "delivery" / "demo_cover.jpg"
    cov.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(out_16x9) as im:
        im.save(cov, format="JPEG", quality=92)
    (proj / "delivery" / "bilibili.md").write_text(
        "# Test Release\n* **视频标题**：【测试】contact sheet 路径测试\n* **简介**：含借物表与 AIGC 声明\n",
        encoding="utf-8",
    )

    VideoQualityGate().evaluate_project(proj)
    assert not (proj / "output" / "output").exists()
    if vid.stat().st_size > 8192:
        assert (proj / "output" / "diagnostic_contact_sheet.jpg").exists()


def test_cover_designer_008_003_009_presets(tmp_path: Path) -> None:
    """Verifies 008, 003, and 009 viral cover presets produce crisp 16:9 (1920x1080) and 4:3 (1440x1080) covers."""
    designer = CoverDesigner()
    for pid, out_name in [
        ("008_ai_agent_day2_takeover_diary", "008_cover.jpg"),
        ("003_ai_managing_ai", "003_cover.jpg"),
        ("009_rem_aeflow_gui_agent", "009_cover.jpg"),
    ]:
        res = designer.design_project_cover(CONTENTFLOW_ROOT / "projects" / pid, output_path=tmp_path / out_name)
        assert res.output_path.exists()
        assert res.output_4x3_path is not None and res.output_4x3_path.exists()
        with Image.open(res.output_path) as im16:
            assert im16.size == (1920, 1080)
        with Image.open(res.output_4x3_path) as im43:
            assert im43.size == (1440, 1080)


def test_audio_mixer_and_human_preference_scorer(tmp_path: Path) -> None:
    """Tests procedural BGM+SFX mixing, local richness analysis, and online Gradio scorer (mocked + offline)."""
    import json
    import math
    import wave
    from unittest.mock import MagicMock

    import numpy as np

    from core.audio_mixer import SAMPLE_RATE, mix_voice_with_bgm_and_sfx
    from core.human_preference_scorer import (
        HumanPreferenceScorer,
        compute_local_audio_richness,
        score_anime_visual_online,
        score_audio_enjoyment_online,
    )

    dry_wav = tmp_path / "dry_voice.wav"
    n_tot = int(2.6 * SAMPLE_RATE)
    t = np.arange(n_tot, dtype=np.float32) / float(SAMPLE_RATE)
    voice_sig = np.where((t >= 0.4) & (t <= 2.1), 0.45 * np.sin(2.0 * math.pi * 260.0 * t), 0.0).astype(np.float32)
    stereo = np.stack([voice_sig, voice_sig], axis=-1)
    with wave.open(str(dry_wav), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes((stereo * 32767.0).astype(np.int16).tobytes())

    dry_rich = compute_local_audio_richness(dry_wav)
    assert dry_rich["dead_air_ratio"] >= 0.25

    mixed_out = tmp_path / "mixed_voice.wav"
    mix_voice_with_bgm_and_sfx(
        voice_mp3=dry_wav,
        output_mp3=mixed_out,
        scenes=[{"start": 0.0, "end": 1.3}, {"start": 1.3, "end": 2.6}],
    )
    assert mixed_out.exists() and mixed_out.stat().st_size > 10_000
    mixed_rich = compute_local_audio_richness(mixed_out)
    assert mixed_rich["dead_air_ratio"] < dry_rich["dead_air_ratio"]
    assert mixed_rich["audio_richness_10"] >= dry_rich["audio_richness_10"]

    class _Resp:
        def __init__(self, *, json_obj: object = None, text: str = "") -> None:
            self.ok = True
            self._json = json_obj
            self.text = text

        def json(self) -> object:
            return self._json

    mock_session = MagicMock()
    plotly_payload = json.dumps(
        {
            "data": [
                {
                    "x": ["Production Quality", "Production Complexity", "Content Enjoyment", "Content Usefulness"],
                    "y": [8.12, 3.65, 6.74, 6.45],
                }
            ]
        }
    )
    mock_session.post.side_effect = [
        _Resp(json_obj=["/tmp/gradio/img.jpg"]),
        _Resp(json_obj={"event_id": "ev_img"}),
        _Resp(json_obj=["/tmp/gradio/aud.wav"]),
        _Resp(json_obj={"event_id": "ev_aud"}),
    ]
    mock_session.get.side_effect = [
        _Resp(text='event: complete\ndata: [{"confidences": [{"label": "score", "confidence": 0.742}]}]\n'),
        _Resp(text="event: complete\ndata: " + json.dumps([{"type": "plotly", "plot": plotly_payload}]) + "\n"),
    ]

    cov_jpg = tmp_path / "cov.jpg"
    Image.new("RGB", (640, 360), (20, 40, 90)).save(cov_jpg)
    a_score = score_anime_visual_online(cov_jpg, crop_box=(320, 0, 640, 360), session=mock_session)
    assert a_score == pytest.approx(0.742, abs=1e-3)

    ab_scores = score_audio_enjoyment_online(mixed_out, session=mock_session)
    assert ab_scores is not None
    assert ab_scores["production_complexity"] == pytest.approx(3.65, abs=1e-2)
    assert ab_scores["content_enjoyment"] == pytest.approx(6.74, abs=1e-2)

    proj_tmp = tmp_path / "098_score_demo"
    (proj_tmp / "delivery").mkdir(parents=True)
    cov_jpg.replace(proj_tmp / "delivery" / "demo_cover.jpg")
    mixed_out.replace(proj_tmp / "delivery" / "demo_audio.wav")
    off_rep = HumanPreferenceScorer(root_dir=tmp_path).evaluate_project(proj_tmp, allow_online=False)
    assert off_rep.online_enabled is False
    assert off_rep.human_appeal_index > 0.0


def test_subtitle_cue_spacing_and_glyph_check() -> None:
    """Verifies stripped clause punctuation preserves word spacing and checks font glyph coverage."""
    from core.local_tts import _split_subtitle_cues
    from core.quality_gate import check_missing_glyphs

    cues = _split_subtitle_cues("把账号交给AI，连夜跑通60帧工作室，全流程交付！", 0.0, 6.0, max_chars=24)
    assert len(cues) >= 1
    assert "把账号交给AI 连夜跑通60帧工作室" in cues[0][2] or "连夜跑通" in cues[0][2]
    assert check_missing_glyphs("简体中文 60FPS • 安全护栏") == []
    try:
        import fontTools  # noqa: F401

        font_ok = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc").exists()
        if font_ok:
            assert "\ue800" in check_missing_glyphs("私有字符 \ue800")
    except ImportError:
        pass


def test_box_smooth_and_tts_timeline_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies O(N) prefix-sum smoother matches numpy uniform smooth and TTS SHA-256 cache hits."""
    import shutil

    import numpy as np

    from core.audio_mixer import _box_smooth_1d
    from core.local_tts import LocalNeuralTTS

    sig = np.linspace(0.0, 1.0, 250, dtype=np.float32) + 0.1 * np.sin(np.arange(250, dtype=np.float32))
    win = 17
    expected = np.convolve(sig, np.ones(win, dtype=np.float32) / float(win), mode="same").astype(np.float32)
    actual = _box_smooth_1d(sig, win)
    assert np.allclose(actual, expected, atol=1e-5)

    if shutil.which("ffmpeg") is None:
        return

    tts = LocalNeuralTTS(sample_rate=16000)
    calls: list[str] = []

    def fake_synth(text: str, voice: str = "zf_001", speed: float = 1.0, edge_voice: str = "") -> np.ndarray:
        calls.append(text)
        t = np.arange(8000, dtype=np.float32) / 16000.0
        return (0.4 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)

    monkeypatch.setattr(tts, "synthesize_text", fake_synth)
    scenes = [{"tts_text": "第一句缓存测试", "subtitle_text": "第一句缓存测试"}]
    out_mp3 = tmp_path / "cached.mp3"
    out_srt = tmp_path / "cached.srt"

    tl1 = tts.synthesize_scenes(scenes, output_mp3=out_mp3, output_srt=out_srt, voice="zf_043")
    assert len(calls) == 1
    assert out_mp3.with_suffix(".timeline.json").exists()

    tl2 = tts.synthesize_scenes(scenes, output_mp3=out_mp3, output_srt=out_srt, voice="zf_043")
    assert len(calls) == 1
    assert tl2 == tl1
