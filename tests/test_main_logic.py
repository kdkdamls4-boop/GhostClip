import unittest
from unittest.mock import MagicMock, patch

import main as app_main
from ghostclip.config import config
from ghostclip.shredder import ghost_timer


class TestMainLogic(unittest.TestCase):
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
        ) = self._saved_state

    def test_clean_clipboard_if_needed_respects_toggles(self):
        sample = "https://site.com/page?id=1&utm_source=ads\u200b"
        config.clean_urls = False
        config.clean_zero_width = True

        with patch("main.write_clipboard_text") as mock_write, patch("main.add_log"):
            final_text, was_cleaned = app_main.clean_clipboard_if_needed(sample, "chrome.exe")

        self.assertTrue(was_cleaned)
        self.assertEqual(final_text, "https://site.com/page?id=1&utm_source=ads")
        mock_write.assert_called_once_with(final_text)

    def test_handle_clipboard_content_arms_and_disarms_timer(self):
        mock_tray = MagicMock()
        mock_tray.is_console_visible.return_value = False
        app_main.tray_manager = mock_tray
        config.timer_seconds = 20

        with patch("main.add_log"), patch("main.render_screen"):
            app_main.handle_clipboard_content("AKIAIOSFODNN7EXAMPLE", "chrome.exe")
            self.assertTrue(ghost_timer.is_armed())
            mock_tray.update_timer_indicator.assert_called_with(20)
            mock_tray.show_balloon.assert_called_once()

            app_main.handle_clipboard_content("Обычное приветствие", "notepad.exe")
            self.assertFalse(ghost_timer.is_armed())
            mock_tray.update_timer_indicator.assert_called_with(0)

    def test_trusted_app_bypasses_cleaning_and_timer(self):
        config.add_trusted_app("KeePassXC.exe")
        mock_tray = MagicMock()
        app_main.tray_manager = mock_tray
        ghost_timer.arm(30)

        with patch("main.add_log"), patch("main.write_clipboard_text") as mock_write:
            final_text, was_cleaned = app_main.process_clipboard_event(
                "https://vault.local/?utm_source=test&secret=AKIAIOSFODNN7EXAMPLE",
                "KeePassXC.exe",
            )

        self.assertFalse(was_cleaned)
        self.assertIn("utm_source=test", final_text)
        self.assertFalse(ghost_timer.is_armed())
        mock_write.assert_not_called()
        mock_tray.update_timer_indicator.assert_called_with(0)

    def test_auto_destruct_respects_shred_win_v_toggle(self):
        mock_tray = MagicMock()
        app_main.tray_manager = mock_tray
        config.shred_win_v = False
        with (
            patch("main.wipe_clipboard") as mock_wipe,
            patch("main.wipe_win_v_history") as mock_win_v,
            patch("main.add_log"),
        ):
            app_main.handle_auto_destruct()
        mock_wipe.assert_called_once()
        mock_win_v.assert_not_called()
        mock_tray.update_timer_indicator.assert_called_with(0)

        config.shred_win_v = True
        with (
            patch("main.wipe_clipboard") as mock_wipe,
            patch("main.wipe_win_v_history") as mock_win_v,
            patch("main.add_log"),
        ):
            app_main.handle_auto_destruct()
        mock_wipe.assert_called_once()
        mock_win_v.assert_called_once()


if __name__ == "__main__":
    unittest.main()
