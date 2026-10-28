"""
ghostclip_mini_explained/shredder.py
Файл 5 из 7: Затирка буфера обмена, экстренная паника (очистка Win+V) и таймер самоуничтожения секретов.
"""

import time       # time — паузы между циклами перезаписи
import threading  # threading — запуск асинхронного таймера в отдельном потоке
import ctypes     # ctypes — системный вызов ole32.OleFlushClipboard

# Импортируем функции записи и очистки буфера из clipboard.py
from clipboard import write_clipboard_text, wipe_clipboard

def shred_clipboard():
    """
    Затирает буфер обмена: перед очисткой 3 раза перезаписывает его нулями и нуль-байтами,
    чтобы данные нельзя было восстановить из остаточной оперативной памяти.
    """
    for _ in range(3):
        write_clipboard_text("0" * 64)       # Перезапись строкой из 64 нулей
        time.sleep(0.01)
        write_clipboard_text("\x00" * 64)    # Перезапись сырыми нулевыми байтами
        time.sleep(0.01)
    wipe_clipboard()                         # Окончательная очистка буфера

def panic_wipe():
    """
    Экстренная ПАНИКА (Panic Flush):
    1. Затирает текущий буфер обмена.
    2. Вызывает системную функцию OleFlushClipboard() для сброса OLE-кэша.
    3. Вытесняет историю встроенного облачного буфера Windows (Win + V) серией фиктивных записей.
    """
    shred_clipboard()
    try:
        # Принудительно выгружает OLE-данные из памяти
        ctypes.windll.ole32.OleFlushClipboard()
    except Exception:
        pass

    # Циклически записываем 25 пустых пробелов с паузой 5 мс,
    # чтобы полностью перетереть стек последних элементов в истории Win+V
    for _ in range(25):
        write_clipboard_text(" ")
        time.sleep(0.005)

    wipe_clipboard()  # В финале оставляем буфер абсолютно пустым

class GhostTimer:
    """
    Таймер самоуничтожения. Если пользователь скопировал пароль или карту,
    таймер запускает обратный отсчёт (45 секунд) и затем стирает буфер.
    """
    def __init__(self):
        self._timer: threading.Timer = None  # type: ignore  # Ссылка на объект фонового таймера
        self._arm_time = 0.0                                 # Время запуска таймера
        self._seconds = 45                                   # Сколько секунд отсчитывать

    def arm(self, seconds: int, callback):
        """Взводит таймер на указанное количество секунд и запускает фоновый поток."""
        self.disarm()  # Если старый таймер ещё тикал, отменяем его
        self._seconds = seconds
        self._arm_time = time.time()
        # threading.Timer вызывает функцию callback ровно через seconds секунд
        self._timer = threading.Timer(seconds, callback)
        self._timer.daemon = True  # Фоновый поток: не блокирует закрытие программы
        self._timer.start()

    def disarm(self):
        """Останавливает и сбрасывает таймер."""
        if self._timer:
            self._timer.cancel()
            self._timer = None  # type: ignore
        self._arm_time = 0.0

    def is_armed(self) -> bool:
        """Проверяет, тикает ли сейчас таймер."""
        return self._timer is not None and self._timer.is_alive()

    def remaining_seconds(self) -> int:
        """Возвращает количество секунд, оставшихся до срабатывания."""
        if not self.is_armed():
            return 0
        elapsed = time.time() - self._arm_time
        return max(0, int(self._seconds - elapsed))

# Глобальный экземпляр таймера
ghost_timer = GhostTimer()
