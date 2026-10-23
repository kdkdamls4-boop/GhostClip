"""
Модуль конфигурации и переключения функций GhostClip Shield.
Хранит флаги включения/выключения компонентов в потокобезопасном виде.
"""

import threading
from dataclasses import dataclass


@dataclass
class ShieldConfig:
    """Конфигурация защитных функций щита."""
    clean_urls: bool = True           # Очистка трекинг-меток в ссылках (utm, fbclid, si)
    clean_zero_width: bool = True     # Удаление невидимых знаков нулевой ширины
    detect_secrets: bool = True       # Поиск паролей, токенов API и банковских карт
    ghost_timer_enabled: bool = True  # Таймер самоуничтожения секретов (45 сек)
    wipe_win_v: bool = True           # Зачистка истории Win+V при уничтожении
    audit_logging: bool = True        # Ведение журнала в clipboard_access.log
    timer_seconds: int = 45           # Время жизни секрета в буфере (сек)

    def __init__(self):
        self.clean_urls = True
        self.clean_zero_width = True
        self.detect_secrets = True
        self.ghost_timer_enabled = True
        self.wipe_win_v = True
        self.audit_logging = True
        self.timer_seconds = 45
        self._lock = threading.Lock()

    def toggle(self, option_id: int) -> tuple[str, bool]:
        """
        Переключает функцию по её порядковому номеру (1-6).
        Возвращает (название_функции, новое_значение).
        """
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

    def get_status_dict(self) -> dict:
        """Возвращает текущие статусы всех функций."""
        with self._lock:
            return {
                1: ("Чистка ссылок (utm, fbclid, si)", self.clean_urls),
                2: ("Удаление невидимых символов", self.clean_zero_width),
                3: ("Детекция секретов и карт", self.detect_secrets),
                4: ("Таймер самоуничтожения (45с)", self.ghost_timer_enabled),
                5: ("Зачистка истории Win+V", self.wipe_win_v),
                6: ("Журнал clipboard_access.log", self.audit_logging),
            }


# Глобальный экземпляр настроек
config = ShieldConfig()
