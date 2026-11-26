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
        secret_sample = "sk-proj-testsecret1234567890abcdef"
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

    def test_log_audit_truncates_long_text(self):
        long_text = "word " * 30
        with patch("ghostclip.config.LOG_FILE_PATH", self._log_path):
            log_audit("CLIPBOARD_SET", "notepad.exe", long_text)

        with open(self._log_path, encoding="utf-8") as log_file:
            content = log_file.read()

        self.assertIn("[всего", content)

    def test_log_audit_respects_disabled_toggle(self):
        config.audit_logging = False
        with patch("ghostclip.config.LOG_FILE_PATH", self._log_path):
            log_audit("CLIPBOARD_SET", "notepad.exe", "normal text")

        self.assertFalse(os.path.exists(self._log_path))


if __name__ == "__main__":
    unittest.main()
