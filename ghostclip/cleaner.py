"""Модуль очистки ссылок в тексте и удаления невидимых символов (CleanClip)."""

import re
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from typing import Tuple, List

ZERO_WIDTH_CHARS = "\u200B\u200C\u200D\uFEFF\u200E\u200F\u202A\u202B\u202C\u202D\u202E\u2060"
ZW_TABLE = str.maketrans("", "", ZERO_WIDTH_CHARS)

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "fbclid", "gclid", "si", "ref", "ref_src", "igshid", "yclid", "mc_cid", "mc_eid",
    "_openstat", "dclid", "msclkid",
}
URL_REGEX = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def strip_zero_width(text: str) -> Tuple[str, int]:
    """Удаляет невидимые символы на скорости C через str.translate."""
    cleaned = text.translate(ZW_TABLE)
    return cleaned, len(text) - len(cleaned)


def clean_url(url_str: str) -> Tuple[str, List[str]]:
    """Вырезает трекинг-метки из URL, сохраняя полезные параметры."""
    try:
        u = urlparse(url_str)
        if not u.scheme or not u.netloc:
            return url_str, []
        clean_q, removed = [], []
        for k, v in parse_qsl(u.query, keep_blank_values=True):
            if k.lower() in TRACKING_PARAMS or k.lower().startswith("utm_"):
                removed.append(k)
            else:
                clean_q.append((k, v))
        if not removed:
            return url_str, []
        return urlunparse(u._replace(query=urlencode(clean_q))), removed
    except Exception:
        return url_str, []


def sanitize_text(text: str, clean_urls_enabled: bool = True, clean_zw_enabled: bool = True) -> Tuple[str, List[str], int]:
    """Очищает невидимые символы и любые ссылки (даже внутри длинного текста)."""
    cleaned, zw_count = strip_zero_width(text) if clean_zw_enabled else (text, 0)
    removed_all: List[str] = []

    if clean_urls_enabled and "http" in cleaned.lower():
        def _repl(match):
            url, rem = clean_url(match.group(0))
            removed_all.extend(rem)
            return url
        cleaned = URL_REGEX.sub(_repl, cleaned)

    return cleaned, removed_all, zw_count
