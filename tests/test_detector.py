import unittest
from ghostclip.detector import (
    luhn_check,
    calculate_entropy,
    detect_secret,
    mask_secret,
)


class TestDetector(unittest.TestCase):

    def test_luhn_check(self):
        # Валидный тестовый номер Visa
        self.assertTrue(luhn_check("4532015112830366"))
        # Невалидный номер
        self.assertFalse(luhn_check("4532015112830367"))
        # Слишком короткий
        self.assertFalse(luhn_check("123456"))

    def test_calculate_entropy(self):
        low_ent = calculate_entropy("aaaaaaaaaaaaaaaa")
        high_ent = calculate_entropy("k9#mP$2vL!9xQ@z1")
        self.assertEqual(low_ent, 0.0)
        self.assertGreater(high_ent, 3.5)

    def test_detect_openai_key(self):
        key = "sk-proj-abcde1234567890abcdef1234567890"
        match = detect_secret(key)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "API_KEY")
        self.assertIn("OpenAI", match[1])

    def test_detect_github_token(self):
        token = "ghp_1234567890abcdefghij1234567890abcdef"
        match = detect_secret(token)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "TOKEN")
        self.assertIn("GitHub", match[1])

    def test_detect_aws_key(self):
        aws = "AKIAIOSFODNN7EXAMPLE"
        match = detect_secret(aws)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "API_KEY")
        self.assertIn("AWS", match[1])

    def test_detect_credit_card(self):
        card = "4532 0151 1283 0366"
        match = detect_secret(card)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "CREDIT_CARD")

    def test_detect_high_entropy_password(self):
        pwd = "vX9#mQ2$pL!8zR@k"
        match = detect_secret(pwd)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "PASSWORD")

    def test_detect_normal_text(self):
        normal = "Привет, как дела? Встретимся в 18:00 у метро."
        self.assertIsNone(detect_secret(normal))

    def test_mask_secret(self):
        secret = "sk-123456789abcdef"
        masked = mask_secret(secret)
        self.assertEqual(masked, "sk-1•••ef")
        self.assertNotIn("123456789", masked)


if __name__ == "__main__":
    unittest.main()
