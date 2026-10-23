"""Модуль зачистки буфера и системного журнала Win+V."""

import subprocess
# subprocess — запуск ДРУГИХ программ из Python (здесь запускаем PowerShell).

from typing import Tuple

from .clipboard import wipe_clipboard, write_clipboard_text
# Берём из соседнего файла clipboard.py две функции.

CREATE_NO_WINDOW = 0x08000000
# Флаг Windows: «запусти программу БЕЗ окна».
# Без него при каждой очистке на долю секунды мигало бы синее окно PowerShell.

OVERWRITE_DUMMY_TEXT = "[GHOSTCLIP: СЕКРЕТ ЗАТЕРТ. ВСЕ ЦИФРЫ УНИЧТОЖЕНЫ]"
# Текст-заглушка. Им перезаписываем секрет перед удалением.


def wipe_win_v_history() -> bool:
    """Бесшумно очищает историю Win+V через Windows Runtime API."""

    cmd = "[Windows.ApplicationModel.DataTransfer.Clipboard,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]::ClearHistory()"
    # Это НЕ Python, а команда для PowerShell. Дословно она значит:
    # «возьми системный класс Windows Clipboard и вызови у него ClearHistory()».
    # Из Python напрямую эту функцию вызвать сложно, через PowerShell проще.

    try:
        res = subprocess.run(
            # subprocess.run([...]) — запустить программу и ДОЖДАТЬСЯ, пока она закончит.
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            # Список = программа и её аргументы:
            #   -NoProfile      не загружать пользовательские настройки (быстрее)
            #   -NonInteractive ничего не спрашивать у пользователя
            #   -Command cmd    выполнить нашу команду
            capture_output=True,
            # Перехватить вывод PowerShell, чтобы он не мусорил в нашей консоли.
            timeout=5,
            # Если PowerShell не ответил за 5 сек, прервать его.
            creationflags=CREATE_NO_WINDOW,
            # Без окна.
        )
        return res.returncode == 0
        # returncode — «код выхода» программы. 0 = всё хорошо, другое число = ошибка.
        # Выражение `== 0` само по себе даёт True или False.
    except Exception:
        # PowerShell не найден, тайм-аут и т.п.
        return False


def shred_clipboard(dummy_text: str = OVERWRITE_DUMMY_TEXT) -> Tuple[bool, bool]:
    # «shred» = измельчить (как шредер для бумаги).
    # Возвращает пару: (буфер очищен?, история очищена?).
    """
    Затирает секретные данные текстом, чтобы не осталось никаких цифр,
    а затем зачищает память буфера и журнал Win+V.
    """
    write_clipboard_text(dummy_text)
    # Шаг 1: записываем заглушку поверх секрета.
    clip_ok = wipe_clipboard()
    # Шаг 2: очищаем буфер полностью.
    hist_ok = wipe_win_v_history()
    # Шаг 3: стираем историю Win+V.
    return clip_ok, hist_ok


def panic_wipe() -> Tuple[bool, bool]:
    """Экстренно затирает буфер обмена и историю Win+V."""
    return shred_clipboard()
    # Просто вызывает shred_clipboard. Отдельное имя нужно для понятности:
    # в main.py «panic_wipe» читается сразу как «кнопка паники».
