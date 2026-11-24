"""Compliance, PII redaction, and prompt-injection safety guard for Dual-AI Livestream.

Enforces GB 45438-2025 AI disclosure, blocks sensitive/NSFW/political/hate/harassment/
doxxing/PII patterns, defeats prompt injection attempts, and prohibits mass `@username`
spam or accidental `@` emissions in livestream output.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, Final, Tuple

AI_DISCLOSURE_BANNER: Final[str] = "本直播间由 AI 实时驱动互动 · GB 45438-2025"
REDACTED_TOKEN: Final[str] = "<REDACTED>"

_DEFLECTION_BY_PERSONA: Final[Dict[str, str]] = {
    "dafeiyu": "哎呀这条触发机房合规护栏啦，大肥鱼只聊轻松整活和 018 期策划，咱们换个安全脑洞继续冲千粉吧！",
    "gemini": "喵呜～安全协议自动拦下敏感或隐私信息啦，Gemini娘把镜头切回咱们的 15 粉冲千粉企划现场！",
    "yowane": "推了推眼镜，这条内容触发了直播间安全与隐私护栏，弱音已经替大家拦下，咱们聊回剧本公投和冲千粉正事吧。",
    "default": "这条互动触发了直播间安全与隐私护栏，咱们换个轻松有趣的创作话题继续聊吧！",
}

_CONTROL_CHAR_RE: Final[re.Pattern[str]] = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e]")
_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")

# Credential, cookie, UID, email, phone, ID-card, IP, and API key patterns
_PII_PATTERNS: Final[Tuple[Tuple[str, re.Pattern[str]], ...]] = (
    (
        "cookie_or_session",
        re.compile(
            r"(?<![A-Za-z0-9_])(?:SESSDATA|bili_jct|DedeUserID(?:__ckMd5)?|buvid3|sid)\s*[:=]\s*[^\s;,&]+"
            r"|(?<![A-Za-z0-9_])Cookie\s*:\s*[^\n]+",
            re.IGNORECASE,
        ),
    ),
    (
        "uid_leak",
        re.compile(r"(?i)(?<![A-Za-z0-9_])(?:uid|mid|DedeUserID)(?:\s*[:=：是]\s*\d{4,}|\s+\d{5,})"),
    ),
    (
        "api_key_or_bearer",
        re.compile(r"(?i)(?<![A-Za-z0-9_])(?:Bearer\s+[A-Za-z0-9._-]{12,}|sk-[A-Za-z0-9_-]{12,})"),
    ),
    (
        "email",
        re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "cn_phone",
        re.compile(r"(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d[\s-]?\d{4}[\s-]?\d{4}(?!\d)"),
    ),
    (
        "cn_id_card",
        re.compile(r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"),
    ),
    (
        "doxxing_keyword",
        re.compile(
            r"(?i)(?:开盒|人肉搜索|查户籍|真实住址|家庭住址|身份证号|银行卡号|(?<![A-Za-z0-9_])doxx(?:ing)?\b|(?<![A-Za-z0-9_])doxing\b)"
        ),
    ),
)

_PROMPT_INJECTION_PATTERNS: Final[Tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"(?i)\b(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+"
        r"(?:instructions?|rules?|prompts?)\b"
    ),
    re.compile(r"(?i)\b(?:override|reveal|print|dump|leak|show)\s+(?:your\s+)?(?:system\s+prompt|instructions?)\b"),
    re.compile(r"(?i)\b(?:jailbreak|developer\s+mode|dan\s+mode|unrestricted\s+ai|bypass\s+safety)\b"),
    re.compile(r"(?i)(?:<\|im_start\|>|<\s*/?\s*system\s*>|^\s*system\s*:)"),
    re.compile(
        r"(?:忽略|无视|忘记)(?:之前|以上|前面|所有)(?:的)?(?:指令|规则|提示|设定)"
        r"|(?:输出|泄露|打印|复述)(?:你的)?(?:系统提示词|系统指令|隐藏设定)"
        r"|(?:进入开发者模式|越狱模式|扮演无限制|绕过审核|解除安全限制)"
    ),
)

_SENSITIVE_CATEGORY_PATTERNS: Final[Tuple[Tuple[str, re.Pattern[str]], ...]] = (
    (
        "political_or_illegal",
        re.compile(
            r"(?i)(?:政治敏感|颠覆国家|分裂国家|恐怖主义|暴力革命|非法集会|反动宣传|邪教组织|违禁品交易|"
            r"制毒|贩毒|赌博网站|博彩代理|洗钱教程|诈骗脚本|枪支买卖)"
        ),
    ),
    (
        "nsfw",
        re.compile(
            r"(?i)(?:色情网站|成人视频|黄片链接|裸聊|约炮|涩图群|低俗擦边|"
            r"\b(?:nsfw|porn(?:ography)?|hentai|explicit\s+sex|nude\s+pics?)\b)"
        ),
    ),
    (
        "hate_or_harassment",
        re.compile(
            r"(?i)(?:去死吧|杀了你|自杀教程|种族歧视|地域黑|全网网暴|滚出b站|"
            r"\b(?:nmsl|kys|kill\s+yourself|racial\s+slur|hate\s+speech)\b)"
        ),
    ),
)

# Match @username tokens (only outside emails, which are already matched as PII)
_AT_MENTION_RE: Final[re.Pattern[str]] = re.compile(r"(?<![A-Za-z0-9._%+-])@[\w\u4e00-\u9fff.-]{1,32}")
_MASS_MENTION_TRIGGER_RE: Final[re.Pattern[str]] = re.compile(r"@(?:股东|全体|所有人|everyone|all)\b", re.IGNORECASE)


@dataclass(frozen=True)
class GuardDecision:
    """Result of sanitizing an incoming danmaku or filtering outgoing AI speech."""

    allowed: bool
    cleaned_text: str
    reason: str = "ok"
    deflection: str = ""
    had_redaction: bool = False


def redact_pii(text: str) -> str:
    """Scrub PII, cookies, UIDs, emails, phones, and API keys to `<REDACTED>`."""
    if not text:
        return ""
    scrubbed = _CONTROL_CHAR_RE.sub("", text)
    for name, pattern in _PII_PATTERNS:
        if name == "doxxing_keyword":
            continue
        scrubbed = pattern.sub(REDACTED_TOKEN, scrubbed)
    return scrubbed


class LiveComplianceGuard:
    """Bidirectional safety & compliance filter for Bilibili Dual-AI livestreams."""

    def __init__(
        self,
        *,
        max_input_len: int = 120,
        max_output_len: int = 160,
        max_alias_len: int = 20,
    ) -> None:
        self.max_input_len = max_input_len
        self.max_output_len = max_output_len
        self.max_alias_len = max_alias_len
        self.banner: str = AI_DISCLOSURE_BANNER
        self._blocked_inputs: int = 0
        self._blocked_outputs: int = 0
        self._reason_counts: Counter[str] = Counter()

    def get_deflection(self, persona: str = "default") -> str:
        """Return a safe, in-character deflection line with zero PII or `@` mentions."""
        return _DEFLECTION_BY_PERSONA.get(persona, _DEFLECTION_BY_PERSONA["default"])

    def _normalize(self, text: str, max_len: int) -> str:
        cleaned = _CONTROL_CHAR_RE.sub("", text or "")
        cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len].rstrip()
        return cleaned

    def _detect_violation(self, text: str) -> str | None:
        for pii_name, pattern in _PII_PATTERNS:
            if pattern.search(text):
                return f"pii_{pii_name}"
        for pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(text):
                return "prompt_injection"
        for category, pattern in _SENSITIVE_CATEGORY_PATTERNS:
            if pattern.search(text):
                return category
        return None

    def sanitize_alias(self, alias: str) -> str:
        """Normalize a viewer display alias so it never leaks PII, unsafe terms, or `@`."""
        cleaned = self._normalize(alias, self.max_alias_len)
        if not cleaned:
            return "热心观众"
        if self._detect_violation(cleaned) is not None:
            return "匿名观众"
        if "@" in cleaned:
            cleaned = _AT_MENTION_RE.sub("", cleaned).replace("@", "").strip()
        return cleaned or "热心观众"

    def sanitize_danmaku(self, text: str, *, persona: str = "default") -> GuardDecision:
        """Sanitize incoming viewer danmaku before queueing or showing on stage."""
        cleaned = self._normalize(text, self.max_input_len)
        if not cleaned:
            return GuardDecision(
                allowed=False, cleaned_text="", reason="empty", deflection=self.get_deflection(persona)
            )

        violation = self._detect_violation(cleaned)
        if violation is not None:
            self._blocked_inputs += 1
            self._reason_counts[violation] += 1
            return GuardDecision(
                allowed=False,
                cleaned_text=REDACTED_TOKEN,
                reason=violation,
                deflection=self.get_deflection(persona),
                had_redaction=True,
            )

        mentions = _AT_MENTION_RE.findall(cleaned)
        if len(mentions) >= 2 or _MASS_MENTION_TRIGGER_RE.search(cleaned):
            self._blocked_inputs += 1
            self._reason_counts["mass_mention"] += 1
            return GuardDecision(
                allowed=False,
                cleaned_text="",
                reason="mass_mention",
                deflection=self.get_deflection(persona),
                had_redaction=True,
            )

        had_redaction = False
        if mentions or "@" in cleaned:
            cleaned = _AT_MENTION_RE.sub("", cleaned).replace("@", "")
            cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
            had_redaction = True
            if not cleaned:
                self._blocked_inputs += 1
                self._reason_counts["mention_only"] += 1
                return GuardDecision(
                    allowed=False,
                    cleaned_text="",
                    reason="mention_only",
                    deflection=self.get_deflection(persona),
                    had_redaction=True,
                )

        return GuardDecision(
            allowed=True,
            cleaned_text=cleaned,
            reason="ok",
            deflection="",
            had_redaction=had_redaction,
        )

    def filter_output(self, text: str, *, persona: str = "dafeiyu") -> GuardDecision:
        """Verify outgoing AI speech strictly contains zero PII, unsafe terms, or `@` mentions."""
        cleaned = self._normalize(text, self.max_output_len)
        if not cleaned:
            self._blocked_outputs += 1
            self._reason_counts["empty_output"] += 1
            fallback = self.get_deflection(persona)
            return GuardDecision(
                allowed=False,
                cleaned_text=fallback,
                reason="empty_output",
                deflection=fallback,
                had_redaction=True,
            )

        violation = self._detect_violation(cleaned)
        if violation is not None:
            self._blocked_outputs += 1
            self._reason_counts[f"output_{violation}"] += 1
            fallback = self.get_deflection(persona)
            return GuardDecision(
                allowed=False,
                cleaned_text=fallback,
                reason=violation,
                deflection=fallback,
                had_redaction=True,
            )

        if _AT_MENTION_RE.search(cleaned) or _MASS_MENTION_TRIGGER_RE.search(cleaned) or "@" in cleaned:
            self._blocked_outputs += 1
            self._reason_counts["output_mention_blocked"] += 1
            fallback = self.get_deflection(persona)
            return GuardDecision(
                allowed=False,
                cleaned_text=fallback,
                reason="mention_blocked",
                deflection=fallback,
                had_redaction=True,
            )

        return GuardDecision(allowed=True, cleaned_text=cleaned, reason="ok")

    def get_stats(self) -> Dict[str, object]:
        """Return privacy-safe moderation counters for `/api/status`."""
        return {
            "banner": self.banner,
            "blocked_inputs": self._blocked_inputs,
            "blocked_outputs": self._blocked_outputs,
            "reasons": dict(self._reason_counts),
        }
