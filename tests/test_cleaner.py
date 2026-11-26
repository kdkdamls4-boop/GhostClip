import unittest

from ghostclip.cleaner import clean_url, sanitize_text, strip_zero_width


class TestCleaner(unittest.TestCase):
    def test_strip_zero_width(self):
        text = "Hello\u200bWorld\ufeff! This has \u200czero\u2060 width."
        cleaned, count = strip_zero_width(text)
        self.assertEqual(cleaned, "HelloWorld! This has zero width.")
        self.assertEqual(count, 4)

    def test_clean_url(self):
        dirty_url = (
            "https://example.com/watch?v=12345&utm_source=telegram"
            "&utm_custom=promo&si=abcdef&ttclid=tt99&hsa_cam=ads1&real_param=ok"
        )
        cleaned, removed = clean_url(dirty_url)
        for tracker in ("utm_source", "utm_custom", "si", "ttclid", "hsa_cam"):
            self.assertIn(tracker, removed)
            self.assertNotIn(f"{tracker}=", cleaned)
        self.assertIn("v=12345", cleaned)
        self.assertIn("real_param=ok", cleaned)

    def test_clean_url_no_tracking(self):
        clean = "https://example.com/api/v1/users?page=1&limit=20"
        result, removed = clean_url(clean)
        self.assertEqual(result, clean)
        self.assertEqual(removed, [])

    def test_clean_url_invalid_text(self):
        text = "просто текст без ссылки"
        result, removed = clean_url(text)
        self.assertEqual(result, text)
        self.assertEqual(removed, [])

    def test_sanitize_text_full_and_parentheses(self):
        mixed = "Посмотри (https://shop.com/item?id=42&fbclid=IwAR09&utm_campaign=sale\u200b)."
        cleaned, is_modified, logs = sanitize_text(mixed)
        self.assertTrue(is_modified)
        self.assertEqual(cleaned, "Посмотри (https://shop.com/item?id=42).")
        self.assertTrue(any("скрытых знаков" in entry for entry in logs))
        self.assertTrue(any("Очищен URL" in entry for entry in logs))

        wiki_url = "https://en.wikipedia.org/wiki/Python_(programming_language)?gbraid=123"
        cleaned_wiki, modified_wiki, _ = sanitize_text(wiki_url)
        self.assertTrue(modified_wiki)
        self.assertEqual(cleaned_wiki, "https://en.wikipedia.org/wiki/Python_(programming_language)")

    def test_sanitize_text_respects_individual_toggles(self):
        mixed = "Текст\u200b https://shop.com/item?id=42&utm_source=tg"

        only_zw, modified_zw, _ = sanitize_text(mixed, clean_urls_enabled=False, clean_zw_enabled=True)
        self.assertTrue(modified_zw)
        self.assertNotIn("\u200b", only_zw)
        self.assertIn("utm_source=tg", only_zw)

        only_urls, modified_urls, _ = sanitize_text(mixed, clean_urls_enabled=True, clean_zw_enabled=False)
        self.assertTrue(modified_urls)
        self.assertIn("\u200b", only_urls)
        self.assertNotIn("utm_source", only_urls)


if __name__ == "__main__":
    unittest.main()
