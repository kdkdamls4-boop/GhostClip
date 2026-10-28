"""
ghostclip_mini_explained/main.py
Файл 7 из 7: Точка входа компактной версии GhostClip Mini (7 файлов).
Управляет консольным интерфейсом, горячими клавишами и потоком событий буфера.
"""

# Импортируем системные модули
import sys        # Настройки вывода консоли и путей поиска модулей
import os         # Системные команды (очистка экрана cls, пути к файлам)
import time       # Паузы между проверками буфера
import datetime   # Форматирование времени для вывода в консоль
import threading  # Многопоточность: замок UI и поток слушателя клавиатуры
import msvcrt     # Моментальное чтение клавиш в Windows без нажатия Enter

# Переключаем стандартный вывод консоли на UTF-8, чтобы не ломались рамки ╔═╗ и русский текст
sys.stdout.reconfigure(encoding="utf-8")

# Добавляем текущую директорию в начало sys.path, чтобы импорты из 7 файлов работали надёжно
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Импортируем компоненты из соседних 6 лёгких файлов проекта
from config import config, log_audit
from cleaner import sanitize_text
from detector import detect_secret, mask_secret
from clipboard import (
    read_clipboard_text, write_clipboard_text, wipe_clipboard,
    get_clipboard_sequence_number, get_active_process_info
)
from shredder import shred_clipboard, panic_wipe, ghost_timer
from tray import TrayManager

# Блокировка (мьютекс) для потокобезопасного вывода в консоль
_ui_lock = threading.Lock()
# Список последних строк лога (не больше 20 строк на экране)
_logs: list[str] = []
# Ссылка на менеджер трея Windows
tray_mgr: TrayManager = None  # type: ignore

def render():
    """Отрисовывает заголовок, статусы переключателей [1-6], таймер и живой лог."""
    with _ui_lock:
        st = config.get_status_dict()
        b = lambda v: "[ВКЛ] " if v else "[ВЫКЛ]"
        t_str = f"АКТИВЕН ({ghost_timer.remaining_seconds()}с)" if ghost_timer.is_armed() else "Ожидание..."

        # Очищаем экран консоли (cls на Windows, clear на Linux/Mac)
        os.system("cls" if os.name == "nt" else "clear")

        print("╔═══════════════════════════════════════════════════════════════════════╗")
        print("║                 GhostClip Mini (7 файлов, Консоль + Трей)             ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        for i in range(1, 7):
            print(f"║  [{i}] {st[i][0]:<49} {b(st[i][1])}   ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║  Таймер: {t_str:<25}  (Иконка щита активна в трее!)     ║")
        print("║  [1-6] Вкл/Выкл | [B] Очистить буфер | [P] ПАНИКА (Буфер + Win+V)     ║")
        print("║  [T] Скрыть в трей (или [_])         | [C] Очистить лог | [Q] Выход   ║")
        print("╚═══════════════════════════════════════════════════════════════════════╝\n--- ЖИВОЙ ЛОГ ---")
        if not _logs:
            print("[*] Ожидание событий буфера обмена...")
        else:
            for l in _logs[-20:]:  # Выводим последние 20 сообщений
                print(l)

def add_log(m: str):
    """Добавляет строку в журнал на экране и в список логов."""
    with _ui_lock:
        _logs.append(m)
        if len(_logs) > 20:
            _logs.pop(0)  # Удаляем самую старую строку при переполнении
        print(m)

def on_clear():
    """Обычная очистка буфера обмена (по нажатию клавиши B или через трей)."""
    ghost_timer.disarm()  # Останавливаем таймер
    wipe_clipboard()      # Очищаем буфер
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging:
        log_audit("CLIP_CLEARED", "User", "[БУФЕР_ОЧИЩЕН]")
    add_log(f"[{now}] [ОЧИСТКА БУФЕРА] Буфер очищен.")
    if tray_mgr:
        tray_mgr.show_balloon("Буфер очищен", "Буфер обмена очищен.")

def on_panic():
    """Экстренная ПАНИКА: затирает буфер и вытесняет историю Win+V."""
    ghost_timer.disarm()
    panic_wipe()          # Глубокое затирание буфера и стека Win+V
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging:
        log_audit("PANIC_FLUSH", "User", "[ПАНИКА]")
    add_log(f"[{now}] [ПАНИКА!] Буфер и история Win+V затерты!")
    if tray_mgr:
        tray_mgr.show_balloon("ПАНИКА", "Буфер и Win+V уничтожены.")

def on_toggle(opt_id: int):
    """Переключает статус функции [1-6]."""
    name, val = config.toggle(opt_id)
    now = datetime.datetime.now().strftime("%H:%M:%S")
    with _ui_lock:
        _logs.append(f"[{now}] [{opt_id}] {name} -> {'ВКЛ' if val else 'ВЫКЛ'}")
    render()  # Перерисовываем экран, чтобы обновить флажки [ВКЛ]/[ВЫКЛ]

def on_exit():
    """Корректный выход из программы с удалением иконки из трея."""
    if tray_mgr:
        tray_mgr.remove_icon()
    print("\n[*] Завершение работы GhostClip Mini...")
    os._exit(0)  # Принудительно завершаем все фоновые потоки процесса

def key_listener():
    """Поток прослушивания нажатий клавиш без ожидания нажатия Enter."""
    while True:
        try:
            ch = msvcrt.getwch().lower()  # Читаем символ сразу при нажатии
            if ch in '123456':
                on_toggle(int(ch))
            elif ch in ('b', 'и'):
                on_clear()
            elif ch in ('p', 'з'):
                on_panic()
            elif ch in ('t', 'е'):
                if tray_mgr:
                    tray_mgr.toggle_console()
            elif ch in ('c', 'с'):
                with _ui_lock:
                    _logs.clear()
                render()
            elif ch in ('q', 'й'):
                on_exit()
        except Exception:
            pass

def main():
    """Главная функция приложения."""
    global tray_mgr
    # 1. Инициализируем и запускаем системный трей в фоновом потоке
    tray_mgr = TrayManager(on_clear, on_panic, on_toggle, on_exit)
    tray_mgr.start()

    # 2. Запускаем поток горячих клавиш клавиатуры
    threading.Thread(target=key_listener, daemon=True).start()

    # 3. Отрисовываем консольный дашборд
    render()

    # Запоминаем начальный системный номер изменения буфера
    last_seq = get_clipboard_sequence_number()
    last_txt = ""
    self_upd = False  # Флаг: изменение сделано самой программой GhostClip

    # 4. Главный цикл слежения за буфером (0% нагрузки на CPU)
    while True:
        time.sleep(0.2)  # Проверка 5 раз в секунду
        if tray_mgr:
            tray_mgr.check_minimized_to_tray()  # Проверяем, не свернул ли юзер окно кнопкой [_]

        cur_seq = get_clipboard_sequence_number()
        if cur_seq == last_seq:
            continue  # Буфер не менялся, продолжаем спать
        last_seq = cur_seq

        if self_upd:
            self_upd = False  # Пропускаем собственное изменение очищенного текста
            continue

        txt = read_clipboard_text()
        if not txt or txt == last_txt:
            continue
        last_txt = txt

        app, _ = get_active_process_info()  # Имя программы, откуда скопировали
        now = datetime.datetime.now().strftime("%H:%M:%S")

        # Проверка 1: Очистка трекеров URL и скрытых символов Zero-Width
        if config.clean_urls or config.clean_zero_width:
            cleaned, mod, details = sanitize_text(txt)
            if mod:
                self_upd = True
                write_clipboard_text(cleaned)
                last_txt = cleaned
                add_log(f"[{now}] [ОЧИСТКА] ({app}) -> {'; '.join(details)}")
                if config.audit_logging:
                    log_audit("CLEANED", app, cleaned[:50], "; ".join(details))
                txt = cleaned

        # Проверка 2: Детекция секретов (API-ключи, карты, пароли)
        if config.detect_secrets:
            is_sec, sec_type, val = detect_secret(txt)
            if is_sec:
                masked = mask_secret(val)
                add_log(f"[{now}] [СЕКРЕТ!] Обнаружен {sec_type}: {masked} (Источник: {app})")
                if config.audit_logging:
                    log_audit("SECRET_FOUND", app, masked, f"Тип: {sec_type}")

                # Если включён таймер самоуничтожения — запускаем обратный отсчёт
                if config.auto_shred_timer:
                    add_log(f"[{now}] [ТАЙМЕР] Запущен отсчет {config.timer_seconds} сек до уничтожения...")

                    def auto_destruct():
                        now2 = datetime.datetime.now().strftime("%H:%M:%S")
                        wipe_clipboard()
                        add_log(f"[{now2}] [ТАЙМЕР ИСТЁК] Секрет удален из буфера!")
                        if tray_mgr:
                            tray_mgr.show_balloon("GhostClip Shield", "Секрет уничтожен таймером!")

                    ghost_timer.arm(config.timer_seconds, auto_destruct)
                    render()

if __name__ == "__main__":
    main()
