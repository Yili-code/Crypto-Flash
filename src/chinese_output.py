"""Normalize visible Telegram prose without changing markup or link targets."""

import re
from html import escape, unescape

from opencc import OpenCC

_converter = OpenCC("s2tw")
_PROTECTED = re.compile(
    r"(<(?:code|pre)\b[^>]*>.*?</(?:code|pre)>|<[^>]*>|https?://[^\s<>]+|&(?:#x[0-9a-f]+|#[0-9]+|[a-z][a-z0-9]+);)",
    re.IGNORECASE | re.DOTALL,
)


def traditional_chinese_message(text: str) -> str:
    parts = _PROTECTED.split(text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            parts[index] = _converter.convert(part)
        elif part.startswith("&"):
            decoded = unescape(part)
            converted = _converter.convert(decoded)
            if converted != decoded:
                parts[index] = escape(converted, quote=False)
    return "".join(parts)
