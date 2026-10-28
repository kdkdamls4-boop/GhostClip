"""
ghostclip_mini/tray.py
Системный трей Windows (Win32 API через ctypes): иконка щита, ПКМ-меню, уведомления и сворачивание.
"""

import threading
import ctypes
from ctypes import wintypes
from config import config

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32

WM_TRAYICON = 0x8000 + 1
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0x00, 0x01, 0x02

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256), ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
    ]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]

class TrayManager:
    def __init__(self, on_clear, on_panic, on_toggle, on_exit):
        self.on_clear = on_clear
        self.on_panic = on_panic
        self.on_toggle = on_toggle
        self.on_exit = on_exit
        self.hwnd = None
        self.nid: NOTIFYICONDATAW = None  # type: ignore
        self._con_hwnd = kernel32.GetConsoleWindow()
        self._wndproc_ref = WNDPROC(self._proc)

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam in (0x0205, 0x007B):  # WM_RBUTTONUP, WM_CONTEXTMENU
                self._menu()
            elif lparam == 0x0203:  # WM_LBUTTONDBLCLK
                self.toggle_console()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self):
        m = user32.CreatePopupMenu()
        is_vis = user32.IsWindowVisible(self._con_hwnd) if self._con_hwnd else True

        items = [
            (10, "Скрыть консоль в трей" if is_vis else "Открыть консоль GhostClip"),
            (0, "---"),
            (20, "Очистить буфер обмена"),
            (30, "ПАНИКА! (Стереть всё и Win+V)"),
            (0, "---"),
        ]
        for i, (name, val) in config.get_status_dict().items():
            items.append((100 + i, f"[{ 'ВКЛ' if val else 'ВЫКЛ' }] {name}", val))
        items += [(0, "---"), (99, "Выход")]

        for item in items:
            if item[1] == "---":
                user32.AppendMenuW(m, 0x0800, 0, None)
            else:
                flags = 0x0008 if (len(item) > 2 and item[2]) else 0
                user32.AppendMenuW(m, flags, item[0], item[1])

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(m, 0x0100, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(m)

        actions = {20: self.on_clear, 30: self.on_panic, 99: self.on_exit}
        if cmd == 10:
            self.toggle_console()
        elif cmd in actions:
            actions[cmd]()
        elif 101 <= cmd <= 106:
            self.on_toggle(cmd - 100)

    def toggle_console(self):
        if not self._con_hwnd: return
        vis = user32.IsWindowVisible(self._con_hwnd)
        user32.ShowWindow(self._con_hwnd, 0 if vis else 5)
        if vis:
            self.show_balloon("GhostClip в трее", "Защита работает в фоне. Нажмите ПКМ для меню.")
        else:
            user32.SetForegroundWindow(self._con_hwnd)

    def check_minimized_to_tray(self):
        if self._con_hwnd and user32.IsIconic(self._con_hwnd):
            user32.ShowWindow(self._con_hwnd, 0)
            self.show_balloon("GhostClip в трее", "Консоль скрыта в трей.")

    def show_balloon(self, title: str, text: str):
        if not self.nid: return
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
        self.nid.szInfoTitle = title[:63]
        self.nid.szInfo = text[:255]
        self.nid.dwInfoFlags = 1
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def remove_icon(self):
        if self.nid:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None  # type: ignore

    def start(self):
        def loop():
            cls_name = "GhostClipMiniTray"
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc_ref
            wc.lpszClassName = cls_name
            wc.hInstance = kernel32.GetModuleHandleW(None)
            user32.RegisterClassW(ctypes.byref(wc))

            self.hwnd = user32.CreateWindowExW(0, cls_name, cls_name, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)
            hicon = user32.LoadIconW(None, ctypes.cast(32518, wintypes.LPCWSTR)) or user32.LoadIconW(None, ctypes.cast(32512, wintypes.LPCWSTR))

            self.nid = NOTIFYICONDATAW()
            self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            self.nid.hWnd = self.hwnd
            self.nid.uID = 1
            self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            self.nid.uCallbackMessage = WM_TRAYICON
            self.nid.hIcon = hicon
            self.nid.szTip = "GhostClip Shield (ПКМ — меню)"
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))

            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        t = threading.Thread(target=loop, daemon=True)
        t.start()
