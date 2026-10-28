"""
ghostclip_mini/main.py
Точка входа компактной версии GhostClip (7 файлов).
Управляет консольным интерфейсом, горячими клавишами и потоком событий буфера.
"""

import sys
import os
import time
import datetime
import threading
import msvcrt

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config, log_audit
from cleaner import sanitize_text
from detector import detect_secret, mask_secret
from clipboard import read_clipboard_text, write_clipboard_text, wipe_clipboard, get_clipboard_sequence_number, get_active_process_info
from shredder import shred_clipboard, panic_wipe, ghost_timer
from tray import TrayManager

_ui_lock = threading.Lock()
_logs: list[str] = []
tray_mgr: TrayManager = None  # type: ignore

def render():
    with _ui_lock:
        st = config.get_status_dict()
        b = lambda v: "[ВКЛ] " if v else "[ВЫКЛ]"
        t_str = f"АКТИВЕН ({ghost_timer.remaining_seconds()}с)" if ghost_timer.is_armed() else "Ожидание..."
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
            for l in _logs[-20:]:
                print(l)

def add_log(m: str):
    with _ui_lock:
        _logs.append(m)
        if len(_logs) > 20:
            _logs.pop(0)
        print(m)

def on_clear():
    ghost_timer.disarm()
    wipe_clipboard()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging:
        log_audit("CLIP_CLEARED", "User", "[БУФЕР_ОЧИЩЕН]")
    add_log(f"[{now}] [ОЧИСТКА БУФЕРА] Буфер очищен.")
    if tray_mgr:
        tray_mgr.show_balloon("Буфер очищен", "Буфер обмена очищен.")

def on_panic():
    ghost_timer.disarm()
    panic_wipe()
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if config.audit_logging:
        log_audit("PANIC_FLUSH", "User", "[ПАНИКА]")
    add_log(f"[{now}] [ПАНИКА!] Буфер и история Win+V затерты!")
    if tray_mgr:
        tray_mgr.show_balloon("ПАНИКА", "Буфер и Win+V уничтожены.")

def on_toggle(opt_id: int):
    name, val = config.toggle(opt_id)
    now = datetime.datetime.now().strftime("%H:%M:%S")
    with _ui_lock:
        _logs.append(f"[{now}] [{opt_id}] {name} -> {'ВКЛ' if val else 'ВЫКЛ'}")
    render()

def on_exit():
    if tray_mgr:
        tray_mgr.remove_icon()
    print("\n[*] Завершение работы GhostClip Mini...")
    os._exit(0)

def key_listener():
    while True:
        try:
            ch = msvcrt.getwch().lower()
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
    global tray_mgr
    tray_mgr = TrayManager(on_clear, on_panic, on_toggle, on_exit)
    tray_mgr.start()
    threading.Thread(target=key_listener, daemon=True).start()
    render()

    last_seq, last_txt, self_upd = get_clipboard_sequence_number(), "", False
    while True:
        time.sleep(0.2)
        if tray_mgr:
            tray_mgr.check_minimized_to_tray()
        cur_seq = get_clipboard_sequence_number()
        if cur_seq == last_seq:
            continue
        last_seq = cur_seq
        if self_upd:
            self_upd = False
            continue
        txt = read_clipboard_text()
        if not txt or txt == last_txt:
            continue
        last_txt = txt
        app, _ = get_active_process_info()
        now = datetime.datetime.now().strftime("%H:%M:%S")

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

        if config.detect_secrets:
            is_sec, sec_type, val = detect_secret(txt)
            if is_sec:
                masked = mask_secret(val)
                add_log(f"[{now}] [СЕКРЕТ!] Обнаружен {sec_type}: {masked} (Источник: {app})")
                if config.audit_logging:
                    log_audit("SECRET_FOUND", app, masked, f"Тип: {sec_type}")
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
