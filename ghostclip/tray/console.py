"""Управление окном консоли: скрытие в трей, показ, защита от закрытия крестиком."""

from typing import Tuple

from .win32_api import user32, kernel32
from .win32_constants import SC_CLOSE, MF_BYCOMMAND, SW_HIDE, SW_RESTORE, SW_SHOW


class ConsoleWindow:
    """Обёртка над окном консоли, в которой работает GhostClip."""

    def __init__(self):
        self._fallback_hwnd: int = self._detect_hwnd()
        self.visible: bool = True

    @staticmethod
    def _detect_hwnd() -> int:
        hwnd = kernel32.GetConsoleWindow()
        if hwnd and user32.IsWindowVisible(hwnd):
            return hwnd
        fg = user32.GetForegroundWindow()
        return fg or hwnd or 0

    def hwnd(self) -> int:
        """Актуальный дескриптор окна консоли (или запасной, найденный при старте)."""
        return kernel32.GetConsoleWindow() or self._fallback_hwnd

    def state(self) -> Tuple[int, bool]:
        """Возвращает кортеж (hwnd, видна_ли_консоль_на_экране)."""
        hwnd = self.hwnd()
        is_shown = bool(hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd))
        return hwnd, is_shown

    def disable_close_button(self) -> None:
        """Отключает кнопку [X], чтобы крестик не убивал процесс."""
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            hmenu = user32.GetSystemMenu(hwnd, False)
            if hmenu:
                user32.DeleteMenu(hmenu, SC_CLOSE, MF_BYCOMMAND)

    def hide(self) -> bool:
        """Прячет консоль. Возвращает True, если окно было найдено и скрыто."""
        hwnd = self.hwnd()
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_HIDE)
        self.visible = False
        return True

    def show(self) -> bool:
        """Разворачивает консоль и выводит её на передний план."""
        hwnd = self.hwnd()
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetForegroundWindow(hwnd)
        self.visible = True
        return True

    def was_minimized(self) -> bool:
        """True, если пользователь свернул видимую консоль кнопкой [_]."""
        hwnd = kernel32.GetConsoleWindow()
        return bool(hwnd and self.visible and user32.IsIconic(hwnd))
