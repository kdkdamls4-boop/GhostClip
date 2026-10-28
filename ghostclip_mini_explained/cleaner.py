"""
ghostclip_mini_explained/cleaner.py
Файл 2 из 7: Чистка URL от трекинг-меток (utm, fbclid, si и др.) и удаление невидимых знаков Zero-Width.
"""

# re — модуль регулярных выражений для поиска URL-ссылок в тексте
import re
# urllib.parse — стандартный парсер интернет-адресов на схему, хост, параметры запроса
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Множество так называемых «невидимых символов» Юникода (Zero-Width Characters).
# Хакеры и шпионские сайты подмешивают их в скопированный текст для цифровой стеганографии и трекинга пользователей.
ZERO_WIDTH_CHARS = {
    '\u200b',  # Zero-width space (пробел нулевой ширины)
    '\u200c',  # Zero-width non-joiner
    '\u200d',  # Zero-width joiner
    '\ufeff',  # Byte Order Mark (BOM)
    '\u200e',  # Left-to-right mark
    '\u200f',  # Right-to-left mark
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',  # Управляющие символы направления текста
}

# Множество параметров слежки и таргетированной рекламы в URL
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',  # Метки Google/Яндекс
    'fbclid',   # Идентификатор клика Facebook
    'gclid',    # Идентификатор клика Google Ads
    'yclid',    # Идентификатор клика Яндекс.Директ
    'si',       # Идентификатор трекинга шаринга YouTube / Spotify
    'igshid',   # Идентификатор шаринга Instagram
    'mc_eid',   # Идентификатор рассылок Mailchimp
    'ysclid',   # Поисковый трекинг Яндекса
}

def strip_zero_width(text: str) -> tuple[str, int]:
    """
    Удаляет все скрытые невидимые символы из текста.
    Возвращает очищенную строку и количество удалённых невидимых символов.
    """
    # Считаем, сколько символов из строки text входят в наше множество ZERO_WIDTH_CHARS
    cnt = sum(1 for c in text if c in ZERO_WIDTH_CHARS)
    # Собираем строку заново, оставляя только видимые символы
    cleaned = ''.join(c for c in text if c not in ZERO_WIDTH_CHARS)
    return cleaned, cnt

def clean_url(url: str) -> tuple[str, list[str]]:
    """
    Удаляет из одной ссылки URL все известные шпионские и рекламные параметры.
    Возвращает очищенный URL и список удалённых параметров.
    """
    try:
        # Разбиваем URL на составные части: схема (https), домен (site.com), путь (/page), параметры (?a=1)
        p = urlparse(url)
        # Если это не полноценный адрес (нет протокола или домена), возвращаем как есть
        if not p.scheme or not p.netloc:
            return url, []

        # Парсим строку запроса query в словарь параметров: {'utm_source': ['google'], 'id': ['123']}
        q = parse_qs(p.query, keep_blank_values=True)
        # Находим параметры, которые есть в списке запрещённых
        rem = [k for k in q if k in TRACKING_PARAMS]
        if not rem:
            return url, []  # Трекеров нет, ничего не меняем

        # Удаляем найденные шпионские ключи из словаря
        for k in rem:
            del q[k]

        # Собираем параметры обратно в строку (например, "id=123")
        new_q = urlencode(q, doseq=True)
        # Собираем весь URL заново без удалённых параметров
        clean = urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment))
        return clean, rem
    except Exception:
        # В случае нестандартного повреждённого URL возвращаем оригинал
        return url, []

def sanitize_text(text: str) -> tuple[str, bool, list[str]]:
    """
    Комплексная очистка текста: убирает невидимые знаки и чистит все ссылки внутри текста.
    Возвращает (очищенный_текст, был_ли_текст_изменен, список_логов).
    """
    mod = False  # Флаг: был ли текст изменён
    # 1. Удаляем скрытые символы
    cleaned, cnt = strip_zero_width(text)
    logs = [f"Удалено {cnt} скрытых знаков"] if cnt else []
    if cnt:
        mod = True

    # 2. Ищем все интернет-ссылки регулярным выражением
    urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', cleaned)
    # Проходимся по каждой уникальной ссылке
    for u in set(urls):
        cu, rem = clean_url(u)
        if rem:  # Если из ссылки были вырезаны рекламные метки
            cleaned = cleaned.replace(u, cu)
            logs.append(f"Очищен URL ({', '.join(rem)})")
            mod = True

    return cleaned, mod, logs
