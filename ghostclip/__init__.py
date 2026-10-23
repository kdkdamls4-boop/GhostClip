"""
GhostClip — Модульный персональный защитник буфера обмена для Windows.
"""

from .clipboard import (
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
