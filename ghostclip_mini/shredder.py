"""
ghostclip_mini/shredder.py
Затирка буфера обмена, экстренная паника (очистка Win+V) и таймер самоуничтожения секретов.
"""

import time
import threading
import ctypes
from clipboard import write_clipboard_text, wipe_clipboard

def shred_clipboard():
    """Затирает память буфера нулями перед очисткой."""
    for _ in range(3):
        write_clipboard_text("0" * 64)
        time.sleep(0.01)
        write_clipboard_text("\x00" * 64)
        time.sleep(0.01)
    wipe_clipboard()

def panic_wipe():
    """Экстренная паника: сбрасывает буфер и принудительно затирает историю Win+V."""
    shred_clipboard()
    try:
        ctypes.windll.ole32.OleFlushClipboard()
    except Exception:
        pass
    for _ in range(25):
        write_clipboard_text(" ")
        time.sleep(0.005)
    wipe_clipboard()

class GhostTimer:
    """Асинхронный таймер самоуничтожения секрета в буфере обмена."""
    def __init__(self):
        self._timer: threading.Timer = None  # type: ignore
        self._arm_time = 0.0
        self._seconds = 45

    def arm(self, seconds: int, callback):
        self.disarm()
        self._seconds = seconds
        self._arm_time = time.time()
        self._timer = threading.Timer(seconds, callback)
        self._timer.daemon = True
        self._timer.start()

    def disarm(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None  # type: ignore
        self._arm_time = 0.0

    def is_armed(self) -> bool:
        return self._timer is not None and self._timer.is_alive()

    def remaining_seconds(self) -> int:
        if not self.is_armed():
            return 0
        return max(0, int(self._seconds - (time.time() - self._arm_time)))

ghost_timer = GhostTimer()
