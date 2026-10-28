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
    # КАК ЭТО РАБОТАЕТ (простыми словами):
    # 1. Скопировал пароль → main.py вызывает ghost_timer.arm(45, ...) («взвести»)
    # 2. В отдельном потоке начинается отсчёт 45, 44, 43...
    # 3. Скопировал обычный текст → disarm() («разрядить»), отсчёт останавливается
    # 4. Дошёл до 0 → буфер стирается

    def __init__(self):
        # Конструктор: задаём начальное состояние таймера.
        self._lock = threading.Lock()
        # Замок: отсчёт идёт в одном потоке, а main.py читает и меняет таймер из другого.

        self._epoch = 0
        # «Эпоха» — номер текущего запуска таймера. Зачем она нужна, см. в _countdown_loop.

        self._remaining = 0          # сколько секунд осталось
        self._armed = False          # взведён ли таймер сейчас
        self._desc = ""              # описание секрета ("OpenAI API Key")
        self._cancel_event = threading.Event()
        # Event — флажок между потоками. .set() поднять, .clear() опустить.
        # (В этом коде флажок поднимается и опускается, но нигде не проверяется.
        #  Остановку на деле обеспечивают _armed и _epoch.)

    def arm(self, seconds: int, desc: str, on_expire=None):
        # on_expire=None — необязательный параметр: ФУНКЦИЯ, которую вызвать,
        # когда время выйдет. main.py передаёт сюда lambda, которая пишет в лог.
        """Взводит таймер самоуничтожения."""
        with self._lock:
            self._epoch += 1
            # Увеличиваем номер запуска: 1, 2, 3...
            current_epoch = self._epoch
            self._remaining = seconds
            self._armed = True
            self._desc = desc
            self._on_expire = on_expire
            self._cancel_event.clear()

        # Запускаем отсчет в фоновом потоке
        threading.Thread(
            target=self._countdown_loop,
            # Какую функцию выполнять в новом потоке.
            # БЕЗ скобок: передаём саму функцию, а не вызываем её.
            args=(current_epoch, seconds),
            # Аргументы для неё. (x, y) — кортеж.
            daemon=True,
            # Поток-«демон»: умрёт сам, когда закроется программа.
        ).start()
        # .start() — запустить поток. После этого arm() сразу возвращается,
        # а отсчёт идёт параллельно, в фоне.

    def disarm(self):
        """Останавливает таймер (например, если скопирован безопасный текст)."""
        with self._lock:
            self._armed = False
            # Поток отсчёта увидит это на следующей секунде и завершится сам.
            self._cancel_event.set()

    def is_armed(self) -> bool:
        with self._lock:
            return self._armed

    def remaining_seconds(self) -> int:
        with self._lock:
            return self._remaining

    def _countdown_loop(self, epoch: int, total_seconds: int):
        # _ в начале имени — внутренний метод, снаружи его не вызывают.
        # Этот код работает в ОТДЕЛЬНОМ потоке.

        for sec in range(total_seconds, 0, -1):
            # range(45, 0, -1) → 45, 44, 43, ... 1 (от 45 до 0, НЕ включая 0, шаг -1)
            with self._lock:
                if not self._armed or self._epoch != epoch:
                    # != значит «не равно».
                    # ЗАЧЕМ ЭПОХА: скопировал пароль 1 (эпоха 1, поток A),
                    # через 10 сек скопировал пароль 2 (эпоха 2, поток B).
                    # Поток A видит, что эпоха уже 2, а не его 1, и тихо завершается.
                    # Без этой проверки два потока стирали бы буфер в разное время.
                    return
                self._remaining = sec

            time.sleep(1.0)
            # Спим 1 секунду. ВАЖНО: спим ВНЕ замка,
            # иначе остальные потоки ждали бы целую секунду.

        # Цикл закончился, значит время вышло. Проверяем ещё раз, не отменили ли таймер.
        with self._lock:
            if not self._armed or self._epoch != epoch:
                return
            self._armed = False

        # ВРЕМЯ ВЫШЛО: Уничтожаем данные в буфере и истории Win+V!
        wipe_clipboard()
        if config.wipe_win_v:
            # Если тумблер [5] включён, чистим ещё и историю Win+V.
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
            # getattr(объект, "имя", по_умолчанию) — безопасно достать атрибут.
            # Если такого атрибута нет, вернётся None, и программа не упадёт.
            self._on_expire(msg)
            # Вызываем функцию, которую передали в arm(). Это callback.
        else:
            print(f"\n{msg}")


# Глобальный синглтон таймера
ghost_timer = GhostTimer()
# «Синглтон» — объект, который существует в программе в ОДНОМ экземпляре.
# Все файлы импортируют именно этот ghost_timer.
