# Правила проекта GhostClip Shield (`amazing-shannon`)

1. **Ноль внешних runtime-зависимостей:** код в `main.py` и `ghostclip/` должен работать исключительно на стандартной библиотеке Python 3.10+ и Win32 API через `ctypes` (`requirements.txt` для работы программы остаётся без сторонних пакетов).
2. **Строгая синхронность `explained/`:** любое изменение логики в `main.py` или `ghostclip/*.py` обязательно дублируй в `explained/main.py` и `explained/ghostclip/*.py` с подробными комментариями на русском языке, сохраняя 1-в-1 эквивалентность AST (`tests/test_explained_sync.py`).
3. **Понятный стиль кода и обучение:** пиши плоский код без загадочных сокращений; для учебных объяснений, `explained/` или подготовки материалов используй скилл `code-mentor-simple`.
4. **Обязательные проверки перед коммитом:**
   - `python run_tests.py` (включая `test_explained_sync.py`);
   - `ruff check .` и `ruff format --check .`;
   - при изменениях сборки — проверка `pyinstaller --clean ghostclip.spec`.
5. **Безопасность:** не коммить реальные секреты, `clipboard_access.log` и локальные `ghostclip_settings.json`; в тестах и демо используй только синтетические генераторы (`demo_generator.py`).
