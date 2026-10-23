"""
Модуль журнала аудита (Audit Logger).
Безопасно фиксирует события доступа к буферу обмена без утечки секретов.
"""

import datetime
import threading
from .detector import detect_secret, mask_secret

LOG_FILE_PATH = "clipboard_access.log"
_log_lock = threading.Lock()


def log_audit(event: str, process: str, content: str, extra: str = ""):
    """
    Записывает событие буфера в файл журнала `clipboard_access.log`.
    Секреты никогда не пишутся в открытом виде — только маскированными!
    """
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Безопасное отображение контента
    sec_info = detect_secret(content)
    if sec_info:
        safe_content = f"{mask_secret(content)} [{sec_info[1]}]"
    else:
        # Обрезаем длинный текст
        content_clean = content.strip().replace("\r\n", " ").replace("\n", " ")
        if len(content_clean) > 80:
            safe_content = f"{content_clean[:80]}... [всего {len(content_clean)} симв.]"
        else:
            safe_content = content_clean

    log_entry = (
        f"[{now_str}] [{event}]\n"
        f"Процесс: {process}\n"
        f"Контент: {safe_content}\n"
    )
    if extra:
        log_entry += f"Инфо: {extra}\n"
    log_entry += "-" * 50 + "\n"

    with _log_lock:
        try:
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"[!] Ошибка записи в журнал: {e}")
