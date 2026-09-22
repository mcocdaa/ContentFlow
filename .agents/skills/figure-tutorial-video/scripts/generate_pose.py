#!/usr/bin/env python3
"""Generate consistent character action poses with Doubao-Seedream-5.0-Pro and auto-rembg."""

import argparse
import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

DEFAULT_ARK_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3/images/generations")


def main():
    parser = argparse.ArgumentParser(description="Generate consistent character pose using Seedream 5.0 Pro")
    parser.add_argument("--ref-image", required=True, help="Path to reference character image (JPEG/PNG)")
    parser.add_argument("--prompt", required=True, help="Action and emotion prompt")
    parser.add_argument("--output", required=True, help="Destination output path for generated image (.jpg)")
    parser.add_argument("--api-key", default=None, help="VolcEngine Ark API Key (defaults to ARK_API_KEY env var)")
    parser.add_argument("--size", default="2560x1440", help="Resolution (default: 2560x1440)")
    parser.add_argument("--skip-rembg", action="store_true", help="Skip rembg background removal")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ARK_API_KEY")
    if not api_key:
        print("[-] Error: VolcEngine Ark API key not provided. Set ARK_API_KEY or use --api-key.")
        sys.exit(1)
    ref_path = Path(args.ref_image)
    if not ref_path.exists():
        print(f"[-] Reference image not found: {ref_path}")
        sys.exit(1)

    with open(ref_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    ref_uri = f"data:image/jpeg;base64,{b64}"

    payload = {
        "model": "doubao-seedream-5.0-pro",
        "prompt": args.prompt,
        "image": ref_uri,
        "size": args.size,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"[*] Calling Ark API (doubao-seedream-5.0-pro) with reference {ref_path.name}...")
    req = urllib.request.Request(DEFAULT_ARK_URL, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            img_url = data["data"][0]["url"]
            print(f"[+] Generation succeeded! Downloading from TOS...")
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(img_url, out_path)
            print(f"[+] Saved original image: {out_path}")
    except urllib.error.HTTPError as e:
        print(f"[-] API Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)

    if not args.skip_rembg:
        try:
            from rembg import remove
            from PIL import Image

            print(f"[*] Extracting transparent cutout with rembg...")
            inp = Image.open(out_path)
            cutout = remove(inp)
            cutout_path = out_path.with_name(out_path.stem + "_transparent.png")
            cutout.save(cutout_path)
            print(f"[+] Saved transparent cutout: {cutout_path}")
        except ImportError:
            print("[!] Warning: rembg is not installed. Skipping transparent cutout.")


if __name__ == "__main__":
    main()
