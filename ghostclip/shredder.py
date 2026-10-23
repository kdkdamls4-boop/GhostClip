"""Модуль зачистки буфера и системного журнала Win+V."""

import subprocess
from typing import Tuple
from .clipboard import wipe_clipboard, write_clipboard_text

CREATE_NO_WINDOW = 0x08000000
OVERWRITE_DUMMY_TEXT = "[GHOSTCLIP: СЕКРЕТ ЗАТЕРТ. ВСЕ ЦИФРЫ УНИЧТОЖЕНЫ]"


def wipe_win_v_history() -> bool:
    """Бесшумно очищает историю Win+V через Windows Runtime API."""
    cmd = "[Windows.ApplicationModel.DataTransfer.Clipboard,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]::ClearHistory()"
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        return res.returncode == 0
    except Exception:
        return False


def shred_clipboard(dummy_text: str = OVERWRITE_DUMMY_TEXT) -> Tuple[bool, bool]:
    """
    Затирает секретные данные текстом, чтобы не осталось никаких цифр,
    а затем зачищает память буфера и журнал Win+V.
    """
    write_clipboard_text(dummy_text)
    clip_ok = wipe_clipboard()
    hist_ok = wipe_win_v_history()
    return clip_ok, hist_ok


def panic_wipe() -> Tuple[bool, bool]:
    """Экстренно затирает буфер обмена и историю Win+V."""
    return shred_clipboard()
