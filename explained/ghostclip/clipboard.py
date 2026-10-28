"""Низкоуровневая работа с буфером обмена и процессами Windows (0% нагрузки на CPU)."""
# «Низкоуровневая» = общаемся с Windows напрямую, без готовых удобных библиотек.

import os
# os — работа с операционной системой (пути к файлам и т.д.).

import time
# time — время и паузы (time.sleep).

import ctypes
# ctypes — позволяет вызывать функции, встроенные в саму Windows (из .dll файлов).
# Python сам по себе не умеет работать с буфером обмена, а Windows умеет.

from ctypes import wintypes
# wintypes — типы данных Windows (HANDLE, DWORD, UINT...) в виде, понятном Python.

from typing import Optional, Tuple


# ═══════════════════════════════════════════════════════════════════
#  ПОДКЛЮЧАЕМ СИСТЕМНЫЕ БИБЛИОТЕКИ WINDOWS
# ═══════════════════════════════════════════════════════════════════

user32 = ctypes.windll.user32
# user32.dll — всё про окна, буфер обмена, клавиатуру и мышь.
kernel32 = ctypes.windll.kernel32
# kernel32.dll — память, процессы, файлы.


# ═══════════════════════════════════════════════════════════════════
#  КОНСТАНТЫ WINDOWS — «магические числа» из документации Microsoft
# ═══════════════════════════════════════════════════════════════════

CF_UNICODETEXT = 13
# Формат буфера «текст в Unicode». Windows обозначает его числом 13.

GMEM_MOVEABLE = 0x0002
# Флаг выделения памяти: «перемещаемая память». 0x0002 — это просто 2, записанное в 16-ричной системе.

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# Право «узнать базовую инфу о процессе» (например, его имя).


# ═══════════════════════════════════════════════════════════════════
#  ОБЪЯСНЯЕМ PYTHON ТИПЫ ДАННЫХ ФУНКЦИЙ WINDOWS
# ═══════════════════════════════════════════════════════════════════
# argtypes = какие аргументы функция принимает.
# restype  = что она возвращает.
# Без этого на 64-битной Windows Python может обрезать адреса памяти, и программа упадёт.
# HANDLE / HGLOBAL — «номерок» на кусок памяти (как номерок в гардеробе).
# LPVOID — указатель (адрес в памяти).

# Настройка 64-битных дескрипторов указателей для стабильной работы в 64-bit Windows
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]


# ═══════════════════════════════════════════════════════════════════
#  ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════

def get_clipboard_sequence_number() -> int:
    """Счетчик изменений буфера ядра Windows (0% нагрузки на CPU при опросе)."""
    # Windows считает, сколько раз менялся буфер обмена.
    # Скопировал что-то — число увеличилось на 1.
    # main.py каждые 0.2 сек сравнивает это число со старым. Если оно изменилось,
    # значит, что-то скопировали. Читать сам буфер каждый раз было бы дороже.
    return int(user32.GetClipboardSequenceNumber())


def read_clipboard_text(retries: int = 5, delay: float = 0.03) -> Optional[str]:
    # retries — сколько раз пытаться, delay — пауза между попытками (в секундах).
    # Возвращает текст или None.
    """Читает UTF-16 текст из буфера обмена."""

    for _ in range(retries):
        # Повторить до 5 раз. _ значит «номер попытки мне не нужен».
        # Зачем повторять: буфер может быть занят другой программой прямо сейчас.

        if user32.OpenClipboard(None):
            # Пытаемся «открыть» буфер. Это получится, только если он не занят.
            try:
                h = user32.GetClipboardData(CF_UNICODETEXT)
                # Просим у Windows номерок (handle) на текст в буфере.
                if not h:
                    # Номерка нет, значит в буфере не текст (например, картинка).
                    return None

                ptr = kernel32.GlobalLock(h)
                # «Блокируем» память и получаем её реальный адрес (указатель).
                if not ptr:
                    return None
                try:
                    return ctypes.c_wchar_p(ptr).value
                    # Читаем по адресу ptr строку Unicode и превращаем её в обычную строку Python.
                finally:
                    # finally выполнится ВСЕГДА, даже после return.
                    kernel32.GlobalUnlock(h)
                    # Разблокируем память. Если забыть, будет утечка.
            finally:
                user32.CloseClipboard()
                # Обязательно закрываем буфер, иначе другие программы не смогут копировать!

        time.sleep(delay)
        # Буфер был занят, поэтому ждём 0.03 сек и пробуем снова.
    return None
    # Все 5 попыток провалились.


def write_clipboard_text(text: str, retries: int = 5, delay: float = 0.03) -> bool:
    """Записывает очищенный UTF-16LE текст обратно в буфер."""

    data = (text + "\0").encode("utf-16-le")
    # Windows хранит текст в кодировке UTF-16, а конец строки отмечается символом "\0".
    # .encode() превращает строку Python в байты (сырые данные).

    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                # Сначала очищаем буфер.

                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                # Просим Windows выделить кусок памяти нужного размера.
                if not h_mem:
                    return False

                ptr = kernel32.GlobalLock(h_mem)
                # Получаем адрес этой памяти.
                if not ptr:
                    return False

                ctypes.memmove(ptr, data, len(data))
                # Копируем наши байты в эту память (memmove = «переместить память»).

                kernel32.GlobalUnlock(h_mem)
                return bool(user32.SetClipboardData(CF_UNICODETEXT, h_mem))
                # Отдаём память буферу обмена. bool(...) превращает результат в True/False.
            finally:
                user32.CloseClipboard()
        time.sleep(delay)
    return False


def wipe_clipboard() -> bool:
    """Очищает оперативную память буфера обмена."""
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.03)
    return False


def get_active_process_info() -> Tuple[str, str]:
    # Возвращает пару: (короткое имя "chrome.exe", полный путь "C:\...\chrome.exe").
    """Определяет программу, скопировавшую данные (проверяет владельца буфера и активное окно)."""

    hwnd = user32.GetClipboardOwner() or user32.GetForegroundWindow()
    # hwnd — «номерок окна».
    # A or B: если A пустое или 0, берётся B.
    # То есть: окно-владелец буфера, а если его нет — окно, которое сейчас на переднем плане.
    if not hwnd:
        return "Фоновый процесс", "N/A"

    pid = wintypes.DWORD()
    # pid (Process ID) — номер процесса. Создаём пустую «ячейку» под число.

    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    # ctypes.byref(pid) — передаём АДРЕС ячейки, чтобы Windows записала туда номер процесса.
    if not pid.value:
        # .value — достать само число из ячейки.
        return "Системный процесс", "N/A"

    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    # «Открываем» процесс с правом читать его информацию.
    if not h_proc:
        # Нет доступа (например, процесс системный). Показываем хотя бы номер.
        return f"PID:{pid.value}", "N/A"
    try:
        buf = ctypes.create_unicode_buffer(512)
        # Буфер на 512 символов, сюда Windows запишет путь к .exe.
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value), buf.value
            # os.path.basename("C:\\a\\chrome.exe") → "chrome.exe"
        return f"PID:{pid.value}", "N/A"
    finally:
        kernel32.CloseHandle(h_proc)
        # Возвращаем номерок процесса. Всё, что открыли, нужно закрыть.
