"""Viral accompaniment & remix audio hunter for ContentFlow.

Codifies WBI-authenticated Bilibili viral BGM discovery, high-bitrate DASH/MP4 audio extraction,
credit metadata tracking for 借物表 attribution, and multi-act sidechain vocal/accompaniment mixing.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import requests

from core.auth_vault import STANDARD_USER_AGENT, AuthVault

logger = logging.getLogger(__name__)

MIXIN_KEY_ENC_TAB = [
    46,
    47,
    18,
    2,
    53,
    8,
    23,
    32,
    15,
    50,
    10,
    31,
    58,
    3,
    45,
    35,
    27,
    43,
    5,
    49,
    33,
    9,
    42,
    19,
    29,
    28,
    14,
    39,
    12,
    38,
    41,
    13,
    37,
    48,
    7,
    16,
    24,
    55,
    40,
    61,
    26,
    17,
    0,
    1,
    60,
    51,
    30,
    4,
    22,
    25,
    54,
    21,
    56,
    59,
    6,
    63,
    57,
    62,
    11,
    36,
    20,
    34,
    44,
    52,
]

BILIBILI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
BILIBILI_WBI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
BILIBILI_VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
BILIBILI_PLAYURL_URL = "https://api.bilibili.com/x/player/playurl"


def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


class BilibiliBgmHunter:
    """Discovers and extracts clean viral accompaniment slices from Bilibili or local media."""

    def __init__(
        self,
        vault: Optional[AuthVault] = None,
        cookies: Optional[Dict[str, str]] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.vault = vault or AuthVault()
        self.cookies = dict(cookies) if cookies is not None else self.vault.load_bilibili_cookies()
        self.session = session or requests.Session()
        self._mixin_key: Optional[str] = None

    @staticmethod
    def _headers(referer: str = "https://www.bilibili.com/") -> Dict[str, str]:
        return {
            "User-Agent": STANDARD_USER_AGENT,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
        }

    def _get_wbi_mixin_key(self) -> str:
        if self._mixin_key:
            return self._mixin_key
        resp = self.session.get(BILIBILI_NAV_URL, cookies=self.cookies, headers=self._headers(), timeout=10)
        resp.raise_for_status()
        wbi_img = ((resp.json().get("data") or {}).get("wbi_img")) or {}
        img_url = str(wbi_img.get("img_url") or "")
        sub_url = str(wbi_img.get("sub_url") or "")
        if not img_url or not sub_url:
            raise RuntimeError("Failed to fetch Bilibili WBI keys from /x/web-interface/nav")
        raw_wbi = Path(img_url).stem + Path(sub_url).stem
        self._mixin_key = "".join(raw_wbi[i] for i in MIXIN_KEY_ENC_TAB)[:32]
        return self._mixin_key

    def search_bgm(self, keyword: str, order: str = "click", limit: int = 8) -> List[Dict[str, Any]]:
        """Searches Bilibili via WBI-signed endpoint for viral accompaniment/meme tracks."""
        mixin_key = self._get_wbi_mixin_key()
        params = {
            "search_type": "video",
            "keyword": keyword,
            "order": order,
            "page": 1,
            "page_size": max(1, min(30, int(limit))),
            "wts": int(time.time()),
        }
        filtered = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in sorted(params.items())}
        query = urllib.parse.urlencode(filtered)
        w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
        url = f"{BILIBILI_WBI_SEARCH_URL}?{query}&w_rid={w_rid}"
        resp = self.session.get(url, cookies=self.cookies, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        items = ((resp.json().get("data") or {}).get("result")) or []
        results: List[Dict[str, Any]] = []
        for it in items[:limit]:
            results.append(
                {
                    "bvid": str(it.get("bvid") or ""),
                    "title": _strip_html_tags(str(it.get("title") or "")),
                    "author": str(it.get("author") or ""),
                    "play": int(it.get("play") or 0),
                    "duration": str(it.get("duration") or ""),
                }
            )
        return results

    @staticmethod
    def _extract_wav_with_ffmpeg(
        input_media: Path,
        output_wav: Path,
        start_sec: float = 0.0,
        duration_sec: Optional[float] = None,
        fade_in_sec: float = 0.04,
        fade_out_sec: float = 0.14,
        sr: int = 48000,
    ) -> float:
        """Extracts a 48kHz stereo PCM WAV slice with smooth fade-in/out using FFmpeg."""
        output_wav = Path(output_wav)
        output_wav.parent.mkdir(parents=True, exist_ok=True)

        eff_dur = duration_sec
        if eff_dur is None:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(input_media),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if probe.returncode == 0 and probe.stdout.strip():
                eff_dur = max(0.2, float(probe.stdout.strip()) - max(0.0, start_sec))

        af_filters: List[str] = []
        if fade_in_sec > 0.005:
            af_filters.append(f"afade=t=in:st=0:d={fade_in_sec:.3f}")
        if fade_out_sec > 0.005 and eff_dur is not None and eff_dur > fade_out_sec + 0.05:
            fade_st = max(0.0, eff_dur - fade_out_sec)
            af_filters.append(f"afade=t=out:st={fade_st:.3f}:d={fade_out_sec:.3f}")

        cmd = ["ffmpeg", "-y", "-nostats", "-loglevel", "error", "-ss", f"{max(0.0, start_sec):.3f}"]
        if eff_dur is not None and eff_dur > 0:
            cmd.extend(["-t", f"{eff_dur:.3f}"])
        cmd.extend(["-i", str(input_media), "-vn", "-ac", "2", "-ar", str(sr)])
        if af_filters:
            cmd.extend(["-af", ",".join(af_filters)])
        cmd.extend(["-c:a", "pcm_s16le", str(output_wav)])
        subprocess.run(cmd, check=True)

        with wave.open(str(output_wav), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())

    def extract_audio_clip(
        self,
        source: Union[str, Path],
        output_wav: Union[str, Path],
        start_sec: float = 0.0,
        duration_sec: Optional[float] = None,
        fade_in_sec: float = 0.04,
        fade_out_sec: float = 0.14,
        sr: int = 48000,
    ) -> Dict[str, Any]:
        """Extracts a clean 48kHz stereo WAV slice from either a local file or a Bilibili BVID."""
        src_str = str(source).strip()
        out_path = Path(output_wav)
        local_cand = Path(src_str)
        if local_cand.exists():
            actual_dur = self._extract_wav_with_ffmpeg(
                input_media=local_cand,
                output_wav=out_path,
                start_sec=start_sec,
                duration_sec=duration_sec,
                fade_in_sec=fade_in_sec,
                fade_out_sec=fade_out_sec,
                sr=sr,
            )
            return {
                "output_wav": str(out_path),
                "source": str(local_cand),
                "bvid": "",
                "title": local_cand.stem,
                "author": "本地参考音频",
                "duration_sec": round(actual_dur, 3),
                "credit_line": f"音频引用自本地素材 `{local_cand.name}`",
            }

        bvid = src_str
        headers = self._headers(f"https://www.bilibili.com/video/{bvid}/")
        v_resp = self.session.get(BILIBILI_VIEW_URL, params={"bvid": bvid}, headers=headers, timeout=12)
        v_resp.raise_for_status()
        v_data = v_resp.json().get("data") or {}
        cid = v_data.get("cid")
        if not cid:
            raise RuntimeError(f"Bilibili video metadata missing cid for {bvid}: {v_resp.text[:300]}")
        title = str(v_data.get("title") or bvid)
        author = str((v_data.get("owner") or {}).get("name") or "")

        # Prefer high-bitrate DASH audio stream (fnval=16), fallback to progressive MP4 durl
        stream_url = ""
        p_dash = self.session.get(
            BILIBILI_PLAYURL_URL,
            params={"bvid": bvid, "cid": cid, "qn": 80, "fnval": 16},
            headers=headers,
            timeout=12,
        ).json()
        audios = ((p_dash.get("data") or {}).get("dash") or {}).get("audio") or []
        if audios:
            top_audio = sorted(audios, key=lambda x: int(x.get("bandwidth") or 0), reverse=True)[0]
            stream_url = str(top_audio.get("baseUrl") or top_audio.get("base_url") or "")
        if not stream_url:
            p_prog = self.session.get(
                BILIBILI_PLAYURL_URL,
                params={"bvid": bvid, "cid": cid, "qn": 64, "fnval": 1},
                headers=headers,
                timeout=12,
            ).json()
            durls = (p_prog.get("data") or {}).get("durl") or []
            if durls:
                stream_url = str(durls[0].get("url") or "")
        if not stream_url:
            raise RuntimeError(f"No downloadable audio stream found for {bvid}")

        with tempfile.TemporaryDirectory() as td:
            raw_dl = Path(td) / f"{bvid}.media"
            with self.session.get(stream_url, headers=headers, stream=True, timeout=60) as dl:
                dl.raise_for_status()
                with open(raw_dl, "wb") as fh:
                    for ch in dl.iter_content(65536):
                        if ch:
                            fh.write(ch)
            actual_dur = self._extract_wav_with_ffmpeg(
                input_media=raw_dl,
                output_wav=out_path,
                start_sec=start_sec,
                duration_sec=duration_sec,
                fade_in_sec=fade_in_sec,
                fade_out_sec=fade_out_sec,
                sr=sr,
            )

        credit = f"BGM/音频片段致谢：B站 UP主「{author}」作品《{title}》（{bvid}）"
        return {
            "output_wav": str(out_path),
            "source": bvid,
            "bvid": bvid,
            "title": title,
            "author": author,
            "duration_sec": round(actual_dur, 3),
            "credit_line": credit,
        }

    @staticmethod
    def load_wav_stereo_f32(wav_path: Union[str, Path], target_sr: int = 48000) -> np.ndarray:
        """Loads a WAV file as (N, 2) float32 normalized in [-1, 1] at target_sr."""
        with wave.open(str(wav_path), "rb") as wf:
            n_ch = wf.getnchannels()
            sw = wf.getsampwidth()
            src_sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())

        if sw == 2:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        elif sw == 4:
            arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported WAV sample width {sw} bytes in {wav_path}")

        arr = arr.reshape(-1, n_ch)
        if n_ch == 1:
            arr = np.repeat(arr, 2, axis=1)
        elif n_ch > 2:
            arr = arr[:, :2]

        if src_sr != target_sr and arr.shape[0] > 1:
            dst_n = max(1, int(round(arr.shape[0] * (target_sr / float(src_sr)))))
            x_old = np.linspace(0.0, 1.0, arr.shape[0], dtype=np.float64)
            x_new = np.linspace(0.0, 1.0, dst_n, dtype=np.float64)
            left = np.interp(x_new, x_old, arr[:, 0]).astype(np.float32)
            right = np.interp(x_new, x_old, arr[:, 1]).astype(np.float32)
            arr = np.stack([left, right], axis=1)
        return arr

    @classmethod
    def _time_stretch_preserve_pitch(cls, v_arr: np.ndarray, target_n: int, sr: int) -> np.ndarray:
        """Time-compresses a vocal segment to target_n via pitch-preserving FFmpeg WSOLA `atempo`."""
        target_n = max(1, int(target_n))
        if v_arr.shape[0] <= target_n:
            return v_arr
        ratio = v_arr.shape[0] / float(target_n)
        if ratio <= 1.005 or shutil.which("ffmpeg") is None:
            if ratio > 1.005:
                logger.warning("ffmpeg not found; trimming vocal overlay instead of pitch-shifting")
            out = v_arr[:target_n].copy()
            fade_n = min(int(0.015 * sr), target_n // 8)
            if fade_n > 0:
                out[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)[:, None]
            return out

        filters: List[str] = []
        rem = ratio
        while rem > 2.0:
            filters.append("atempo=2.0")
            rem /= 2.0
        filters.append(f"atempo={rem:.4f}")
        af_str = ",".join(filters)

        pcm_in = (np.clip(v_arr, -0.98, 0.98) * 32767.0).astype(np.int16)
        with tempfile.TemporaryDirectory() as td:
            in_wav = Path(td) / "vocal_in.wav"
            out_wav = Path(td) / "vocal_out.wav"
            with wave.open(str(in_wav), "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(sr)
                wf.writeframes(pcm_in.tobytes())
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-nostats",
                    "-loglevel",
                    "error",
                    "-i",
                    str(in_wav),
                    "-af",
                    af_str,
                    "-ac",
                    "2",
                    "-ar",
                    str(sr),
                    "-c:a",
                    "pcm_s16le",
                    str(out_wav),
                ],
                check=True,
            )
            stretched = cls.load_wav_stereo_f32(out_wav, target_sr=sr)

        if stretched.shape[0] < target_n:
            pad = np.zeros((target_n - stretched.shape[0], 2), dtype=np.float32)
            return np.concatenate([stretched, pad], axis=0)
        if stretched.shape[0] > target_n:
            trimmed = stretched[:target_n].copy()
            fade_n = min(int(0.010 * sr), target_n // 8)
            if fade_n > 0:
                trimmed[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)[:, None]
            return trimmed
        return stretched

    @classmethod
    def concat_or_duck_segments(
        cls,
        segments: List[Dict[str, Any]],
        output_wav: Union[str, Path],
        vocal_overlays: Optional[List[Dict[str, Any]]] = None,
        impact_times_sec: Optional[List[float]] = None,
        sr: int = 48000,
    ) -> Path:
        """Builds an exact-length multi-act stereo 48kHz master WAV from music slices + optional vocals."""
        if not segments:
            raise ValueError("segments must not be empty")

        bed_chunks: List[np.ndarray] = []
        for seg in segments:
            dur = float(seg["duration_sec"])
            n_target = max(1, int(round(dur * sr)))
            gain = float(seg.get("gain", 1.0))
            fade_sec = float(seg.get("edge_fade_sec", 0.03))
            if seg.get("wav_path"):
                arr = cls.load_wav_stereo_f32(Path(seg["wav_path"]), target_sr=sr)
            else:
                arr = np.zeros((n_target, 2), dtype=np.float32)

            if arr.shape[0] < n_target:
                pad = np.zeros((n_target - arr.shape[0], 2), dtype=np.float32)
                arr = np.concatenate([arr, pad], axis=0)
            else:
                arr = arr[:n_target]

            arr = arr * gain
            fade_n = min(int(fade_sec * sr), n_target // 4)
            if fade_n > 0:
                ramp_in = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)[:, None]
                ramp_out = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)[:, None]
                arr[:fade_n] *= ramp_in
                arr[-fade_n:] *= ramp_out
            bed_chunks.append(arr)

        master_bed = np.concatenate(bed_chunks, axis=0)
        n_total = master_bed.shape[0]

        # Add optional dramatic bass-drop / slam impacts (e.g. at act cut boundaries)
        for t_imp in impact_times_sec or []:
            i0 = int(round(float(t_imp) * sr))
            imp_len = min(int(0.45 * sr), n_total - i0)
            if 0 <= i0 < n_total and imp_len > 32:
                dt = np.arange(imp_len, dtype=np.float32) / float(sr)
                freq = 48.0 + 135.0 * np.exp(-dt * 28.0)
                boom = 0.42 * np.tanh(1.5 * np.sin(2.0 * math.pi * freq * dt)) * np.exp(-dt * 7.5)
                master_bed[i0 : i0 + imp_len, 0] += boom
                master_bed[i0 : i0 + imp_len, 1] += boom

        vocal_buf = np.zeros((n_total, 2), dtype=np.float32)
        duck_env = np.ones(n_total, dtype=np.float32)
        for ov in vocal_overlays or []:
            if ov.get("wav_path"):
                v_arr = cls.load_wav_stereo_f32(Path(ov["wav_path"]), target_sr=sr)
            else:
                raw_v = np.asarray(ov["wav"], dtype=np.float32)
                src_sr = int(ov.get("src_sr") or 24000)
                if raw_v.ndim == 1:
                    raw_v = np.stack([raw_v, raw_v], axis=1)
                if src_sr != sr and raw_v.shape[0] > 1:
                    dst_n = max(1, int(round(raw_v.shape[0] * (sr / float(src_sr)))))
                    x_old = np.linspace(0.0, 1.0, raw_v.shape[0], dtype=np.float64)
                    x_new = np.linspace(0.0, 1.0, dst_n, dtype=np.float64)
                    l_v = np.interp(x_new, x_old, raw_v[:, 0]).astype(np.float32)
                    r_v = np.interp(x_new, x_old, raw_v[:, 1]).astype(np.float32)
                    v_arr = np.stack([l_v, r_v], axis=1)
                else:
                    v_arr = raw_v

            max_dur = ov.get("max_duration_sec")
            if max_dur is not None:
                max_n = max(16, int(round(float(max_dur) * sr)))
                if v_arr.shape[0] > max_n:
                    ratio = v_arr.shape[0] / float(max_n)
                    max_tempo_ratio = float(ov.get("max_tempo_ratio", 1.18))
                    if ratio > max_tempo_ratio:
                        if ov.get("truncate_if_exceeds", False):
                            pre_target_n = max(max_n, int(round(v_arr.shape[0] / max_tempo_ratio)))
                            v_arr = cls._time_stretch_preserve_pitch(v_arr, pre_target_n, sr)[:max_n].copy()
                            fade_n = min(int(0.020 * sr), v_arr.shape[0] // 8)
                            if fade_n > 0:
                                v_arr[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)[:, None]
                        else:
                            raise ValueError(
                                f"Vocal overlay exceeds max_duration_sec by {ratio:.2f}x "
                                f"(limit {max_tempo_ratio:.2f}x); shorten spoken text or widen window "
                                "instead of pitch-shifting audio."
                            )
                    else:
                        v_arr = cls._time_stretch_preserve_pitch(v_arr, max_n, sr)

            s_idx = max(0, int(round(float(ov.get("start_sec", 0.0)) * sr)))
            fit_n = min(v_arr.shape[0], n_total - s_idx)
            if fit_n > 0:
                v_gain = float(ov.get("gain", 1.15))
                d_gain = float(ov.get("duck_gain", 0.35))
                vocal_buf[s_idx : s_idx + fit_n] += v_arr[:fit_n] * v_gain
                duck_env[s_idx : s_idx + fit_n] = np.minimum(duck_env[s_idx : s_idx + fit_n], d_gain)

        if vocal_overlays:
            duck_env = np.convolve(duck_env, np.ones(1200, dtype=np.float32) / 1200.0, mode="same")

        mixed = master_bed * duck_env[:, None] + vocal_buf
        # Tail fade to avoid clicks
        tail_n = min(int(0.08 * sr), n_total // 8)
        if tail_n > 0:
            mixed[-tail_n:] *= np.linspace(1.0, 0.0, tail_n, dtype=np.float32)[:, None]

        # Soft safety limiter preventing digital clipping while preserving punch
        peak = float(np.max(np.abs(mixed))) if mixed.size else 1.0
        if peak > 0.92:
            mixed = np.tanh(mixed * (0.90 / peak))

        pcm = (np.clip(mixed, -0.98, 0.98) * 32767.0).astype(np.int16)
        out_p = Path(output_wav)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_p), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())
        return out_p
