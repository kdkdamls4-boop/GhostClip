import contextlib
import ctypes
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import winreg
from unittest.mock import patch

import ghostclip.tray as tray_module
import main as app_main
from ghostclip.clipboard import (
    PRIVATE_FORMAT_NAMES,
    _with_clipboard,
    kernel32,
    read_clipboard_text,
    user32,
    wipe_clipboard,
    write_clipboard_text,
)
from ghostclip.config import (
    AUTOSTART_REG_PATH,
    config,
    get_autostart_command,
    is_autostart_enabled,
    set_autostart,
)
from ghostclip.shredder import CREATE_NO_WINDOW, ghost_timer, shred_clipboard

_WINRT_HISTORY_CHECK_SCRIPT = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$enabled = [Windows.ApplicationModel.DataTransfer.Clipboard,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]::IsHistoryEnabled()
if (-not $enabled) {
    Write-Output 'ENABLED=False;STATUS=Disabled;FOUND=False'
    exit 0
}
$op = [Windows.ApplicationModel.DataTransfer.Clipboard,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]::GetHistoryItemsAsync()
$task = $asTaskGeneric.MakeGenericMethod([Windows.ApplicationModel.DataTransfer.ClipboardHistoryItemsResult]).Invoke($null, @($op))
$task.Wait(5000) | Out-Null
$res = $task.Result
$textFormat = [Windows.ApplicationModel.DataTransfer.StandardDataFormats,Windows.ApplicationModel.DataTransfer,ContentType=WindowsRuntime]::Text
$found = $false
foreach ($item in $res.Items) {
    if ($item.Content.Contains($textFormat)) {
        $textOp = $item.Content.GetTextAsync()
        $textTask = $asTaskGeneric.MakeGenericMethod([string]).Invoke($null, @($textOp))
        $textTask.Wait(3000) | Out-Null
        if ($textTask.Result -eq $env:GHOSTCLIP_TEST_MARKER) {
            $found = $true
        }
    }
}
Write-Output ('ENABLED=' + $enabled + ';STATUS=' + $res.Status + ';FOUND=' + $found)
""".strip()


@contextlib.contextmanager
def _preserve_clipboard():
    """Сохраняет текстовое содержимое буфера обмена и восстанавливает его с private=True."""
    previous_text = read_clipboard_text()
    try:
        yield
    finally:
        if previous_text:
            write_clipboard_text(previous_text, private=True)
        else:
            wipe_clipboard()


def _read_private_dword_formats() -> dict[str, int | None]:
    """Читает DWORD-значения приватных форматов из открытого буфера обмена Windows."""

    def _read_flags() -> dict[str, int | None]:
        flags: dict[str, int | None] = {}
        for format_name in PRIVATE_FORMAT_NAMES:
            format_id = user32.RegisterClipboardFormatW(format_name)
            if not format_id or not user32.IsClipboardFormatAvailable(format_id):
                flags[format_name] = None
                continue
            memory_handle = user32.GetClipboardData(format_id)
            if not memory_handle:
                flags[format_name] = None
                continue
            memory_pointer = kernel32.GlobalLock(memory_handle)
            if not memory_pointer:
                flags[format_name] = None
                continue
            try:
                raw_bytes = ctypes.string_at(memory_pointer, 4)
            finally:
                kernel32.GlobalUnlock(memory_handle)
            flags[format_name] = struct.unpack("<I", raw_bytes)[0]
        return flags

    return _with_clipboard(_read_flags, default={})


class TestWin32Integration(unittest.TestCase):
    def setUp(self):
        ghost_timer.disarm()
        self._saved_state = (
            config.clean_urls,
            config.clean_zero_width,
            config.detect_secrets,
            config.auto_shred_timer,
            config.shred_win_v,
            config.audit_logging,
            config.timer_seconds,
            list(config.trusted_apps),
            config._settings_path,
            app_main.tray_manager,
            app_main._last_error_message,
        )
        config._settings_path = None
        config.clean_urls = True
        config.clean_zero_width = True
        config.detect_secrets = True
        config.auto_shred_timer = True
        config.shred_win_v = True
        config.audit_logging = False
        config.timer_seconds = 45
        config.trusted_apps = []
        app_main.tray_manager = None
        app_main._last_error_message = ""

    def tearDown(self):
        ghost_timer.disarm()
        (
            config.clean_urls,
            config.clean_zero_width,
            config.detect_secrets,
            config.auto_shred_timer,
            config.shred_win_v,
            config.audit_logging,
            config.timer_seconds,
            config.trusted_apps,
            config._settings_path,
            app_main.tray_manager,
            app_main._last_error_message,
        ) = self._saved_state

    def test_single_instance_blocks_second_process(self):
        package_root = os.path.dirname(os.path.dirname(os.path.abspath(tray_module.__file__)))
        entry_script = os.path.abspath(app_main.__file__)
        child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        holder_code = (
            "import sys; "
            "sys.path.insert(0, sys.argv[1]); "
            "from ghostclip.tray import acquire_single_instance_lock; "
            "locked = acquire_single_instance_lock(); "
            "print('LOCKED' if locked else 'ALREADY_HELD', flush=True); "
            "sys.stdin.readline()"
        )
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code, package_root],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=child_env,
            creationflags=CREATE_NO_WINDOW,
        )
        try:
            assert holder.stdout is not None
            assert holder.stderr is not None
            ready_line = holder.stdout.readline().strip()
            if not ready_line:
                stderr_output = holder.stderr.read()
                self.fail(f"Дочерний процесс-держатель мьютекса завершился без ответа: {stderr_output}")
            self.assertIn(ready_line, ("LOCKED", "ALREADY_HELD"))

            second_run = subprocess.run(
                [sys.executable, entry_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                env=child_env,
                creationflags=CREATE_NO_WINDOW,
            )
            self.assertEqual(second_run.returncode, 1)
            self.assertIn("уже запущен", second_run.stdout)
        finally:
            if holder.stdin is not None and not holder.stdin.closed:
                try:
                    holder.stdin.write("\n")
                    holder.stdin.flush()
                except OSError:
                    pass
                holder.stdin.close()
            try:
                holder.wait(timeout=5)
            except subprocess.TimeoutExpired:
                holder.kill()
                holder.wait(timeout=5)
            if holder.stdout is not None and not holder.stdout.closed:
                holder.stdout.close()
            if holder.stderr is not None and not holder.stderr.closed:
                holder.stderr.close()

    def test_audit_log_hides_real_clipboard_content_end_to_end(self):
        with _preserve_clipboard(), tempfile.TemporaryDirectory() as temp_dir:
            log_path = os.path.join(temp_dir, "integration_audit.log")
            config.audit_logging = True
            config.detect_secrets = True
            config.clean_urls = True
            config.clean_zero_width = True
            config.trusted_apps = []

            plain_sample = "Личная переписка для интеграционной проверки"
            bracket_sample = "[Личная заметка в квадратных скобках]"

            with (
                patch("ghostclip.config.LOG_FILE_PATH", log_path),
                patch("main.add_log"),
            ):
                for sample in (plain_sample, bracket_sample):
                    self.assertTrue(write_clipboard_text(sample, private=True))
                    copied_text = read_clipboard_text()
                    self.assertEqual(copied_text, sample)
                    app_main.process_clipboard_event(copied_text, "notepad.exe")

            with open(log_path, encoding="utf-8") as log_file:
                log_content = log_file.read()

        self.assertIn("CLIPBOARD_SET", log_content)
        self.assertIn(f"[текст, {len(plain_sample)} симв.]", log_content)
        self.assertNotIn("Личная переписка", log_content)
        self.assertIn(f"[текст, {len(bracket_sample)} симв.]", log_content)
        self.assertNotIn("Личная заметка", log_content)

    def test_private_clipboard_flags_and_shred_exclude_win_v_history(self):
        with _preserve_clipboard():
            unique_marker = f"[GHOSTCLIP_TEST_{uuid.uuid4().hex}]"
            self.assertTrue(write_clipboard_text(unique_marker, private=True))
            self.assertEqual(read_clipboard_text(), unique_marker)

            flags = _read_private_dword_formats()
            for format_name in PRIVATE_FORMAT_NAMES:
                self.assertIn(format_name, flags)
                self.assertEqual(flags[format_name], 0)

            self.assertTrue(shred_clipboard(dummy_text=unique_marker))
            self.assertEqual(read_clipboard_text(), "")

            time.sleep(0.25)
            history_check = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINRT_HISTORY_CHECK_SCRIPT],
                capture_output=True,
                text=True,
                timeout=10,
                env={**os.environ, "GHOSTCLIP_TEST_MARKER": unique_marker},
                creationflags=CREATE_NO_WINDOW,
            )
            self.assertEqual(history_check.returncode, 0, history_check.stderr)

            parsed: dict[str, str] = {}
            for pair in history_check.stdout.strip().split(";"):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    parsed[key] = value

            if parsed.get("ENABLED") == "True":
                self.assertEqual(parsed.get("STATUS"), "Success")
            self.assertEqual(parsed.get("FOUND"), "False")

    def test_non_iin_card_number_does_not_arm_timer(self):
        config.detect_secrets = True
        config.auto_shred_timer = True
        config.audit_logging = False

        with patch("main.add_log"), patch("main.render_screen"):
            app_main.process_clipboard_event("9000 0000 0000 0001", "notepad.exe")

        self.assertFalse(ghost_timer.is_armed())

    def test_autostart_real_registry_roundtrip(self):
        test_value_name = "GhostClipShield_IntegrationTest"
        with patch("ghostclip.config.AUTOSTART_VALUE_NAME", test_value_name):
            try:
                self.assertTrue(set_autostart(False))
                self.assertFalse(is_autostart_enabled())

                self.assertTrue(set_autostart(True))
                self.assertTrue(is_autostart_enabled())

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_READ
                ) as reg_key:
                    stored_value, _ = winreg.QueryValueEx(reg_key, test_value_name)
                self.assertEqual(stored_value, get_autostart_command())

                self.assertTrue(set_autostart(False))
                self.assertFalse(is_autostart_enabled())
                self.assertTrue(set_autostart(False))
            finally:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE
                    ) as reg_key:
                        winreg.DeleteValue(reg_key, test_value_name)
                except (FileNotFoundError, OSError):
                    pass


if __name__ == "__main__":
    unittest.main()
