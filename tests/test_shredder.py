import unittest
from unittest.mock import patch

from ghostclip.shredder import (
    CREATE_NO_WINDOW,
    OVERWRITE_DUMMY_TEXT,
    shred_clipboard,
    wipe_win_v_history,
)


class TestShredder(unittest.TestCase):
    def test_shred_clipboard_writes_private_dummy_and_wipes(self):
        with (
            patch("ghostclip.shredder.write_clipboard_text") as mock_write,
            patch("ghostclip.shredder.wipe_clipboard", return_value=True) as mock_wipe,
        ):
            result = shred_clipboard()

        self.assertTrue(result)
        mock_write.assert_called_once_with(OVERWRITE_DUMMY_TEXT, private=True)
        mock_wipe.assert_called_once_with()

    def test_wipe_win_v_history_uses_create_no_window_and_handles_errors(self):
        with patch("ghostclip.shredder.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            self.assertTrue(wipe_win_v_history())
            self.assertEqual(mock_run.call_args.kwargs["creationflags"], CREATE_NO_WINDOW)

        with patch("ghostclip.shredder.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            self.assertFalse(wipe_win_v_history())

        with patch("ghostclip.shredder.subprocess.run", side_effect=OSError("powershell failed")):
            self.assertFalse(wipe_win_v_history())


if __name__ == "__main__":
    unittest.main()
