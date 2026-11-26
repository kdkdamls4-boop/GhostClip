import unittest
from unittest.mock import MagicMock, patch

from ghostclip.tray import NIF_INFO, NIM_MODIFY, NOTIFYICONDATAW, TrayManager


class TestTrayManager(unittest.TestCase):
    def _create_mocked_tray(self):
        on_clear = MagicMock()
        on_panic = MagicMock()
        on_toggle = MagicMock()
        on_exit = MagicMock()
        with (
            patch("ghostclip.tray.kernel32.GetConsoleWindow", return_value=0),
            patch("ghostclip.tray.user32.GetForegroundWindow", return_value=0),
        ):
            manager = TrayManager(
                on_clear=on_clear,
                on_panic=on_panic,
                on_toggle=on_toggle,
                on_exit=on_exit,
            )
        return manager, on_clear, on_panic, on_toggle, on_exit

    def test_build_menu_items_and_command_dispatch(self):
        manager, on_clear, on_panic, on_toggle, on_exit = self._create_mocked_tray()
        items = manager._build_menu_items(is_console_visible=True)
        labels = [label for _, label, _ in items]
        self.assertIn("Скрыть консоль в трей", labels)
        self.assertTrue(any("Ctrl+Shift+X" in label for label in labels))

        manager._dispatch_menu_command(20)
        on_clear.assert_called_once()

        manager._dispatch_menu_command(30)
        on_panic.assert_called_once()

        manager._dispatch_menu_command(104)
        on_toggle.assert_called_once_with(4)

        manager._dispatch_menu_command(99)
        on_exit.assert_called_once()

    def test_update_timer_indicator_switches_icon_and_avoids_duplicate_calls(self):
        manager, _, _, _, _ = self._create_mocked_tray()
        manager._shield_icon = 101
        manager._warning_icon = 202
        manager.notify_icon_data = NOTIFYICONDATAW()

        with patch("ghostclip.tray.shell32.Shell_NotifyIconW", return_value=1) as mock_notify:
            manager.update_timer_indicator(12)
            self.assertEqual(manager.notify_icon_data.hIcon, 202)
            self.assertIn("12с", manager.notify_icon_data.szTip)
            self.assertFalse(manager.notify_icon_data.uFlags & NIF_INFO)
            self.assertEqual(mock_notify.call_args.args[0], NIM_MODIFY)

            # Повторный вызов с тем же оставшимся временем не должен дёргать Win32 API
            manager.update_timer_indicator(12)
            self.assertEqual(mock_notify.call_count, 1)

            manager.update_timer_indicator(0)
            self.assertEqual(manager.notify_icon_data.hIcon, 101)
            self.assertIn("Ctrl+Shift+X", manager.notify_icon_data.szTip)
            self.assertEqual(mock_notify.call_count, 2)


if __name__ == "__main__":
    unittest.main()
