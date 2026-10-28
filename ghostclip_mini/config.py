"""
ghostclip_mini/config.py
Настройки переключателей [1-6] и журнал аудита (clipboard_access.log).
"""

import datetime

LOG_FILE_PATH = "clipboard_access.log"

class ShieldConfig:
    def __init__(self):
        self.clean_urls = True
        self.clean_zero_width = True
        self.detect_secrets = True
        self.auto_shred_timer = True
        self.shred_win_v = True
        self.audit_logging = True
        self.timer_seconds = 45

    def toggle(self, opt_id: int):
        attrs = {1: "clean_urls", 2: "clean_zero_width", 3: "detect_secrets",
                 4: "auto_shred_timer", 5: "shred_win_v", 6: "audit_logging"}
        names = {1: "Чистка ссылок", 2: "Удаление невидимых знаков", 3: "Детекция секретов",
                 4: "Таймер самоуничтожения", 5: "Зачистка истории Win+V", 6: "Журнал аудита"}
        if opt_id not in attrs:
            return "Неизвестно", False
        attr = attrs[opt_id]
        val = not getattr(self, attr)
        setattr(self, attr, val)
        return names[opt_id], val

    def get_status_dict(self):
        return {
            1: ("Чистка ссылок (utm, fbclid, si)", self.clean_urls),
            2: ("Удаление невидимых символов", self.clean_zero_width),
            3: ("Детекция секретов и карт", self.detect_secrets),
            4: (f"Таймер самоуничтожения ({self.timer_seconds}с)", self.auto_shred_timer),
            5: ("Зачистка истории Win+V", self.shred_win_v),
            6: ("Журнал clipboard_access.log", self.audit_logging),
        }

config = ShieldConfig()

def log_audit(event_type: str, app_name: str, snippet: str, details: str = ""):
    if not config.audit_logging:
        return
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{event_type}] [APP: {app_name}] [DATA: {snippet}] {details}".strip()
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
