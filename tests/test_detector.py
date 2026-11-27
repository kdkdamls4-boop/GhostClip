import unittest

from ghostclip.detector import (
    calculate_entropy,
    detect_secret,
    has_known_card_prefix,
    luhn_check,
    mask_secret,
)


class TestDetector(unittest.TestCase):
    def test_luhn_check(self):
        self.assertTrue(luhn_check("4532015112830366"))
        self.assertTrue(luhn_check("2202 2012 3456 7895"))
        self.assertFalse(luhn_check("4532015112830367"))
        self.assertFalse(luhn_check("123456"))

    def test_calculate_entropy(self):
        self.assertEqual(calculate_entropy(""), 0.0)
        self.assertEqual(calculate_entropy("aaaaaaaaaaaaaaaa"), 0.0)
        self.assertGreater(calculate_entropy("k9#mP$2vL!9xQ@z1"), 3.6)

    def test_detect_openai_and_anthropic_keys(self):
        openai_key = "sk-" + "proj-" + "abcde1234567890abcdef1234567890"
        found, secret_type, value = detect_secret(openai_key)
        self.assertTrue(found)
        self.assertEqual(secret_type, "OPENAI_KEY")
        self.assertEqual(value, openai_key)

        anthropic_key = "sk-" + "ant-" + "api03-abcdef1234567890abcdef1234567890"
        found_ant, ant_type, ant_value = detect_secret(anthropic_key)
        self.assertTrue(found_ant)
        self.assertEqual(ant_type, "ANTHROPIC_KEY")
        self.assertEqual(ant_value, anthropic_key)

    def test_detect_github_tokens(self):
        classic = "ghp" + "_1234567890abcdefghij1234567890abcdef"
        found, secret_type, value = detect_secret(classic)
        self.assertTrue(found)
        self.assertEqual(secret_type, "GITHUB_TOKEN")
        self.assertEqual(value, classic)

        fine_grained = "github" + "_pat_" + "11AABBCCDD0123456789_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
        found_pat, pat_type, pat_value = detect_secret(fine_grained)
        self.assertTrue(found_pat)
        self.assertEqual(pat_type, "GITHUB_PAT")
        self.assertEqual(pat_value, fine_grained)

    def test_detect_google_telegram_jwt_and_db_urls(self):
        google_key = "AIza" + "SyD-TestKey_1234567890abcdefghijklmnop"
        self.assertEqual(detect_secret(google_key)[:2], (True, "GOOGLE_API_KEY"))

        telegram_token = "123456789:AAH0xYzAbCdEfGhIjKlMnOpQrStUvWxYz123"
        self.assertEqual(detect_secret(telegram_token)[:2], (True, "TELEGRAM_BOT_TOKEN"))

        jwt_token = (
            "eyJ"
            + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            + "eyJ"
            + "zdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
            + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        self.assertEqual(detect_secret(jwt_token)[:2], (True, "JWT_TOKEN"))

        pg_url = "postgresql://admin:SuperSecret123@db.example.internal:5432/prod"
        self.assertEqual(detect_secret(pg_url)[:2], (True, "DB_CONNECTION_STRING"))

        redis_url = "redis://:PassOnlySecret99@127.0.0.1:6379/0"
        self.assertEqual(detect_secret(redis_url)[:2], (True, "DB_CONNECTION_STRING"))

    def test_detect_expanded_service_tokens(self):
        samples = [
            ("SLACK_TOKEN", "xox" + "b-1234567890-abcdefghij"),
            ("STRIPE_KEY", "sk_" + "live_" + "AbCd1234EfGh5678IjKlMnOp"),
            ("GITLAB_PAT", "glpat" + "-abcDef123456_7890GhIjKl"),
            ("NPM_TOKEN", "npm_" + ("a1B2c3" * 6)),
            ("HUGGINGFACE_TOKEN", "hf_" + ("xY9zAb" * 5)),
            (
                "SENDGRID_KEY",
                "SG"
                + "."
                + ("AbCdEf1234567890GhIjKl")
                + "."
                + ("MnOpQr1234567890StUvWxYz_" * 1)
                + "AbCdEfGhIjKlMnOpQr",
            ),
            ("AZURE_STORAGE_KEY", "Account" + "Key=" + ("AbCdEfGhIj1234567890" * 2) + "=="),
        ]
        for expected_type, token_sample in samples:
            with self.subTest(secret_type=expected_type):
                self.assertEqual(detect_secret(token_sample)[:2], (True, expected_type))

    def test_card_prefix_filter_rejects_random_luhn_numbers(self):
        non_card_luhn = "9000000000000001"
        self.assertTrue(luhn_check(non_card_luhn))
        self.assertFalse(has_known_card_prefix(non_card_luhn))
        self.assertFalse(has_known_card_prefix("1234"))
        self.assertFalse(has_known_card_prefix("4532abc123456789"))
        self.assertFalse(detect_secret(non_card_luhn)[0])

        for known_card in ("4532015112830366", "5425233430109903", "2202201234567895", "341234567890123"):
            with self.subTest(card=known_card[:4]):
                self.assertTrue(has_known_card_prefix(known_card))

    def test_detect_aws_and_private_key(self):
        aws_key = "AKIAIOSFODNN7EXAMPLE"
        found, secret_type, value = detect_secret(aws_key)
        self.assertTrue(found)
        self.assertEqual(secret_type, "AWS_KEY")
        self.assertEqual(value, aws_key)

        ssh_key = "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nabc123\n-----END " + "OPENSSH PRIVATE KEY-----"
        found_key, key_type, _ = detect_secret(ssh_key)
        self.assertTrue(found_key)
        self.assertEqual(key_type, "PRIVATE_KEY")

    def test_detect_credit_card(self):
        card = "4532 0151 1283 0366"
        found, secret_type, value = detect_secret(card)
        self.assertTrue(found)
        self.assertEqual(secret_type, "CREDIT_CARD")
        self.assertEqual(value, card)

    def test_detect_high_entropy_password(self):
        password = "vX9#mQ2$pL!8zR@kW4%n"
        found, secret_type, value = detect_secret(password)
        self.assertTrue(found)
        self.assertEqual(secret_type, "HIGH_ENTROPY_PASSWORD")
        self.assertEqual(value, password)

    def test_ignores_normal_text_and_urls(self):
        for safe_text in (
            "Привет, как дела? Встретимся в 18:00 у метро.",
            "supercalifragilisticexpialidocious",
            "VeryLongCamelCaseIdentifierName",
            "https://example.com/docs/v2/getting-started?page=12&section=intro",
            "https://example.com/assets/mask-1234567890abcdefghijklmnop",
            "postgres://readonly@localhost:5432/public_docs",
        ):
            found, secret_type, value = detect_secret(safe_text)
            self.assertFalse(found, f"Ложное срабатывание на: {safe_text}")
            self.assertEqual(secret_type, "")
            self.assertEqual(value, "")

    def test_mask_secret(self):
        self.assertEqual(mask_secret("secret"), "••••••")
        self.assertEqual(mask_secret("abcd1234"), "ab•••34")
        masked = mask_secret("sk-" + "123456789abcdef")
        self.assertEqual(masked, "sk-1•••ef")
        self.assertNotIn("123456789", masked)


if __name__ == "__main__":
    unittest.main()
