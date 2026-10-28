"""
ghostclip_mini/detector.py
Детекция секретов: токены OpenAI, AWS, GitHub, номера кредитных карт (алгоритм Луна), пароли.
"""

import re
import math

PATTERNS = [
    ("OPENAI_KEY", re.compile(r"sk-[a-zA-Z0-9_-]{20,}")),
    ("AWS_KEY", re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}")),
    ("GITHUB_TOKEN", re.compile(r"gh[pousr]-[A-Za-z0-9_]{36,}")),
]

def calculate_entropy(s: str) -> float:
    if not s:
        return 0.0
    return -sum((s.count(c)/len(s)) * math.log2(s.count(c)/len(s)) for c in set(s))

def luhn_check(num: str) -> bool:
    d = [int(c) for c in num if c.isdigit()]
    if not (13 <= len(d) <= 19):
        return False
    checksum = 0
    for i, digit in enumerate(d[::-1]):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0

def detect_secret(text: str) -> tuple[bool, str, str]:
    for name, rgx in PATTERNS:
        m = rgx.search(text)
        if m:
            return True, name, m.group(0)
    for m in re.finditer(r"\b(?:\d[ -]*?){13,19}\b", text):
        clean = re.sub(r"\D", "", m.group(0))
        if luhn_check(clean):
            return True, "CREDIT_CARD", m.group(0)
    tokens = text.strip().split()
    if len(tokens) == 1 and len(tokens[0]) >= 12 and calculate_entropy(tokens[0]) >= 3.6:
        return True, "HIGH_ENTROPY_PASSWORD", tokens[0]
    return False, "", ""

def mask_secret(secret: str) -> str:
    s = secret.strip()
    return s[:2] + "*" * (len(s) - 4) + s[-2:] if len(s) > 6 else "*" * len(s)
