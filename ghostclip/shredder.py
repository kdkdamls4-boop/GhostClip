"""Затирка буфера обмена, экстренная паника (очистка Win+V через WinRT) и таймер самоуничтожения."""

import subprocess
import threading
import time

from .clipboard import wipe_clipboard, write_clipboard_text

CREATE_NO_WINDOW = 0x08000000
OVERWRITE_DUMMY_TEXT = "[GHOSTCLIP: СЕКРЕТ ЗАТЕРТ]"


def wipe_win_v_history() -> bool:
    """Бесшумно очищает историю буфера обмена Windows (Win+V) через WinRT API."""
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
    """Перезаписывает текущий буфер заглушкой и очищает его."""
    write_clipboard_text(dummy_text)
    return wipe_clipboard()


def panic_wipe() -> tuple[bool, bool]:
    """Экстренная паника: затирает буфер обмена и полностью очищает историю Win+V."""
    clipboard_ok = shred_clipboard()
    history_ok = wipe_win_v_history()
    return clipboard_ok, history_ok


class GhostTimer:
    """Потокобезопасный таймер самоуничтожения секрета с защитой от гонок (epoch)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._epoch = 0
        self._armed = False
        self._arm_time = 0.0
        self._seconds = 45

    def arm(self, seconds: float, on_expire=None) -> None:
        """Взводит таймер на указанное число секунд и вызывает on_expire по истечении."""
        with self._lock:
            self._cancel_locked()
            self._epoch += 1
            current_epoch = self._epoch
            self._seconds = seconds
            self._arm_time = time.monotonic()
            self._armed = True
            self._timer = threading.Timer(seconds, self._fire, args=(current_epoch, on_expire))
            self._timer.daemon = True
            self._timer.start()

    def disarm(self) -> None:
        """Останавливает активный таймер и отменяет запланированный сброс."""
        with self._lock:
            self._epoch += 1
            self._cancel_locked()

    def _cancel_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._armed = False
        self._arm_time = 0.0

    def _fire(self, expected_epoch: int, on_expire) -> None:
        with self._lock:
            if not self._armed or self._epoch != expected_epoch:
                return
            self._armed = False
            self._timer = None
            self._arm_time = 0.0

        if on_expire is not None:
            on_expire()

    def is_armed(self) -> bool:
        """Возвращает True, если таймер сейчас запущен и ещё не сработал."""
        with self._lock:
            return self._armed

    def remaining_seconds(self) -> int:
        """Возвращает оставшееся количество секунд до срабатывания таймера."""
        with self._lock:
            if not self._armed:
                return 0
            elapsed = time.monotonic() - self._arm_time
            return max(0, int(self._seconds - elapsed))


ghost_timer = GhostTimer()
