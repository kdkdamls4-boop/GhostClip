"""
GhostClip Shield — Главная точка входа.
Поддерживает работу в системном трее Windows (ПКМ-меню возле часов),
отдельную очистку буфера [B], панику [P], сворачивание в трей [T] и переключатели [1-6].
"""

import sys
import os
import time
import datetime
import threading
import msvcrt

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ghostclip import (
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

_ui_lock = threading.Lock()
_log_lines: list[str] = []
MAX_LOG_LINES = 25
tray_manager: TrayManager = None  # type: ignore


def render_screen():
    """Отрисовывает единое меню сверху и живой поток логов снизу."""
    with _ui_lock:
        statuses = config.get_status_dict()

        def badge(enabled: bool) -> str:
            return "[ВКЛ] " if enabled else "[ВЫКЛ]"

        timer_str = (
            f"АКТИВЕН ({ghost_timer.remaining_seconds()} сек)"
            if ghost_timer.is_armed()
            else "Ожидание..."
        )

        os.system("cls" if os.name == "nt" else "clear")
        print("╔═══════════════════════════════════════════════════════════════════════╗")
        print("║                    GhostClip Shield (Консоль + Трей)                  ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║  [1] Чистка трекинг-меток в URL (utm, fbclid, si):       {badge(statuses[1][1])}       ║")
        print(f"║  [2] Удаление невидимых знаков (Zero-Width):             {badge(statuses[2][1])}       ║")
        print(f"║  [3] Детекция секретов (API-ключи, карты, пароли):       {badge(statuses[3][1])}       ║")
        print(f"║  [4] Таймер самоуничтожения (45 сек):                    {badge(statuses[4][1])}       ║")
        print(f"║  [5] Зачистка истории Win+V:                             {badge(statuses[5][1])}       ║")
        print(f"║  [6] Журнал аудита (clipboard_access.log):               {badge(statuses[6][1])}       ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║  Таймер: {timer_str:<25}  (Иконка щита активна в трее!)     ║")
        print("║  [1-6] Вкл/Выкл | [B] Очистить буфер | [P] ПАНИКА (Буфер + Win+V)     ║")
        print("║  [T] Скрыть в трей (или кнопка [_])  | [C] Очистить лог | [Q] Выход   ║")
        print("╚═══════════════════════════════════════════════════════════════════════╝")
        print("\n--- ЖИВОЙ ЛОГ СОБЫТИЙ БУФЕРА ---")
        if not _log_lines:
            print("[*] Ожидание копирования в буфер обмена...")
        else:
            for line in _log_lines[-MAX_LOG_LINES:]:
                print(line)


def add_log(msg: str):
    """Добавляет строку в живой лог и сразу выводит её на экран."""
    with _ui_lock:
        _log_lines.append(msg)
        if len(_log_lines) > MAX_LOG_LINES:
            _log_lines.pop(0)
        print(msg)


def handle_clear_clipboard():
    """Обычная очистка буфера обмена (без сброса всей истории Win+V)."""
    ghost_timer.disarm()
    wipe_clipboard()
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging:
        log_audit("CLIPBOARD_CLEARED", "User", "[БУФЕР_ОЧИЩЕН]", "Обычная очистка буфера")
    add_log(f"[{now_time}] [ОЧИСТКА БУФЕРА] Текущее содержимое буфера обмена удалено.")
    if tray_manager:
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
    state_str = "ВКЛ" if new_val else "ВЫКЛ"
    now_time = datetime.datetime.now().strftime("%H:%M:%S")
    with _ui_lock:
        _log_lines.append(f"[{now_time}] [ТУМБЛЕР {opt_id}] {name} -> {state_str}")
    render_screen()


def handle_exit():
    """Полный выход из программы."""
    if tray_manager:
        tray_manager.remove_icon()
    print("\n[*] Завершение работы GhostClip...")
    os._exit(0)


def run_monitor():
    """
    Основной цикл слежения за буфером обмена (0% нагрузки на CPU).
    Также проверяет, не свернул ли пользователь окно консоли, чтобы спрятать его в трей.
    """
    last_seq = get_clipboard_sequence_number()
    last_processed_text = ""
    is_internal_update = False

    while True:
        try:
            time.sleep(0.2)

            # Если пользователь свернул консоль кнопкой [_] — прячем окно в трей
            if tray_manager:
                tray_manager.check_minimized_to_tray()

            current_seq = get_clipboard_sequence_number()
            if current_seq == last_seq:
                continue

            last_seq = current_seq

            if is_internal_update:
                is_internal_update = False
                continue

            text = read_clipboard_text()
            if not text or text == last_processed_text:
                continue

            last_processed_text = text
            proc_name, _ = get_active_process_info()
            now_time = datetime.datetime.now().strftime("%H:%M:%S")

            # 1. Очистка ссылок и невидимых символов (если включены [1] или [2])
            if config.clean_urls or config.clean_zero_width:
                cleaned_text, removed_params, zw_count = sanitize_text(
                    text,
                    clean_urls_enabled=config.clean_urls,
                    clean_zw_enabled=config.clean_zero_width,
                )

                if removed_params or zw_count > 0:
                    details = []
                    if removed_params:
                        details.append(f"удалены метки: {', '.join(set(removed_params))}")
                    if zw_count > 0:
                        details.append(f"невидимых знаков: {zw_count}")
                    add_log(f"[{now_time}] [ОЧИСТКА URL] ({proc_name}) -> {' | '.join(details)}")

                    is_internal_update = True
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

            # 2. Детекция секретов (если включен тумблер [3])
            secret_match = detect_secret(text) if config.detect_secrets else None

            if secret_match:
                cat, desc = secret_match
                add_log(f"[{now_time}] [СЕКРЕТ!] ({proc_name}) {desc}: {mask_secret(text)}")

                if config.ghost_timer_enabled:
                    add_log(f"[{now_time}] [ТАЙМЕР] Удаление секрета через {config.timer_seconds} сек...")
                    ghost_timer.arm(
                        config.timer_seconds,
                        desc,
                        on_expire=lambda m: add_log(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {m}"),
                    )

                if config.audit_logging:
                    log_audit(
                        event="SECRET_ARMED",
                        process=proc_name,
                        content=text,
                        extra=f"Детекция: {desc} (Таймер: {config.timer_seconds}с)",
                    )
            else:
                if ghost_timer.is_armed():
                    ghost_timer.disarm()
                    add_log(f"[{now_time}] [ИНФО] Скопирован обычный текст, таймер сброшен.")

                preview = text.strip().replace("\r\n", " ").replace("\n", " ")
                if len(preview) > 45:
                    preview = preview[:45] + "..."
                add_log(f"[{now_time}] [КОПИЯ] ({proc_name}) \"{preview}\" ({len(text)} симв.)")

                if config.audit_logging:
                    log_audit(event="CLIPBOARD_SET", process=proc_name, content=text)

        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(0.5)


def run_key_listener():
    """
    Ждёт нажатия клавиш без Enter (msvcrt.getwch).
    Цифры 1-6 мгновенно переключают тумблер, B очищает буфер, P включает панику, T прячет в трей.
    """
    while True:
        try:
            ch = msvcrt.getwch()

            if ch in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue

            key = ch.lower()

            if key in ("1", "2", "3", "4", "5", "6"):
                handle_toggle_option(int(key))
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
                render_screen()
            elif key in ("q", "й", "\x03"):
                handle_exit()
        except Exception:
            time.sleep(0.1)


def main():
    global tray_manager
    tray_manager = TrayManager(
        on_clear_clipboard=handle_clear_clipboard,
        on_panic=handle_panic,
        on_toggle_option=handle_toggle_option,
        on_exit=handle_exit,
    )
    tray_manager.start()

    render_screen()

    key_thread = threading.Thread(target=run_key_listener, daemon=True)
    key_thread.start()

    try:
        run_monitor()
    except KeyboardInterrupt:
        handle_exit()


if __name__ == "__main__":
    main()
