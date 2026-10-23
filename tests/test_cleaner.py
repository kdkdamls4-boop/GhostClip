import unittest
from ghostclip.cleaner import strip_zero_width, clean_url, sanitize_text


class TestCleaner(unittest.TestCase):

    def test_strip_zero_width(self):
        text = "Hello\u200BWorld\uFEFF! This has \u200Czero width."
        cleaned, count = strip_zero_width(text)
        self.assertEqual(cleaned, "HelloWorld! This has zero width.")
        self.assertEqual(count, 3)

    def test_clean_url(self):
        dirty_url = "https://example.com/watch?v=12345&utm_source=telegram&utm_medium=social&si=abcdef&real_param=ok"
        cleaned, removed = clean_url(dirty_url)
        self.assertIn("utm_source", removed)
        self.assertIn("utm_medium", removed)
        self.assertIn("si", removed)
        self.assertIn("v=12345", cleaned)
        self.assertIn("real_param=ok", cleaned)
        self.assertNotIn("utm_source", cleaned)
        self.assertNotIn("si=", cleaned)

    def test_clean_url_no_tracking(self):
        clean = "https://example.com/api/v1/users?page=1&limit=20"
        res, removed = clean_url(clean)
        self.assertEqual(res, clean)
        self.assertEqual(removed, [])

    def test_sanitize_text(self):
        mixed = "Посмотри ссылку https://shop.com/item?id=42&fbclid=IwAR09&utm_campaign=sale\u200B круто!"
        cleaned, removed, zw_count = sanitize_text(mixed)
        self.assertEqual(zw_count, 1)
        self.assertIn("fbclid", removed)
        self.assertIn("utm_campaign", removed)
        self.assertIn("id=42", cleaned)
        self.assertNotIn("fbclid", cleaned)
        self.assertNotIn("\u200B", cleaned)


if __name__ == "__main__":
    unittest.main()
