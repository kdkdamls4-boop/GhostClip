# ⚙️ Разбор `config.py` и `audit.py` — Настройки тумблеров и журнал аудита

Эти два модуля обеспечивают управление состоянием функций и безопасное ведение истории доступа к буферу.

---

## ⚙️ Часть 1: `ghostclip/config.py` — Потокобезопасные тумблеры `[1–6]`

Класс `ShieldConfig` хранит логические флаги всех 6 защитных механизмов:

```python
@dataclass
class ShieldConfig:
    clean_urls: bool = True           # [1] Очистка ссылок от трекеров
    clean_zero_width: bool = True     # [2] Удаление невидимых знаков
    detect_secrets: bool = True       # [3] Детекция карт и токенов
    ghost_timer_enabled: bool = True  # [4] Таймер самоуничтожения (45с)
    wipe_win_v: bool = True           # [5] Зачистка истории Win+V
    audit_logging: bool = True        # [6] Журнал аудита в файл
    timer_seconds: int = 45

    def __init__(self):
        ...
        # Мьютекс для защиты от одновременного чтения/записи из разных потоков:
        self._lock = threading.Lock()
```

### Переключение функции по номеру: `toggle`

Когда пользователь нажимает цифру `1-6` на клавиатуре или кликает пункт в ПКМ-меню трея:

```python
def toggle(self, option_id: int) -> tuple[str, bool]:
    with self._lock:
        if option_id == 1:
            self.clean_urls = not self.clean_urls
            return ("Чистка ссылок от трекеров", self.clean_urls)
        elif option_id == 2:
            self.clean_zero_width = not self.clean_zero_width
            return ("Удаление невидимых символов", self.clean_zero_width)
        elif option_id == 3:
            self.detect_secrets = not self.detect_secrets
            return ("Детекция секретов и карт", self.detect_secrets)
        elif option_id == 4:
            self.ghost_timer_enabled = not self.ghost_timer_enabled
            return ("Таймер самоуничтожения", self.ghost_timer_enabled)
        elif option_id == 5:
            self.wipe_win_v = not self.wipe_win_v
            return ("Зачистка журнала Win+V", self.wipe_win_v)
        elif option_id == 6:
            self.audit_logging = not self.audit_logging
            return ("Журнал аудита", self.audit_logging)
        else:
            raise ValueError(f"Неизвестный номер функции: {option_id}")
```

---

## 📝 Часть 2: `ghostclip/audit.py` — Безопасный журнал событий

Файл [`ghostclip/audit.py`](../ghostclip/audit.py) записывает историю операций в файл `clipboard_access.log`.

### Главное правило безопасности: Секреты никогда не пишутся на диск в открытом виде!

Если программа будет сохранять пароли и токены в текстовый лог, то этот лог станет первой целью для вирусов. Поэтому перед записью текст обязательно проверяется через `detect_secret()`:

```python
LOG_FILE_PATH = "clipboard_access.log"
_log_lock = threading.Lock()

def log_audit(event: str, process: str, content: str, extra: str = ""):
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Проверяем, является ли контент секретом (карта, токен, пароль):
    sec_info = detect_secret(content)
    if sec_info:
        # Если это секрет, маскируем его: "sk-proj-123456" -> "sk-p•••56"
        safe_content = f"{mask_secret(content)} [{sec_info[1]}]"
    else:
        # Если это обычный текст, обрезаем длинные строки до 80 символов:
        content_clean = content.strip().replace("\r\n", " ").replace("\n", " ")
        if len(content_clean) > 80:
            safe_content = f"{content_clean[:80]}... [всего {len(content_clean)} симв.]"
        else:
            safe_content = content_clean

    # 2. Формируем запись:
    log_entry = (
        f"[{now_str}] [{event}]\n"
        f"Процесс: {process}\n"
        f"Контент: {safe_content}\n"
    )
    if extra:
        log_entry += f"Инфо: {extra}\n"
    log_entry += "-" * 50 + "\n"

    # 3. Потокобезопасно дописываем в конец файла:
    with _log_lock:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(log_entry)
```
