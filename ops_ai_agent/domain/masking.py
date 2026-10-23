"""LLM 送信前の機密情報マスキング（正規表現ベース）。

ログ・アラート本文に含まれるクレデンシャルや個人情報を
`***MASKED***` に置換する。正規化後のログ集計にも同じ変換が
効くよう、取り込み段（ingest）とアラート本文に適用する。
"""

import re

_MASKED = "***MASKED***"

# 全体をマスクするパターン（優先度高→低の順に適用）
_WHOLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?"
            r"-----END [A-Z ]*PRIVATE KEY-----"
        ),
    ),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"),
    ),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
)

# キー=値 / Bearer 形式（値の部分だけをマスク）
_BEARER_RE = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_CRED_PARAM_RE = re.compile(
    r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|token)"
    r"(=|:\s)([^\s&'\"]{4,})"
)


def mask_sensitive(text: str) -> str:
    """テキスト内の機密情報をマスクして返す（原文は変更しない）。"""
    masked = text
    for _name, pattern in _WHOLE_PATTERNS:
        masked = pattern.sub(_MASKED, masked)
    masked = _BEARER_RE.sub(lambda m: f"{m.group(1)} {_MASKED}", masked)
    masked = _CRED_PARAM_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{_MASKED}", masked)
    return masked
