"""Модуль обнаружения секретов: API-ключи, карты (алгоритм Луна) и пароли (энтропия Шеннона)."""

import re
import math
from collections import Counter
from typing import Optional, Tuple

PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "API_KEY", "OpenAI API Key"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "TOKEN", "GitHub Personal Token"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{50,}"), "TOKEN", "GitHub Fine-Grained Token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "API_KEY", "AWS Access Key ID"),
    (re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP)?\s?PRIVATE KEY-----"), "PRIVATE_KEY", "Приватный ключ (SSH/TLS)"),
]
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def luhn_check(card_number: str) -> bool:
    """Алгоритм Луна для проверки настоящих номеров банковских карт (отсеивает случайные цифры)."""
    digits = [int(c) for c in card_number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    total = sum(d * 2 - 9 if (i % 2 == 1 and d * 2 > 9) else (d * 2 if i % 2 == 1 else d) for i, d in enumerate(digits[::-1]))
    return total % 10 == 0


def calculate_entropy(s: str) -> float:
    """Быстрый расчет энтропии Шеннона через C-оптимизированный Counter."""
    if not s:
        return 0.0
    n = len(s)
    return -sum((count / n) * math.log2(count / n) for count in Counter(s).values())


def detect_secret(text: str) -> Optional[Tuple[str, str]]:
    """Возвращает (категория, описание) при обнаружении секрета или None."""
    s = text.strip()
    for pattern, cat, desc in PATTERNS:
        if pattern.search(s):
            return cat, desc

    for match in CARD_PATTERN.findall(s):
        digits = "".join(filter(str.isdigit, match))
        if luhn_check(digits):
            return "CREDIT_CARD", f"Банковская карта ({len(digits)} цифр)"

    if " " not in s and "\n" not in s and len(s) >= 16:
        variety = sum([any(c.isdigit() for c in s), any(c.isupper() for c in s), any(c.islower() for c in s), any(not c.isalnum() for c in s)])
        ent = calculate_entropy(s)
        if variety >= 3 and ent >= 3.75:
            return "PASSWORD", f"Сложный пароль (энтропия {ent:.2f} бит)"

    return None


def mask_secret(text: str) -> str:
    """Безопасная маскировка секрета для экрана и логов: 'sk-p•••ef'."""
    s = text.strip()
    return "••••••" if len(s) <= 6 else f"{s[:4]}•••{s[-2:]}"
