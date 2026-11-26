# 🎓 GhostClip Shield — учебная копия с объяснениями

Это **полная рабочая копия** компактной архитектуры проекта (`7` основных файлов логики), в которой все модули подробно прокомментированы на русском языке.
Логика работы полностью совпадает с основным кодом из корня и папки `ghostclip/`.

## 📖 В каком порядке читать

| № | Файл | За что отвечает |
|:---:|---|---|
| 0 | [00_ОСНОВЫ_PYTHON.md](00_ОСНОВЫ_PYTHON.md) | Базовые конструкции Python на примерах из проекта |
| 1 | [ghostclip/config.py](ghostclip/config.py) | Переключатели `[1-6]`, JSON-настройки, автозапуск, белый список и приватный ротируемый лог |
| 2 | [ghostclip/detector.py](ghostclip/detector.py) | Поиск API-ключей (OpenAI, Anthropic, Google, GitHub, AWS, Slack, Stripe, GitLab, npm, HF, SendGrid, Azure, Telegram), JWT, БД, карт по IIN+Луну и паролей |
| 3 | [ghostclip/cleaner.py](ghostclip/cleaner.py) | Вырезание трекинг-меток (`utm_*`, `hsa_*`, `fbclid`, `si`...) и невидимых знаков |
| 4 | [ghostclip/clipboard.py](ghostclip/clipboard.py) | Чтение/запись буфера обмена Windows через `ctypes`, приватные флаги `Win+V`, проверка HTML/RTF и имя процесса |
| 5 | [ghostclip/shredder.py](ghostclip/shredder.py) | Приватная затирка буфера, очистка истории `Win+V` (WinRT) и потокобезопасный таймер |
| 6 | [ghostclip/tray.py](ghostclip/tray.py) | Иконка щита в трее, мьютекс одиночного запуска, индикация таймера, `Ctrl+Shift+X`, ПКМ-меню и скрытие консоли |
| 7 | [ghostclip/\_\_init\_\_.py](ghostclip/__init__.py) | Общий экспорт компонентов пакета `ghostclip` |
| 8 | [main.py](main.py) | Главная точка входа: консольный пульт, настройки `[S]`, горячие клавиши и цикл защиты |

## 🗺️ Как всё связано

```text
               main.py (пульт управления + клавиатура + цикл)
                  │
   ┌──────────────┼────────────────┬──────────────────┐
   ▼              ▼                ▼                  ▼
clipboard.py   cleaner.py      detector.py        tray.py
(буфер/окно)  (чистка URL)     (поиск секретов)  (трей/ПКМ)
                                   │
                                   ▼
                              shredder.py (таймер + Win+V)
   │                               │
   └───────────────────────────────┴──► config.py (настройки + аудит)
```

## ▶️ Запуск учебной версии

```bash
python explained/main.py
```
