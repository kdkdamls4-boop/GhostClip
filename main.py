"""Точка входа GhostClip Shield: консольный пульт, горячие клавиши и цикл защиты буфера."""

import datetime
import msvcrt
import os
import sys
import threading
import time

from ghostclip import (
    TrayManager,
    config,
    detect_secret,
    get_active_process_info,
    get_clipboard_sequence_number,
    ghost_timer,
    log_audit,
    mask_secret,
    panic_wipe,
    read_clipboard_text,
    sanitize_text,
    wipe_clipboard,
    wipe_win_v_history,
    write_clipboard_text,
)

MAX_LOG_LINES = 25
NIIF_WARNING = 2
_ui_lock = threading.Lock()
_in_settings_mode = threading.Event()
_log_lines: list[str] = []
tray_manager: TrayManager | None = None


def _current_time_str() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def render_screen() -> None:
    """Отрисовывает панель переключателей [1-6], статус таймера, белый список и живой лог."""
    if _in_settings_mode.is_set():
        return

    with _ui_lock:
        statuses = config.get_status_dict()
        trusted_count = len(config.get_trusted_apps())
        timer_text = (
            f"АКТИВЕН ({ghost_timer.remaining_seconds()}с)" if ghost_timer.is_armed() else "Ожидание..."
        )
        hotkey_status = (
            "Ctrl+Shift+X: активен"
            if (tray_manager and tray_manager.hotkey_registered)
            else "Ctrl+Shift+X: недоступен"
        )
        trusted_text = f"Белый список: {trusted_count} прил." if trusted_count else "Белый список: пуст"

        os.system("cls" if os.name == "nt" else "clear")
        print("╔═══════════════════════════════════════════════════════════════════════╗")
        print("║                    GhostClip Shield (Консоль + Трей)                  ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        for option_id in range(1, 7):
            title, enabled = statuses[option_id]
            badge = "[ВКЛ] " if enabled else "[ВЫКЛ]"
            print(f"║  [{option_id}] {title:<57} {badge} ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║  Таймер: {timer_text:<21} | {trusted_text:<36} ║")
        print(f"║  Глобальная паника: {hotkey_status:<49} ║")
        print("║  [1-6] Вкл/Выкл | [S] Настройки | [B] Очистить | [P] ПАНИКА (Win+V)   ║")
        print("║  [T] Скрыть в трей (или [_])    | [C] Лог      | [Q] Выход            ║")
        print("╚═══════════════════════════════════════════════════════════════════════╝")
        print("\n--- ЖИВОЙ ЛОГ СОБЫТИЙ БУФЕРА ---")
        if not _log_lines:
            print("[*] Ожидание событий буфера обмена...")
        else:
            for log_line in _log_lines[-MAX_LOG_LINES:]:
                print(log_line)


def add_log(message: str) -> None:
    """Добавляет строку в живой лог и сразу печатает её (если не открыто меню настроек)."""
    with _ui_lock:
        _log_lines.append(message)
        if len(_log_lines) > MAX_LOG_LINES:
            _log_lines.pop(0)
        if not _in_settings_mode.is_set():
            print(message)


def handle_clear() -> None:
    """Обычная очистка текущего содержимого буфера обмена."""
    ghost_timer.disarm()
    if tray_manager:
        tray_manager.update_timer_indicator(0)
    wipe_clipboard()
    log_audit("CLIP_CLEARED", "User", "[БУФЕР_ОЧИЩЕН]")
    add_log(f"[{_current_time_str()}] [ОЧИСТКА БУФЕРА] Текущий буфер очищен.")
    if tray_manager:
        tray_manager.show_balloon("Буфер очищен", "Содержимое буфера обмена удалено.")


def handle_panic() -> None:
    """Экстренная паника: затирает буфер обмена и всю историю Win+V."""
    ghost_timer.disarm()
    if tray_manager:
        tray_manager.update_timer_indicator(0)
    panic_wipe()
    log_audit("PANIC_FLUSH", "User", "[ПАНИКА]")
    add_log(f"[{_current_time_str()}] [ПАНИКА!] Буфер обмена и история Win+V затерты!")
    if tray_manager:
        tray_manager.show_balloon("ПАНИКА", "Буфер обмена и история Win+V уничтожены.", NIIF_WARNING)


def handle_toggle(option_id: int) -> None:
    """Переключает настройку [1-6] из консоли или меню трея."""
    option_name, new_value = config.toggle(option_id)
    state_label = "ВКЛ" if new_value else "ВЫКЛ"
    with _ui_lock:
        _log_lines.append(f"[{_current_time_str()}] [{option_id}] {option_name} -> {state_label}")
    render_screen()


def handle_exit() -> None:
    """Корректно завершает работу программы и убирает иконку из трея."""
    ghost_timer.disarm()
    if tray_manager:
        tray_manager.remove_icon()
    print("\n[*] Завершение работы GhostClip Shield...")
    os._exit(0)


def handle_auto_destruct() -> None:
    """Срабатывает по истечении таймера: стирает секрет из буфера и (если включено [5]) из Win+V."""
    if tray_manager:
        tray_manager.update_timer_indicator(0)
    wipe_clipboard()
    if config.shred_win_v:
        wipe_win_v_history()

    log_audit(
        "GHOST_WIPED",
        "GhostClip",
        "[СЕКРЕТ_ЗАТЕРТ]",
        f"Таймер {config.timer_seconds}с истёк",
    )
    add_log(f"[{_current_time_str()}] [ТАЙМЕР ИСТЁК] Секрет удалён из буфера!")
    if tray_manager:
        tray_manager.show_balloon("GhostClip Shield", "Секрет уничтожен таймером!", NIIF_WARNING)


def handle_settings() -> None:
    """Открывает интерактивное меню настройки таймера и белого списка приложений."""
    _in_settings_mode.set()
    try:
        while True:
            trusted = config.get_trusted_apps()
            os.system("cls" if os.name == "nt" else "clear")
            print("═══════════════════════════════════════════════════════════════════════")
            print("                 НАСТРОЙКИ GHOSTCLIP SHIELD (ghostclip_settings.json)  ")
            print("═══════════════════════════════════════════════════════════════════════")
            print(f"  Текущий таймер самоуничтожения: {config.timer_seconds} сек (диапазон 5..3600)")
            print(f"  Белый список (.exe): {', '.join(trusted) if trusted else '(пусто)'}")
            print("───────────────────────────────────────────────────────────────────────")
            print("  [1] Изменить время таймера (сек)")
            print("  [2] Добавить приложение в белый список (например: keepassxc.exe)")
            print("  [3] Удалить приложение из белого списка")
            print("  [0] Вернуться на главный экран")
            print("───────────────────────────────────────────────────────────────────────")

            choice = input("Выберите действие [0-3]: ").strip()
            if choice in ("0", ""):
                break
            if choice == "1":
                raw_seconds = input("Новое время таймера в секундах (5..3600): ").strip()
                try:
                    new_seconds = config.set_timer_seconds(int(raw_seconds))
                    add_log(f"[{_current_time_str()}] [НАСТРОЙКИ] Таймер изменён на {new_seconds} сек.")
                except ValueError as error:
                    print(f"[!] Ошибка: {error}")
                    time.sleep(1.5)
            elif choice == "2":
                app_name = input("Имя процесса (например bitwarden.exe или notepad.exe): ").strip()
                try:
                    normalized = os.path.basename(app_name.strip('"').strip("'")).lower()
                    if config.add_trusted_app(app_name):
                        add_log(f"[{_current_time_str()}] [БЕЛЫЙ СПИСОК] Добавлено: {normalized}")
                    else:
                        print("[*] Это приложение уже есть в белом списке.")
                        time.sleep(1.2)
                except ValueError as error:
                    print(f"[!] Ошибка: {error}")
                    time.sleep(1.2)
            elif choice == "3":
                app_name = input("Имя процесса для удаления: ").strip()
                normalized = os.path.basename(app_name.strip('"').strip("'")).lower()
                if config.remove_trusted_app(app_name):
                    add_log(f"[{_current_time_str()}] [БЕЛЫЙ СПИСОК] Удалено: {normalized}")
                else:
                    print("[!] Такого приложения нет в белом списке.")
                    time.sleep(1.2)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        _in_settings_mode.clear()
        render_screen()


def clean_clipboard_if_needed(text: str, source_app: str) -> tuple[str, bool]:
    """Очищает ссылки и невидимые символы, если включены переключатели [1] или [2]."""
    if not (config.clean_urls or config.clean_zero_width):
        return text, False

    cleaned_text, is_modified, cleaning_logs = sanitize_text(
        text,
        clean_urls_enabled=config.clean_urls,
        clean_zw_enabled=config.clean_zero_width,
    )
    if not is_modified:
        return text, False

    write_clipboard_text(cleaned_text)
    details = "; ".join(cleaning_logs)
    add_log(f"[{_current_time_str()}] [ОЧИСТКА] ({source_app}) -> {details}")
    log_audit("URL_CLEANED", source_app, cleaned_text, details)
    return cleaned_text, True


def handle_clipboard_content(text: str, source_app: str) -> None:
    """Проверяет текст на секреты, запускает или сбрасывает таймер и ведёт лог."""
    if config.detect_secrets:
        is_secret, secret_type, secret_value = detect_secret(text)
        if is_secret:
            masked_secret = mask_secret(secret_value)
            add_log(f"[{_current_time_str()}] [СЕКРЕТ!] ({source_app}) {secret_type}: {masked_secret}")
            log_audit("SECRET_FOUND", source_app, secret_value, f"Тип: {secret_type}")

            if config.auto_shred_timer:
                add_log(f"[{_current_time_str()}] [ТАЙМЕР] Удаление через {config.timer_seconds} сек...")
                ghost_timer.arm(config.timer_seconds, handle_auto_destruct)
                if tray_manager:
                    tray_manager.update_timer_indicator(config.timer_seconds)
                    if not tray_manager.is_console_visible():
                        tray_manager.show_balloon(
                            "Секрет обнаружен",
                            f"{secret_type}: удаление через {config.timer_seconds}с",
                            NIIF_WARNING,
                        )
                render_screen()
            return

    if ghost_timer.is_armed():
        ghost_timer.disarm()
        if tray_manager:
            tray_manager.update_timer_indicator(0)
        add_log(f"[{_current_time_str()}] [ИНФО] Скопирован обычный текст — таймер сброшен.")

    preview = text.strip().replace("\r\n", " ").replace("\n", " ")
    if len(preview) > 45:
        preview = preview[:45] + "..."
    add_log(f'[{_current_time_str()}] [КОПИЯ] ({source_app}) "{preview}" ({len(text)} симв.)')
    log_audit("CLIPBOARD_SET", source_app, text)


def process_clipboard_event(text: str, source_app: str) -> tuple[str, bool]:
    """Обрабатывает новое содержимое буфера с учётом белого списка, очистки и детекции."""
    if config.is_trusted_app(source_app):
        if ghost_timer.is_armed():
            ghost_timer.disarm()
            if tray_manager:
                tray_manager.update_timer_indicator(0)
        add_log(f"[{_current_time_str()}] [БЕЛЫЙ СПИСОК] ({source_app}) Пропущено (доверенное приложение).")
        log_audit("TRUSTED_APP", source_app, "[ПРОПУЩЕНО]", "Доверенное приложение")
        return text, False

    final_text, was_cleaned = clean_clipboard_if_needed(text, source_app)
    handle_clipboard_content(final_text, source_app)
    return final_text, was_cleaned


def key_listener() -> None:
    """Слушает горячие клавиши без нажатия Enter (включая русскую раскладку)."""
    while True:
        try:
            key_char = msvcrt.getwch()
            if key_char in ("\x00", "\xe0"):
                msvcrt.getwch()
                continue

            pressed_key = key_char.lower()
            if pressed_key in "123456":
                handle_toggle(int(pressed_key))
            elif pressed_key in ("s", "ы"):
                handle_settings()
            elif pressed_key in ("b", "и"):
                handle_clear()
            elif pressed_key in ("p", "з"):
                handle_panic()
            elif pressed_key in ("t", "е"):
                if tray_manager:
                    tray_manager.hide_console_to_tray()
            elif pressed_key in ("c", "с"):
                with _ui_lock:
                    _log_lines.clear()
                render_screen()
            elif pressed_key in ("q", "й", "\x03"):
                handle_exit()
        except Exception:
            time.sleep(0.1)


def monitor_clipboard() -> None:
    """Главный цикл отслеживания буфера обмена по счётчику Windows (0% CPU)."""
    last_sequence_number = get_clipboard_sequence_number()
    last_clipboard_text = ""
    last_tray_remaining = 0

    while True:
        try:
            time.sleep(0.2)
            if tray_manager:
                tray_manager.check_minimized_to_tray()
                current_remaining = ghost_timer.remaining_seconds() if ghost_timer.is_armed() else 0
                if current_remaining != last_tray_remaining:
                    last_tray_remaining = current_remaining
                    tray_manager.update_timer_indicator(current_remaining)

            current_sequence_number = get_clipboard_sequence_number()
            if current_sequence_number == last_sequence_number:
                continue
            last_sequence_number = current_sequence_number

            current_text = read_clipboard_text()
            if not current_text:
                last_clipboard_text = ""
                continue
            if current_text == last_clipboard_text:
                continue
            last_clipboard_text = current_text

            source_app, _ = get_active_process_info()
            final_text, was_cleaned = process_clipboard_event(current_text, source_app)
            if was_cleaned:
                last_clipboard_text = final_text
                last_sequence_number = get_clipboard_sequence_number()
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(0.5)


def main() -> None:
    """Инициализирует кодировку, трей, клавиатуру, экран и цикл мониторинга."""
    global tray_manager
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    tray_manager = TrayManager(
        on_clear=handle_clear,
        on_panic=handle_panic,
        on_toggle=handle_toggle,
        on_exit=handle_exit,
    )
    tray_manager.start()
    render_screen()

    threading.Thread(target=key_listener, daemon=True).start()
    try:
        monitor_clipboard()
    except KeyboardInterrupt:
        handle_exit()


if __name__ == "__main__":
    main()
