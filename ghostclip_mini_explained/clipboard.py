"""
ghostclip_mini_explained/clipboard.py
Файл 4 из 7: Прямая работа с буфером обмена Windows (0% нагрузки на CPU) и определение активного процесса.
"""

import os       # os — получение имени исполняемого файла из полного пути
import time     # time — микропаузы при повторных попытках захвата буфера
import ctypes   # ctypes — вызов нативных Си-функций Win32 API напрямую из Python
from ctypes import wintypes  # Стандартные типы данных Windows (DWORD, HWND, WCHAR)

# Загружаем системные библиотеки Windows
user32 = ctypes.windll.user32      # Функции оконной подсистемы и буфера обмена
kernel32 = ctypes.windll.kernel32  # Функции работы с памятью и процессами

# Константы Win32 API
GMEM_MOVEABLE = 0x0002   # Флаг выделения перемещаемой глобальной памяти Windows
CF_UNICODETEXT = 13      # Формат данных: Юникод-текст (UTF-16LE)

def read_clipboard_text() -> str:
    """
    Безопасно читает Юникод-текст из буфера обмена Windows.
    Делает до 5 попыток с задержкой 20 мс, если буфер временно занят другой программой.
    """
    for _ in range(5):
        # OpenClipboard(None) блокирует буфер для текущего потока
        if user32.OpenClipboard(None):
            try:
                # Получаем дескриптор памяти, где хранится текст
                h_mem = user32.GetClipboardData(CF_UNICODETEXT)
                if h_mem:
                    # Блокируем блок памяти и получаем указатель на сырые байты
                    ptr = kernel32.GlobalLock(h_mem)
                    if ptr:
                        # Читаем нуль-терминированную Юникод-строку по указателю ptr
                        text = ctypes.wstring_at(ptr)
                        kernel32.GlobalUnlock(h_mem)  # Снимаем блокировку памяти
                        return text
                return ""  # В буфере нет текста (например, там картинка или файл)
            finally:
                # ВСЕГДА освобождаем буфер обмена для остальных программ
                user32.CloseClipboard()
        time.sleep(0.02)
    return ""

def write_clipboard_text(text: str) -> bool:
    """
    Записывает строку Юникод-текста в буфер обмена Windows.
    """
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()  # Очищаем старые данные любого формата
                # Кодируем строку в UTF-16LE и добавляем 2 нулевых байта окончания строки \0\0
                raw = text.encode("utf-16le") + b"\x00\x00"
                # Выделяем блок глобальной памяти Windows нужного размера
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(raw))
                if h_mem:
                    ptr = kernel32.GlobalLock(h_mem)
                    if ptr:
                        # Копируем наши байты в выделенную системную память
                        ctypes.memmove(ptr, raw, len(raw))
                        kernel32.GlobalUnlock(h_mem)
                        # Передаём владение памятью буферу обмена
                        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                        return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.02)
    return False

def wipe_clipboard() -> bool:
    """Быстро очищает буфер обмена Windows."""
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
    """
    Возвращает системный счётчик изменений буфера обмена Windows.
    Windows автоматически увеличивает это число каждый раз, когда любая программа меняет буфер.
    Это позволяет отслеживать копирование без перегрузки процессора (0% CPU).
    """
    return user32.GetClipboardSequenceNumber()

def get_active_process_info() -> tuple[str, str]:
    """
    Определяет имя исполняемого файла (.exe) приложения, из которого было выполнено копирование.
    """
    hwnd = user32.GetForegroundWindow()  # Получаем окно на переднем плане
    if not hwnd:
        return "Unknown", ""

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))  # Получаем ID процесса (PID)

    # Открываем процесс с флагом PROCESS_QUERY_LIMITED_INFORMATION (0x1000)
    h_proc = kernel32.OpenProcess(0x1000, False, pid.value)
    if not h_proc:
        return "Unknown", ""

    buf = ctypes.create_unicode_buffer(1024)
    sz = wintypes.DWORD(1024)
    try:
        # Узнаём полный путь к файлу запущенной программы
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(sz)):
            full_path = buf.value
            return os.path.basename(full_path), full_path  # Возвращаем ("chrome.exe", "C:\...\chrome.exe")
    finally:
        kernel32.CloseHandle(h_proc)  # Закрываем дескриптор процесса
    return "Unknown", ""
