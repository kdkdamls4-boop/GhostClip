"""Детекция секретов: токены API, JWT, строки БД, приватные ключи, карты (Луна) и пароли."""

import math
import re
from collections import Counter

PATTERNS = [
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-[a-zA-Z0-9_-]{20,}")),
    ("AWS_KEY", re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
    ("GITHUB_PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{32,}\b")),
    ("TELEGRAM_BOT_TOKEN", re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_-]{30,}\b")),
    ("JWT_TOKEN", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    (
        "DB_CONNECTION_STRING",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqp)://[^:\s/]*:[^@\s]+@[^\s\"'<>]+",
            re.IGNORECASE,
        ),
    ),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
]
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def calculate_entropy(text: str) -> float:
    """Вычисляет энтропию Шеннона (меру случайности символов) для строки."""
    if not text:
        return 0.0
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in Counter(text).values())


def luhn_check(card_number: str) -> bool:
    """Проверяет номер банковской карты по алгоритму Луна."""
    digits = [int(char) for char in card_number if char.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False

    checksum = 0
    for index, digit in enumerate(digits[::-1]):
        if index % 2 == 1:
            doubled = digit * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0


def _looks_like_strong_password(word: str) -> bool:
    """Отличает случайный пароль высокой энтропии от обычных слов и URL."""
    if len(word) < 12 or "://" in word:
        return False
    char_classes = sum(
        [
            any(char.isdigit() for char in word),
            any(char.isupper() for char in word),
            any(char.islower() for char in word),
            any(not char.isalnum() for char in word),
        ]
    )
    return char_classes >= 3 and calculate_entropy(word) >= 3.6


def detect_secret(text: str) -> tuple[bool, str, str]:
    """Ищет секрет в тексте и возвращает (найден, тип_секрета, значение)."""
    for secret_type, pattern in PATTERNS:
        match = pattern.search(text)
        if match:
            return True, secret_type, match.group(0)

    for match in CARD_PATTERN.finditer(text):
        digits_only = re.sub(r"\D", "", match.group(0))
        if luhn_check(digits_only):
            return True, "CREDIT_CARD", match.group(0)

    words = text.strip().split()
    if len(words) == 1 and _looks_like_strong_password(words[0]):
        return True, "HIGH_ENTROPY_PASSWORD", words[0]

    return False, "", ""


def mask_secret(secret: str) -> str:
    """Маскирует секрет для безопасного вывода на экран и записи в лог."""
    stripped = secret.strip()
    if len(stripped) <= 6:
        return "••••••"
    if len(stripped) <= 8:
        return f"{stripped[:2]}•••{stripped[-2:]}"
    return f"{stripped[:4]}•••{stripped[-2:]}"
