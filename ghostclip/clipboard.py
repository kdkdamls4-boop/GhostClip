"""Прямая работа с буфером обмена Windows (0% CPU) и определение активного процесса."""

import ctypes
import os
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Настраиваем 64-битные типы аргументов и возвращаемых значений для стабильности на x64 Windows
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
    """Безопасно открывает буфер обмена (до 5 попыток), выполняет action и всегда закрывает его."""
    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                return action()
            finally:
                user32.CloseClipboard()
        time.sleep(delay)
    return default


def read_clipboard_text() -> str:
    """Читает Юникод-текст (UTF-16) из буфера обмена Windows."""

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
    """Записывает Юникод-текст (UTF-16LE) в буфер обмена Windows."""
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
        if not user32.SetClipboardData(CF_UNICODETEXT, memory_handle):
            kernel32.GlobalFree(memory_handle)
            return False
        return True

    return bool(_with_clipboard(_write, default=False))


def wipe_clipboard() -> bool:
    """Мгновенно очищает текущее содержимое буфера обмена Windows."""
    return bool(_with_clipboard(lambda: bool(user32.EmptyClipboard()), default=False))


def get_clipboard_sequence_number() -> int:
    """Возвращает счётчик изменений буфера обмена ядра Windows (0% нагрузки на CPU)."""
    return int(user32.GetClipboardSequenceNumber())


def get_active_process_info() -> tuple[str, str]:
    """Определяет имя (.exe) и полный путь программы-источника копирования."""
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
