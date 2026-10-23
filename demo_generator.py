"""
Генератор тестовых данных для проверки всех функций GhostClip Shield.
Может генерировать новые валидные карты (по алгоритму Луна), токены, пароли и грязные ссылки,
а также сразу отправлять их в буфер обмена по нажатию клавиши [1-8]!
"""

import sys
import os
import random
import string

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ghostclip.clipboard import write_clipboard_text


def generate_luhn_card(prefix: str = "4532") -> str:
    """Генерирует случайный 16-значный номер банковской карты, проходящий проверку Луна."""
    digits = [int(x) for x in prefix]
    while len(digits) < 15:
        digits.append(random.randint(0, 9))

    # Вычисляем контрольную 16-ю цифру по алгоритму Луна
    checksum = 0
    for i, d in enumerate(digits[::-1]):
        if i % 2 == 0:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    check_digit = (10 - (checksum % 10)) % 10
    digits.append(check_digit)

    raw = "".join(map(str, digits))
    return f"{raw[:4]} {raw[4:8]} {raw[8:12]} {raw[12:]}"


def generate_openai_key() -> str:
    chars = string.ascii_letters + string.digits
    return "sk-proj-" + "".join(random.choices(chars, k=32))


def generate_github_token() -> str:
    chars = string.ascii_letters + string.digits
    return "ghp_" + "".join(random.choices(chars, k=36))


def generate_aws_key() -> str:
    chars = string.ascii_uppercase + string.digits
    return "AKIA" + "".join(random.choices(chars, k=16))


def generate_strong_password() -> str:
    pool = (
        random.choices(string.ascii_uppercase, k=5)
        + random.choices(string.ascii_lowercase, k=5)
        + random.choices(string.digits, k=5)
        + random.choices("!@#$%^&*?", k=5)
    )
    random.shuffle(pool)
    return "".join(pool)


def generate_dirty_url() -> str:
    vid = "".join(random.choices(string.ascii_letters + string.digits, k=11))
    si = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    fb = "".join(random.choices(string.ascii_letters + string.digits, k=20))
    return f"https://www.youtube.com/watch?v={vid}&si={si}&utm_source=telegram&utm_medium=cpc&fbclid={fb}"


def generate_zero_width_text() -> str:
    return "Секретный\u200Bдокумент\u200Cкомпании\uFEFFсо_скрытыми\u200Dсимволами_слежки"


def main():
    print("=" * 72)
    print("   🧪 ГЕНЕРАТОР ТЕСТОВЫХ ПРИМЕРОВ ДЛЯ ПРОВЕРКИ GHOSTCLIP SHIELD")
    print("=" * 72)
    print(" Нажмите цифру [1-8] и Enter — пример сгенерируется и СРАЗУ скопируется")
    print(" в буфер обмена (смотрите на реакцию запущенного окна main.py!):")
    print("-" * 72)
    print("  [1] 🧹 Сгенерировать грязную ссылку с метками (utm_source, si, fbclid)")
    print("  [2] 🥷 Сгенерировать текст с невидимыми шпионскими символами (Zero-Width)")
    print("  [3] 💳 Сгенерировать случайную валидную карту Visa/МИР (алгоритм Луна)")
    print("  [4] 🤖 Сгенерировать случайный OpenAI API Key (sk-proj-...)")
    print("  [5] 🐙 Сгенерировать случайный GitHub Token (ghp_...)")
    print("  [6] ☁️  Сгенерировать случайный AWS Access Key (AKIA...)")
    print("  [7] 🔐 Сгенерировать сложный пароль (высокая энтропия Шеннона)")
    print("  [8] 📋 Скопировать обычный безопасный текст (проверка сброса таймера)")
    print("  [p] 📄 Вывести все примеры списком в консоль для ручного копирования")
    print("  [q] 🚪 Выход")
    print("=" * 72)

    while True:
        try:
            choice = input("\nВыберите тест [1-8, p, q]: ").strip().lower()
            if not choice:
                continue

            if choice == "q":
                break
            elif choice == "p":
                print("\n--- СВЕЖИЕ СГЕНЕРИРОВАННЫЕ ПРИМЕРЫ ---")
                print(f"1. Грязная ссылка : {generate_dirty_url()}")
                print(f"2. Карта Visa     : {generate_luhn_card('4532')}")
                print(f"3. Карта МИР      : {generate_luhn_card('2202')}")
                print(f"4. OpenAI Key     : {generate_openai_key()}")
                print(f"5. GitHub Token   : {generate_github_token()}")
                print(f"6. AWS Key        : {generate_aws_key()}")
                print(f"7. Сложный пароль : {generate_strong_password()}")
                continue

            sample = None
            label = ""

            if choice == "1":
                sample = generate_dirty_url()
                label = "Грязная ссылка с трекерами"
            elif choice == "2":
                sample = generate_zero_width_text()
                label = "Текст с 4 невидимыми Zero-Width символами"
            elif choice == "3":
                prefix = random.choice(["4532", "5425", "2202"])
                sample = generate_luhn_card(prefix)
                label = "Валидная банковская карта (проходит тест Луна)"
            elif choice == "4":
                sample = generate_openai_key()
                label = "OpenAI API Key"
            elif choice == "5":
                sample = generate_github_token()
                label = "GitHub Personal Token"
            elif choice == "6":
                sample = generate_aws_key()
                label = "AWS Access Key ID"
            elif choice == "7":
                sample = generate_strong_password()
                label = "Высокоэнтропийный пароль"
            elif choice == "8":
                sample = "Привет! Это обычный безопасный текст без секретов и ссылок."
                label = "Обычный безопасный текст"
            else:
                print("[!] Введите цифру от 1 до 8, 'p' или 'q'.")
                continue

            if write_clipboard_text(sample):
                print(f"✅ Скопировано в буфер [{label}]:\n   {sample}")
            else:
                print("❌ Не удалось записать в буфер обмена.")

        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    main()
