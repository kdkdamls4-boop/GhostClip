"""
explained/ghostclip/__init__.py
Единая точка экспорта компонентов пакета ghostclip для удобного импорта из main.py.
"""

from .cleaner import clean_url, sanitize_text, strip_zero_width
from .clipboard import (
    get_active_process_info,
    get_clipboard_sequence_number,
    read_clipboard_text,
    wipe_clipboard,
    write_clipboard_text,
)
from .config import LOG_FILE_PATH, SETTINGS_FILE_PATH, ShieldConfig, config, get_app_dir, log_audit
from .detector import calculate_entropy, detect_secret, luhn_check, mask_secret
from .shredder import GhostTimer, ghost_timer, panic_wipe, shred_clipboard, wipe_win_v_history
from .tray import TrayManager

__all__ = [
    "LOG_FILE_PATH",
    "SETTINGS_FILE_PATH",
    "get_app_dir",
    "ShieldConfig",
    "config",
    "log_audit",
    "strip_zero_width",
    "clean_url",
    "sanitize_text",
    "detect_secret",
    "mask_secret",
    "luhn_check",
    "calculate_entropy",
    "read_clipboard_text",
    "write_clipboard_text",
    "wipe_clipboard",
    "get_clipboard_sequence_number",
    "get_active_process_info",
    "shred_clipboard",
    "panic_wipe",
    "wipe_win_v_history",
    "GhostTimer",
    "ghost_timer",
    "TrayManager",
]
