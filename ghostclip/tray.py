"""
Модуль системного трея Windows (System Tray Icon) через чистый Win32 API (ctypes).
Создает иконку щита возле часов, обрабатывает ПКМ-меню и управляет скрытием/открытием консоли.
"""

import os
import sys
import threading
import ctypes
from ctypes import wintypes
from typing import Callable, Optional

from .config import config

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# Константы Win32 для окна, меню и трея
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20

WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

IDI_SHIELD = 32518
IDI_APPLICATION = 32512

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9

SC_CLOSE = 0xF060
MF_BYCOMMAND = 0x00000000

# Идентификаторы команд контекстного меню трея (ПКМ)
ID_TRAY_TOGGLE_CONSOLE = 1001
ID_TRAY_CLEAR_CLIPBOARD = 1002
ID_TRAY_PANIC = 1003
ID_TRAY_EXIT = 1004
ID_TRAY_OPT_BASE = 1010  # 1011..1016 — переключатели функций [1-6]

# Настройка типов аргументов для 64-битной Windows
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetConsoleWindow.argtypes = []
kernel32.GetConsoleWindow.restype = wintypes.HWND

user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, wintypes.HWND, wintypes.LPVOID,
]
user32.TrackPopupMenu.restype = wintypes.BOOL
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.GetSystemMenu.restype = wintypes.HMENU
user32.DeleteMenu.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
user32.DeleteMenu.restype = wintypes.BOOL


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


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
        self._console_hwnd: int = self._detect_console_hwnd()
        self._console_visible: bool = True
        self._wnd_proc_ref = WNDPROC(self._wnd_proc)

        # Отключаем принудительное убийство процесса крестиком [X], чтобы сворачивать в трей
        self._protect_console_close()

    def _detect_console_hwnd(self) -> int:
        hwnd = kernel32.GetConsoleWindow()
        if hwnd and user32.IsWindowVisible(hwnd):
            return hwnd
        fg = user32.GetForegroundWindow()
        return fg or hwnd or 0

    def _protect_console_close(self):
        """Отключает системную кнопку [X] у окна консоли, чтобы окно сворачивалось в трей, а не убивало процесс."""
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            hmenu = user32.GetSystemMenu(hwnd, False)
            if hmenu:
                user32.DeleteMenu(hmenu, SC_CLOSE, MF_BYCOMMAND)

    def hide_console_to_tray(self):
        """Скрывает окно консоли в системный трей."""
        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        if hwnd:
            user32.ShowWindow(hwnd, SW_HIDE)
            self._console_visible = False
            self.show_balloon("GhostClip Shield в трее", "Защита продолжает работать в фоне. Нажмите ПКМ по иконке для управления.")

    def show_console_from_tray(self):
        """Возвращает окно консоли из трея на передний план."""
        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        if hwnd:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetForegroundWindow(hwnd)
            self._console_visible = True

    def toggle_console(self):
        """Переключает видимость окна консоли."""
        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        if hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            self.hide_console_to_tray()
        else:
            self.show_console_from_tray()

    def check_minimized_to_tray(self):
        """Если пользователь свернул окно консоли кнопкой [_], прячет его в трей."""
        hwnd = kernel32.GetConsoleWindow()
        if hwnd and self._console_visible and user32.IsIconic(hwnd):
            self.hide_console_to_tray()

    def show_balloon(self, title: str, text: str):
        """Показывает всплывающее уведомление из системного трея."""
        if not self._nid or not self._hwnd:
            return
        self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
        self._nid.szInfoTitle = title[:63]
        self._nid.szInfo = text[:255]
        self._nid.dwInfoFlags = 0x01  # NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def _show_context_menu(self):
        """Отрисовывает нативное контекстное меню Windows по правому клику (ПКМ) в трее."""
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return

        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        is_vis = bool(hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd))
        console_label = "Скрыть консоль в трей" if is_vis else "Управление (Открыть консоль)"

        # Основные действия
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_TOGGLE_CONSOLE, console_label)
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_CLEAR_CLIPBOARD, "Очистить буфер обмена")
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_PANIC, "ПАНИКА (Стереть буфер + Win+V)")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)

        # Переключатели [1-6] прямо в меню трея с галочками
        for opt_id, (desc, enabled) in config.get_status_dict().items():
            flag = MF_STRING | (MF_CHECKED if enabled else MF_UNCHECKED)
            user32.AppendMenuW(hmenu, flag, ID_TRAY_OPT_BASE + opt_id, f"[{opt_id}] {desc}")

        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_EXIT, "Полный выход")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self._hwnd)

        cmd = user32.TrackPopupMenu(
            hmenu,
            TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            pt.x,
            pt.y,
            0,
            self._hwnd,
            None,
        )
        user32.DestroyMenu(hmenu)

        if cmd == ID_TRAY_TOGGLE_CONSOLE:
            self.toggle_console()
        elif cmd == ID_TRAY_CLEAR_CLIPBOARD:
            self.on_clear_clipboard()
        elif cmd == ID_TRAY_PANIC:
            self.on_panic()
        elif cmd == ID_TRAY_EXIT:
            self.remove_icon()
            self.on_exit()
        elif ID_TRAY_OPT_BASE + 1 <= cmd <= ID_TRAY_OPT_BASE + 6:
            self.on_toggle_option(cmd - ID_TRAY_OPT_BASE)

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

    def remove_icon(self):
        if self._nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            self._nid = None

    def start(self):
        """Запускает поток системного трея Windows."""
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        hinst = kernel32.GetModuleHandleW(None)
        class_name = f"GhostClipTrayWnd_{os.getpid()}"

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        self._hwnd = user32.CreateWindowExW(
            0, class_name, "GhostClip Shield Tray", 0,
            0, 0, 0, 0, None, None, hinst, None,
        )
        if not self._hwnd:
            return

        hicon = user32.LoadIconW(None, ctypes.cast(IDI_SHIELD, wintypes.LPCWSTR))
        if not hicon:
            hicon = user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = hicon
        nid.szTip = "GhostClip Shield — Защита буфера (ПКМ — меню)"
        self._nid = nid

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
