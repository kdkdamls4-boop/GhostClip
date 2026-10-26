# 🪟 Разбор файла `ghostclip/clipboard.py` — Win32 API и буфер обмена Windows

Файл [`ghostclip/clipboard.py`](../ghostclip/clipboard.py) — это низкоуровневый системный мост между Python и ядром Windows. Он работает вообще без сторонних библиотек, напрямую через `ctypes`.

---

## ⚡ 1. Главный секрет 0.0% нагрузки на CPU: `GetClipboardSequenceNumber`

Большинство плохих скриптов для буфера работают так: каждые 100 мс открывают буфер, читают текст и сравнивают строки. Это грузит процессор, тормозит систему и конфликтует с другими программами.

Windows сама ведёт системный 32-битный счётчик `GetClipboardSequenceNumber`:

```python
def get_clipboard_sequence_number() -> int:
    """Счетчик изменений буфера ядра Windows (0% нагрузки на CPU при опросе)."""
    return int(user32.GetClipboardSequenceNumber())
```

* Каждый раз, когда любая программа или пользователь нажимает `Ctrl + C`, Windows **увеличивает это число на 1**.
* GhostClip каждые 200 мс просто проверяет: `current_seq == last_seq`.
* Это обычное сравнение двух чисел в оперативной памяти — **0% нагрузки на процессор!**
* Буфер обмена открывается и читается **только тогда, когда это число изменилось**.

---

## 📖 2. Чтение буфера обмена: `read_clipboard_text`

Буфер обмена в Windows — это глобальный ресурс. Если Word или браузер прямо сейчас пишут в него, он заблокирован.

```python
def read_clipboard_text(retries: int = 5, delay: float = 0.03) -> Optional[str]:
    # 1. Цикл повторных попыток: если буфер занят, пробуем 5 раз с паузой 30 мс
    for _ in range(retries):
        # user32.OpenClipboard(None) блокирует буфер для чтения нашим процессом
        if user32.OpenClipboard(None):
            try:
                # 2. CF_UNICODETEXT = 13 — просим Windows вернуть текст в кодировке UTF-16
                h = user32.GetClipboardData(CF_UNICODETEXT)
                if not h:
                    return None

                # 3. h — это дескриптор (хэндл) блока памяти.
                # Функция GlobalLock фиксирует этот блок в памяти и возвращает указатель (адрес)
                ptr = kernel32.GlobalLock(h)
                if not ptr:
                    return None

                try:
                    # 4. ctypes.c_wchar_p считывает текст по этому адресу как строку Python
                    return ctypes.c_wchar_p(ptr).value
                finally:
                    # 5. Обязательно снимаем фиксацию памяти:
                    kernel32.GlobalUnlock(h)
            finally:
                # 6. Обязательно закрываем буфер обмена, чтобы другие программы могли работать!
                user32.CloseClipboard()
        time.sleep(delay)
    return None
```

---

## ✍️ 3. Запись в буфер обмена: `write_clipboard_text`

Чтобы поместить текст в буфер Windows, недостаточно просто передать строку. Windows требует выделить системный глобальный блок памяти:

```python
def write_clipboard_text(text: str, retries: int = 5, delay: float = 0.03) -> bool:
    # 1. Переводим строку в байты UTF-16LE и добавляем нулевой байт окончания строки (\0)
    data = (text + "\0").encode("utf-16-le")

    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                # 2. Очищаем старое содержимое буфера:
                user32.EmptyClipboard()

                # 3. GMEM_MOVEABLE (0x0002) — выделяем глобальный блок памяти нужного размера
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not h_mem:
                    return False

                # 4. Блокируем блок памяти для копирования байтов:
                ptr = kernel32.GlobalLock(h_mem)
                if not ptr:
                    return False

                # 5. Копируем байты нашей строки в системную память Windows:
                ctypes.memmove(ptr, data, len(data))
                kernel32.GlobalUnlock(h_mem)

                # 6. Передаем блок памяти в буфер обмена под типом CF_UNICODETEXT:
                return bool(user32.SetClipboardData(CF_UNICODETEXT, h_mem))
            finally:
                user32.CloseClipboard()
        time.sleep(delay)
    return False
```

---

## 🕵️ 4. Как узнать, кто скопировал текст: `get_active_process_info`

Когда в буфер попадает секрет или ссылка, нам важно знать, из какой программы это пришло (`chrome.exe`, `telegram.exe`, `code.exe`).

```python
def get_active_process_info() -> Tuple[str, str]:
    # 1. Сначала спрашиваем у Windows: кто ВЛАДЕЛЕЦ буфера обмена?
    # Если это фоновый процесс, резервный вариант — GetForegroundWindow (окно в фокусе)
    hwnd = user32.GetClipboardOwner() or user32.GetForegroundWindow()
    if not hwnd:
        return "Фоновый процесс", "N/A"

    # 2. По дескриптору окна (hwnd) получаем идентификатор процесса (PID):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return "Системный процесс", "N/A"

    # 3. PROCESS_QUERY_LIMITED_INFORMATION (0x1000) — запрашиваем права
    # на чтение информации о процессе (работает даже без прав администратора!):
    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h_proc:
        return f"PID:{pid.value}", "N/A"

    try:
        # 4. Создаем буфер для имени файла и вызываем QueryFullProcessImageNameW:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            # Например, получаем: "C:\Program Files\Google\Chrome\Application\chrome.exe"
            # os.path.basename оставляет только "chrome.exe":
            return os.path.basename(buf.value), buf.value
        return f"PID:{pid.value}", "N/A"
    finally:
        # 5. Обязательно закрываем дескриптор процесса, чтобы не было утечек:
        kernel32.CloseHandle(h_proc)
```
