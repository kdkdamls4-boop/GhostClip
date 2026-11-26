import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ghostclip.config import (
    AUTOSTART_VALUE_NAME,
    ShieldConfig,
    get_autostart_command,
    is_autostart_enabled,
    set_autostart,
)


class TestConfig(unittest.TestCase):
    def test_default_config(self):
        cfg = ShieldConfig()
        self.assertTrue(cfg.clean_urls)
        self.assertTrue(cfg.clean_zero_width)
        self.assertTrue(cfg.detect_secrets)
        self.assertTrue(cfg.auto_shred_timer)
        self.assertTrue(cfg.shred_win_v)
        self.assertTrue(cfg.audit_logging)
        self.assertEqual(cfg.timer_seconds, 45)
        self.assertEqual(cfg.get_trusted_apps(), [])

    def test_toggle_all_options(self):
        cfg = ShieldConfig()
        expected_attributes = [
            "clean_urls",
            "clean_zero_width",
            "detect_secrets",
            "auto_shred_timer",
            "shred_win_v",
            "audit_logging",
        ]
        for option_id, attribute_name in enumerate(expected_attributes, start=1):
            _, disabled_value = cfg.toggle(option_id)
            self.assertFalse(disabled_value)
            self.assertFalse(getattr(cfg, attribute_name))

            _, enabled_value = cfg.toggle(option_id)
            self.assertTrue(enabled_value)
            self.assertTrue(getattr(cfg, attribute_name))

    def test_toggle_invalid_id(self):
        cfg = ShieldConfig()
        for invalid_id in (0, 7, 99):
            with self.assertRaises(ValueError):
                cfg.toggle(invalid_id)

    def test_status_dict(self):
        cfg = ShieldConfig()
        statuses = cfg.get_status_dict()
        self.assertEqual(set(statuses.keys()), {1, 2, 3, 4, 5, 6})
        self.assertTrue(all(isinstance(label, str) and enabled for label, enabled in statuses.values()))

    def test_timer_seconds_validation(self):
        cfg = ShieldConfig()
        self.assertEqual(cfg.set_timer_seconds(90), 90)
        self.assertEqual(cfg.timer_seconds, 90)
        for invalid_value in (0, 4, 3601, True, "30"):
            with self.assertRaises(ValueError):
                cfg.set_timer_seconds(invalid_value)  # type: ignore[arg-type]

    def test_trusted_apps_management(self):
        cfg = ShieldConfig()
        self.assertFalse(cfg.is_trusted_app(""))
        self.assertFalse(cfg.is_trusted_app("Unknown"))

        self.assertTrue(cfg.add_trusted_app(r'"C:\Program Files\KeePassXC\KeePassXC.exe"'))
        self.assertFalse(cfg.add_trusted_app("keepassxc.exe"))
        self.assertTrue(cfg.is_trusted_app("KEEPASSXC.EXE"))
        self.assertEqual(cfg.get_trusted_apps(), ["keepassxc.exe"])

        with self.assertRaises(ValueError):
            cfg.add_trusted_app("   ")

        self.assertTrue(cfg.remove_trusted_app("keepassxc.exe"))
        self.assertFalse(cfg.remove_trusted_app("keepassxc.exe"))
        self.assertFalse(cfg.is_trusted_app("keepassxc.exe"))

    def test_persistence_json_roundtrip_and_corrupt_recovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = os.path.join(temp_dir, "ghostclip_settings.json")
            first = ShieldConfig(settings_path=settings_path)
            first.toggle(1)
            first.set_timer_seconds(120)
            first.add_trusted_app("bitwarden.exe")

            reloaded = ShieldConfig(settings_path=settings_path)
            self.assertFalse(reloaded.clean_urls)
            self.assertTrue(reloaded.detect_secrets)
            self.assertEqual(reloaded.timer_seconds, 120)
            self.assertEqual(reloaded.get_trusted_apps(), ["bitwarden.exe"])

            with open(settings_path, "w", encoding="utf-8") as broken_file:
                broken_file.write("{broken json")
            fallback = ShieldConfig(settings_path=settings_path)
            self.assertEqual(fallback.timer_seconds, 45)
            self.assertTrue(fallback.clean_urls)

    def test_autostart_registry_helpers(self):
        command = get_autostart_command()
        self.assertIn("main.py", command)

        mock_winreg = MagicMock()
        mock_winreg.HKEY_CURRENT_USER = object()
        mock_winreg.KEY_READ = 1
        mock_winreg.KEY_SET_VALUE = 2
        mock_winreg.REG_SZ = 1
        mock_key = mock_winreg.CreateKeyEx.return_value.__enter__.return_value
        mock_delete_key = mock_winreg.OpenKey.return_value.__enter__.return_value
        mock_winreg.QueryValueEx.return_value = (command, 1)

        with patch("ghostclip.config.winreg", mock_winreg):
            self.assertTrue(is_autostart_enabled())
            self.assertTrue(set_autostart(True))
            mock_winreg.CreateKeyEx.assert_called_once()
            mock_winreg.SetValueEx.assert_called_once_with(
                mock_key, AUTOSTART_VALUE_NAME, 0, mock_winreg.REG_SZ, command
            )

            self.assertTrue(set_autostart(False))
            mock_winreg.DeleteValue.assert_called_once_with(mock_delete_key, AUTOSTART_VALUE_NAME)

            mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
            self.assertFalse(is_autostart_enabled())

            mock_winreg.OpenKey.side_effect = FileNotFoundError()
            self.assertTrue(set_autostart(False))


if __name__ == "__main__":
    unittest.main()
