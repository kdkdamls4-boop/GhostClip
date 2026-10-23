"""
Модуль конфигурации и переключения функций GhostClip Shield.
Хранит флаги включения/выключения компонентов в потокобезопасном виде.
"""
# ↑ Это docstring (строка документации). Описывает, что делает весь файл.
#   Python её не выполняет, она для людей.

# ═══════════════════════════════════════════════════════════════════
#  ИМПОРТЫ — подключаем чужой готовый код
# ═══════════════════════════════════════════════════════════════════

import threading
# threading — встроенный модуль Python для работы с ПОТОКАМИ
# (несколько дел одновременно). Нам отсюда нужен Lock (замок).

from dataclasses import dataclass
# dataclass — «декоратор», который автоматически дописывает к классу
# служебный код (красивый вывод через print, сравнение объектов и т.д.).


# ═══════════════════════════════════════════════════════════════════
#  КЛАСС НАСТРОЕК
# ═══════════════════════════════════════════════════════════════════

@dataclass
# ↑ Декоратор: «обработай класс ниже как dataclass».
class ShieldConfig:
    # class — объявляем КЛАСС (чертёж). ShieldConfig — его имя.
    # Потом по этому чертежу создаётся один объект config (в самом низу файла).

    """Конфигурация защитных функций щита."""

    # Ниже — ПОЛЯ класса в формате:  имя: тип = значение_по_умолчанию
    # bool = True/False (вкл/выкл), int = целое число.
    clean_urls: bool = True           # Очистка трекинг-меток в ссылках (utm, fbclid, si)
    clean_zero_width: bool = True     # Удаление невидимых знаков нулевой ширины
    detect_secrets: bool = True       # Поиск паролей, токенов API и банковских карт
    ghost_timer_enabled: bool = True  # Таймер самоуничтожения секретов (45 сек)
    wipe_win_v: bool = True           # Зачистка истории Win+V при уничтожении
    audit_logging: bool = True        # Ведение журнала в clipboard_access.log
    timer_seconds: int = 45           # Время жизни секрета в буфере (сек)

    def __init__(self):
        # __init__ — «конструктор». Запускается АВТОМАТИЧЕСКИ,
        # когда пишут ShieldConfig() и создаётся новый объект.
        #
        # self — это «я сам», конкретный объект настроек.
        # self.clean_urls = True  →  «у меня поле clean_urls теперь True».
        #
        # (Примечание: раз здесь написан свой __init__, @dataclass свой не создаёт.
        #  Поэтому значения продублированы тут вручную.)
        self.clean_urls = True
        self.clean_zero_width = True
        self.detect_secrets = True
        self.ghost_timer_enabled = True
        self.wipe_win_v = True
        self.audit_logging = True
        self.timer_seconds = 45

        self._lock = threading.Lock()
        # Замок. Настройки могут менять одновременно консоль (клавиши 1-6)
        # и меню в трее. Замок не даёт им сделать это в один и тот же момент.
        # Подчёркивание _ в начале имени значит «внутреннее, снаружи не трогать».

    def toggle(self, option_id: int) -> tuple[str, bool]:
        # def — объявляем МЕТОД (функцию внутри класса).
        # option_id: int       — принимает целое число (номер функции 1-6)
        # -> tuple[str, bool]  — возвращает пару: (название, новое значение)
        """
        Переключает функцию по её порядковому номеру (1-6).
        Возвращает (название_функции, новое_значение).
        """
        with self._lock:
            # with self._lock: — «захвати замок». Пока мы внутри этого блока,
            # другой поток ждёт. На выходе из блока замок отпускается сам.

            if option_id == 1:
                # == это СРАВНЕНИЕ («равно ли?»), а = это ПРИСВАИВАНИЕ.
                self.clean_urls = not self.clean_urls
                # not превращает True в False и наоборот. Это и есть «переключить».
                return ("Чистка ссылок от трекеров", self.clean_urls)
                # return — вернуть результат и сразу выйти из метода.
            elif option_id == 2:
                # elif = «иначе, если...»
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
                # else = «во всех остальных случаях».
                raise ValueError(f"Неизвестный номер функции: {option_id}")
                # raise — САМИ выбрасываем ошибку. ValueError = «неправильное значение».
                # f"...{option_id}" — f-строка: вместо {option_id} подставится число.

    def get_status_dict(self) -> dict:
        """Возвращает текущие статусы всех функций."""
        with self._lock:
            return {
                # dict (словарь) — пары «ключ: значение» в фигурных скобках.
                # Ключ — номер (1..6), значение — кортеж (название, вкл/выкл).
                # Пример использования: statuses[3][1] → включена ли детекция секретов.
                1: ("Чистка ссылок (utm, fbclid, si)", self.clean_urls),
                2: ("Удаление невидимых символов", self.clean_zero_width),
                3: ("Детекция секретов и карт", self.detect_secrets),
                4: ("Таймер самоуничтожения (45с)", self.ghost_timer_enabled),
                5: ("Зачистка истории Win+V", self.wipe_win_v),
                6: ("Журнал clipboard_access.log", self.audit_logging),
            }


# ═══════════════════════════════════════════════════════════════════
#  ГЛОБАЛЬНЫЙ ОБЪЕКТ
# ═══════════════════════════════════════════════════════════════════

# Глобальный экземпляр настроек
config = ShieldConfig()
# Создаём ОДИН объект по чертежу. Все остальные файлы делают
# `from .config import config` и получают ЭТОТ ЖЕ объект.
# Поэтому если поменять настройку в одном месте, она поменяется везде.
