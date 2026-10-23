import os
import unittest
from ghostclip.audit import log_audit, LOG_FILE_PATH


class TestAudit(unittest.TestCase):

    def test_log_audit_masks_secrets(self):
        secret_sample = "sk-proj-testsecret1234567890abcdef"
        log_audit("TEST_EVENT", "test_proc.exe", secret_sample)
        self.assertTrue(os.path.exists(LOG_FILE_PATH))
        with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("sk-p•••ef", content)
        self.assertNotIn("testsecret1234567890", content)


if __name__ == "__main__":
    unittest.main()
