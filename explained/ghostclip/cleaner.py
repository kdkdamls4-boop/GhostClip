"""Модуль очистки ссылок в тексте и удаления невидимых символов (CleanClip)."""

import re
# re — регулярные выражения (поиск по шаблону).

from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
# Встроенные инструменты для разбора ссылок:
#   urlparse   — разбирает ссылку на части (схема, сайт, путь, параметры...)
#   parse_qsl  — разбирает параметры "a=1&b=2" в список [("a","1"), ("b","2")]
#   urlencode  — собирает обратно: [("a","1")] → "a=1"
#   urlunparse — собирает ссылку из частей обратно в строку

from typing import Tuple, List


# ═══════════════════════════════════════════════════════════════════
#  НЕВИДИМЫЕ СИМВОЛЫ
# ═══════════════════════════════════════════════════════════════════

ZERO_WIDTH_CHARS = "\u200B\u200C\u200D\uFEFF\u200E\u200F\u202A\u202B\u202C\u202D\u202E\u2060"
# \u200B и т.д. — коды символов Unicode, у которых НЕТ ширины, то есть их не видно.
# Ими иногда «метят» текст, чтобы отследить, кто его скопировал,
# или ломают пароли и ссылки.

ZW_TABLE = str.maketrans("", "", ZERO_WIDTH_CHARS)
# maketrans создаёт «таблицу замен». Третий аргумент = «эти символы удалить».
# Потом text.translate(ZW_TABLE) удалит их все за один проход, очень быстро.


# ═══════════════════════════════════════════════════════════════════
#  ТРЕКИНГ-МЕТКИ В ССЫЛКАХ
# ═══════════════════════════════════════════════════════════════════

TRACKING_PARAMS = {
    # Фигурные скобки без двоеточий — это SET (множество).
    # Поиск `x in set` в нём очень быстрый.
    # Это параметры, по которым сайты следят, откуда ты пришёл.
    # Пример: youtube.com/watch?v=abc&si=XYZ  ← si — это слежка.
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "fbclid", "gclid", "si", "ref", "ref_src", "igshid", "yclid", "mc_cid", "mc_eid",
    "_openstat", "dclid", "msclkid",
}

URL_REGEX = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
# Шаблон ссылки: "http", затем необязательная "s" (s?), затем "://",
# затем всё подряд, кроме пробела и символов < > " '.
# re.IGNORECASE — не важно, большие буквы или маленькие.


def strip_zero_width(text: str) -> Tuple[str, int]:
    """Удаляет невидимые символы на скорости C через str.translate."""
    cleaned = text.translate(ZW_TABLE)
    return cleaned, len(text) - len(cleaned)
    # Возвращаем ДВА значения: очищенный текст и число удалённых символов
    # (длина «до» минус длина «после»).


def clean_url(url_str: str) -> Tuple[str, List[str]]:
    """Вырезает трекинг-метки из URL, сохраняя полезные параметры."""
    try:
        # try — «попробуй». Если внутри что-то сломается, перейдём в except.

        u = urlparse(url_str)
        # u.scheme = "https", u.netloc = "youtube.com", u.query = "v=abc&si=XYZ"

        if not u.scheme or not u.netloc:
            # or — хотя бы одно условие истинно.
            # Если нет схемы или сайта, это не ссылка. Возвращаем как было.
            return url_str, []

        clean_q, removed = [], []
        # Создаём сразу ДВА пустых списка:
        # clean_q — параметры, которые оставим; removed — имена удалённых.

        for k, v in parse_qsl(u.query, keep_blank_values=True):
            # k — имя параметра ("si"), v — значение ("XYZ").
            if k.lower() in TRACKING_PARAMS or k.lower().startswith("utm_"):
                # .lower() — в нижний регистр. .startswith("utm_") — начинается ли с "utm_".
                removed.append(k)
                # .append() — добавить в конец списка.
            else:
                clean_q.append((k, v))
                # Двойные скобки: добавляем один кортеж (k, v).

        if not removed:
            # Ничего не удалили, поэтому возвращаем исходную ссылку без изменений.
            return url_str, []

        return urlunparse(u._replace(query=urlencode(clean_q))), removed
        # u._replace(query=...) — копия ссылки с заменёнными параметрами.
        # urlunparse — собираем её обратно в строку.
    except Exception:
        # Exception — любая ошибка. Если что-то сломалось, просто отдаём ссылку как была.
        return url_str, []


def sanitize_text(text: str, clean_urls_enabled: bool = True, clean_zw_enabled: bool = True) -> Tuple[str, List[str], int]:
    # Параметры с = True — значения по умолчанию. Если их не передать, будут True.
    """Очищает невидимые символы и любые ссылки (даже внутри длинного текста)."""

    cleaned, zw_count = strip_zero_width(text) if clean_zw_enabled else (text, 0)
    # Тернарный оператор: если включено — чистим, иначе (text, 0) «как есть, удалено 0».

    removed_all: List[str] = []
    # Сюда будем собирать ВСЕ удалённые метки со всех ссылок в тексте.

    if clean_urls_enabled and "http" in cleaned.lower():
        # Быстрая проверка: если в тексте вообще нет "http", ссылки не ищем.

        def _repl(match):
            # Функция ВНУТРИ функции. Её вызовет URL_REGEX.sub для каждой найденной ссылки.
            # match.group(0) — текст найденной ссылки.
            url, rem = clean_url(match.group(0))
            removed_all.extend(rem)
            # .extend() — добавить в список ВСЕ элементы другого списка.
            return url
            # То, что вернём, встанет в текст на место старой ссылки.

        cleaned = URL_REGEX.sub(_repl, cleaned)
        # .sub(функция, текст) — найти все ссылки и заменить каждую результатом _repl.

    return cleaned, removed_all, zw_count
    # Возвращаем ТРИ значения: текст, список удалённых меток, число невидимых символов.
