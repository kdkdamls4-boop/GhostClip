"""
explained/ghostclip/detector.py
Модуль детекции секретов: API-ключи, JWT, строки БД, приватные ключи, карты (Луна) и пароли.
"""

import math  # math.log2 — логарифм по основанию 2 для формулы энтропии Шеннона
import re  # re — поиск токенов и цифр карты по регулярным выражениям
from collections import Counter  # Counter — быстрый подсчёт частоты каждого символа в строке

# Регулярные выражения для известных форматов ключей и токенов.
# Важно: более узкий шаблон (sk-ant-...) стоит ПЕРЕД общим (sk-...), чтобы Anthropic не путался с OpenAI!
PATTERNS = [
    ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-[a-zA-Z0-9_-]{20,}")),
    ("AWS_KEY", re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b")),
    # Токены GitHub начинаются с префикса ghp_, gho_, ghu_, ghs_ или ghr_
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
    ("GITHUB_PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{32,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("STRIPE_KEY", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b")),
    ("GITLAB_PAT", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("NPM_TOKEN", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("HUGGINGFACE_TOKEN", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("SENDGRID_KEY", re.compile(r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b")),
    ("AZURE_STORAGE_KEY", re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}")),
    ("TELEGRAM_BOT_TOKEN", re.compile(r"\b\d{8,12}:AA[A-Za-z0-9_-]{30,}\b")),
    # Классический JWT состоит из трёх base64url-блоков (header.payload.signature)
    ("JWT_TOKEN", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    # Строка подключения к БД с паролем внутри: postgres://user:password@host/db
    (
        "DB_CONNECTION_STRING",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqp)://[^:\s/]*:[^@\s]+@[^\s\"'<>]+",
            re.IGNORECASE,
        ),
    ),
    # Заголовки приватных SSH, TLS и PGP ключей
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
]

# Ищем от 13 до 19 цифр, между которыми могут стоять пробелы или дефисы
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def calculate_entropy(text: str) -> float:
    """
    Вычисляет энтропию Шеннона для строки.
    У обычных слов она обычно 2.0–3.0 бита на символ, у случайных паролей — от 3.6 и выше.
    """
    if not text:
        return 0.0
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in Counter(text).values())


def has_known_card_prefix(digits: str) -> bool:
    """
    Проверяет префикс (IIN/BIN) платёжной системы: Visa, Mastercard, Мир,
    American Express, UnionPay, JCB, Discover или Maestro. Отсекает случайные длинные номера заказов.
    """
    length = len(digits)
    if length < 13 or not digits.isdigit():
        return False
    two = int(digits[:2])
    three = int(digits[:3])
    four = int(digits[:4])
    return (
        (digits[0] == "4" and length in (13, 16, 19))  # Visa
        or (51 <= two <= 55 and length == 16)  # Mastercard
        or (2221 <= four <= 2720 and length == 16)  # Mastercard (2-серия)
        or (2200 <= four <= 2204 and 16 <= length <= 19)  # Мир
        or (two in (34, 37) and length == 15)  # American Express
        or (two == 62 and 16 <= length <= 19)  # UnionPay
        or (3528 <= four <= 3589 and 16 <= length <= 19)  # JCB
        or ((four == 6011 or two == 65 or 644 <= three <= 649) and 16 <= length <= 19)  # Discover
        or (two in (50, 56, 57, 58, 63, 67) and 12 <= length <= 19)  # Maestro
    )


def luhn_check(card_number: str) -> bool:
    """
    Проверяет номер банковской карты по официальному алгоритму Луна.
    Помогает отличать реальные номера карт от случайных длинных чисел.
    """
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
    """Проверяет, похоже ли одиночное слово на надёжный случайный пароль (отсекая любые URL)."""
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
    """
    Ищет секрет в тексте по порядку: известные ключи -> карты -> случайные пароли.
    Возвращает кортеж (найден_ли_секрет, тип_секрета, найденная_строка).
    """
    for secret_type, pattern in PATTERNS:
        match = pattern.search(text)
        if match:
            return True, secret_type, match.group(0)

    for match in CARD_PATTERN.finditer(text):
        digits_only = re.sub(r"\D", "", match.group(0))
        if has_known_card_prefix(digits_only) and luhn_check(digits_only):
            return True, "CREDIT_CARD", match.group(0)

    words = text.strip().split()
    if len(words) == 1 and _looks_like_strong_password(words[0]):
        return True, "HIGH_ENTROPY_PASSWORD", words[0]

    return False, "", ""


def mask_secret(secret: str) -> str:
    """Прячет середину секрета символами •••, чтобы безопасно показать его пользователю или в логе."""
    stripped = secret.strip()
    if len(stripped) <= 6:
        return "••••••"
    if len(stripped) <= 8:
        return f"{stripped[:2]}•••{stripped[-2:]}"
    return f"{stripped[:4]}•••{stripped[-2:]}"
