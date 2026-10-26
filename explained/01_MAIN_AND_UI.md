# 🖥️ Разбор файла `main.py` — Главная точка входа и интерфейс

Файл [`main.py`](../main.py) — это дирижер проекта. Он запускает потоки, выводит единый экран управления, моментально перехватывает нажатия клавиш без `Enter` и отслеживает буфер с нулевой нагрузкой на процессор.

---

## 🏗️ Общая структура `main.py`

При запуске функция `main()` запускает 3 параллельных процесса:

```python
def main():
    global tray_manager
    # 1. Создаем менеджер трея (иконка щита возле часов + ПКМ-меню):
    tray_manager = TrayManager(
        on_clear_clipboard=handle_clear_clipboard,
        on_panic=handle_panic,
        on_toggle_option=handle_toggle_option,
        on_exit=handle_exit,
    )
    tray_manager.start()  # Запускает поток Win32 сообщений трея

    # 2. Отрисовываем единый стартовый экран:
    render_screen()

    # 3. Запускаем поток слушателя клавиатуры (мгновенные клавиши):
    key_thread = threading.Thread(target=run_key_listener, daemon=True)
    key_thread.start()

    # 4. В главном потоке крутится цикл слежения за буфером:
    run_monitor()
```

---

## ⚡ 1. Мгновенный перехват клавиш без `Enter` (`msvcrt.getwch`)

В обычном Python вызов `input()` блокирует выполнение и требует обязательно нажимать `Enter`. Кроме того, при вводе случайных цифр они печатаются прямо в консоль.

В GhostClip используется функция `msvcrt.getwch()` (встроенная в стандартную библиотеку Python для Windows):

```python
def run_key_listener():
    while True:
        try:
            # msvcrt.getwch() ждет ровно ОДНО нажатие клавиши
            # и возвращает символ СРАЗУ, без нажатия Enter!
            ch = msvcrt.getwch()

            # Игнорируем стрелочки и спецкнопки (F1-F12), у которых 2 байта
            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue

            key = ch.lower()

            # Если нажата цифра 1-6 — переключаем тумблер:
            if key in ("1", "2", "3", "4", "5", "6"):
                handle_toggle_option(int(key))
            elif key in ("b", "и"):  # 'и' — русская раскладка на клавише B
                handle_clear_clipboard()
            elif key in ("p", "з"):  # 'з' — русская раскладка на клавише P
                handle_panic()
            elif key in ("t", "е"):  # 'е' — русская раскладка на клавише T
                tray_manager.hide_console_to_tray()
            elif key in ("c", "с"):  # 'с' — русская раскладка на клавише C
                _log_lines.clear()
                render_screen()
            elif key in ("q", "й", "\x03"):
                handle_exit()
            # 💡 ГЛАВНОЕ: любые другие цифры (7, 8, 9, 0) просто игнорируются!
            # Они не попадают в print и не забивают консоль!
        except Exception:
            time.sleep(0.1)
```

---

## 📋 2. Единый экран: таблица сверху + живой лог снизу

Чтобы консоль не превращалась в кашу из повторяющихся меню, экран разделен на две зоны:

1. **Верхняя зона (`render_screen`)**:
   Очищает экран (`cls`) и заново рисует актуальное состояние всех 6 тумблеров `[ВКЛ]` / `[ВЫКЛ]`.
2. **Нижняя зона (`_log_lines`)**:
   Хранит последние 25 событий буфера. При каждом копировании или очистке добавляется новая строчка:

```python
def add_log(msg: str):
    """Потокобезопасно добавляет сообщение в живой лог и печатает его."""
    with _ui_lock:
        _log_lines.append(msg)
        if len(_log_lines) > MAX_LOG_LINES:
            _log_lines.pop(0)  # Удаляем самую старую строчку, если их больше 25
        print(msg)
```

---

## 🔄 3. Цикл мониторинга буфера (`run_monitor`)

```python
def run_monitor():
    last_seq = get_clipboard_sequence_number()
    last_processed_text = ""
    is_internal_update = False

    while True:
        time.sleep(0.2)

        # 1. Проверяем, не свернул ли пользователь окно кнопкой [_]
        if tray_manager:
            tray_manager.check_minimized_to_tray()

        # 2. ПРОВЕРКА 0% CPU:
        current_seq = get_clipboard_sequence_number()
        if current_seq == last_seq:
            continue  # Число не изменилось — в буфере ничего нового, спим дальше!

        last_seq = current_seq

        # 3. Защита от бесконечного цикла:
        # Если очистку буфера только что сделал сам GhostClip, пропускаем этот шаг
        if is_internal_update:
            is_internal_update = False
            continue

        text = read_clipboard_text()
        if not text or text == last_processed_text:
            continue

        last_processed_text = text
        proc_name, _ = get_active_process_info()  # Узнаем программу (chrome.exe)

        # 4. Проверка на секреты (карты, токены, пароли):
        secret_match = detect_secret(text) if config.detect_secrets else None
        if secret_match:
            # Сработал секрет -> запускаем таймер самоуничтожения
            ...
```

---

## 🛑 4. Разница между Очисткой `[B]` и Паникой `[P]`

* **`handle_clear_clipboard()` (`[B]` / рус. `[И]`):**
  Очищает только текущий текст из буфера обмена (`wipe_clipboard()`). История `Win + V` не сбрасывается.
* **`handle_panic()` (`[P]` / рус. `[З]`):**
  Экстренный режим. Вызывает `panic_wipe()`: затирает текущий буфер текстом-заглушкой, стирает память и **полностью обнуляет облачный и локальный журнал `Win + V`**.
