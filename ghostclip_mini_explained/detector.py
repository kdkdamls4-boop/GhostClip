"""
ghostclip_mini_explained/detector.py
Файл 3 из 7: Детекция секретов: токены OpenAI, AWS, GitHub, номера кредитных карт (алгоритм Луна), пароли.
"""

# re — регулярные выражения для распознавания шаблонов API-ключей и токенов
import re
# math — математический модуль для вычисления информационной энтропии Шеннона
import math

# Шаблоны популярных провайдеров API-ключей
PATTERNS = [
    # Ключи OpenAI начинаются с "sk-" и содержат от 20 буквенно-цифровых знаков
    ("OPENAI_KEY", re.compile(r"sk-[a-zA-Z0-9_-]{20,}")),
    # Ключи доступа Amazon Web Services (AWS) начинаются с AKIA/ABIA/ACCA/ASIA
    ("AWS_KEY", re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}")),
    # Персональные токены доступа GitHub начинаются с ghp_, gho_, ghu_ и т.д.
    ("GITHUB_TOKEN", re.compile(r"gh[pousr]-[A-Za-z0-9_]{36,}")),
]

def calculate_entropy(s: str) -> float:
    """
    Вычисляет энтропию Шеннона для строки.
    Показывает степень случайности символов:
    Обычные слова имеют энтропию 2.0-3.0, а случайные пароли/ключи — от 3.6 и выше.
    """
    if not s:
        return 0.0
    length = len(s)
    # Формула Шеннона: H = -sum(p * log2(p))
    return -sum((s.count(c) / length) * math.log2(s.count(c) / length) for c in set(s))

def luhn_check(num: str) -> bool:
    """
    Проверяет валидность номера банковской карты по официальному алгоритму Луна (Luhn Checksum).
    Исключает ложные срабатывания на случайные наборы цифр (номера телефонов, заказы).
    """
    # Оставляем только цифры
    digits = [int(c) for c in num if c.isdigit()]
    # Банковские карты Visa, MasterCard, МИР имеют длину от 13 до 19 цифр
    if not (13 <= len(digits) <= 19):
        return False

    checksum = 0
    # Идём по цифрам справа налево (разворачиваем список через [::-1])
    for i, digit in enumerate(digits[::-1]):
        if i % 2 == 1:  # Каждую вторую цифру удваиваем
            doubled = digit * 2
            # Если результат больше 9, вычитаем 9 (например, 7*2=14 -> 14-9=5, то же самое что 1+4)
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit

    # Если сумма делится на 10 без остатка — это валидный номер карты
    return checksum % 10 == 0

def detect_secret(text: str) -> tuple[bool, str, str]:
    """
    Анализирует текст на наличие конфиденциальных данных.
    Возвращает (найден_ли_секрет, тип_секрета, найденное_значение).
    """
    # 1. Проверяем шаблоны известных API-ключей (OpenAI, AWS, GitHub)
    for name, rgx in PATTERNS:
        match = rgx.search(text)
        if match:
            return True, name, match.group(0)

    # 2. Ищем последовательности из 13-19 цифр с возможными пробелами/дефисами
    for match in re.finditer(r"\b(?:\d[ -]*?){13,19}\b", text):
        clean_num = re.sub(r"\D", "", match.group(0))  # Убираем пробелы и дефисы
        if luhn_check(clean_num):
            return True, "CREDIT_CARD", match.group(0)

    # 3. Проверяем на высокоэнтропийный пароль (одно слово длиной >= 12 символов со случайным набором)
    words = text.strip().split()
    if len(words) == 1 and len(words[0]) >= 12 and calculate_entropy(words[0]) >= 3.6:
        return True, "HIGH_ENTROPY_PASSWORD", words[0]

    return False, "", ""

def mask_secret(secret: str) -> str:
    """
    Безопасно маскирует секрет звёздочками для вывода на экран и записи в лог.
    Например: "sk-proj-1234567890" -> "sk**************90".
    """
    s = secret.strip()
    if len(s) > 6:
        # Первые 2 символа + звёздочки + последние 2 символа
        return s[:2] + "*" * (len(s) - 4) + s[-2:]
    return "*" * len(s)
