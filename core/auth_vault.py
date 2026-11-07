"""Multi-Platform Social Matrix Authentication Vault & WSL-Friendly Bilibili QR Login.

Manages restricted (0600 chmod) session files under ~/.contentflow/accounts/<platform>/
for Bilibili, Douyin, Xiaohongshu, and WeChat Official Account (wechat_mp).
Includes a zero-dependency ISO/IEC 18004 QR Code encoder that renders both:
  1. High-contrast PNG image (`output/auth/bilibili_qr.png`) via Pillow
  2. Compact Unicode half-block (`▀`/`▄`/`█`) terminal QR matrix for WSL2 consoles
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
from PIL import Image

from config.settings import OUTPUT_DIR

SUPPORTED_PLATFORMS: Tuple[str, ...] = ("bilibili", "douyin", "xiaohongshu", "wechat_mp")

DEFAULT_VAULT_DIR: Path = Path.home() / ".contentflow" / "accounts"
DEFAULT_QR_OUTPUT_PATH: Path = OUTPUT_DIR / "auth" / "bilibili_qr.png"

BILIBILI_QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
BILIBILI_QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
BILIBILI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"

STANDARD_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

BILIBILI_CORE_COOKIE_KEYS: Tuple[str, ...] = (
    "SESSDATA",
    "bili_jct",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "sid",
)


# ============================================================================
# Pure-Python ISO/IEC 18004 QR Code Generator (Versions 1..10, ECC Level L)
# ============================================================================

# (version, total_data_cw, ec_cw_per_block, g1_blocks, g1_data_cw, g2_blocks, g2_data_cw, align_coords)
_QR_VERSION_L_TABLE: Dict[int, Tuple[int, int, int, int, int, int, List[int]]] = {
    1: (19, 7, 1, 19, 0, 0, []),
    2: (34, 10, 1, 34, 0, 0, [6, 18]),
    3: (55, 15, 1, 55, 0, 0, [6, 22]),
    4: (80, 20, 1, 80, 0, 0, [6, 26]),
    5: (108, 26, 1, 108, 0, 0, [6, 30]),
    6: (136, 18, 2, 68, 0, 0, [6, 34]),
    7: (156, 20, 2, 78, 0, 0, [6, 22, 38]),
    8: (194, 24, 2, 97, 0, 0, [6, 24, 42]),
    9: (232, 30, 2, 116, 0, 0, [6, 26, 46]),
    10: (274, 18, 2, 68, 2, 69, [6, 28, 50]),
}

# Precomputed 15-bit BCH Format Information for Level L (01) and Mask 0..7
_QR_FORMAT_BITS_L: Tuple[int, ...] = (
    0x77C4,
    0x72F3,
    0x7DAA,
    0x789D,
    0x662F,
    0x6318,
    0x6C41,
    0x6976,
)

# GF(256) log/exp tables with primitive polynomial 0x11D
_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(degree: int) -> List[int]:
    poly = [1]
    for i in range(degree):
        next_poly = [0] * (len(poly) + 1)
        factor = _GF_EXP[i]
        for j, coeff in enumerate(poly):
            next_poly[j] ^= coeff
            next_poly[j + 1] ^= _gf_mul(coeff, factor)
        poly = next_poly
    return poly


def _rs_encode(data: List[int], ec_len: int) -> List[int]:
    gen = _rs_generator_poly(ec_len)
    rem = [0] * ec_len
    for byte in data:
        factor = byte ^ rem.pop(0)
        rem.append(0)
        if factor != 0:
            for j in range(ec_len):
                rem[j] ^= _gf_mul(gen[j + 1], factor)
    return rem


def encode_qr_matrix(text: str) -> List[List[bool]]:
    """Encodes a UTF-8 string into a 2D boolean QR Code matrix (True = dark module)."""
    # Try external qrcode library first if installed
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(border=0)
        qr.add_data(text)
        qr.make(fit=True)
        return [[bool(cell) for cell in row] for row in qr.get_matrix()]
    except ImportError:
        pass

    payload = text.encode("utf-8")
    length = len(payload)

    selected_ver = None
    for ver in range(1, 11):
        total_cw = _QR_VERSION_L_TABLE[ver][0]
        count_bits = 8 if ver <= 9 else 16
        max_bytes = (total_cw * 8 - 4 - count_bits) // 8
        if length <= max_bytes:
            selected_ver = ver
            break
    if selected_ver is None:
        raise ValueError(f"QR payload too long ({length} bytes; max supported is 271 bytes)")

    total_cw, ec_cw, g1_blocks, g1_cw, g2_blocks, g2_cw, align_coords = _QR_VERSION_L_TABLE[selected_ver]
    count_bits = 8 if selected_ver <= 9 else 16

    # Build bit stream: Byte mode (0100) + char count + payload + terminator + padding
    bits: List[int] = [0, 1, 0, 0]
    for i in range(count_bits - 1, -1, -1):
        bits.append((length >> i) & 1)
    for b in payload:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)

    capacity_bits = total_cw * 8
    term_len = min(4, capacity_bits - len(bits))
    bits.extend([0] * term_len)
    while len(bits) % 8 != 0:
        bits.append(0)

    data_codewords: List[int] = []
    for i in range(0, len(bits), 8):
        val = 0
        for bit in bits[i : i + 8]:
            val = (val << 1) | bit
        data_codewords.append(val)

    pad_bytes = (0xEC, 0x11)
    pad_idx = 0
    while len(data_codewords) < total_cw:
        data_codewords.append(pad_bytes[pad_idx % 2])
        pad_idx += 1

    # Split into blocks and compute Reed-Solomon EC codewords
    data_blocks: List[List[int]] = []
    ec_blocks: List[List[int]] = []
    offset = 0
    for _ in range(g1_blocks):
        blk = data_codewords[offset : offset + g1_cw]
        offset += g1_cw
        data_blocks.append(blk)
        ec_blocks.append(_rs_encode(blk, ec_cw))
    for _ in range(g2_blocks):
        blk = data_codewords[offset : offset + g2_cw]
        offset += g2_cw
        data_blocks.append(blk)
        ec_blocks.append(_rs_encode(blk, ec_cw))

    # Interleave data and EC codewords
    interleaved: List[int] = []
    max_data_len = max(len(b) for b in data_blocks)
    for i in range(max_data_len):
        for blk in data_blocks:
            if i < len(blk):
                interleaved.append(blk[i])
    for i in range(ec_cw):
        for blk in ec_blocks:
            interleaved.append(blk[i])

    final_bits: List[int] = []
    for cw in interleaved:
        for i in range(7, -1, -1):
            final_bits.append((cw >> i) & 1)
    # Remainder bits (0 for v1, 7 for v2..v6, 0 for v7..v10)
    if selected_ver in (2, 3, 4, 5, 6):
        final_bits.extend([0] * 7)

    size = 17 + 4 * selected_ver
    matrix: List[List[Optional[bool]]] = [[None] * size for _ in range(size)]
    is_func: List[List[bool]] = [[False] * size for _ in range(size)]

    def _set_func(r: int, c: int, dark: bool) -> None:
        if 0 <= r < size and 0 <= c < size:
            matrix[r][c] = dark
            is_func[r][c] = True

    def _place_finder(top: int, left: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = top + dr, left + dc
                if 0 <= r < size and 0 <= c < size:
                    if 0 <= dr <= 6 and 0 <= dc <= 6:
                        dark = dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)
                    else:
                        dark = False
                    _set_func(r, c, dark)

    _place_finder(0, 0)
    _place_finder(0, size - 7)
    _place_finder(size - 7, 0)

    # Timing patterns
    for i in range(8, size - 8):
        _set_func(6, i, i % 2 == 0)
        _set_func(i, 6, i % 2 == 0)

    # Alignment patterns
    for ar in align_coords:
        for ac in align_coords:
            if (ar < 9 and ac < 9) or (ar < 9 and ac > size - 10) or (ar > size - 10 and ac < 9):
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    dark = max(abs(dr), abs(dc)) in (0, 2)
                    _set_func(ar + dr, ac + dc, dark)

    # Reserve format info modules & dark module
    for i in range(9):
        if not is_func[8][i]:
            _set_func(8, i, False)
        if not is_func[i][8]:
            _set_func(i, 8, False)
    for i in range(8):
        if not is_func[8][size - 1 - i]:
            _set_func(8, size - 1 - i, False)
        if not is_func[size - 1 - i][8]:
            _set_func(size - 1 - i, 8, False)
    _set_func(size - 8, 8, True)

    # Place data bits in upward/downward 2-column zig-zag
    bit_idx = 0
    upward = True
    col = size - 1
    while col > 0:
        if col == 6:
            col -= 1
        row_iter = range(size - 1, -1, -1) if upward else range(size)
        for r in row_iter:
            for dc in (0, 1):
                c = col - dc
                if not is_func[r][c]:
                    dark = bool(final_bits[bit_idx]) if bit_idx < len(final_bits) else False
                    matrix[r][c] = dark
                    bit_idx += 1
        upward = not upward
        col -= 2

    # Apply Mask 0 ((r + c) % 2 == 0) and write format bits for Level L, Mask 0
    mask_id = 0
    out_matrix: List[List[bool]] = [[bool(cell) for cell in row] for row in matrix]
    for r in range(size):
        for c in range(size):
            if not is_func[r][c] and (r + c) % 2 == 0:
                out_matrix[r][c] = not out_matrix[r][c]

    fmt = _QR_FORMAT_BITS_L[mask_id]
    # Bit 0..14 placement around top-left and edges
    for i in range(6):
        out_matrix[8][i] = bool((fmt >> (14 - i)) & 1)
    out_matrix[8][7] = bool((fmt >> 8) & 1)
    out_matrix[8][8] = bool((fmt >> 7) & 1)
    out_matrix[7][8] = bool((fmt >> 6) & 1)
    for i in range(6):
        out_matrix[5 - i][8] = bool((fmt >> (5 - i)) & 1)

    for i in range(8):
        out_matrix[8][size - 8 + i] = bool((fmt >> (7 - i)) & 1)
    for i in range(7):
        out_matrix[size - 7 + i][8] = bool((fmt >> (14 - i)) & 1)

    return out_matrix


def render_qr_png(matrix: List[List[bool]], output_path: Path, box_size: int = 10, border: int = 4) -> Path:
    """Renders a 2D boolean QR matrix to a crisp PNG file using Pillow."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n = len(matrix)
    total_modules = n + 2 * border
    img_px = total_modules * box_size

    img = Image.new("RGB", (img_px, img_px), color=(255, 255, 255))
    pixels = img.load()
    assert pixels is not None

    for r in range(n):
        for c in range(n):
            if matrix[r][c]:
                y0 = (r + border) * box_size
                x0 = (c + border) * box_size
                for dy in range(box_size):
                    for dx in range(box_size):
                        pixels[x0 + dx, y0 + dy] = (0, 0, 0)

    img.save(output_path, format="PNG")
    return output_path


def render_qr_terminal_halfblock(matrix: List[List[bool]], border: int = 2) -> str:
    """Renders a 2D boolean QR matrix using compact Unicode half-block characters (▀/▄/█/ ).

    Each character row encodes 2 vertical QR modules so the QR code remains square in
    standard monospaced WSL2 / Linux terminals.
    Here we render dark modules as spaces on light background or block characters:
    Specifically, using dark background friendly inverted blocks or standard blocks:
      - Top dark, Bottom dark   -> '█'
      - Top dark, Bottom light  -> '▀'
      - Top light, Bottom dark  -> '▄'
      - Top light, Bottom light -> ' '
    """
    n = len(matrix)
    padded_size = n + 2 * border
    padded: List[List[bool]] = [[False] * padded_size for _ in range(padded_size)]
    for r in range(n):
        for c in range(n):
            padded[r + border][c + border] = matrix[r][c]

    lines: List[str] = []
    for r in range(0, padded_size, 2):
        row_chars: List[str] = []
        for c in range(padded_size):
            top = padded[r][c]
            bottom = padded[r + 1][c] if (r + 1) < padded_size else False
            if top and bottom:
                row_chars.append("█")
            elif top and not bottom:
                row_chars.append("▀")
            elif not top and bottom:
                row_chars.append("▄")
            else:
                row_chars.append(" ")
        lines.append("".join(row_chars))
    return "\n".join(lines)


# ============================================================================
# AuthVault & Bilibili QR Code Passport Workflow
# ============================================================================


def _enforce_0600(file_path: Path) -> None:
    """Enforces strict 0600 (-rw-------) permissions on sensitive session files."""
    if file_path.exists():
        os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)


def _enforce_0700(dir_path: Path) -> None:
    """Enforces strict 0700 (drwx------) permissions on vault directories."""
    dir_path.mkdir(parents=True, exist_ok=True)
    os.chmod(dir_path, stat.S_IRWXU)


class AuthVault:
    """Manages restricted (0600 chmod) session files under ~/.contentflow/accounts/<platform>/."""

    def __init__(self, vault_dir: Optional[Path] = None) -> None:
        self.vault_dir = Path(vault_dir) if vault_dir is not None else DEFAULT_VAULT_DIR

    def get_platform_dir(self, platform: str, create: bool = False) -> Path:
        platform = platform.lower().strip()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform '{platform}'. Supported: {SUPPORTED_PLATFORMS}")
        p_dir = self.vault_dir / platform
        if create:
            _enforce_0700(self.vault_dir)
            _enforce_0700(p_dir)
        return p_dir

    def initialize_vault(self) -> Dict[str, Path]:
        """Creates restricted vault directories for all supported platforms."""
        _enforce_0700(self.vault_dir)
        result: Dict[str, Path] = {}
        for platform in SUPPORTED_PLATFORMS:
            result[platform] = self.get_platform_dir(platform, create=True)
        return result

    def save_bilibili_session(
        self,
        cookies: Dict[str, str],
        refresh_token: str = "",
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Path]:
        """Saves Bilibili cookies.json (for biliup/HTTP API) and storage_state.json (for Playwright) with 0600 chmod."""
        p_dir = self.get_platform_dir("bilibili", create=True)
        cookies_path = p_dir / "cookies.json"
        storage_path = p_dir / "storage_state.json"

        now_ts = int(time.time())
        cookie_list = [
            {
                "name": k,
                "value": str(v),
                "domain": ".bilibili.com",
                "path": "/",
                "expires": now_ts + 86400 * 180,
                "http_only": 1 if k == "SESSDATA" else 0,
                "secure": 1,
            }
            for k, v in cookies.items()
        ]

        # Compatible with both biliup (cookie_info.cookies + token_info) and direct dict lookup
        cookies_payload: Dict[str, Any] = {
            "platform": "bilibili",
            "updated_at": now_ts,
            "refresh_token": refresh_token,
            "cookies": dict(cookies),
            "cookie_info": {
                "cookies": cookie_list,
                "domains": [".bilibili.com", ".biligame.com", ".bigfun.cn"],
            },
            "token_info": {
                "refresh_token": refresh_token,
                "mid": int(cookies["DedeUserID"]) if cookies.get("DedeUserID", "").isdigit() else 0,
            },
        }
        for k in BILIBILI_CORE_COOKIE_KEYS:
            if k in cookies:
                cookies_payload[k] = cookies[k]
        if profile:
            cookies_payload["profile"] = profile

        cookies_path.write_text(json.dumps(cookies_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _enforce_0600(cookies_path)

        # Playwright storage_state.json format
        playwright_cookies = [
            {
                "name": k,
                "value": str(v),
                "domain": ".bilibili.com",
                "path": "/",
                "expires": float(now_ts + 86400 * 180),
                "httpOnly": k == "SESSDATA",
                "secure": True,
                "sameSite": "Lax",
            }
            for k, v in cookies.items()
        ]
        storage_payload = {
            "cookies": playwright_cookies,
            "origins": [
                {
                    "origin": "https://www.bilibili.com",
                    "localStorage": ([{"name": "ac_time_value", "value": refresh_token}] if refresh_token else []),
                }
            ],
        }
        storage_path.write_text(json.dumps(storage_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _enforce_0600(storage_path)

        return {
            "cookies_path": cookies_path,
            "storage_state_path": storage_path,
        }

    def load_bilibili_cookies(self) -> Dict[str, str]:
        """Loads saved Bilibili cookies dict from ~/.contentflow/accounts/bilibili/cookies.json."""
        p_dir = self.get_platform_dir("bilibili", create=False)
        cookies_path = p_dir / "cookies.json"
        if not cookies_path.exists():
            return {}
        try:
            data = json.loads(cookies_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        if isinstance(data.get("cookies"), dict):
            return {str(k): str(v) for k, v in data["cookies"].items()}
        if isinstance(data.get("cookie_info"), dict) and isinstance(data["cookie_info"].get("cookies"), list):
            return {
                str(item["name"]): str(item["value"])
                for item in data["cookie_info"]["cookies"]
                if isinstance(item, dict) and "name" in item and "value" in item
            }
        return {k: str(data[k]) for k in BILIBILI_CORE_COOKIE_KEYS if k in data and data[k] is not None}

    def save_platform_session(self, platform: str, payload: Dict[str, Any], filename: str = "cookies.json") -> Path:
        """Saves a generic platform session or credential file with 0600 chmod."""
        p_dir = self.get_platform_dir(platform, create=True)
        target = p_dir / filename
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _enforce_0600(target)
        return target

    def get_platform_status(self, platform: str, verify_online: bool = False) -> Dict[str, Any]:
        """Returns login status, nickname/UID, and session file paths for a single platform."""
        p_dir = self.get_platform_dir(platform, create=False)
        cookies_file = p_dir / "cookies.json"
        storage_file = p_dir / "storage_state.json"

        if platform == "wechat_mp":
            cred_file = p_dir / "credentials.json"
            appid = os.environ.get("WECHAT_MP_APPID", "").strip()
            secret = os.environ.get("WECHAT_MP_APPSECRET", "").strip()
            if (not appid or not secret) and cred_file.exists():
                try:
                    cdata = json.loads(cred_file.read_text(encoding="utf-8"))
                    appid = appid or str(cdata.get("appid", "")).strip()
                    secret = secret or str(cdata.get("appsecret", "")).strip()
                except Exception:
                    pass
            logged_in = bool(appid and secret)
            return {
                "platform": "wechat_mp",
                "logged_in": logged_in,
                "uname": f"AppID:{appid[:6]}***" if appid else None,
                "mid": appid or None,
                "level": None,
                "session_file": str(cred_file if cred_file.exists() else p_dir),
                "mode": "api_credentials",
            }

        has_cookies = cookies_file.exists() or storage_file.exists()
        uname: Optional[str] = None
        mid: Optional[str] = None
        level: Optional[int] = None
        logged_in = False

        if cookies_file.exists():
            try:
                raw = json.loads(cookies_file.read_text(encoding="utf-8"))
                cookies_dict = self.load_bilibili_cookies() if platform == "bilibili" else raw.get("cookies", {})
                logged_in = bool(cookies_dict.get("SESSDATA") or cookies_dict)
                mid = str(cookies_dict.get("DedeUserID") or raw.get("mid") or "") or None
                profile = raw.get("profile") or {}
                uname = profile.get("uname") or raw.get("uname")
                level = profile.get("level") or raw.get("level")
            except Exception:
                logged_in = False

        if platform == "bilibili" and logged_in and verify_online:
            nav_info = verify_bilibili_session(vault=self)
            logged_in = bool(nav_info.get("logged_in", False))
            uname = nav_info.get("uname") or uname
            mid = str(nav_info.get("mid") or mid or "") or None
            level = nav_info.get("level") if nav_info.get("level") is not None else level

        return {
            "platform": platform,
            "logged_in": logged_in,
            "uname": uname,
            "mid": mid,
            "level": level,
            "session_file": str(cookies_file),
            "storage_state_file": str(storage_file),
            "has_files": has_cookies,
        }

    def get_all_statuses(self, verify_online: bool = False) -> Dict[str, Dict[str, Any]]:
        """Returns vault status across all supported platforms."""
        return {p: self.get_platform_status(p, verify_online=verify_online) for p in SUPPORTED_PLATFORMS}


def generate_bilibili_qr(
    qr_image_path: Optional[Path] = None,
    session: Optional[requests.Session] = None,
    print_terminal: bool = True,
) -> Dict[str, Any]:
    """Requests a fresh Bilibili Passport QR login URL & key and renders both PNG and terminal half-blocks.

    Calls GET https://passport.bilibili.com/x/passport-login/web/qrcode/generate
    """
    http = session or requests.Session()
    headers = {
        "User-Agent": STANDARD_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
    }
    resp = http.get(BILIBILI_QR_GENERATE_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0 or "data" not in payload:
        raise RuntimeError(f"Bilibili QR generate API error: {payload}")

    data = payload["data"]
    qr_url = str(data["url"])
    qrcode_key = str(data["qrcode_key"])

    out_png = Path(qr_image_path) if qr_image_path is not None else DEFAULT_QR_OUTPUT_PATH
    matrix = encode_qr_matrix(qr_url)
    render_qr_png(matrix, out_png)
    terminal_qr = render_qr_terminal_halfblock(matrix)

    if print_terminal:
        print("\n=== Bilibili Passport QR Code (WSL-Friendly Dual Renderer) ===")
        print(terminal_qr)
        print(f"[+] QR PNG saved to: {out_png}")
        print(f"[+] Scan with Bilibili Mobile App (qrcode_key={qrcode_key})\n")

    return {
        "url": qr_url,
        "qrcode_key": qrcode_key,
        "qr_image_path": str(out_png),
        "terminal_qr": terminal_qr,
    }


def _extract_cookies_from_poll_response(resp: requests.Response, data: Dict[str, Any]) -> Dict[str, str]:
    """Extracts Bilibili session cookies from both Set-Cookie headers/jar and redirect URL query params."""
    cookies: Dict[str, str] = {}

    # 1. Extract from URL query parameters in data["url"] (Bilibili encodes SESSDATA, bili_jct, DedeUserID here too)
    redirect_url = str(data.get("url") or "")
    if redirect_url and "?" in redirect_url:
        qs = parse_qs(urlparse(redirect_url).query)
        for key in BILIBILI_CORE_COOKIE_KEYS:
            if key in qs and qs[key]:
                cookies[key] = qs[key][0]

    # 2. Extract from requests Response cookies jar
    if getattr(resp, "cookies", None):
        try:
            for k, v in resp.cookies.items():
                cookies[str(k)] = str(v)
        except Exception:
            pass

    # 3. Also parse raw Set-Cookie header if present in resp.headers
    raw_set_cookie = resp.headers.get("Set-Cookie") or resp.headers.get("set-cookie") or ""
    if raw_set_cookie:
        for segment in raw_set_cookie.replace("\n", ";").split(";"):
            segment = segment.strip()
            if "=" in segment:
                k, v = segment.split("=", 1)
                k = k.strip()
                if k in BILIBILI_CORE_COOKIE_KEYS:
                    cookies[k] = v.strip()

    return cookies


def poll_bilibili_qr(
    qrcode_key: str,
    timeout: int = 180,
    interval: float = 2.0,
    vault: Optional[AuthVault] = None,
    session: Optional[requests.Session] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Dict[str, Any]:
    """Polls Bilibili Passport QR status until scanned & confirmed (code == 0), then saves vault files."""
    auth_vault = vault or AuthVault()
    http = session or requests.Session()
    headers = {
        "User-Agent": STANDARD_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
    }

    deadline = time.monotonic() + max(timeout, 1)
    last_status_code = -1

    while True:
        resp = http.get(
            BILIBILI_QR_POLL_URL,
            params={"qrcode_key": qrcode_key},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or {}
        status_code = int(data.get("code", -1))
        status_msg = str(data.get("message", ""))

        if status_code == 0:
            cookies = _extract_cookies_from_poll_response(resp, data)
            refresh_token = str(data.get("refresh_token") or "")
            paths = auth_vault.save_bilibili_session(cookies=cookies, refresh_token=refresh_token)

            # Verify session to enrich profile metadata if possible
            nav_result = verify_bilibili_session(vault=auth_vault, session=http)
            if nav_result.get("logged_in"):
                paths = auth_vault.save_bilibili_session(
                    cookies=cookies,
                    refresh_token=refresh_token,
                    profile={
                        "uname": nav_result.get("uname"),
                        "mid": nav_result.get("mid"),
                        "level": nav_result.get("level"),
                    },
                )

            return {
                "status": "confirmed",
                "code": 0,
                "cookies": cookies,
                "refresh_token": refresh_token,
                "cookies_path": str(paths["cookies_path"]),
                "storage_state_path": str(paths["storage_state_path"]),
                "profile": nav_result,
            }

        if status_code == 86038:
            return {
                "status": "expired",
                "code": status_code,
                "message": status_msg or "QR code expired",
            }

        if status_code != last_status_code:
            last_status_code = status_code

        if time.monotonic() >= deadline:
            return {
                "status": "timeout",
                "code": status_code,
                "message": status_msg or "Polling timed out before confirmation",
            }

        sleep_fn(interval)


def verify_bilibili_session(
    vault: Optional[AuthVault] = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """Verifies Bilibili login state via https://api.bilibili.com/x/web-interface/nav using saved cookies."""
    auth_vault = vault or AuthVault()
    cookies = auth_vault.load_bilibili_cookies()
    if not cookies:
        return {
            "logged_in": False,
            "uname": None,
            "mid": None,
            "level": None,
            "error": "No saved Bilibili cookies found in vault",
        }

    http = session or requests.Session()
    headers = {
        "User-Agent": STANDARD_USER_AGENT,
        "Referer": "https://www.bilibili.com/",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        resp = http.get(BILIBILI_NAV_URL, cookies=cookies, headers=headers, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        return {
            "logged_in": False,
            "uname": None,
            "mid": cookies.get("DedeUserID"),
            "level": None,
            "error": str(exc),
        }

    data = payload.get("data") or {}
    is_login = bool(payload.get("code") == 0 and data.get("isLogin", False))
    uname = data.get("uname")
    mid = data.get("mid") or cookies.get("DedeUserID")
    level_info = data.get("level_info") or {}
    level = level_info.get("current_level") if isinstance(level_info, dict) else data.get("level")

    return {
        "logged_in": is_login,
        "uname": uname,
        "mid": mid,
        "level": level,
        "vip_type": data.get("vipType"),
        "money": data.get("money"),
    }
