# 🛡️ Разбор `ghostclip/tray/` — Системный трей Windows и нативное ПКМ-меню

Пакет [`ghostclip/tray/`](../ghostclip/tray) отвечает за работу иконки щита возле часов в Windows, отображение системного контекстного меню по правому клику (ПКМ) и безопасное скрытие консоли.

---

## 🏗️ Как Windows общается с иконками трея

В Windows системный трей устроен так:
1. Иконку в трее нельзя добавить «просто так» — Windows требует, чтобы у иконки было **ОКНО-владелец**, которому операционная система будет отправлять сообщения о кликах мыши.
2. GhostClip создает **невидимое окно сообщений** (`CreateWindowExW`), которое не отображается на экране.
3. Через функцию `Shell_NotifyIconW` мы регистрируем иконку в трее и говорим Windows:
   * «Когда пользователь кликнет по иконке, отправь нашему невидимому окну сообщение с кодом `WM_USER + 20`».
4. Оконная процедура `_wnd_proc` перехватывает клики:
   * **Двойной клик ЛКМ (`WM_LBUTTONDBLCLK`)** — показать окно консоли на передний план.
   * **Правый клик ПКМ (`WM_RBUTTONUP` / `WM_CONTEXTMENU`)** — показать контекстное меню.

---

## 🪟 1. Структура `NOTIFYICONDATAW` (размер 976 байт на 64-bit Windows)

Структура `NOTIFYICONDATAW` передает в Windows параметры иконки:

```python
class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),          # Размер структуры (976 байт в 64-bit Windows)
        ("hWnd", wintypes.HWND),             # Дескриптор нашего окна
        ("uID", wintypes.UINT),              # Уникальный номер иконки (1)
        ("uFlags", wintypes.UINT),           # Флаги: иконка + подсказка + сообщения
        ("uCallbackMessage", wintypes.UINT), # Наш код сообщения (WM_USER + 20)
        ("hIcon", wintypes.HICON),           # Дескриптор загруженной иконки
        ("szTip", wintypes.WCHAR * 128),     # Всплывающая подсказка при наведении мыши
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),    # Текст всплывающего уведомления (Balloon)
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),# Заголовок всплывающего уведомления
        ("dwInfoFlags", wintypes.DWORD),     # Тип уведомления (NIIF_INFO)
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]
```

Иконка щита загружается прямо из встроенных ресурсов Windows без сторонних файлов картинок:
```python
# IDI_SHIELD = 32518 — это системная иконка щита контроля учетных записей Windows (UAC Shield):
hicon = user32.LoadIconW(None, ctypes.cast(32518, wintypes.LPCWSTR))
```

---

## 🖱️ 2. Нативное контекстное меню по правому клику (ПКМ)

Когда пользователь нажимает ПКМ по иконке в трее, вызываются функции создания меню Windows:

```python
def _show_context_menu(self):
    # 1. Создаем всплывающее меню Windows:
    hmenu = user32.CreatePopupMenu()

    # 2. Добавляем основные команды:
    user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_TOGGLE_CONSOLE, "Управление (Открыть консоль)")
    user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_CLEAR_CLIPBOARD, "Очистить буфер обмена")
    user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_PANIC, "ПАНИКА (Стереть буфер + Win+V)")
    user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)

    # 3. Добавляем переключатели [1-6] с галочками (MF_CHECKED):
    for opt_id, (desc, enabled) in config.get_status_dict().items():
        flag = MF_STRING | (MF_CHECKED if enabled else MF_UNCHECKED)
        user32.AppendMenuW(hmenu, flag, ID_TRAY_OPT_BASE + opt_id, f"[{opt_id}] {desc}")

    user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_EXIT, "Полный выход")

    # 4. Узнаем позицию курсора мыши и показываем меню ровно в точке клика:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(self._hwnd)

    cmd = user32.TrackPopupMenu(
        hmenu,
        TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
        pt.x, pt.y, 0, self._hwnd, None,
    )
    user32.DestroyMenu(hmenu)  # Освобождаем память меню

    # 5. Обрабатываем выбранную команду:
    if cmd == ID_TRAY_CLEAR_CLIPBOARD:
        self.on_clear_clipboard()
    elif cmd == ID_TRAY_PANIC:
        self.on_panic()
    ...
```

---

## 🛡️ 3. Защита консоли от случайного закрытия и скрытие в трей

В стандартном окне консоли Windows нажатие на крестик `[X]` сразу убивает процесс операционной системой.

GhostClip решает это на системном уровне:

```python
def disable_close_button(self):
    """Отключает системную кнопку [X] у окна консоли."""
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        hmenu = user32.GetSystemMenu(hwnd, False)
        if hmenu:
            # SC_CLOSE (0xF060) — удаляем команду закрытия из меню окна.
            # Теперь крестик [X] становится серым и неактивным!
            user32.DeleteMenu(hmenu, 0xF060, 0x00000000)
```

А если пользователь нажимает кнопку свернуть `[_]` на заголовке окна или клавишу `T` в консоли:

```python
def hide_console_to_tray(self):
    """Скрывает окно консоли в трей."""
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        # SW_HIDE (0) — окно полностью исчезает с экрана и с панели задач:
        user32.ShowWindow(hwnd, 0)
        self.show_balloon("GhostClip Shield в трее", "Защита продолжает работать в фоне.")

def show_console_from_tray(self):
    """Возвращает окно консоли на передний план."""
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE (9) — восстановить размер
        user32.ShowWindow(hwnd, 5)  # SW_SHOW (5) — показать
        user32.SetForegroundWindow(hwnd)  # Вывести на передний план
```
