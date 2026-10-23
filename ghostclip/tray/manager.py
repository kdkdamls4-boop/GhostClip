"""
TrayManager — связывает вместе невидимое окно, иконку в трее, меню и консоль.
Создаёт окно сообщений Win32 и обрабатывает клики по иконке.
"""

import os
import threading
import ctypes
from ctypes import wintypes
from typing import Callable, Optional

from ..config import config
from .win32_api import user32, kernel32, WNDPROC, WNDCLASSW, NOTIFYICONDATAW
from .win32_constants import (
    WM_TRAYICON, WM_LBUTTONDBLCLK, WM_RBUTTONUP, WM_CONTEXTMENU, WM_DESTROY,
)
from .console import ConsoleWindow
from . import icon
from .menu import (
    ID_TRAY_TOGGLE_CONSOLE, ID_TRAY_CLEAR_CLIPBOARD, ID_TRAY_PANIC, ID_TRAY_EXIT,
    build_menu_items, show_popup_menu, option_id_from_command,
)


class TrayManager:
    """Управляет иконкой в системном трее, ПКМ-меню и сворачиванием консоли в трей."""

    def __init__(
        self,
        on_clear_clipboard: Callable[[], None],
        on_panic: Callable[[], None],
        on_toggle_option: Callable[[int], None],
        on_exit: Callable[[], None],
    ):
        self.on_clear_clipboard = on_clear_clipboard
        self.on_panic = on_panic
        self.on_toggle_option = on_toggle_option
        self.on_exit = on_exit

        self._hwnd: Optional[int] = None
        self._nid: Optional[NOTIFYICONDATAW] = None
        self._console = ConsoleWindow()
        self._wnd_proc_ref = WNDPROC(self._wnd_proc)  # ссылку храним, иначе её съест сборщик мусора

        # Отключаем принудительное убийство процесса крестиком [X], чтобы сворачивать в трей
        self._console.disable_close_button()

    # ─── Консоль ────────────────────────────────────────────────────

    def hide_console_to_tray(self):
        """Скрывает окно консоли в системный трей."""
        if self._console.hide():
            self.show_balloon("GhostClip Shield в трее", "Защита продолжает работать в фоне. Нажмите ПКМ по иконке для управления.")

    def show_console_from_tray(self):
        """Возвращает окно консоли из трея на передний план."""
        self._console.show()

    def toggle_console(self):
        """Переключает видимость окна консоли."""
        _, is_shown = self._console.state()
        if is_shown:
            self.hide_console_to_tray()
        else:
            self.show_console_from_tray()

    def check_minimized_to_tray(self):
        """Если пользователь свернул окно консоли кнопкой [_], прячет его в трей."""
        if self._console.was_minimized():
            self.hide_console_to_tray()

    # ─── Иконка ─────────────────────────────────────────────────────

    def show_balloon(self, title: str, text: str):
        """Показывает всплывающее уведомление из системного трея."""
        if not self._nid or not self._hwnd:
            return
        icon.show_balloon(self._nid, title, text)

    def remove_icon(self):
        if self._nid:
            icon.delete_tray_icon(self._nid)
            self._nid = None

    # ─── Меню ───────────────────────────────────────────────────────

    def _show_context_menu(self):
        """Отрисовывает нативное контекстное меню Windows по правому клику (ПКМ) в трее."""
        _, is_shown = self._console.state()
        items = build_menu_items(is_shown, config.get_status_dict())
        cmd = show_popup_menu(self._hwnd, items)

        if cmd == ID_TRAY_TOGGLE_CONSOLE:
            self.toggle_console()
        elif cmd == ID_TRAY_CLEAR_CLIPBOARD:
            self.on_clear_clipboard()
        elif cmd == ID_TRAY_PANIC:
            self.on_panic()
        elif cmd == ID_TRAY_EXIT:
            self.remove_icon()
            self.on_exit()
        else:
            opt_id = option_id_from_command(cmd)
            if opt_id is not None:
                self.on_toggle_option(opt_id)

    # ─── Окно сообщений Win32 ───────────────────────────────────────

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_LBUTTONDBLCLK:
                self.show_console_from_tray()
                return 0
            elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_context_menu()
                return 0
        elif msg == WM_DESTROY:
            self.remove_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def start(self):
        """Запускает поток системного трея Windows."""
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _create_message_window(self) -> Optional[int]:
        """Регистрирует класс окна и создаёт невидимое окно для получения сообщений."""
        hinst = kernel32.GetModuleHandleW(None)
        class_name = f"GhostClipTrayWnd_{os.getpid()}"

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        return user32.CreateWindowExW(
            0, class_name, "GhostClip Shield Tray", 0,
            0, 0, 0, 0, None, None, hinst, None,
        )

    def _run_loop(self):
        self._hwnd = self._create_message_window()
        if not self._hwnd:
            return

        self._nid = icon.add_tray_icon(self._hwnd, icon.load_shield_icon())

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
