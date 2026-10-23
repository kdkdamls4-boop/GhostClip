"""Контекстное меню трея (ПКМ): описание пунктов кортежами и показ меню."""

import ctypes
from ctypes import wintypes
from typing import Dict, List, Optional, Tuple

from .win32_api import user32
from .win32_constants import (
    MF_STRING, MF_SEPARATOR, MF_CHECKED, MF_UNCHECKED,
    TPM_LEFTALIGN, TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY,
)

# Идентификаторы команд меню
ID_TRAY_TOGGLE_CONSOLE = 1001
ID_TRAY_CLEAR_CLIPBOARD = 1002
ID_TRAY_PANIC = 1003
ID_TRAY_EXIT = 1004
ID_TRAY_OPT_BASE = 1010  # 1011..1016 — переключатели функций [1-6]

# Один пункт меню — кортеж: (флаги, id_команды, текст)
MenuItem = Tuple[int, int, Optional[str]]
# Статусы из config.get_status_dict(): {номер: (название, включено)}
StatusDict = Dict[int, Tuple[str, bool]]

SEPARATOR: MenuItem = (MF_SEPARATOR, 0, None)


def build_menu_items(console_shown: bool, statuses: StatusDict) -> List[MenuItem]:
    """Собирает список пунктов меню в виде кортежей."""
    console_label = "Скрыть консоль в трей" if console_shown else "Управление (Открыть консоль)"

    items: List[MenuItem] = [
        (MF_STRING, ID_TRAY_TOGGLE_CONSOLE, console_label),
        SEPARATOR,
        (MF_STRING, ID_TRAY_CLEAR_CLIPBOARD, "Очистить буфер обмена"),
        (MF_STRING, ID_TRAY_PANIC, "ПАНИКА (Стереть буфер + Win+V)"),
        SEPARATOR,
    ]

    # Переключатели [1-6] с галочками
    for opt_id, (desc, enabled) in statuses.items():
        flags = MF_STRING | (MF_CHECKED if enabled else MF_UNCHECKED)
        items.append((flags, ID_TRAY_OPT_BASE + opt_id, f"[{opt_id}] {desc}"))

    items.append(SEPARATOR)
    items.append((MF_STRING, ID_TRAY_EXIT, "Полный выход"))
    return items


def get_cursor_pos() -> Tuple[int, int]:
    """Текущие координаты курсора мыши (x, y)."""
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def show_popup_menu(owner_hwnd: int, items: List[MenuItem]) -> int:
    """
    Показывает меню у курсора и ждёт выбора.
    Возвращает id выбранной команды или 0, если кликнули мимо.
    """
    hmenu = user32.CreatePopupMenu()
    if not hmenu:
        return 0

    for flags, cmd_id, label in items:
        user32.AppendMenuW(hmenu, flags, cmd_id, label)

    x, y = get_cursor_pos()
    user32.SetForegroundWindow(owner_hwnd)  # иначе меню не закроется кликом мимо

    cmd = user32.TrackPopupMenu(
        hmenu,
        TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
        x,
        y,
        0,
        owner_hwnd,
        None,
    )
    user32.DestroyMenu(hmenu)
    return cmd


def option_id_from_command(cmd: int) -> Optional[int]:
    """Если cmd — переключатель [1-6], возвращает его номер, иначе None."""
    if ID_TRAY_OPT_BASE + 1 <= cmd <= ID_TRAY_OPT_BASE + 6:
        return cmd - ID_TRAY_OPT_BASE
    return None
