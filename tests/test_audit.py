import os
import tempfile
import unittest
from unittest.mock import patch

from ghostclip.config import config, log_audit


class TestAudit(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self._log_path = os.path.join(self._temp_dir.name, "test_clipboard_access.log")
        self._original_audit = config.audit_logging
        config.audit_logging = True

    def tearDown(self):
        config.audit_logging = self._original_audit
        self._temp_dir.cleanup()

    def test_log_audit_masks_secrets(self):
        secret_sample = "sk-" + "proj-" + "testsecret1234567890abcdef"
        card_sample = "4532 0151 1283 0366"
        with patch("ghostclip.config.LOG_FILE_PATH", self._log_path):
            log_audit("TEST_EVENT", "test_proc.exe", secret_sample)
            log_audit("CARD_EVENT", "chrome.exe", card_sample)

        with open(self._log_path, encoding="utf-8") as log_file:
            content = log_file.read()

        self.assertIn("sk-p•••ef", content)
        self.assertNotIn("testsecret1234567890", content)
        self.assertIn("4532•••66", content)
        self.assertNotIn("4532 0151 1283 0366", content)

    def test_log_audit_hides_plain_text_content(self):
        long_text = "личная переписка " * 10
        bracketed_note = "[Встреча с Алисой в клинике в 12:00]"
        with patch("ghostclip.config.LOG_FILE_PATH", self._log_path):
            log_audit("CLIPBOARD_SET", "notepad.exe", long_text)
            log_audit("CLIPBOARD_SET", "notepad.exe", bracketed_note)
            log_audit("PANIC_FLUSH", "User", "[ПАНИКА]")

        with open(self._log_path, encoding="utf-8") as log_file:
            content = log_file.read()

        self.assertIn(f"[текст, {len(long_text)} симв.]", content)
        self.assertNotIn("личная переписка", content)
        self.assertIn(f"[текст, {len(bracketed_note)} симв.]", content)
        self.assertNotIn("клинике", content)
        self.assertIn("[DATA: [ПАНИКА]]", content)

    def test_log_audit_rotates_on_size_limit(self):
        with (
            patch("ghostclip.config.LOG_FILE_PATH", self._log_path),
            patch("ghostclip.config.MAX_LOG_BYTES", 50),
        ):
            log_audit("CLIPBOARD_SET", "notepad.exe", "first copied message")
            log_audit("CLIPBOARD_SET", "notepad.exe", "second copied message")

        rotated_path = f"{self._log_path}.1"
        self.assertTrue(os.path.exists(rotated_path))
        self.assertTrue(os.path.exists(self._log_path))

    def test_log_audit_respects_disabled_toggle(self):
        config.audit_logging = False
        with patch("ghostclip.config.LOG_FILE_PATH", self._log_path):
            log_audit("CLIPBOARD_SET", "notepad.exe", "normal text")

        self.assertFalse(os.path.exists(self._log_path))


if __name__ == "__main__":
    unittest.main()
