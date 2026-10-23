"""
GhostClip — Модульный персональный защитник буфера обмена для Windows.
"""
# ═══════════════════════════════════════════════════════════════════
#  ЧТО ЭТО ЗА ФАЙЛ
# ═══════════════════════════════════════════════════════════════════
# __init__.py (два подчёркивания с каждой стороны) — особый файл.
#
# 1. Он делает папку ghostclip ПАКЕТОМ, то есть одним целым, которое можно импортировать.
# 2. Он выполняется автоматически, когда кто-то пишет `import ghostclip`
#    или `from ghostclip import ...`.
# 3. Здесь он работает как «витрина»: собирает функции из всех файлов в одно место.
#
# БЕЗ него в main.py пришлось бы писать так:
#     from ghostclip.clipboard import read_clipboard_text
#     from ghostclip.detector import detect_secret
#     ...
# А С НИМ можно короче:
#     from ghostclip import read_clipboard_text, detect_secret
# ═══════════════════════════════════════════════════════════════════

from .clipboard import (
    # Скобки позволяют перечислить много имён на нескольких строках.
    read_clipboard_text,
    write_clipboard_text,
    wipe_clipboard,
    get_clipboard_sequence_number,
    get_active_process_info,
)
from .shredder import wipe_win_v_history, panic_wipe, shred_clipboard
from .cleaner import strip_zero_width, clean_url, sanitize_text
from .detector import detect_secret, mask_secret, luhn_check, calculate_entropy
from .audit import log_audit, LOG_FILE_PATH
from .timer import ghost_timer, GhostTimer
from .config import config, ShieldConfig
from .tray import TrayManager

__all__ = [
    # __all__ — официальный список того, что пакет «выставляет наружу».
    # Он определяет, что попадёт к тебе при `from ghostclip import *` (звёздочка = всё).
    # Кроме того, это просто удобное оглавление пакета.
    "read_clipboard_text",
    "write_clipboard_text",
    "wipe_clipboard",
    "get_clipboard_sequence_number",
    "get_active_process_info",
    "wipe_win_v_history",
    "panic_wipe",
    "shred_clipboard",
    "strip_zero_width",
    "clean_url",
    "sanitize_text",
    "detect_secret",
    "mask_secret",
    "luhn_check",
    "calculate_entropy",
    "log_audit",
    "LOG_FILE_PATH",
    "ghost_timer",
    "GhostTimer",
    "config",
    "ShieldConfig",
    "TrayManager",
]
