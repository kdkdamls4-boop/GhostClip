"""Чистка URL от трекинг-меток и удаление невидимых символов Zero-Width."""

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

ZERO_WIDTH_CHARS = "\u200b\u200c\u200d\ufeff\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2060"
ZERO_WIDTH_TABLE = str.maketrans("", "", ZERO_WIDTH_CHARS)

TRACKING_PARAMS = {
    "_openstat",
    "dclid",
    "fbclid",
    "gad_campaignid",
    "gad_source",
    "gbraid",
    "gclid",
    "igsh",
    "igshid",
    "li_fat_id",
    "mc_cid",
    "mc_eid",
    "mkt_tok",
    "msclkid",
    "oly_anon_id",
    "oly_enc_id",
    "rb_clickid",
    "ref",
    "ref_src",
    "scm",
    "si",
    "spm",
    "ttclid",
    "twclid",
    "vero_id",
    "wbraid",
    "wickedid",
    "yclid",
    "ysclid",
}
TRACKING_PREFIXES = ("utm_", "hsa_")
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def strip_zero_width(text: str) -> tuple[str, int]:
    """Удаляет невидимые символы из текста и возвращает (текст, сколько_удалено)."""
    cleaned_text = text.translate(ZERO_WIDTH_TABLE)
    return cleaned_text, len(text) - len(cleaned_text)


def clean_url(url: str) -> tuple[str, list[str]]:
    """Удаляет трекинг-параметры из одной ссылки, сохраняя полезные параметры."""
    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return url, []

        kept_params = []
        removed_params = []
        for param_name, param_value in parse_qsl(parsed_url.query, keep_blank_values=True):
            lower_name = param_name.lower()
            if lower_name in TRACKING_PARAMS or lower_name.startswith(TRACKING_PREFIXES):
                removed_params.append(param_name)
            else:
                kept_params.append((param_name, param_value))

        if not removed_params:
            return url, []

        cleaned_url = urlunparse(parsed_url._replace(query=urlencode(kept_params)))
        return cleaned_url, removed_params
    except Exception:
        return url, []


def _split_trailing_punctuation(raw_token: str) -> tuple[str, str]:
    """Отделяет хвостовую пунктуацию и лишние закрывающие скобки от URL в тексте."""
    url_part = raw_token.rstrip(".,;:!?")
    trailing = raw_token[len(url_part) :]
    while url_part.endswith(")") and url_part.count(")") > url_part.count("("):
        url_part = url_part[:-1]
        trailing = ")" + trailing
    return url_part, trailing


def sanitize_text(
    text: str,
    clean_urls_enabled: bool = True,
    clean_zw_enabled: bool = True,
) -> tuple[str, bool, list[str]]:
    """Выполняет чистку текста с учётом переключателей [1] и [2]."""
    cleaned_text, removed_zw_count = strip_zero_width(text) if clean_zw_enabled else (text, 0)
    cleaning_logs = [f"Удалено {removed_zw_count} скрытых знаков"] if removed_zw_count else []
    is_modified = removed_zw_count > 0

    if clean_urls_enabled and "http" in cleaned_text.lower():
        removed_url_params: list[str] = []

        def replace_url(match: re.Match[str]) -> str:
            url_part, trailing = _split_trailing_punctuation(match.group(0))
            cleaned_url, removed_params = clean_url(url_part)
            removed_url_params.extend(removed_params)
            return cleaned_url + trailing

        cleaned_text = URL_PATTERN.sub(replace_url, cleaned_text)
        if removed_url_params:
            unique_params = list(dict.fromkeys(removed_url_params))
            cleaning_logs.append(f"Очищен URL ({', '.join(unique_params)})")
            is_modified = True

    return cleaned_text, is_modified, cleaning_logs
