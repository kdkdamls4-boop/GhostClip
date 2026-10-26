# 🧹 Разбор `cleaner.py` и `detector.py` — Очистка ссылок и поиск секретов

В этих двух модулях сосредоточена вся логика фильтрации и математического анализа текста.

---

## 🧹 Часть 1: `ghostclip/cleaner.py` — Очистка ссылок и невидимых знаков

### 1. Удаление невидимых знаков Zero-Width на скорости языка Си

Невидимые символы нулевой ширины (`\u200B`, `\u200C`, `\uFEFF` и др.) часто внедряют в конфиденциальные документы или чаты как скрытые водяные знаки для деанонимизации утечек.

Вместо медленного перебора символов в цикле `for ch in text:` используется метод `str.translate` со строковой таблицей подстановки:

```python
ZERO_WIDTH_CHARS = "\u200B\u200C\u200D\uFEFF\u200E\u200F\u202A\u202B\u202C\u202D\u202E\u2060"

# str.maketrans("", "", ZERO_WIDTH_CHARS) создает бинарную таблицу для мгновенного удаления символов
ZW_TABLE = str.maketrans("", "", ZERO_WIDTH_CHARS)

def strip_zero_width(text: str) -> Tuple[str, int]:
    # text.translate(ZW_TABLE) выполняется целиком внутри скомпилированного кода C в ядре Python:
    cleaned = text.translate(ZW_TABLE)
    # Количество удаленных символов — это просто разница длин до и после:
    return cleaned, len(text) - len(cleaned)
```
*(Этот вызов работает более чем в 20 раз быстрее обычного цикла).*

---

### 2. Вырезание рекламных меток из URL (`clean_url`)

```python
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "si", "ref", "igshid", "yclid", ...
}

def clean_url(url_str: str) -> Tuple[str, List[str]]:
    # 1. urlparse разбирает ссылку на составляющие:
    # scheme='https', netloc='youtube.com', path='/watch', query='v=123&si=abc', fragment=''
    u = urlparse(url_str)
    if not u.scheme or not u.netloc:
        return url_str, []

    clean_q, removed = [], []
    # 2. parse_qsl превращает строку запроса в список пар: [('v', '123'), ('si', 'abc')]
    for k, v in parse_qsl(u.query, keep_blank_values=True):
        if k.lower() in TRACKING_PARAMS or k.lower().startswith("utm_"):
            removed.append(k)  # Найден трекер — запоминаем и удаляем
        else:
            clean_q.append((k, v))  # Полезный параметр (v=123) — оставляем

    if not removed:
        return url_str, []  # Если трекеров не было, возвращаем ссылку без изменений

    # 3. urlencode собирает оставшиеся параметры обратно в строку: 'v=123'
    # 4. urlunparse собирает весь URL заново:
    return urlunparse(u._replace(query=urlencode(clean_q))), removed
```

---

## 🔍 Часть 2: `ghostclip/detector.py` — Детекция карт, токенов и паролей

### 1. Проверка банковских карт: Алгоритм Луна (`luhn_check`)

Обычные программы путают любые 16 цифр подряд (например, номер заказа `1234567890123456`) с банковской картой.

GhostClip проверяет **математическую контрольную сумму Луна**, по которой выпускаются все карты Visa, MasterCard и МИР:

```python
def luhn_check(card_number: str) -> bool:
    digits = [int(c) for c in card_number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False

    # Математика алгоритма Луна:
    # 1. Идем с конца (digits[::-1]).
    # 2. Каждую вторую цифру удваиваем (d * 2). Если получилось больше 9, вычитаем 9.
    # 3. Суммируем все полученные числа.
    total = sum(
        d * 2 - 9 if (i % 2 == 1 and d * 2 > 9) else (d * 2 if i % 2 == 1 else d)
        for i, d in enumerate(digits[::-1])
    )
    # 4. Итоговая сумма должна делиться на 10 без остатка:
    return total % 10 == 0
```

---

### 2. Распознавание сложных паролей: Энтропия Шеннона (`calculate_entropy`)

Как понять, что скопированная строка `vX9#mQ2$pL!8zR@k` — это сложный пароль из менеджера паролей (Bitwarden / 1Password), а не просто набор букв?

Используется **формула энтропии Шеннона** из теории информации:

$$H = -\sum_{i} P(x_i) \log_2 P(x_i)$$

Она измеряет «случайность» и непредсказуемость символов в строке:

```python
from collections import Counter

def calculate_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    # Counter(s) мгновенно подсчитывает частоту каждого символа в коде C.
    # p = count / n — вероятность встретить данный символ в строке.
    return -sum((count / n) * math.log2(count / n) for count in Counter(s).values())
```

* Обычное слово (`"password"`, `"hello"`) имеет энтропию **$\approx 1.5 - 2.5$ бит/символ**.
* Сгенерированный пароль из 16 символов со спецсимволами имеет энтропию **$\ge 3.75$ бит/символ** и сразу три типа знаков (цифры, заглавные буквы, пунктуация).
* При обнаружении такой строки GhostClip классифицирует её как `PASSWORD`!

---

### 3. Регулярные выражения для API-токенов разработчика

```python
PATTERNS = [
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "API_KEY", "OpenAI API Key"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "TOKEN", "GitHub Personal Token"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{50,}"), "TOKEN", "GitHub Fine-Grained Token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "API_KEY", "AWS Access Key ID"),
    (re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP)?\s?PRIVATE KEY-----"), "PRIVATE_KEY", "Приватный ключ (SSH/TLS)"),
]
```

### 4. Безопасное маскирование (`mask_secret`)

Секреты никогда не выводятся на экран и в логи целиком:

```python
def mask_secret(text: str) -> str:
    s = text.strip()
    return "••••••" if len(s) <= 6 else f"{s[:4]}•••{s[-2:]}"
    # "sk-proj-1234567890abcdef" -> "sk-p•••ef"
```
