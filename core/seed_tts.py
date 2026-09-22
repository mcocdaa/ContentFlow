"""Doubao Seed-TTS 2.0 Integration for ContentFlow.
Implements ByteDance OpenSpeech V3 Unidirectional HTTP streaming API
for ultra-high fidelity, natural character voiceovers.

API Reference:
- Base URL: https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional
- Resource-Id: seed-tts-2.0
- Auth: X-Api-Key: <token>
"""

import os
import sys
import json
import uuid
import base64
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import requests


DEFAULT_TTS_BASE_URL = os.environ.get(
    "DOUBAO_TTS_BASE_URL",
    "https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional"
)
DEFAULT_RESOURCE_ID = os.environ.get("DOUBAO_TTS_RESOURCE_ID", "seed-tts-2.0")


class DoubaoSeedTTS:
    """Client for ByteDance OpenSpeech V3 Seed-TTS 2.0."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_TTS_BASE_URL,
        resource_id: str = DEFAULT_RESOURCE_ID,
    ):
        self.api_key = api_key or os.environ.get("DOUBAO_TTS_API_KEY") or os.environ.get("ARK_API_KEY")
        self.base_url = base_url
        self.resource_id = resource_id

    def synthesize(
        self,
        text: str,
        output_file: str | Path,
        voice_type: str = "zh_female_shuangkuaisisi_moon_bigtts",
        speed_ratio: float = 1.0,
        volume_ratio: float = 1.0,
        pitch_ratio: float = 1.0,
        audio_format: str = "mp3",
        sample_rate: int = 24000,
    ) -> Path:
        """Synthesize text to audio using Seed-TTS 2.0.

        Args:
            text: Plain text content to synthesize.
            output_file: Destination path for audio (.mp3 or .wav).
            voice_type: Speaker ID / voice model name.
            speed_ratio: Speech rate (0.5 - 2.0).
            volume_ratio: Speech volume (0.5 - 2.0).
            pitch_ratio: Speech pitch (0.5 - 2.0).
            audio_format: Output container format ('mp3', 'wav', 'pcm').
            sample_rate: Audio sampling frequency (e.g. 24000).

        Returns:
            Path to generated audio file.
        """
        if not self.api_key:
            raise ValueError(
                "Doubao TTS API Key not provided. Set DOUBAO_TTS_API_KEY environment variable."
            )

        output_path = Path(output_file).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        req_id = str(uuid.uuid4())
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": req_id,
        }

        payload: Dict[str, Any] = {
            "user": {
                "uid": f"contentflow_{uuid.uuid4().hex[:8]}"
            },
            "audio": {
                "voice_type": voice_type,
                "encoding": audio_format,
                "sample_rate": sample_rate,
                "speed_ratio": speed_ratio,
                "volume_ratio": volume_ratio,
                "pitch_ratio": pitch_ratio,
            },
            "req_params": {
                "text": text,
                "speaker": voice_type,
                "audio_params": {
                    "format": audio_format,
                    "sample_rate": sample_rate,
                },
                "speed_ratio": speed_ratio,
                "volume_ratio": volume_ratio,
                "pitch_ratio": pitch_ratio,
            },
        }

        # Open stream connection
        with requests.Session() as session:
            response = session.post(
                self.base_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=60,
            )

            if response.status_code != 200:
                try:
                    err_json = response.json()
                    err_code = err_json.get("header", {}).get("code") or err_json.get("code")
                    err_msg = err_json.get("header", {}).get("message") or err_json.get("message")
                    raise RuntimeError(
                        f"Seed-TTS API Error [HTTP {response.status_code}, code {err_code}]: {err_msg}"
                    )
                except Exception as parse_err:
                    if isinstance(parse_err, RuntimeError):
                        raise
                    raise RuntimeError(
                        f"Seed-TTS API Error [HTTP {response.status_code}]: {response.text}"
                    )

            total_bytes = 0
            with open(output_path, "wb") as out_fp:
                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode("utf-8"))
                        code = data.get("code") if data.get("code") is not None else data.get("header", {}).get("code", 0)
                        # In OpenSpeech V3: 0 is streaming chunk, 20000000 is final OK completion
                        if code not in (0, 20000000):
                            msg = data.get("message") or data.get("header", {}).get("message", "Unknown error")
                            raise RuntimeError(
                                f"Seed-TTS synthesis failed: code={code}, msg={msg}"
                            )
                        audio_b64 = data.get("data") or data.get("audio")
                        if audio_b64:
                            raw_chunk = base64.b64decode(audio_b64)
                            out_fp.write(raw_chunk)
                            total_bytes += len(raw_chunk)
                    except json.JSONDecodeError:
                        out_fp.write(line)
                        total_bytes += len(line)

        if total_bytes == 0:
            raise RuntimeError("Seed-TTS returned zero bytes of audio output.")

        return output_path


def main():
    parser = argparse.ArgumentParser(description="Synthesize speech with Doubao Seed-TTS 2.0")
    parser.add_argument("--text", required=True, help="Text to speak")
    parser.add_argument("--output", default="output_seed_tts.mp3", help="Output audio path (.mp3)")
    parser.add_argument("--voice", default="zh_female_shuangkuaisisi_moon_bigtts", help="Voice model ID")
    parser.add_argument("--api-key", default=None, help="VolcEngine API key")
    parser.add_argument("--resource-id", default=DEFAULT_RESOURCE_ID, help="Resource ID (seed-tts-2.0)")
    parser.add_argument("--base-url", default=DEFAULT_TTS_BASE_URL, help="Base URL for OpenSpeech V3")
    args = parser.parse_args()

    client = DoubaoSeedTTS(
        api_key=args.api_key,
        base_url=args.base_url,
        resource_id=args.resource_id,
    )
    print(f"[*] Calling Doubao Seed-TTS 2.0...")
    print(f"    - Base URL:    {args.base_url}")
    print(f"    - Resource ID: {args.resource_id}")
    print(f"    - Voice:       {args.voice}")
    try:
        out = client.synthesize(args.text, args.output, voice_type=args.voice)
        print(f"[+] Audio successfully saved to: {out} ({out.stat().st_size} bytes)")
    except Exception as e:
        print(f"[-] Synthesis failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
