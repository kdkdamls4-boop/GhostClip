"""
Модуль системного трея Windows (System Tray Icon) через чистый Win32 API (ctypes).
Создает иконку щита возле часов, обрабатывает ПКМ-меню и управляет скрытием/открытием консоли.
"""
# ═══════════════════════════════════════════════════════════════════
#  ⚠️ САМЫЙ СЛОЖНЫЙ ФАЙЛ ПРОЕКТА. Читай последним.
#
#  Здесь нет никакой «магии Python». Почти всё — это вызовы функций Windows
#  через ctypes. Если не понятна какая-то константа (например, WM_COMMAND),
#  не переживай: это просто номера, придуманные Microsoft. Их не запоминают,
#  а смотрят в документации.
#
#  ОБЩАЯ ИДЕЯ:
#  1. Windows общается с программами СООБЩЕНИЯМИ: «по иконке кликнули»,
#     «окно закрывают» и т.д.
#  2. Чтобы получать сообщения, нужно ОКНО. Мы создаём невидимое окно.
#  3. Добавляем иконку в трей и говорим Windows: «события иконки шли в это окно».
#  4. Функция _wnd_proc получает сообщения и решает, что делать.
# ═══════════════════════════════════════════════════════════════════

import os
import sys
import threading
import ctypes
from ctypes import wintypes
from typing import Callable, Optional
# Callable — подсказка типа «это функция».

from .config import config

user32 = ctypes.windll.user32     # окна, меню
shell32 = ctypes.windll.shell32   # трей (Shell_NotifyIconW)
kernel32 = ctypes.windll.kernel32 # консоль, модули

LRESULT = ctypes.c_ssize_t
# Тип результата, который возвращает обработчик сообщений окна (число размером с указатель).

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
# Описываем «форму» функции-обработчика, которую Windows будет вызывать:
# она возвращает LRESULT и принимает (окно, сообщение, параметр1, параметр2).
# Через WNDPROC обычную функцию Python можно отдать Windows.


# ═══════════════════════════════════════════════════════════════════
#  КОНСТАНТЫ WIN32 — номера из документации Microsoft
# ═══════════════════════════════════════════════════════════════════

# Константы Win32 для окна, меню и трея
# --- WM_ = Window Message (типы сообщений окну) ---
WM_DESTROY = 0x0002        # окно уничтожается
WM_COMMAND = 0x0111        # выбрана команда меню
WM_USER = 0x0400           # начиная с этого номера можно придумывать свои сообщения
WM_TRAYICON = WM_USER + 20 # наше собственное сообщение «что-то случилось с иконкой»

WM_LBUTTONDBLCLK = 0x0203  # двойной клик левой кнопкой
WM_RBUTTONUP = 0x0205      # отпустили правую кнопку
WM_CONTEXTMENU = 0x007B    # запрос контекстного меню

# --- NIM_ = Notify Icon Message (что сделать с иконкой в трее) ---
NIM_ADD = 0x00000000       # добавить
NIM_MODIFY = 0x00000001    # изменить
NIM_DELETE = 0x00000002    # удалить

# --- NIF_ = Notify Icon Flags (какие поля структуры заполнены) ---
# Флаги объединяют через | (побитовое ИЛИ): NIF_ICON | NIF_TIP = «и иконка, и подсказка».
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004       # всплывающая подсказка при наведении мыши
NIF_INFO = 0x00000010      # «пузырь»-уведомление

# --- Встроенные иконки Windows ---
IDI_SHIELD = 32518         # щит
IDI_APPLICATION = 32512    # стандартная иконка программы (запасной вариант)

# --- MF_ = Menu Flags (вид пунктов меню) ---
MF_STRING = 0x00000000     # обычный текстовый пункт
MF_SEPARATOR = 0x00000800  # горизонтальная линия-разделитель
MF_CHECKED = 0x00000008    # с галочкой
MF_UNCHECKED = 0x00000000  # без галочки
# --- TPM_ = Track Popup Menu (как показать всплывающее меню) ---
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100     # вернуть номер выбранного пункта вместо отправки сообщения
TPM_NONOTIFY = 0x0080

# --- SW_ = Show Window (что сделать с окном) ---
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9             # развернуть из свёрнутого состояния

SC_CLOSE = 0xF060          # системная команда «закрыть» (крестик [X])
MF_BYCOMMAND = 0x00000000

# Идентификаторы команд контекстного меню трея (ПКМ)
# Номера мы придумали сами. По ним потом узнаём, какой пункт выбрали.
ID_TRAY_TOGGLE_CONSOLE = 1001
ID_TRAY_CLEAR_CLIPBOARD = 1002
ID_TRAY_PANIC = 1003
ID_TRAY_EXIT = 1004
ID_TRAY_OPT_BASE = 1010  # 1011..1016 — переключатели функций [1-6]


# ═══════════════════════════════════════════════════════════════════
#  ТИПЫ АРГУМЕНТОВ ФУНКЦИЙ WINDOWS (для 64-бит, см. clipboard.py)
#  Это скучная, но обязательная настройка. Каждая пара строк говорит:
#  «функция X принимает вот такие типы и возвращает вот такой».
# ═══════════════════════════════════════════════════════════════════

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
# IsIconic = «окно свёрнуто?» (в старой терминологии Windows свёрнутое окно = «иконка»)
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
user32.GetSystemMenu.restype = wintypes.HMENU
user32.DeleteMenu.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
user32.DeleteMenu.restype = wintypes.BOOL


# ═══════════════════════════════════════════════════════════════════
#  СТРУКТУРЫ — «анкеты», которые Windows ждёт заполненными
#  ctypes.Structure описывает, как данные лежат в памяти.
#  _fields_ = список (имя_поля, тип). Порядок ВАЖЕН, он должен совпадать с Windows.
# ═══════════════════════════════════════════════════════════════════

class WNDCLASSW(ctypes.Structure):
    # «Класс окна» — шаблон, по которому Windows создаёт окна.
    # Самое важное поле здесь — lpfnWndProc, функция-обработчик сообщений.
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),        # ← наш обработчик сообщений
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR), # ← имя шаблона
    ]


class GUID(ctypes.Structure):
    # Уникальный 128-битный идентификатор. Здесь не используется, но обязан быть
    # в структуре NOTIFYICONDATAW, чтобы совпал её размер.
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
        # BYTE * 8 — массив из 8 байт.
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    # «Анкета» иконки в трее: какое окно, какая иконка, какая подсказка, текст уведомления.
    _fields_ = [
        ("cbSize", wintypes.DWORD),             # размер самой структуры (Windows так проверяет версию)
        ("hWnd", wintypes.HWND),                # окно, которое получит события иконки
        ("uID", wintypes.UINT),                 # номер иконки (у нас одна, поэтому 1)
        ("uFlags", wintypes.UINT),              # какие поля заполнены (NIF_...)
        ("uCallbackMessage", wintypes.UINT),    # каким сообщением сообщать о кликах
        ("hIcon", wintypes.HICON),              # сама картинка
        ("szTip", wintypes.WCHAR * 128),        # подсказка при наведении (до 128 символов)
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),       # текст уведомления
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),   # заголовок уведомления
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


# ═══════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ КЛАСС
# ═══════════════════════════════════════════════════════════════════

class TrayManager:
    """Управляет иконкой в системном трее, ПКМ-меню и сворачиванием консоли в трей."""

    def __init__(
        self,
        on_clear_clipboard: Callable[[], None],
        # Callable[[], None] = «функция без аргументов, ничего не возвращает».
        on_panic: Callable[[], None],
        on_toggle_option: Callable[[int], None],
        # Callable[[int], None] = «функция, принимающая одно число».
        on_exit: Callable[[], None],
    ):
        # Запоминаем функции из main.py. Трей сам не знает, КАК чистить буфер:
        # он просто вызовет то, что ему передали. Так модули не зависят друг от друга.
        self.on_clear_clipboard = on_clear_clipboard
        self.on_panic = on_panic
        self.on_toggle_option = on_toggle_option
        self.on_exit = on_exit

        self._hwnd: Optional[int] = None
        # Номерок нашего невидимого окна (появится в _run_loop).
        self._nid: Optional[NOTIFYICONDATAW] = None
        # Анкета иконки (тоже появится позже).
        self._console_hwnd: int = self._detect_console_hwnd()
        # Номерок окна консоли (чёрного окна, где идёт лог).
        self._console_visible: bool = True
        self._wnd_proc_ref = WNDPROC(self._wnd_proc)
        # Оборачиваем метод _wnd_proc в форму, понятную Windows.
        # ВАЖНО сохранить ссылку в self: иначе Python удалит обёртку из памяти,
        # а Windows попытается её вызвать, и программа упадёт.

        # Отключаем принудительное убийство процесса крестиком [X], чтобы сворачивать в трей
        self._protect_console_close()

    def _detect_console_hwnd(self) -> int:
        # Находим окно консоли.
        hwnd = kernel32.GetConsoleWindow()
        if hwnd and user32.IsWindowVisible(hwnd):
            return hwnd
        fg = user32.GetForegroundWindow()
        # Запасной вариант (например, для нового Windows Terminal): окно на переднем плане.
        return fg or hwnd or 0
        # A or B or C — первое «непустое» значение.

    def _protect_console_close(self):
        """Отключает системную кнопку [X] у окна консоли, чтобы окно сворачивалось в трей, а не убивало процесс."""
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            hmenu = user32.GetSystemMenu(hwnd, False)
            # Системное меню окна (то, что открывается по клику на иконку в углу).
            if hmenu:
                user32.DeleteMenu(hmenu, SC_CLOSE, MF_BYCOMMAND)
                # Удаляем пункт «Закрыть», и крестик [X] становится неактивным.

    def hide_console_to_tray(self):
        """Скрывает окно консоли в системный трей."""
        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        if hwnd:
            user32.ShowWindow(hwnd, SW_HIDE)
            # Прячем окно. Программа при этом продолжает работать.
            self._console_visible = False
            self.show_balloon("GhostClip Shield в трее", "Защита продолжает работать в фоне. Нажмите ПКМ по иконке для управления.")

    def show_console_from_tray(self):
        """Возвращает окно консоли из трея на передний план."""
        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        if hwnd:
            user32.ShowWindow(hwnd, SW_RESTORE)   # развернуть
            user32.ShowWindow(hwnd, SW_SHOW)      # показать
            user32.SetForegroundWindow(hwnd)      # вывести поверх других окон
            self._console_visible = True

    def toggle_console(self):
        """Переключает видимость окна консоли."""
        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        if hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            # Окно видно и не свёрнуто, значит прячем.
            self.hide_console_to_tray()
        else:
            self.show_console_from_tray()

    def check_minimized_to_tray(self):
        """Если пользователь свернул окно консоли кнопкой [_], прячет его в трей."""
        # main.py вызывает этот метод каждые 0.2 сек.
        hwnd = kernel32.GetConsoleWindow()
        if hwnd and self._console_visible and user32.IsIconic(hwnd):
            self.hide_console_to_tray()

    def show_balloon(self, title: str, text: str):
        """Показывает всплывающее уведомление из системного трея."""
        if not self._nid or not self._hwnd:
            # Иконка ещё не создана, показывать уведомление не из чего.
            return
        self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
        # | — побитовое ИЛИ: объединяем флаги в одно число.
        self._nid.szInfoTitle = title[:63]
        self._nid.szInfo = text[:255]
        # Обрезаем текст под размер полей структуры (64 и 256, минус 1 символ на "\0" в конце).
        self._nid.dwInfoFlags = 0x01  # NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
        # «Обнови иконку по этой анкете», и Windows показывает уведомление.

    def _show_context_menu(self):
        """Отрисовывает нативное контекстное меню Windows по правому клику (ПКМ) в трее."""
        hmenu = user32.CreatePopupMenu()
        # Создаём пустое всплывающее меню.
        if not hmenu:
            return

        hwnd = kernel32.GetConsoleWindow() or self._console_hwnd
        is_vis = bool(hwnd and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd))
        console_label = "Скрыть консоль в трей" if is_vis else "Управление (Открыть консоль)"
        # Текст первого пункта зависит от того, видна ли консоль сейчас.

        # Основные действия
        # AppendMenuW(меню, флаги, номер_команды, текст) — добавить пункт в конец меню.
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_TOGGLE_CONSOLE, console_label)
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_CLEAR_CLIPBOARD, "Очистить буфер обмена")
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_PANIC, "ПАНИКА (Стереть буфер + Win+V)")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)

        # Переключатели [1-6] прямо в меню трея с галочками
        for opt_id, (desc, enabled) in config.get_status_dict().items():
            # .items() — пары (ключ, значение) из словаря.
            # (desc, enabled) — значение само является кортежем, сразу раскладываем его.
            flag = MF_STRING | (MF_CHECKED if enabled else MF_UNCHECKED)
            user32.AppendMenuW(hmenu, flag, ID_TRAY_OPT_BASE + opt_id, f"[{opt_id}] {desc}")
            # Номер команды: 1010 + 1 = 1011, ..., 1010 + 6 = 1016.

        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_EXIT, "Полный выход")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        # Узнаём, где сейчас курсор мыши: pt.x, pt.y.
        user32.SetForegroundWindow(self._hwnd)
        # Известная особенность Windows: без этой строки меню не закроется,
        # если кликнуть мимо него.

        cmd = user32.TrackPopupMenu(
            hmenu,
            TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
            pt.x,
            pt.y,
            0,
            self._hwnd,
            None,
        )
        # Показываем меню у курсора и ЖДЁМ, пока пользователь что-то выберет.
        # Благодаря TPM_RETURNCMD в cmd вернётся номер выбранного пункта (или 0, если кликнули мимо).
        user32.DestroyMenu(hmenu)
        # Меню больше не нужно, освобождаем память.

        # Смотрим, что выбрали, и вызываем нужную функцию из main.py.
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
            # Номер команды от 1011 до 1016, значит это тумблер.
            self.on_toggle_option(cmd - ID_TRAY_OPT_BASE)
            # 1013 - 1010 = 3 → переключить функцию [3].

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        # ОБРАБОТЧИК СООБЩЕНИЙ. Его вызывает сама Windows, когда что-то происходит с окном.
        #   msg    — тип сообщения
        #   lparam — для нашей иконки здесь лежит «что именно сделала мышь»
        if msg == WM_TRAYICON:
            # Событие от нашей иконки в трее.
            if lparam == WM_LBUTTONDBLCLK:
                self.show_console_from_tray()
                return 0
                # return 0 = «сообщение обработано».
            elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_context_menu()
                return 0
        elif msg == WM_DESTROY:
            self.remove_icon()
            user32.PostQuitMessage(0)
            # Говорим циклу сообщений в _run_loop: «пора заканчивать».
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        # Все остальные сообщения отдаём стандартному обработчику Windows.
        # Без этой строки окно вело бы себя странно.

    def remove_icon(self):
        if self._nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            # Удаляем иконку из трея.
            self._nid = None

    def start(self):
        """Запускает поток системного трея Windows."""
        threading.Thread(target=self._run_loop, daemon=True).start()
        # Трей работает в своём потоке, потому что _run_loop — бесконечный цикл.

    def _run_loop(self):
        # Здесь всё и создаётся. Работает в отдельном потоке.

        hinst = kernel32.GetModuleHandleW(None)
        # Номерок нашей программы (Windows требует его при создании окна).
        class_name = f"GhostClipTrayWnd_{os.getpid()}"
        # Уникальное имя шаблона окна. os.getpid() — номер нашего процесса.
        # Так можно запустить две копии программы без конфликта имён.

        # --- Шаг 1: регистрируем шаблон окна ---
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wnd_proc_ref   # «сообщения отправляй сюда»
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        # --- Шаг 2: создаём невидимое окно по этому шаблону ---
        self._hwnd = user32.CreateWindowExW(
            0, class_name, "GhostClip Shield Tray", 0,
            0, 0, 0, 0, None, None, hinst, None,
            # Размер 0×0 и без стилей: окно существует, но его не видно.
            # Оно нужно ТОЛЬКО для того, чтобы получать сообщения.
        )
        if not self._hwnd:
            return

        # --- Шаг 3: загружаем иконку щита ---
        hicon = user32.LoadIconW(None, ctypes.cast(IDI_SHIELD, wintypes.LPCWSTR))
        # ctypes.cast(число, тип) — «притвориться», что число — это указатель на строку.
        # Так Windows API принимает номера встроенных иконок.
        if not hicon:
            hicon = user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))

        # --- Шаг 4: заполняем анкету иконки ---
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        # sizeof — размер структуры в байтах.
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        # «О кликах по иконке сообщай нашему окну сообщением WM_TRAYICON».
        nid.hIcon = hicon
        nid.szTip = "GhostClip Shield — Защита буфера (ПКМ — меню)"
        self._nid = nid

        # --- Шаг 5: добавляем иконку в трей ---
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))

        # --- Шаг 6: ЦИКЛ СООБЩЕНИЙ ---
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            # GetMessageW ЖДЁТ следующее сообщение (процессор при этом не нагружается).
            # Возвращает 0, когда пришёл PostQuitMessage, и тогда цикл заканчивается.
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
            # DispatchMessage передаёт сообщение в наш _wnd_proc.
