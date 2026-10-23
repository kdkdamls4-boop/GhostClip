"""
GhostClip Shield — Главная точка входа.
Поддерживает работу в системном трее Windows (ПКМ-меню возле часов),
отдельную очистку буфера [B], панику [P], сворачивание в трей [T] и переключатели [1-6].
"""
# ═══════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ ФАЙЛ. Запускается командой:  python main.py
#
#  Схема работы:
#    main()  ─┬─► TrayManager.start()  → поток 1: иконка в трее
#             ├─► run_key_listener()   → поток 2: ждёт нажатия клавиш
#             └─► run_monitor()        → основной поток: следит за буфером
#  (+ timer.py запускает свой поток, когда тикает таймер)
# ═══════════════════════════════════════════════════════════════════

import sys        # sys — доступ к настройкам самого Python (вывод, пути поиска модулей)
import os         # os — работа с ОС (очистка экрана, пути)
import time       # time — паузы
import datetime   # datetime — текущее время для логов
import threading  # threading — потоки
import msvcrt     # msvcrt — только для Windows: читать нажатия клавиш без Enter

sys.stdout.reconfigure(encoding="utf-8")
# Переключаем вывод в консоль на UTF-8. Без этого рамки ╔═╗ и русский текст
# в некоторых консолях Windows превращаются в «????».

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Разберём изнутри наружу:
#   __file__                — путь к этому файлу (main.py)
#   os.path.abspath(...)    — превращаем его в полный путь C:\...\main.py
#   os.path.dirname(...)    — берём только папку C:\...\
#   sys.path.insert(0, ...) — добавляем эту папку В НАЧАЛО списка мест,
#                             где Python ищет модули.
# Итог: `from ghostclip import ...` сработает, даже если запустить main.py из другой папки.

from ghostclip import (
    # Благодаря ghostclip/__init__.py всё берётся из одного места.
    read_clipboard_text,
    write_clipboard_text,
    wipe_clipboard,
    get_clipboard_sequence_number,
    get_active_process_info,
    sanitize_text,
    detect_secret,
    mask_secret,
    ghost_timer,
    panic_wipe,
    log_audit,
    config,
    TrayManager,
)


# ═══════════════════════════════════════════════════════════════════
#  ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ (видны во всём файле)
# ═══════════════════════════════════════════════════════════════════

_ui_lock = threading.Lock()
# Замок для экрана. Сюда пишут сразу несколько потоков (монитор, клавиши, таймер).
# Без замка строки перемешались бы.

_log_lines: list[str] = []
# Список строк живого лога. `: list[str]` — подсказка «это список строк».

MAX_LOG_LINES = 25
# Храним и показываем не больше 25 последних строк.

tray_manager: TrayManager = None  # type: ignore
# Пока None, настоящий объект создастся в main().
# `# type: ignore` — просьба к редактору не ругаться,
# что None не похож на TrayManager.


# ═══════════════════════════════════════════════════════════════════
#  ОТРИСОВКА ЭКРАНА
# ═══════════════════════════════════════════════════════════════════

def render_screen():
    """Отрисовывает единое меню сверху и живой поток логов снизу."""
    with _ui_lock:
        statuses = config.get_status_dict()
        # Словарь {1: ("название", True), 2: (...), ...}

        def badge(enabled: bool) -> str:
            # Маленькая функция внутри функции, нужна только здесь.
            return "[ВКЛ] " if enabled else "[ВЫКЛ]"

        timer_str = (
            f"АКТИВЕН ({ghost_timer.remaining_seconds()} сек)"
            if ghost_timer.is_armed()
            else "Ожидание..."
        )
        # Тернарный оператор, разбитый на 3 строки для читаемости.

        os.system("cls" if os.name == "nt" else "clear")
        # os.system(...) — выполнить команду консоли.
        # os.name == "nt" — мы на Windows? Тогда "cls" (очистить экран), иначе "clear" (Linux/Mac).

        print("╔═══════════════════════════════════════════════════════════════════════╗")
        print("║                    GhostClip Shield (Консоль + Трей)                  ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║  [1] Чистка трекинг-меток в URL (utm, fbclid, si):       {badge(statuses[1][1])}       ║")
        # statuses[1]    → ("Чистка ссылок...", True)
        # statuses[1][1] → True  (второй элемент, нумерация с 0)
        # badge(True)    → "[ВКЛ] "
        print(f"║  [2] Удаление невидимых знаков (Zero-Width):             {badge(statuses[2][1])}       ║")
        print(f"║  [3] Детекция секретов (API-ключи, карты, пароли):       {badge(statuses[3][1])}       ║")
        print(f"║  [4] Таймер самоуничтожения (45 сек):                    {badge(statuses[4][1])}       ║")
        print(f"║  [5] Зачистка истории Win+V:                             {badge(statuses[5][1])}       ║")
        print(f"║  [6] Журнал аудита (clipboard_access.log):               {badge(statuses[6][1])}       ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║  Таймер: {timer_str:<25}  (Иконка щита активна в трее!)     ║")
        # {timer_str:<25} — выровнять текст влево и дополнить пробелами до 25 символов,
        # чтобы рамка не «поехала».
        print("║  [1-6] Вкл/Выкл | [B] Очистить буфер | [P] ПАНИКА (Буфер + Win+V)     ║")
        print("║  [T] Скрыть в трей (или кнопка [_])  | [C] Очистить лог | [Q] Выход   ║")
        print("╚═══════════════════════════════════════════════════════════════════════╝")
        print("\n--- ЖИВОЙ ЛОГ СОБЫТИЙ БУФЕРА ---")
        if not _log_lines:
            # Пустой список считается «ложью».
            print("[*] Ожидание копирования в буфер обмена...")
        else:
            for line in _log_lines[-MAX_LOG_LINES:]:
                # [-25:] — последние 25 элементов.
                print(line)


def add_log(msg: str):
    """Добавляет строку в живой лог и сразу выводит её на экран."""
    with _ui_lock:
        _log_lines.append(msg)
        if len(_log_lines) > MAX_LOG_LINES:
            _log_lines.pop(0)
            # .pop(0) — удалить первый (самый старый) элемент.
        print(msg)


# ═══════════════════════════════════════════════════════════════════
#  ОБРАБОТЧИКИ ДЕЙСТВИЙ
#  Их вызывают и клавиши в консоли, и пункты меню в трее
# ═══════════════════════════════════════════════════════════════════

def handle_clear_clipboard():
    """Обычная очистка буфера обмена (без сброса всей истории Win+V)."""
    ghost_timer.disarm()          # остановить таймер (стирать уже нечего)
    wipe_clipboard()              # очистить буфер
    now_time = datetime.datetime.now().strftime("%H:%M:%S")   # "10:16:13"
    if config.audit_logging:
        log_audit("CLIPBOARD_CLEARED", "User", "[БУФЕР_ОЧИЩЕН]", "Обычная очистка буфера")
    add_log(f"[{now_time}] [ОЧИСТКА БУФЕРА] Текущее содержимое буфера обмена удалено.")
    if tray_manager:
        # Если трей создан (не None), показываем всплывающее уведомление.
        tray_manager.show_balloon("Буфер очищен", "Текущее содержимое буфера обмена удалено.")


def handle_panic():
    """Экстренная ПАНИКА: затирает буфер обмена И всю историю Win+V."""
    ghost_timer.disarm()
    panic_wipe()
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging:
        log_audit("PANIC_FLUSH", "User", "[ВСЕ_ОЧИЩЕНО]", "Экстренный сброс буфера и Win+V")
    add_log(f"[{now_time}] [ПАНИКА!] БУФЕР ОБМЕНА И ИСТОРИЯ WIN+V ЗАТЕРТЫ В НОЛЬ!")
    if tray_manager:
        tray_manager.show_balloon("ПАНИКА: Всё стерто!", "Буфер обмена и история Win+V полностью уничтожены.")


def handle_toggle_option(opt_id: int):
    """Переключает функцию [1-6] из консоли или из ПКМ-меню трея."""
    name, new_val = config.toggle(opt_id)
    # toggle возвращает пару, раскладываем её в две переменные.
    state_str = "ВКЛ" if new_val else "ВЫКЛ"
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    with _ui_lock:
        _log_lines.append(f"[{now_time}] [ТУМБЛЕР {opt_id}] {name} -> {state_str}")
    render_screen()
    # Перерисовываем экран, чтобы обновились [ВКЛ]/[ВЫКЛ].
    # Важно: render_screen() вызывается ПОСЛЕ выхода из `with`,
    # потому что внутри он сам захватывает тот же замок.
    # Обычный Lock нельзя захватить дважды, программа бы зависла.


def handle_exit():
    """Полный выход из программы."""
    if tray_manager:
        tray_manager.remove_icon()
        # Убираем иконку из трея, иначе она «повисит», пока не наведёшь мышь.
    print("\n[*] Завершение работы GhostClip...")
    os._exit(0)
    # Немедленно убить процесс со всеми потоками. 0 = «завершился без ошибок».
    # Обычный sys.exit() не сработал бы из фонового потока.


# ═══════════════════════════════════════════════════════════════════
#  ГЛАВНЫЙ ЦИКЛ: СЛЕЖЕНИЕ ЗА БУФЕРОМ
# ═══════════════════════════════════════════════════════════════════

def run_monitor():
    """
    Основной цикл слежения за буфером обмена (0% нагрузки на CPU).
    Также проверяет, не свернул ли пользователь окно консоли, чтобы спрятать его в трей.
    """
    last_seq = get_clipboard_sequence_number()
    # Запоминаем текущий номер изменения буфера.

    last_processed_text = ""
    # Последний обработанный текст, чтобы не обрабатывать одно и то же дважды.

    is_internal_update = False
    # Флаг «это МЫ сами изменили буфер». Нужен, чтобы программа
    # не реагировала на собственную запись (иначе получится бесконечный цикл).

    while True:
        # Бесконечный цикл. Работает, пока программу не закроют.
        try:
            time.sleep(0.2)
            # Пауза 0.2 сек = 5 проверок в секунду. Поэтому процессор почти не нагружается.

            # Если пользователь свернул консоль кнопкой [_] — прячем окно в трей
            if tray_manager:
                tray_manager.check_minimized_to_tray()

            current_seq = get_clipboard_sequence_number()
            if current_seq == last_seq:
                continue
                # Номер не изменился, значит никто ничего не копировал.
                # continue = сразу на следующий круг цикла.

            last_seq = current_seq

            if is_internal_update:
                # Изменение сделали мы сами (записали очищенную ссылку).
                # Сбрасываем флаг и пропускаем этот круг.
                is_internal_update = False
                continue

            text = read_clipboard_text()
            if not text or text == last_processed_text:
                # Текста нет (например, скопирована картинка) или он тот же самый.
                continue

            last_processed_text = text
            proc_name, _ = get_active_process_info()
            # Функция возвращает (имя, путь). Путь нам не нужен, поэтому пишем _.
            now_time = datetime.datetime.now().strftime("%H:%M:%S")

            # ───────────────────────────────────────────────────────
            # 1. Очистка ссылок и невидимых символов (если включены [1] или [2])
            # ───────────────────────────────────────────────────────
            if config.clean_urls or config.clean_zero_width:
                cleaned_text, removed_params, zw_count = sanitize_text(
                    text,
                    clean_urls_enabled=config.clean_urls,
                    clean_zw_enabled=config.clean_zero_width,
                )

                if removed_params or zw_count > 0:
                    # Что-то реально удалили, значит надо записать чистый текст обратно.
                    details = []
                    if removed_params:
                        details.append(f"удалены метки: {', '.join(set(removed_params))}")
                        # set(...) — убрать повторы. ', '.join(...) — склеить через запятую.
                    if zw_count > 0:
                        details.append(f"невидимых знаков: {zw_count}")
                    add_log(f"[{now_time}] [ОЧИСТКА URL] ({proc_name}) -> {' | '.join(details)}")

                    is_internal_update = True
                    # Поднимаем флаг: «следующее изменение буфера сделали мы».
                    write_clipboard_text(cleaned_text)
                    last_processed_text = cleaned_text
                    last_seq = get_clipboard_sequence_number()

                    if config.audit_logging:
                        log_audit(
                            event="URL_CLEANED",
                            process=proc_name,
                            content=cleaned_text,
                            extra=" | ".join(details),
                        )
                    text = cleaned_text
                    # Дальше проверяем на секреты уже очищенный текст.

            # ───────────────────────────────────────────────────────
            # 2. Детекция секретов (если включен тумблер [3])
            # ───────────────────────────────────────────────────────
            secret_match = detect_secret(text) if config.detect_secrets else None
            # Если детекция выключена, сразу None.

            if secret_match:
                cat, desc = secret_match
                # cat — категория ("API_KEY"), desc — описание ("OpenAI API Key").
                add_log(f"[{now_time}] [СЕКРЕТ!] ({proc_name}) {desc}: {mask_secret(text)}")

                if config.ghost_timer_enabled:
                    add_log(f"[{now_time}] [ТАЙМЕР] Удаление секрета через {config.timer_seconds} сек...")
                    ghost_timer.arm(
                        config.timer_seconds,
                        desc,
                        on_expire=lambda m: add_log(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {m}"),
                        # lambda m: ... — функция без имени, принимает m (сообщение).
                        # Таймер вызовет её через 45 сек, и она допишет в лог время и сообщение.
                    )

                if config.audit_logging:
                    log_audit(
                        event="SECRET_ARMED",
                        process=proc_name,
                        content=text,
                        # Не страшно, что передаём сам секрет: log_audit его замаскирует.
                        extra=f"Детекция: {desc} (Таймер: {config.timer_seconds}с)",
                    )
            else:
                # Скопирован обычный текст.
                if ghost_timer.is_armed():
                    ghost_timer.disarm()
                    # Секрет в буфере уже перезаписан обычным текстом, стирать нечего.
                    add_log(f"[{now_time}] [ИНФО] Скопирован обычный текст, таймер сброшен.")

                preview = text.strip().replace("\r\n", " ").replace("\n", " ")
                if len(preview) > 45:
                    preview = preview[:45] + "..."
                add_log(f"[{now_time}] [КОПИЯ] ({proc_name}) \"{preview}\" ({len(text)} симв.)")
                # \" — кавычка внутри строки (экранированная обратным слэшем).

                if config.audit_logging:
                    log_audit(event="CLIPBOARD_SET", process=proc_name, content=text)

        except KeyboardInterrupt:
            # Пользователь нажал Ctrl+C, выходим из цикла.
            break
        except Exception:
            # Любая другая ошибка: не падаем, ждём полсекунды и продолжаем.
            time.sleep(0.5)


# ═══════════════════════════════════════════════════════════════════
#  СЛУШАТЕЛЬ КЛАВИАТУРЫ (работает в отдельном потоке)
# ═══════════════════════════════════════════════════════════════════

def run_key_listener():
    """
    Ждёт нажатия клавиш без Enter (msvcrt.getwch).
    Цифры 1-6 мгновенно переключают тумблер, B очищает буфер, P включает панику, T прячет в трей.
    """
    while True:
        try:
            ch = msvcrt.getwch()
            # Ждёт нажатия ОДНОЙ клавиши и возвращает символ. Нажимать Enter не нужно.

            if ch in ("\x00", "\xe0"):
                # Стрелки и F1-F12 присылают ДВА кода: сначала \x00 или \xe0, потом сам код клавиши.
                # Читаем второй код и выбрасываем его: эти клавиши мы не используем.
                msvcrt.getwch()
                continue

            key = ch.lower()
            # Приводим к нижнему регистру, чтобы B и b работали одинаково.

            if key in ("1", "2", "3", "4", "5", "6"):
                handle_toggle_option(int(key))
                # int("3") → 3. Превращаем символ в число.
            elif key in ("b", "и"):  # 'и' — русская раскладка на клавише B
                handle_clear_clipboard()
            elif key in ("p", "з"):  # 'з' — русская раскладка на клавише P
                handle_panic()
            elif key in ("t", "е"):  # 'е' — русская раскладка на клавише T
                if tray_manager:
                    tray_manager.hide_console_to_tray()
            elif key in ("c", "с"):  # 'с' — русская раскладка на клавише C
                with _ui_lock:
                    _log_lines.clear()
                    # .clear() — очистить список полностью.
                render_screen()
            elif key in ("q", "й", "\x03"):
                # \x03 — это Ctrl+C.
                handle_exit()
        except Exception:
            time.sleep(0.1)


# ═══════════════════════════════════════════════════════════════════
#  ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════

def main():
    global tray_manager
    # «Внутри этой функции tray_manager — это ГЛОБАЛЬНАЯ переменная файла».
    # Без этой строки Python создал бы новую локальную переменную,
    # а глобальная так и осталась бы None.

    tray_manager = TrayManager(
        on_clear_clipboard=handle_clear_clipboard,
        on_panic=handle_panic,
        on_toggle_option=handle_toggle_option,
        on_exit=handle_exit,
        # Передаём функции БЕЗ скобок, то есть сами функции, а не результат их вызова.
        # Трей вызовет их, когда пользователь кликнет пункт меню. Это и есть callback.
    )
    tray_manager.start()
    # Запускаем иконку в трее (в отдельном потоке).

    render_screen()
    # Рисуем меню.

    key_thread = threading.Thread(target=run_key_listener, daemon=True)
    key_thread.start()
    # Запускаем слушатель клавиш в отдельном потоке.

    try:
        run_monitor()
        # Основной поток уходит в бесконечный цикл слежения за буфером.
    except KeyboardInterrupt:
        handle_exit()


if __name__ == "__main__":
    # __name__ равно "__main__", только если файл запустили напрямую (python main.py).
    # Если файл импортировали из другого кода, main() НЕ запустится.
    main()
