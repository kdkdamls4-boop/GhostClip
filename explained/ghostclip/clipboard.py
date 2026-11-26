"""
explained/ghostclip/clipboard.py
Прямая работа с буфером обмена Windows (0% нагрузки на CPU) и определение активной программы.
"""

import ctypes  # ctypes — вызов функций из системных библиотек Windows (DLL) напрямую из Python
import os  # os.path.basename — выделяет только имя файла (chrome.exe) из полного пути
import time  # time.sleep — короткая пауза между повторными попытками доступа к буферу
from ctypes import wintypes  # Готовые типы данных Windows (HANDLE, HWND, DWORD, BOOL)

# Системные DLL Windows:
# user32.dll   — буфер обмена и окна программ
# kernel32.dll — глобальная память и дескрипторы процессов
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GMEM_MOVEABLE = 0x0002  # Флаг выделения перемещаемой памяти Windows
CF_UNICODETEXT = 13  # Формат данных буфера: Юникод-текст UTF-16LE
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # Право прочитать только путь к .exe процесса

# Описываем 64-битные типы аргументов (argtypes) и результата (restype) для Win32 API.
# Без этого на 64-битном Windows указатели могут обрезаться до 32 бит!
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.GetClipboardSequenceNumber.argtypes = []
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetClipboardOwner.argtypes = []
user32.GetClipboardOwner.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def _with_clipboard(action, default=None, retries: int = 5, delay: float = 0.03):
    """
    Общий помощник: делает до 5 попыток открыть буфер (если он занят другой программой),
    выполняет переданную функцию action() и гарантированно закрывает буфер в блоке finally.
    """
    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                return action()
            finally:
                # CloseClipboard() нужно вызвать всегда, иначе другие программы потеряют доступ к буферу!
                user32.CloseClipboard()
        time.sleep(delay)
    return default


def read_clipboard_text() -> str:
    """Читает Юникод-текст из буфера обмена Windows."""

    def _read() -> str:
        memory_handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not memory_handle:
            return ""
        memory_pointer = kernel32.GlobalLock(memory_handle)
        if not memory_pointer:
            return ""
        try:
            return ctypes.wstring_at(memory_pointer)
        finally:
            kernel32.GlobalUnlock(memory_handle)

    return _with_clipboard(_read, default="")


def write_clipboard_text(text: str) -> bool:
    """Записывает очищенную или тестовую Юникод-строку в буфер обмена Windows."""
    encoded_bytes = (text + "\0").encode("utf-16-le")

    def _write() -> bool:
        user32.EmptyClipboard()
        memory_handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded_bytes))
        if not memory_handle:
            return False
        memory_pointer = kernel32.GlobalLock(memory_handle)
        if not memory_pointer:
            kernel32.GlobalFree(memory_handle)
            return False
        try:
            ctypes.memmove(memory_pointer, encoded_bytes, len(encoded_bytes))
        finally:
            kernel32.GlobalUnlock(memory_handle)
        # Если SetClipboardData удался, память переходит во владение Windows (GlobalFree вызывать нельзя)
        if not user32.SetClipboardData(CF_UNICODETEXT, memory_handle):
            kernel32.GlobalFree(memory_handle)
            return False
        return True

    return bool(_with_clipboard(_write, default=False))


def wipe_clipboard() -> bool:
    """Очищает текущее содержимое буфера обмена."""
    return bool(_with_clipboard(lambda: bool(user32.EmptyClipboard()), default=False))


def get_clipboard_sequence_number() -> int:
    """
    Возвращает системный счётчик изменений буфера Windows.
    Пока пользователь ничего не копирует, число не меняется, и цикл почти не нагружает процессор.
    """
    return int(user32.GetClipboardSequenceNumber())


def get_active_process_info() -> tuple[str, str]:
    """Определяет, из какого приложения (.exe) были скопированы данные."""
    window_handle = user32.GetClipboardOwner() or user32.GetForegroundWindow()
    if not window_handle:
        return "Unknown", ""

    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window_handle, ctypes.byref(process_id))
    if not process_id.value:
        return "Unknown", ""

    process_handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
    if not process_handle:
        return f"PID:{process_id.value}", ""

    path_buffer = ctypes.create_unicode_buffer(1024)
    buffer_size = wintypes.DWORD(1024)
    try:
        if kernel32.QueryFullProcessImageNameW(process_handle, 0, path_buffer, ctypes.byref(buffer_size)):
            return os.path.basename(path_buffer.value), path_buffer.value
    finally:
        kernel32.CloseHandle(process_handle)
    return f"PID:{process_id.value}", ""
