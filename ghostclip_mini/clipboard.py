"""
ghostclip_mini/clipboard.py
Прямая работа с буфером обмена Windows (0% нагрузки на CPU) и определение активного процесса.
"""

import os
import time
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13

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

def wipe_clipboard() -> bool:
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return False

def get_clipboard_sequence_number() -> int:
    return user32.GetClipboardSequenceNumber()

def get_active_process_info() -> tuple[str, str]:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "Unknown", ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return "Unknown", ""
    buf = ctypes.create_unicode_buffer(1024)
    sz = wintypes.DWORD(1024)
    try:
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)):
            return os.path.basename(buf.value), buf.value
    finally:
        kernel32.CloseHandle(h)
    return "Unknown", ""
