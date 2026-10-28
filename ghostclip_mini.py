"""
GhostClip Shield — Ультра-компактная версия (Single-file Portable Edition).
Весь функционал в одном файле (~260 строк) без сторонних библиотек:
- Чистка трекинг-меток в URL (utm, fbclid, si и др.)
- Удаление невидимых zero-width знаков
- Детекция секретов (OpenAI, AWS, GitHub, кредитные карты Luhn, пароли)
- Таймер самоуничтожения (45 сек)
- Зачистка истории буфера Win+V и паника
- Системный трей Windows (ПКМ-меню, уведомления, сворачивание)
- Моментальные горячие клавиши без нажатия Enter
"""

import sys
import os
import time
import datetime
import re
import math
import threading
import msvcrt
import ctypes
from ctypes import wintypes
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

sys.stdout.reconfigure(encoding="utf-8")

# ═══════════════════════════════════════════════════════════════════
#  1. КОНФИГУРАЦИЯ И ЖУРНАЛ АУДИТА
# ═══════════════════════════════════════════════════════════════════

LOG_FILE_PATH = "clipboard_access.log"

class ShieldConfig:
    def __init__(self):
        self.clean_urls = True
        self.clean_zero_width = True
        self.detect_secrets = True
        self.auto_shred_timer = True
        self.shred_win_v = True
        self.audit_logging = True
        self.timer_seconds = 45

    def toggle(self, opt_id: int):
        m = {1: "clean_urls", 2: "clean_zero_width", 3: "detect_secrets",
             4: "auto_shred_timer", 5: "shred_win_v", 6: "audit_logging"}
        if opt_id not in m: return "Неизвестно", False
        attr = m[opt_id]
        new_val = not getattr(self, attr)
        setattr(self, attr, new_val)
        names = {1: "Чистка ссылок", 2: "Удаление невидимых знаков", 3: "Детекция секретов",
                 4: "Таймер самоуничтожения", 5: "Зачистка истории Win+V", 6: "Журнал аудита"}
        return names[opt_id], new_val

    def get_status_dict(self):
        return {
            1: ("Чистка ссылок (utm, fbclid, si)", self.clean_urls),
            2: ("Удаление невидимых символов", self.clean_zero_width),
            3: ("Детекция секретов и карт", self.detect_secrets),
            4: (f"Таймер самоуничтожения ({self.timer_seconds}с)", self.auto_shred_timer),
            5: ("Зачистка истории Win+V", self.shred_win_v),
            6: ("Журнал clipboard_access.log", self.audit_logging),
        }

config = ShieldConfig()

def log_audit(event_type: str, app_name: str, snippet: str, details: str = ""):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{event_type}] [APP: {app_name}] [DATA: {snippet}] {details}".strip()
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  2. ЧИСТКА ССЫЛОК И НЕВИДИМЫХ ЗНАКОВ
# ═══════════════════════════════════════════════════════════════════

ZERO_WIDTH_CHARS = {'\u200b', '\u200c', '\u200d', '\ufeff', '\u200e', '\u200f', '\u202a', '\u202b', '\u202c', '\u202d', '\u202e'}
TRACKING_PARAMS = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid', 'yclid', 'si', 'igshid', 'mc_eid', 'ysclid'}

def strip_zero_width(text: str) -> tuple[str, int]:
    cnt = sum(1 for c in text if c in ZERO_WIDTH_CHARS)
    return (''.join(c for c in text if c not in ZERO_WIDTH_CHARS), cnt)

def clean_url(url: str) -> tuple[str, list[str]]:
    try:
        p = urlparse(url)
        if not p.scheme or not p.netloc: return url, []
        q = parse_qs(p.query, keep_blank_values=True)
        rem = [k for k in q if k in TRACKING_PARAMS]
        if not rem: return url, []
        for k in rem: del q[k]
        new_q = urlencode(q, doseq=True)
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_q, p.fragment)), rem
    except Exception:
        return url, []

def sanitize_text(text: str) -> tuple[str, bool, list[str]]:
    mod = False
    cleaned, cnt = strip_zero_width(text)
    logs = [f"Удалено {cnt} скрытых знаков"] if cnt else []
    if cnt: mod = True
    urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', cleaned)
    for u in set(urls):
        cu, rem = clean_url(u)
        if rem:
            cleaned = cleaned.replace(u, cu)
            logs.append(f"Очищен URL ({', '.join(rem)})")
            mod = True
    return cleaned, mod, logs


# ═══════════════════════════════════════════════════════════════════
#  3. ДЕТЕКЦИЯ СЕКРЕТОВ И КАРТ
# ═══════════════════════════════════════════════════════════════════

def calculate_entropy(s: str) -> float:
    if not s: return 0.0
    return -sum((s.count(c)/len(s)) * math.log2(s.count(c)/len(s)) for c in set(s))

def luhn_check(num: str) -> bool:
    d = [int(c) for c in num if c.isdigit()]
    if not (13 <= len(d) <= 19): return False
    checksum = 0
    for i, digit in enumerate(d[::-1]):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0

PATTERNS = [
    ("OPENAI_KEY", re.compile(r"sk-[a-zA-Z0-9_-]{20,}")),
    ("AWS_KEY", re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}")),
    ("GITHUB_TOKEN", re.compile(r"gh[pousr]-[A-Za-z0-9_]{36,}")),
]

def detect_secret(text: str) -> tuple[bool, str, str]:
    for name, rgx in PATTERNS:
        m = rgx.search(text)
        if m: return True, name, m.group(0)
    for m in re.finditer(r"\b(?:\d[ -]*?){13,19}\b", text):
        clean = re.sub(r"\D", "", m.group(0))
        if luhn_check(clean): return True, "CREDIT_CARD", m.group(0)
    tokens = text.strip().split()
    if len(tokens) == 1 and len(tokens[0]) >= 12 and calculate_entropy(tokens[0]) >= 3.6:
        return True, "HIGH_ENTROPY_PASSWORD", tokens[0]
    return False, "", ""

def mask_secret(secret: str) -> str:
    s = secret.strip()
    return s[:2] + "*" * (len(s) - 4) + s[-2:] if len(s) > 6 else "*" * len(s)


# ═══════════════════════════════════════════════════════════════════
#  4. WIN32 БУФЕР ОБМЕНА И ШРЕДДЕР (WIN+V)
# ═══════════════════════════════════════════════════════════════════

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
GMEM_MOVEABLE, CF_UNICODETEXT = 0x0002, 13

def read_clipboard_text() -> str:
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                h = user32.GetClipboardData(CF_UNICODETEXT)
                if h:
                    p = kernel32.GlobalLock(h)
                    if p:
                        txt = ctypes.wstring_at(p)
                        kernel32.GlobalUnlock(h)
                        return txt
                return ""
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return ""

def write_clipboard_text(text: str) -> bool:
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                raw = text.encode("utf-16le") + b"\x00\x00"
                h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
                if h:
                    p = kernel32.GlobalLock(h)
                    if p:
                        ctypes.memmove(p, raw, len(raw))
                        kernel32.GlobalUnlock(h)
                        user32.SetClipboardData(CF_UNICODETEXT, h)
                        return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return False

def wipe_clipboard():
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return False

def shred_clipboard():
    for _ in range(3):
        write_clipboard_text("0" * 64)
        time.sleep(0.01)
        write_clipboard_text("\x00" * 64)
        time.sleep(0.01)
    wipe_clipboard()

def panic_wipe():
    shred_clipboard()
    try: ctypes.windll.ole32.OleFlushClipboard()
    except Exception: pass
    for _ in range(25):
        write_clipboard_text(" ")
        time.sleep(0.005)
    wipe_clipboard()

def get_clipboard_sequence_number() -> int:
    return user32.GetClipboardSequenceNumber()

def get_active_process_info() -> tuple[str, str]:
    hwnd = user32.GetForegroundWindow()
    if not hwnd: return "Unknown", ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h: return "Unknown", ""
    buf = ctypes.create_unicode_buffer(1024)
    sz = wintypes.DWORD(1024)
    try:
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)):
            return os.path.basename(buf.value), buf.value
    finally:
        kernel32.CloseHandle(h)
    return "Unknown", ""


# ═══════════════════════════════════════════════════════════════════
#  5. ТАЙМЕР САМОУНИЧТОЖЕНИЯ
# ═══════════════════════════════════════════════════════════════════

class GhostTimer:
    def __init__(self):
        self._timer: threading.Timer = None  # type: ignore
        self._arm_time = 0.0
        self._seconds = 45

    def arm(self, seconds: int, callback):
        self.disarm()
        self._seconds = seconds
        self._arm_time = time.time()
        self._timer = threading.Timer(seconds, callback)
        self._timer.daemon = True
        self._timer.start()

    def disarm(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None  # type: ignore
        self._arm_time = 0.0

    def is_armed(self) -> bool:
        return self._timer is not None and self._timer.is_alive()

    def remaining_seconds(self) -> int:
        if not self.is_armed(): return 0
        return max(0, int(self._seconds - (time.time() - self._arm_time)))

ghost_timer = GhostTimer()


# ═══════════════════════════════════════════════════════════════════
#  6. СИСТЕМНЫЙ ТРЕЙ WINDOWS (ЧИСТЫЙ CTYPES)
# ═══════════════════════════════════════════════════════════════════

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
        user32.AppendMenuW(m, 0, 10, "Скрыть консоль в трей" if is_vis else "Открыть консоль GhostClip")
        user32.AppendMenuW(m, 0x0800, 0, None)  # Separator
        user32.AppendMenuW(m, 0, 20, "Очистить буфер обмена")
        user32.AppendMenuW(m, 0, 30, "ПАНИКА! (Стереть всё и Win+V)")
        user32.AppendMenuW(m, 0x0800, 0, None)
        for i, (name, val) in config.get_status_dict().items():
            flags = 0x0008 if val else 0  # MF_CHECKED
            user32.AppendMenuW(m, flags, 100 + i, f"[{ 'ВКЛ' if val else 'ВЫКЛ' }] {name}")
        user32.AppendMenuW(m, 0x0800, 0, None)
        user32.AppendMenuW(m, 0, 99, "Выход")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(m, 0x0100, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(m)

        if cmd == 10: self.toggle_console()
        elif cmd == 20: self.on_clear()
        elif cmd == 30: self.on_panic()
        elif 101 <= cmd <= 106: self.on_toggle(cmd - 100)
        elif cmd == 99: self.on_exit()

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


# ═══════════════════════════════════════════════════════════════════
#  7. ИНТЕРФЕЙС И ГЛАВНЫЙ ЦИКЛ
# ═══════════════════════════════════════════════════════════════════

_ui_lock = threading.Lock()
_logs: list[str] = []
tray_mgr: TrayManager = None  # type: ignore

def render():
    with _ui_lock:
        st = config.get_status_dict()
        b = lambda v: "[ВКЛ] " if v else "[ВЫКЛ]"
        t_str = f"АКТИВЕН ({ghost_timer.remaining_seconds()}с)" if ghost_timer.is_armed() else "Ожидание..."
        os.system("cls" if os.name == "nt" else "clear")
        print("╔═══════════════════════════════════════════════════════════════════════╗")
        print("║                 GhostClip Shield (Компактный 1-файл)                  ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        for i in range(1, 7):
            print(f"║  [{i}] {st[i][0]:<49} {b(st[i][1])}   ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║  Таймер: {t_str:<25}  (Иконка щита активна в трее!)     ║")
        print("║  [1-6] Вкл/Выкл | [B] Очистить буфер | [P] ПАНИКА (Буфер + Win+V)     ║")
        print("║  [T] Скрыть в трей (или [_])         | [C] Очистить лог | [Q] Выход   ║")
        print("╚═══════════════════════════════════════════════════════════════════════╝\n--- ЖИВОЙ ЛОГ ---")
        if not _logs: print("[*] Ожидание событий буфера обмена...")
        else:
            for l in _logs[-20:]: print(l)

def add_log(m: str):
    with _ui_lock:
        _logs.append(m)
        if len(_logs) > 20: _logs.pop(0)
        print(m)

def on_clear():
    ghost_timer.disarm()
    wipe_clipboard()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging: log_audit("CLIP_CLEARED", "User", "[БУФЕР_ОЧИЩЕН]")
    add_log(f"[{now}] [ОЧИСТКА БУФЕРА] Буфер очищен.")
    if tray_mgr: tray_mgr.show_balloon("Буфер очищен", "Буфер обмена очищен.")

def on_panic():
    ghost_timer.disarm()
    panic_wipe()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging: log_audit("PANIC_FLUSH", "User", "[ПАНИКА]")
    add_log(f"[{now}] [ПАНИКА!] Буфер и история Win+V затерты!")
    if tray_mgr: tray_mgr.show_balloon("ПАНИКА", "Буфер и Win+V уничтожены.")

def on_toggle(opt_id: int):
    name, val = config.toggle(opt_id)
    now = datetime.datetime.now().strftime("%H:%M:%S")
    with _ui_lock: _logs.append(f"[{now}] [{opt_id}] {name} -> {'ВКЛ' if val else 'ВЫКЛ'}")
    render()

def on_exit():
    if tray_mgr: tray_mgr.remove_icon()
    print("\n[*] Завершение работы GhostClip...")
    os._exit(0)

def key_listener():
    while True:
        try:
            ch = msvcrt.getwch().lower()
            if ch in '123456': on_toggle(int(ch))
            elif ch == 'b': on_clear()
            elif ch == 'p': on_panic()
            elif ch == 't':
                if tray_mgr: tray_mgr.toggle_console()
            elif ch == 'c':
                with _ui_lock: _logs.clear()
                render()
            elif ch == 'q': on_exit()
        except Exception: pass

def main():
    global tray_mgr
    tray_mgr = TrayManager(on_clear, on_panic, on_toggle, on_exit)
    tray_mgr.start()
    threading.Thread(target=key_listener, daemon=True).start()
    render()

    last_seq, last_txt, self_upd = get_clipboard_sequence_number(), "", False
    while True:
        time.sleep(0.2)
        if tray_mgr: tray_mgr.check_minimized_to_tray()
        cur_seq = get_clipboard_sequence_number()
        if cur_seq == last_seq: continue
        last_seq = cur_seq
        if self_upd:
            self_upd = False
            continue
        txt = read_clipboard_text()
        if not txt or txt == last_txt: continue
        last_txt = txt
        app, _ = get_active_process_info()
        now = datetime.datetime.now().strftime("%H:%M:%S")

        if config.clean_urls or config.clean_zero_width:
            cleaned, mod, details = sanitize_text(txt)
            if mod:
                self_upd = True
                write_clipboard_text(cleaned)
                last_txt = cleaned
                add_log(f"[{now}] [ОЧИСТКА] ({app}) -> {'; '.join(details)}")
                if config.audit_logging: log_audit("CLEANED", app, cleaned[:50], "; ".join(details))
                txt = cleaned

        if config.detect_secrets:
            is_sec, sec_type, val = detect_secret(txt)
            if is_sec:
                masked = mask_secret(val)
                add_log(f"[{now}] [СЕКРЕТ!] Обнаружен {sec_type}: {masked} (Источник: {app})")
                if config.audit_logging: log_audit("SECRET_FOUND", app, masked, f"Тип: {sec_type}")
                if config.auto_shred_timer:
                    add_log(f"[{now}] [ТАЙМЕР] Запущен отсчет {config.timer_seconds} сек до уничтожения...")
                    def auto_destruct():
                        now2 = datetime.datetime.now().strftime("%H:%M:%S")
                        wipe_clipboard()
                        add_log(f"[{now2}] [ТАЙМЕР ИСТЁК] Секрет удален из буфера!")
                        if tray_mgr: tray_mgr.show_balloon("GhostClip Shield", "Секрет уничтожен таймером!")
                    ghost_timer.arm(config.timer_seconds, auto_destruct)
                    render()

if __name__ == "__main__":
    main()
