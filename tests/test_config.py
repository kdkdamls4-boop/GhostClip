import unittest
from ghostclip.config import ShieldConfig


class TestConfig(unittest.TestCase):

    def test_default_config(self):
        cfg = ShieldConfig()
        self.assertTrue(cfg.clean_urls)
        self.assertTrue(cfg.clean_zero_width)
        self.assertTrue(cfg.detect_secrets)
        self.assertTrue(cfg.ghost_timer_enabled)
        self.assertTrue(cfg.wipe_win_v)
        self.assertTrue(cfg.audit_logging)

    def test_toggle_options(self):
        cfg = ShieldConfig()
        name, val = cfg.toggle(1)
        self.assertFalse(val)
        self.assertFalse(cfg.clean_urls)

        # Переключаем обратно
        name, val = cfg.toggle(1)
        self.assertTrue(val)
        self.assertTrue(cfg.clean_urls)

    def test_toggle_invalid_id(self):
        cfg = ShieldConfig()
        with self.assertRaises(ValueError):
            cfg.toggle(99)

    def test_status_dict(self):
        cfg = ShieldConfig()
        statuses = cfg.get_status_dict()
        self.assertEqual(len(statuses), 6)
        self.assertIn(1, statuses)
        self.assertTrue(statuses[1][1])


if __name__ == "__main__":
    unittest.main()
