"""
ghostclip_mini/cleaner.py
Чистка URL от трекинг-меток (utm, fbclid, si и др.) и удаление невидимых знаков Zero-Width.
"""

import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

ZERO_WIDTH_CHARS = {'\u200b', '\u200c', '\u200d', '\ufeff', '\u200e', '\u200f', '\u202a', '\u202b', '\u202c', '\u202d', '\u202e'}
TRACKING_PARAMS = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid', 'yclid', 'si', 'igshid', 'mc_eid', 'ysclid'}

def strip_zero_width(text: str) -> tuple[str, int]:
    cnt = sum(1 for c in text if c in ZERO_WIDTH_CHARS)
    return (''.join(c for c in text if c not in ZERO_WIDTH_CHARS), cnt)

def clean_url(url: str) -> tuple[str, list[str]]:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return url, []
        q = parse_qs(p.query, keep_blank_values=True)
        rem = [k for k in q if k in TRACKING_PARAMS]
        if not rem:
            return url, []
        for k in rem:
            del q[k]
        new_q = urlencode(q, doseq=True)
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment)), rem
    except Exception:
        return url, []

def sanitize_text(text: str) -> tuple[str, bool, list[str]]:
    mod = False
    cleaned, cnt = strip_zero_width(text)
    logs = [f"Удалено {cnt} скрытых знаков"] if cnt else []
    if cnt:
        mod = True
    urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', cleaned)
    for u in set(urls):
        cu, rem = clean_url(u)
        if rem:
            cleaned = cleaned.replace(u, cu)
            logs.append(f"Очищен URL ({', '.join(rem)})")
            mod = True
    return cleaned, mod, logs
