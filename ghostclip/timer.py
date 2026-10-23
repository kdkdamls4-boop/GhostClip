"""
Модуль таймера самоуничтожения секретов в буфере обмена (Ghost Timer).
"""

import time
import threading
from typing import Optional
from .clipboard import wipe_clipboard
from .shredder import wipe_win_v_history
from .audit import log_audit
from .config import config


class GhostTimer:
    """
    Управляет обратным отсчетом до стирания секрета из буфера обмена.
    Один фоновый поток — никаких утечек памяти и параллельных гонок!
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._epoch = 0
        self._remaining = 0
        self._armed = False
        self._desc = ""
        self._cancel_event = threading.Event()

    def arm(self, seconds: int, desc: str, on_expire=None):
        """Взводит таймер самоуничтожения."""
        with self._lock:
            self._epoch += 1
            current_epoch = self._epoch
            self._remaining = seconds
            self._armed = True
            self._desc = desc
            self._on_expire = on_expire
            self._cancel_event.clear()

        # Запускаем отсчет в фоновом потоке
        threading.Thread(
            target=self._countdown_loop,
            args=(current_epoch, seconds),
            daemon=True,
        ).start()

    def disarm(self):
        """Останавливает таймер (например, если скопирован безопасный текст)."""
        with self._lock:
            self._armed = False
            self._cancel_event.set()

    def is_armed(self) -> bool:
        with self._lock:
            return self._armed

    def remaining_seconds(self) -> int:
        with self._lock:
            return self._remaining

    def _countdown_loop(self, epoch: int, total_seconds: int):
        for sec in range(total_seconds, 0, -1):
            with self._lock:
                if not self._armed or self._epoch != epoch:
                    return
                self._remaining = sec

            time.sleep(1.0)

        with self._lock:
            if not self._armed or self._epoch != epoch:
                return
            self._armed = False

        # ВРЕМЯ ВЫШЛО: Уничтожаем данные в буфере и истории Win+V!
        wipe_clipboard()
        if config.wipe_win_v:
            wipe_win_v_history()

        if config.audit_logging:
            log_audit(
                event="GHOST_WIPED",
                process="GhostClip",
                content="[СЕКРЕТ_ЗАТЕРТ]",
                extra=f"Таймер {total_seconds}с истек. Буфер и Win+V стерты.",
            )
        msg = f"[GHOST] Время вышло ({total_seconds}с)! Буфер обмена и журнал Win+V ЗАТЕРТЫ."
        if getattr(self, "_on_expire", None):
            self._on_expire(msg)
        else:
            print(f"\n{msg}")


# Глобальный синглтон таймера
ghost_timer = GhostTimer()
