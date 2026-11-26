"""
explained/ghostclip/tray.py
Системный трей Windows (Win32 API): иконка щита, индикация таймера, Ctrl+Shift+X и ПКМ-меню.
"""

import ctypes  # ctypes — прямые вызовы системных библиотек Windows
import os  # os.getpid — уникальный ID процесса для имени класса окна
import threading  # threading — фоновый поток обработки сообщений Windows и замки
from ctypes import wintypes  # Стандартные типы Windows (HWND, UINT, POINT и т.д.)

from .config import config

# Загружаем базовые системные библиотеки Windows (DLL) через ctypes:
# user32.dll   — отвечает за пользовательский интерфейс: окна, меню, горячие клавиши и клики
user32 = ctypes.windll.user32

# kernel32.dll — ядро Windows: управление памятью, процессами, потоками и дескриптором консоли
kernel32 = ctypes.windll.kernel32

# shell32.dll  — системная оболочка Windows: проводник, панель задач и иконки в трее возле часов
shell32 = ctypes.windll.shell32

# Коды оконных сообщений Windows (WM = Window Message)
WM_DESTROY = 0x0002  # Окно закрывается
WM_HOTKEY = 0x0312  # Сработала зарегистрированная глобальная горячая клавиша
WM_TRAYICON = 0x8000 + 1  # Наше пользовательское событие от иконки в трее
WM_LBUTTONDBLCLK = 0x0203  # Двойной клик левой кнопкой мыши
WM_RBUTTONUP = 0x0205  # Отпустили правую кнопку мыши
WM_CONTEXTMENU = 0x007B  # Открытие контекстного меню

# Параметры глобальной горячей клавиши Ctrl+Shift+X
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_X = 0x58
HOTKEY_PANIC_ID = 1

# Флаги структуры NOTIFYICONDATAW (какие её поля заполнены)
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0x00, 0x01, 0x02
NIIF_INFO, NIIF_WARNING = 1, 2
SW_HIDE, SW_SHOW, SW_RESTORE = 0, 5, 9
SC_CLOSE, MF_BYCOMMAND = 0xF060, 0x0000
MF_CHECKED, MF_SEPARATOR, TPM_RETURNCMD = 0x0008, 0x0800, 0x0100
IDI_APPLICATION, IDI_WARNING, IDI_SHIELD = 32512, 32515, 32518

# На 64-битной Windows результат оконной процедуры имеет размер указателя (c_ssize_t)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class NOTIFYICONDATAW(ctypes.Structure):
    """Си-структура Windows, описывающая иконку, подсказку и всплывающее уведомление в трее."""

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
    ]


class WNDCLASSW(ctypes.Structure):
    """Си-структура Windows для регистрации скрытого окна, принимающего события трея и хоткеев."""

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


# Явно задаём 64-битные типы аргументов и возвращаемых значений для всех функций Win32 API
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetConsoleWindow.argtypes = []
kernel32.GetConsoleWindow.restype = wintypes.HWND

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
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
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.LPVOID,
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
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostQuitMessage.restype = None
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL


class TrayManager:
    """Управляет иконкой в трее Windows, индикацией таймера, глобальной горячей клавишей и меню."""

    _DEFAULT_TIP = "GhostClip Shield (ПКМ — меню | Ctrl+Shift+X — паника)"

    def __init__(self, on_clear, on_panic, on_toggle, on_exit):
        self.on_clear = on_clear
        self.on_panic = on_panic
        self.on_toggle = on_toggle
        self.on_exit = on_exit
        self.window_handle = None
        self.notify_icon_data: NOTIFYICONDATAW | None = None
        self.hotkey_registered = False
        self._tray_lock = threading.Lock()
        self._ready_event = threading.Event()
        self._shield_icon = None
        self._warning_icon = None
        self._last_indicator_state: tuple[str, int] | None = None
        self._console_window_handle = self._detect_console_window()
        self._console_visible = True
        # Важно сохранить ссылку на WNDPROC в self, чтобы сборщик мусора Python не удалил её
        self._window_proc_reference = WNDPROC(self._window_procedure)
        self._disable_console_close_button()

    @staticmethod
    def _detect_console_window():
        """Находит системный дескриптор (HWND) окна консоли для скрытия/восстановления."""
        console_hwnd = kernel32.GetConsoleWindow()
        if console_hwnd and user32.IsWindowVisible(console_hwnd):
            return console_hwnd
        return user32.GetForegroundWindow() or console_hwnd

    def _disable_console_close_button(self) -> None:
        """Удаляет пункт закрытия [X] из системного меню окна консоли для защиты от случайного выхода."""
        console_hwnd = kernel32.GetConsoleWindow()
        if console_hwnd:
            system_menu = user32.GetSystemMenu(console_hwnd, False)
            if system_menu:
                user32.DeleteMenu(system_menu, SC_CLOSE, MF_BYCOMMAND)

    def _unregister_hotkey_locked(self) -> None:
        if self.hotkey_registered and self.window_handle:
            user32.UnregisterHotKey(self.window_handle, HOTKEY_PANIC_ID)
            self.hotkey_registered = False

    def _window_procedure(self, window_handle, message_id, wparam, lparam):
        """Обработчик сообщений Windows: клики по иконке трея, Ctrl+Shift+X и закрытие окна."""
        if message_id == WM_TRAYICON:
            if lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_context_menu()
            elif lparam == WM_LBUTTONDBLCLK:
                self.toggle_console()
            return 0
        if message_id == WM_HOTKEY and wparam == HOTKEY_PANIC_ID:
            # Запускаем панику в отдельном потоке, чтобы цикл сообщений трея не замер ни на миллисекунду
            threading.Thread(target=self.on_panic, daemon=True).start()
            return 0
        if message_id == WM_DESTROY:
            self.remove_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(window_handle, message_id, wparam, lparam)

    def _build_menu_items(self, is_console_visible: bool) -> list[tuple]:
        """Собирает список пунктов контекстного меню трея (id, подпись, отмечен_ли_галочкой)."""
        toggle_label = "Скрыть консоль в трей" if is_console_visible else "Открыть консоль GhostClip"
        items: list[tuple] = [
            (10, toggle_label, False),
            (0, "---", False),
            (20, "Очистить буфер обмена", False),
            (30, "ПАНИКА! (Стереть всё и Win+V) [Ctrl+Shift+X]", False),
            (0, "---", False),
        ]
        for option_id, (option_name, is_enabled) in config.get_status_dict().items():
            badge = "ВКЛ" if is_enabled else "ВЫКЛ"
            items.append((100 + option_id, f"[{badge}] {option_name}", is_enabled))
        items.extend([(0, "---", False), (99, "Выход", False)])
        return items

    def _dispatch_menu_command(self, selected_command: int) -> None:
        """Вызывает нужный обработчик по ID выбранного пункта меню трея."""
        actions = {20: self.on_clear, 30: self.on_panic, 99: self.on_exit}
        option_count = len(config.get_status_dict())
        if selected_command == 10:
            self.toggle_console()
        elif selected_command in actions:
            actions[selected_command]()
        elif 101 <= selected_command <= 100 + option_count:
            self.on_toggle(selected_command - 100)

    def _show_context_menu(self) -> None:
        """Создаёт и показывает всплывающее ПКМ-меню рядом с курсором мыши."""
        menu_handle = user32.CreatePopupMenu()
        is_visible = bool(
            self._console_window_handle
            and user32.IsWindowVisible(self._console_window_handle)
            and not user32.IsIconic(self._console_window_handle)
        )
        for command_id, label, is_checked in self._build_menu_items(is_visible):
            if label == "---":
                user32.AppendMenuW(menu_handle, MF_SEPARATOR, 0, None)
            else:
                flags = MF_CHECKED if is_checked else 0
                user32.AppendMenuW(menu_handle, flags, command_id, label)

        cursor_point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(cursor_point))
        user32.SetForegroundWindow(self.window_handle)
        selected_command = user32.TrackPopupMenu(
            menu_handle, TPM_RETURNCMD, cursor_point.x, cursor_point.y, 0, self.window_handle, None
        )
        user32.DestroyMenu(menu_handle)
        self._dispatch_menu_command(selected_command)

    def is_console_visible(self) -> bool:
        """Возвращает True, если консоль видна пользователю (не спрятана в трей)."""
        return self._console_visible

    def hide_console_to_tray(self) -> None:
        """Прячет окно консоли с экрана и из панели задач в системный трей."""
        if not self._console_window_handle:
            return
        user32.ShowWindow(self._console_window_handle, SW_HIDE)
        self._console_visible = False
        self.show_balloon("GhostClip в трее", "Защита работает в фоне. Ctrl+Shift+X — мгновенная паника.")

    def show_console_from_tray(self) -> None:
        """Восстанавливает окно консоли из трея и выводит его на передний план."""
        if not self._console_window_handle:
            return
        user32.ShowWindow(self._console_window_handle, SW_RESTORE)
        user32.ShowWindow(self._console_window_handle, SW_SHOW)
        user32.SetForegroundWindow(self._console_window_handle)
        self._console_visible = True

    def toggle_console(self) -> None:
        """Переключает видимость консоли (при двойном клике по иконке трея)."""
        if not self._console_window_handle:
            return
        is_visible = bool(
            user32.IsWindowVisible(self._console_window_handle)
            and not user32.IsIconic(self._console_window_handle)
        )
        if is_visible:
            self.hide_console_to_tray()
        else:
            self.show_console_from_tray()

    def check_minimized_to_tray(self) -> None:
        """Автоматически убирает консоль в трей, если пользователь нажал системную кнопку [_]."""
        console_hwnd = kernel32.GetConsoleWindow() or self._console_window_handle
        if console_hwnd and self._console_visible and user32.IsIconic(console_hwnd):
            self.hide_console_to_tray()

    def update_timer_indicator(self, remaining_seconds: int) -> None:
        """Меняет иконку на предупреждающую и обновляет тултип трея, пока идёт таймер."""
        desired_state = ("armed", remaining_seconds) if remaining_seconds > 0 else ("idle", 0)
        with self._tray_lock:
            if not self.notify_icon_data or desired_state == self._last_indicator_state:
                return
            self._last_indicator_state = desired_state

            if remaining_seconds > 0:
                self.notify_icon_data.hIcon = self._warning_icon or self._shield_icon
                self.notify_icon_data.szTip = f"GhostClip: Секрет! Удаление через {remaining_seconds}с"[:127]
            else:
                self.notify_icon_data.hIcon = self._shield_icon
                self.notify_icon_data.szTip = self._DEFAULT_TIP[:127]

            self.notify_icon_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.notify_icon_data))

    def show_balloon(self, title: str, text: str, info_flags: int = NIIF_INFO) -> None:
        """Отправляет системе команду показать всплывающее уведомление возле часов."""
        with self._tray_lock:
            if not self.notify_icon_data:
                return
            self.notify_icon_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
            self.notify_icon_data.szInfoTitle = title[:63]
            self.notify_icon_data.szInfo = text[:255]
            self.notify_icon_data.dwInfoFlags = info_flags
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.notify_icon_data))

    def remove_icon(self) -> None:
        """Удаляет иконку щита из трея и снимает глобальную горячую клавишу Ctrl+Shift+X."""
        with self._tray_lock:
            self._unregister_hotkey_locked()
            if self.notify_icon_data:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.notify_icon_data))
                self.notify_icon_data = None

    def start(self) -> None:
        """Запускает фоновый поток с циклом сообщений Win32, иконкой щита и Ctrl+Shift+X."""

        def message_loop() -> None:
            class_name = f"GhostClipTray_{os.getpid()}"
            module_handle = kernel32.GetModuleHandleW(None)

            window_class = WNDCLASSW()
            window_class.lpfnWndProc = self._window_proc_reference
            window_class.lpszClassName = class_name
            window_class.hInstance = module_handle
            user32.RegisterClassW(ctypes.byref(window_class))

            self.window_handle = user32.CreateWindowExW(
                0, class_name, class_name, 0, 0, 0, 0, 0, None, None, module_handle, None
            )
            self._shield_icon = user32.LoadIconW(
                None, ctypes.cast(IDI_SHIELD, wintypes.LPCWSTR)
            ) or user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))
            self._warning_icon = (
                user32.LoadIconW(None, ctypes.cast(IDI_WARNING, wintypes.LPCWSTR)) or self._shield_icon
            )

            with self._tray_lock:
                # RegisterHotKey привязываем к тому же окну и потоку, где крутится GetMessageW
                self.hotkey_registered = bool(
                    self.window_handle
                    and user32.RegisterHotKey(
                        self.window_handle,
                        HOTKEY_PANIC_ID,
                        MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
                        VK_X,
                    )
                )
                self.notify_icon_data = NOTIFYICONDATAW()
                self.notify_icon_data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
                self.notify_icon_data.hWnd = self.window_handle
                self.notify_icon_data.uID = 1
                self.notify_icon_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
                self.notify_icon_data.uCallbackMessage = WM_TRAYICON
                self.notify_icon_data.hIcon = self._shield_icon
                self.notify_icon_data.szTip = self._DEFAULT_TIP[:127]
                self._last_indicator_state = ("idle", 0)
                shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.notify_icon_data))

            self._ready_event.set()

            window_message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(window_message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(window_message))
                user32.DispatchMessageW(ctypes.byref(window_message))

        threading.Thread(target=message_loop, daemon=True).start()
        self._ready_event.wait(timeout=1.0)
