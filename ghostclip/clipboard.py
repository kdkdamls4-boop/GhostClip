"""Низкоуровневая работа с буфером обмена и процессами Windows (0% нагрузки на CPU)."""

import os
import time
import ctypes
from ctypes import wintypes
from typing import Optional, Tuple

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Настройка 64-битных дескрипторов указателей для стабильной работы в 64-bit Windows
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]


def get_clipboard_sequence_number() -> int:
    """Счетчик изменений буфера ядра Windows (0% нагрузки на CPU при опросе)."""
    return int(user32.GetClipboardSequenceNumber())


def read_clipboard_text(retries: int = 5, delay: float = 0.03) -> Optional[str]:
    """Читает UTF-16 текст из буфера обмена."""
    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                h = user32.GetClipboardData(CF_UNICODETEXT)
                if not h:
                    return None
                ptr = kernel32.GlobalLock(h)
                if not ptr:
                    return None
                try:
                    return ctypes.c_wchar_p(ptr).value
                finally:
                    kernel32.GlobalUnlock(h)
            finally:
                user32.CloseClipboard()
        time.sleep(delay)
    return None


def write_clipboard_text(text: str, retries: int = 5, delay: float = 0.03) -> bool:
    """Записывает очищенный UTF-16LE текст обратно в буфер."""
    data = (text + "\0").encode("utf-16-le")
    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not h_mem:
                    return False
                ptr = kernel32.GlobalLock(h_mem)
                if not ptr:
                    return False
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(h_mem)
                return bool(user32.SetClipboardData(CF_UNICODETEXT, h_mem))
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
    """Определяет программу, скопировавшую данные (проверяет владельца буфера и активное окно)."""
    hwnd = user32.GetClipboardOwner() or user32.GetForegroundWindow()
    if not hwnd:
        return "Фоновый процесс", "N/A"

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return "Системный процесс", "N/A"

    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h_proc:
        return f"PID:{pid.value}", "N/A"
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value), buf.value
        return f"PID:{pid.value}", "N/A"
    finally:
        kernel32.CloseHandle(h_proc)
