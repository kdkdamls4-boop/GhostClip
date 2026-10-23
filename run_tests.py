#!/usr/bin/env python3
"""
Запуск всех тестов проекта GhostClip.
Использование: python run_tests.py
"""

import sys
import os
import unittest

# Добавляем корневой каталог проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    loader = unittest.TestLoader()
    start_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")
    suite = loader.discover(start_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
