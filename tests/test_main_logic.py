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

    def test_clean_clipboard_if_needed_respects_toggles(self):
        sample = "https://site.com/page?id=1&utm_source=ads\u200b"
        config.clean_urls = False
        config.clean_zero_width = True

        with (
            patch("main.clipboard_has_rich_format", return_value=False),
            patch("main.write_clipboard_text") as mock_write,
            patch("main.add_log"),
        ):
            final_text, was_cleaned = app_main.clean_clipboard_if_needed(sample, "chrome.exe")

        self.assertTrue(was_cleaned)
        self.assertEqual(final_text, "https://site.com/page?id=1&utm_source=ads")
        mock_write.assert_called_once_with(final_text)

    def test_clean_clipboard_preserves_rich_multiword_text(self):
        rich_text = "Откройте статью https://site.com/post?utm_source=tg здесь"
        with (
            patch("main.clipboard_has_rich_format", return_value=True),
            patch("main.write_clipboard_text") as mock_write,
            patch("main.add_log") as mock_log,
        ):
            final_text, was_cleaned = app_main.clean_clipboard_if_needed(rich_text, "winword.exe")

        self.assertFalse(was_cleaned)
        self.assertEqual(final_text, rich_text)
        mock_write.assert_not_called()
        self.assertIn("ОЧИСТКА ПРОПУЩЕНА", mock_log.call_args.args[0])

    def test_clean_clipboard_cleans_single_url_even_when_rich_format_present(self):
        single_url = "https://site.com/post?id=42&utm_source=tg"
        with (
            patch("main.clipboard_has_rich_format", return_value=True),
            patch("main.write_clipboard_text") as mock_write,
            patch("main.add_log"),
        ):
            final_text, was_cleaned = app_main.clean_clipboard_if_needed(single_url, "chrome.exe")

        self.assertTrue(was_cleaned)
        self.assertEqual(final_text, "https://site.com/post?id=42")
        mock_write.assert_called_once_with("https://site.com/post?id=42")

    def test_rich_text_skip_still_detects_secret_with_zero_width(self):
        obfuscated_token = "token sk-\u200babcdefghijklmnopqrstuv1234"
        with (
            patch("main.clipboard_has_rich_format", return_value=True),
            patch("main.write_clipboard_text") as mock_write,
            patch("main.add_log"),
            patch("main.render_screen"),
        ):
            final_text, was_cleaned = app_main.process_clipboard_event(obfuscated_token, "winword.exe")

        self.assertFalse(was_cleaned)
        self.assertEqual(final_text, obfuscated_token)
        mock_write.assert_not_called()
        self.assertTrue(ghost_timer.is_armed())

    def test_report_error_deduplicates_consecutive_errors(self):
        with patch("main.add_log") as mock_log:
            app_main.report_error("монитор", RuntimeError("boom"))
            app_main.report_error("монитор", RuntimeError("boom"))
            app_main.report_error("монитор", ValueError("other"))

        self.assertEqual(mock_log.call_count, 2)

    def test_report_error_tolerates_stdout_failure(self):
        with patch("main.add_log", side_effect=OSError("stdout broken")):
            app_main.report_error("клавиатура", RuntimeError("io fail"))

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
