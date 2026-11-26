"""
explained/ghostclip/shredder.py
Затирка буфера обмена, очистка системного журнала Win+V через WinRT API и таймер самоуничтожения.
"""

import subprocess  # subprocess — тихий запуск встроенной команды Windows Runtime для очистки Win+V
import threading  # threading.Timer и Lock — фоновый таймер с защитой от гонок потоков
import time  # time.monotonic — точный отсчёт секунд, не зависящий от перевода системных часов

from .clipboard import wipe_clipboard, write_clipboard_text

CREATE_NO_WINDOW = 0x08000000  # Флаг Windows: запускать процесс полностью невидимо, без чёрного окна
OVERWRITE_DUMMY_TEXT = "[GHOSTCLIP: СЕКРЕТ ЗАТЕРТ]"


def wipe_win_v_history() -> bool:
    """Бесшумно очищает историю системного буфера обмена Windows 10/11 (Win+V) через WinRT."""
    command = "[Windows.ApplicationModel.DataTransfer.Clipboard,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]::ClearHistory()"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def shred_clipboard(dummy_text: str = OVERWRITE_DUMMY_TEXT) -> bool:
    """Перезаписывает буфер приватной заглушкой (без записи в Win+V и облако) и очищает его."""
    write_clipboard_text(dummy_text, private=True)
    return wipe_clipboard()


def panic_wipe() -> tuple[bool, bool]:
    """Экстренная паника: затирает буфер обмена и удаляет всю историю Win+V."""
    clipboard_ok = shred_clipboard()
    history_ok = wipe_win_v_history()
    return clipboard_ok, history_ok


class GhostTimer:
    """
    Потокобезопасный таймер самоуничтожения секретов.
    Счётчик _epoch защищает от редкой гонки: старый таймер никогда не сотрёт новый текст,
    если пользователь успел отменить или перезапустить отсчёт в последнюю миллисекунду.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._epoch = 0
        self._armed = False
        self._arm_time = 0.0
        self._seconds = 45

    def arm(self, seconds: float, on_expire=None) -> None:
        """Взводит таймер на указанное число секунд и по истечении вызывает callback on_expire."""
        with self._lock:
            self._cancel_locked()
            self._epoch += 1
            current_epoch = self._epoch
            self._seconds = seconds
            self._arm_time = time.monotonic()
            self._armed = True
            self._timer = threading.Timer(seconds, self._fire, args=(current_epoch, on_expire))
            self._timer.daemon = True  # Фоновый поток не мешает закрытию программы
            self._timer.start()

    def disarm(self) -> None:
        """Останавливает таймер (например, при копировании обычного безопасного текста)."""
        with self._lock:
            self._epoch += 1
            self._cancel_locked()

    def _cancel_locked(self) -> None:
        """Внутренний метод сброса: вызывается только когда _lock уже захвачен."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._armed = False
        self._arm_time = 0.0

    def _fire(self, expected_epoch: int, on_expire) -> None:
        """Срабатывает в фоновом потоке, когда время вышло."""
        with self._lock:
            if not self._armed or self._epoch != expected_epoch:
                return  # Таймер уже отменили или перезапустили — выходим без действий
            self._armed = False
            self._timer = None
            self._arm_time = 0.0

        # Вызываем callback уже после освобождения замка, чтобы избежать взаимной блокировки
        if on_expire is not None:
            on_expire()

    def is_armed(self) -> bool:
        """Проверяет, активен ли сейчас обратный отсчёт."""
        with self._lock:
            return self._armed

    def remaining_seconds(self) -> int:
        """Возвращает количество целых секунд, оставшихся до срабатывания."""
        with self._lock:
            if not self._armed:
                return 0
            elapsed = time.monotonic() - self._arm_time
            return max(0, int(self._seconds - elapsed))


# Глобальный экземпляр таймера
ghost_timer = GhostTimer()
