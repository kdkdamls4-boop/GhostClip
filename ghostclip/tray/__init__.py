"""
Пакет системного трея Windows (System Tray Icon) через чистый Win32 API (ctypes).

Структура:
    win32_constants.py — числовые константы Win32
    win32_api.py       — библиотеки user32/shell32/kernel32, сигнатуры, структуры
    console.py         — ConsoleWindow: скрыть/показать консоль, защита от [X]
    icon.py            — иконка в трее и всплывающие уведомления
    menu.py            — ПКМ-меню (пункты описаны кортежами MenuItem)
    manager.py         — TrayManager: связывает всё вместе
"""

from .manager import TrayManager

__all__ = ["TrayManager"]
