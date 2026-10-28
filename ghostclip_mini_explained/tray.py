"""
ghostclip_mini_explained/tray.py
Файл 6 из 7: Системный трей Windows (Win32 API через ctypes): иконка щита, ПКМ-меню, уведомления и сворачивание.
"""

import threading  # threading — запуск цикла обработки сообщений Win32 в фоне
import ctypes     # ctypes — прямые вызовы user32, kernel32 и shell32
from ctypes import wintypes  # Типы данных Win32 (HWND, UINT, POINT и т.д.)
from config import config    # Чтение текущего состояния переключателей [1-6]

# Загружаем системные библиотеки Windows
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

# Пользовательское сообщение Windows: посылается окну, когда юзер кликает по иконке в трее
WM_TRAYICON = 0x8000 + 1

# Флаги структуры NOTIFYICONDATA: определяют, какие поля структуры активны
NIF_MESSAGE = 0x01   # Принимать сообщения мыши (клик, ПКМ)
NIF_ICON    = 0x02   # Показывать саму иконку
NIF_TIP     = 0x04   # Показывать всплывающую подсказку при наведении
NIF_INFO    = 0x10   # Показывать всплывающее уведомление (Balloon tooltip)

# Действия с иконкой: добавить (0), изменить (1), удалить (2)
NIM_ADD    = 0x00
NIM_MODIFY = 0x01
NIM_DELETE = 0x02

class NOTIFYICONDATAW(ctypes.Structure):
    """Си-структура Windows для регистрации и управления иконкой в области уведомлений (трее)."""
    _fields_ = [
        ("cbSize", wintypes.DWORD),             # Размер структуры в байтах
        ("hWnd", wintypes.HWND),                 # Дескриптор окна-владельца
        ("uID", wintypes.UINT),                  # Уникальный ID иконки
        ("uFlags", wintypes.UINT),               # Флаги активности (NIF_*)
        ("uCallbackMessage", wintypes.UINT),     # Какое сообщение слать при клике (WM_TRAYICON)
        ("hIcon", wintypes.HICON),               # Дескриптор иконки (.ico)
        ("szTip", wintypes.WCHAR * 128),         # Подсказка при наведении мыши
        ("dwState", wintypes.DWORD),             # Состояние
        ("dwStateMask", wintypes.DWORD),         # Маска состояния
        ("szInfo", wintypes.WCHAR * 256),        # Текст всплывающего уведомления
        ("uTimeoutOrVersion", wintypes.UINT),    # Таймаут показа
        ("szInfoTitle", wintypes.WCHAR * 64),    # Заголовок всплывающего уведомления
        ("dwInfoFlags", wintypes.DWORD),         # Флаги уведомления (значок Info)
    ]

# Объявляем сигнатуру оконной процедуры Win32: long WindowProc(HWND, UINT, WPARAM, LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

class WNDCLASSW(ctypes.Structure):
    """Си-структура для регистрации оконного класса в Windows."""
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),                # Указатель на функцию-обработчик сообщений
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),       # Дескриптор модуля процесса
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),     # Уникальное имя класса окна
    ]

class TrayManager:
    """
    Управляет жизненным циклом иконки GhostClip в системном трее Windows:
    создаёт фоновое окно, слушает клики мыши, показывает ПКМ-меню и скрывает консоль.
    """
    def __init__(self, on_clear, on_panic, on_toggle, on_exit):
        self.on_clear = on_clear            # Callback: очистить буфер
        self.on_panic = on_panic            # Callback: паника (буфер + Win+V)
        self.on_toggle = on_toggle          # Callback: переключить тумблер [1-6]
        self.on_exit = on_exit              # Callback: полный выход
        self.hwnd = None                    # Дескриптор нашего скрытого окна
        self.nid: NOTIFYICONDATAW = None    # type: ignore
        self._con_hwnd = kernel32.GetConsoleWindow()  # Находим дескриптор текущего окна консоли
        self._wndproc_ref = WNDPROC(self._proc)       # Храним ссылку, чтобы сборщик мусора не удалил её

    def _proc(self, hwnd, msg, wparam, lparam):
        """Оконная процедура: получает системные события от Windows."""
        if msg == WM_TRAYICON:
            # 0x0205 = WM_RBUTTONUP (отпустили правую кнопку мыши), 0x007B = WM_CONTEXTMENU
            if lparam in (0x0205, 0x007B):
                self._menu()  # Показываем контекстное меню возле курсора
            # 0x0203 = WM_LBUTTONDBLCLK (двойной клик левой кнопкой мыши)
            elif lparam == 0x0203:
                self.toggle_console()  # Показываем или прячем окно консоли
            return 0
        # Все остальные сообщения передаём стандартному обработчику Windows
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self):
        """Отрисовывает нативное меню Windows по клику ПКМ на иконке."""
        m = user32.CreatePopupMenu()  # Создаём пустое всплывающее меню
        is_vis = user32.IsWindowVisible(self._con_hwnd) if self._con_hwnd else True

        # Формируем список пунктов меню в виде удобных кортежей (ID, Текст, [Значение])
        # "---" означает разделительную черту (MF_SEPARATOR)
        items = [
            (10, "Скрыть консоль в трей" if is_vis else "Открыть консоль GhostClip"),
            (0, "---"),
            (20, "Очистить буфер обмена"),
            (30, "ПАНИКА! (Стереть всё и Win+V)"),
            (0, "---"),
        ]

        # Добавляем пункты [1-6] с текущим статусом активности (True / False)
        for i, (name, val) in config.get_status_dict().items():
            items.append((100 + i, f"[{ 'ВКЛ' if val else 'ВЫКЛ' }] {name}", val))

        items += [(0, "---"), (99, "Выход")]

        # Быстрый цикл добавления всех пунктов в меню Windows вместо повтора AppendMenuW
        for item in items:
            if item[1] == "---":
                user32.AppendMenuW(m, 0x0800, 0, None)  # 0x0800 = MF_SEPARATOR
            else:
                # 0x0008 = MF_CHECKED (галочка напротив пункта, если функция включена)
                flags = 0x0008 if (len(item) > 2 and item[2]) else 0
                user32.AppendMenuW(m, flags, item[0], item[1])

        # Получаем координаты курсора мыши на экране
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        # Открываем меню в координатах курсора и ждём выбора пользователя
        cmd = user32.TrackPopupMenu(m, 0x0100, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(m)  # Очищаем память меню

        # Словарь действий для быстрого вызова нужной функции по номеру пункта
        actions = {20: self.on_clear, 30: self.on_panic, 99: self.on_exit}
        if cmd == 10:
            self.toggle_console()
        elif cmd in actions:
            actions[cmd]()
        elif 101 <= cmd <= 106:
            self.on_toggle(cmd - 100)

    def toggle_console(self):
        """Сворачивает консоль в трей или возвращает её на передний план."""
        if not self._con_hwnd:
            return
        vis = user32.IsWindowVisible(self._con_hwnd)
        # 0 = SW_HIDE (спрятать окно), 5 = SW_SHOW (показать)
        user32.ShowWindow(self._con_hwnd, 0 if vis else 5)
        if vis:
            self.show_balloon("GhostClip в трее", "Защита работает в фоне. Нажмите ПКМ для меню.")
        else:
            user32.SetForegroundWindow(self._con_hwnd)

    def check_minimized_to_tray(self):
        """Если юзер нажал кнопку свернуть [_] в окне консоли, прячем окно в трей."""
        if self._con_hwnd and user32.IsIconic(self._con_hwnd):
            user32.ShowWindow(self._con_hwnd, 0)  # Скрываем с панели задач
            self.show_balloon("GhostClip в трее", "Консоль скрыта в трей.")

    def show_balloon(self, title: str, text: str):
        """Вызывает системное всплывающее уведомление Windows у иконки трея."""
        if not self.nid:
            return
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
        self.nid.szInfoTitle = title[:63]
        self.nid.szInfo = text[:255]
        self.nid.dwInfoFlags = 1  # 1 = NIIF_INFO (значок информации)
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def remove_icon(self):
        """Удаляет иконку из системного трея при выходе."""
        if self.nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None  # type: ignore

    def start(self):
        """Запускает цикл обработки оконных сообщений Windows в отдельном потоке."""
        def loop():
            cls_name = "GhostClipMiniTray"
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc_ref
            wc.lpszClassName = cls_name
            wc.hInstance = kernel32.GetModuleHandleW(None)
            user32.RegisterClassW(ctypes.byref(wc))  # Регистрируем оконный класс

            # Создаём невидимое окно для приёма сообщений от трея
            self.hwnd = user32.CreateWindowExW(0, cls_name, cls_name, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)
            # Загружаем системную иконку щита безопасности Windows (ID 32518)
            hicon = user32.LoadIconW(None, ctypes.cast(32518, wintypes.LPCWSTR)) or user32.LoadIconW(None, ctypes.cast(32512, wintypes.LPCWSTR))

            # Инициализируем структуру иконки трея
            self.nid = NOTIFYICONDATAW()
            self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            self.nid.hWnd = self.hwnd
            self.nid.uID = 1
            self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            self.nid.uCallbackMessage = WM_TRAYICON
            self.nid.hIcon = hicon
            self.nid.szTip = "GhostClip Shield (ПКМ — меню)"
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))  # Добавляем значок в трей

            # Стандартный цикл сообщений Win32 GetMessage/Translate/Dispatch
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        t = threading.Thread(target=loop, daemon=True)
        t.start()
