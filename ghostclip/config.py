"""Настройки [1-6], сохранение конфигурации в JSON, белый список программ и журнал аудита."""

import datetime
import json
import os
import sys
import threading
import winreg

from .detector import detect_secret, mask_secret


def get_app_dir() -> str:
    """Возвращает каталог программы: рядом с .exe или корень проекта."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = get_app_dir()
LOG_FILE_PATH = os.path.join(APP_DIR, "clipboard_access.log")
SETTINGS_FILE_PATH = os.path.join(APP_DIR, "ghostclip_settings.json")
MIN_TIMER_SECONDS = 5
MAX_TIMER_SECONDS = 3600
MAX_LOG_BYTES = 1_048_576
AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "GhostClipShield"
AUDIT_STATUS_LABELS = frozenset({"[БУФЕР_ОЧИЩЕН]", "[ПАНИКА]", "[СЕКРЕТ_ЗАТЕРТ]", "[ПРОПУЩЕНО]"})
_log_lock = threading.Lock()


def get_autostart_command() -> str:
    """Формирует команду запуска GhostClip для реестра автозагрузки Windows."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_script_path = os.path.join(APP_DIR, "main.py")
    return f'"{sys.executable}" "{main_script_path}"'


def is_autostart_enabled() -> bool:
    """Проверяет, прописан ли GhostClip Shield в автозагрузке текущего пользователя."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return bool(value)
    except (FileNotFoundError, OSError):
        return False


def set_autostart(enabled: bool) -> bool:
    """Включает или выключает автозапуск GhostClip в ветке HKCU\\...\\Run."""
    try:
        if enabled:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, AUTOSTART_VALUE_NAME, 0, winreg.REG_SZ, get_autostart_command())
        else:
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.DeleteValue(key, AUTOSTART_VALUE_NAME)
            except FileNotFoundError:
                pass
        return True
    except OSError:
        return False


class ShieldConfig:
    """Хранит состояние защитных функций, таймер, белый список и синхронизирует их с JSON."""

    _OPTION_MAP = {
        1: ("clean_urls", "Чистка ссылок"),
        2: ("clean_zero_width", "Удаление невидимых знаков"),
        3: ("detect_secrets", "Детекция секретов"),
        4: ("auto_shred_timer", "Таймер самоуничтожения"),
        5: ("shred_win_v", "Зачистка истории Win+V"),
        6: ("audit_logging", "Журнал аудита"),
    }

    def __init__(self, settings_path: str | None = None):
        self.clean_urls = True
        self.clean_zero_width = True
        self.detect_secrets = True
        self.auto_shred_timer = True
        self.shred_win_v = True
        self.audit_logging = True
        self.timer_seconds = 45
        self.trusted_apps: list[str] = []
        self._settings_path = settings_path
        self._lock = threading.Lock()
        if self._settings_path:
            self.load()

    @staticmethod
    def _normalize_app_name(app_name: str) -> str:
        cleaned = app_name.strip().strip('"').strip("'")
        return os.path.basename(cleaned).lower()

    def load(self) -> bool:
        """Загружает настройки из JSON-файла (если он существует и корректен)."""
        if not self._settings_path or not os.path.exists(self._settings_path):
            return False
        try:
            with open(self._settings_path, encoding="utf-8") as settings_file:
                payload = json.load(settings_file)
        except Exception:
            return False

        if not isinstance(payload, dict):
            return False

        with self._lock:
            for attr_name, _ in self._OPTION_MAP.values():
                if isinstance(payload.get(attr_name), bool):
                    setattr(self, attr_name, payload[attr_name])

            saved_timer = payload.get("timer_seconds")
            if (
                isinstance(saved_timer, int)
                and not isinstance(saved_timer, bool)
                and MIN_TIMER_SECONDS <= saved_timer <= MAX_TIMER_SECONDS
            ):
                self.timer_seconds = saved_timer

            saved_apps = payload.get("trusted_apps")
            if isinstance(saved_apps, list):
                normalized_apps: list[str] = []
                for item in saved_apps:
                    if isinstance(item, str):
                        app = self._normalize_app_name(item)
                        if app and app not in normalized_apps:
                            normalized_apps.append(app)
                self.trusted_apps = normalized_apps
        return True

    def _save_locked(self) -> bool:
        if not self._settings_path:
            return False
        payload = {
            "clean_urls": self.clean_urls,
            "clean_zero_width": self.clean_zero_width,
            "detect_secrets": self.detect_secrets,
            "auto_shred_timer": self.auto_shred_timer,
            "shred_win_v": self.shred_win_v,
            "audit_logging": self.audit_logging,
            "timer_seconds": self.timer_seconds,
            "trusted_apps": list(self.trusted_apps),
        }
        temp_path = f"{self._settings_path}.tmp"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._settings_path)), exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as settings_file:
                json.dump(payload, settings_file, ensure_ascii=False, indent=2)
            os.replace(temp_path, self._settings_path)
            return True
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return False

    def save(self) -> bool:
        """Сохраняет текущую конфигурацию в JSON-файл."""
        with self._lock:
            return self._save_locked()

    def toggle(self, option_id: int) -> tuple[str, bool]:
        """Переключает опцию [1-6], сохраняет конфиг и возвращает (название, новое_значение)."""
        if option_id not in self._OPTION_MAP:
            raise ValueError(f"Неизвестный номер функции: {option_id}")

        attribute_name, display_name = self._OPTION_MAP[option_id]
        with self._lock:
            new_value = not getattr(self, attribute_name)
            setattr(self, attribute_name, new_value)
            self._save_locked()
            return display_name, new_value

    def set_timer_seconds(self, seconds: int) -> int:
        """Устанавливает время самоуничтожения в секундах (5..3600) и сохраняет конфиг."""
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise ValueError("Время таймера должно быть целым числом секунд.")
        if not (MIN_TIMER_SECONDS <= seconds <= MAX_TIMER_SECONDS):
            raise ValueError(f"Допустимый диапазон таймера: {MIN_TIMER_SECONDS}..{MAX_TIMER_SECONDS} сек.")
        with self._lock:
            self.timer_seconds = seconds
            self._save_locked()
            return self.timer_seconds

    def is_trusted_app(self, app_name: str) -> bool:
        """Проверяет, входит ли процесс-источник в белый список доверенных программ."""
        normalized = self._normalize_app_name(app_name)
        if not normalized or normalized == "unknown":
            return False
        with self._lock:
            return normalized in self.trusted_apps

    def add_trusted_app(self, app_name: str) -> bool:
        """Добавляет приложение (.exe) в белый список и сохраняет настройки."""
        normalized = self._normalize_app_name(app_name)
        if not normalized:
            raise ValueError("Имя приложения не может быть пустым.")
        with self._lock:
            if normalized in self.trusted_apps:
                return False
            self.trusted_apps.append(normalized)
            self._save_locked()
            return True

    def remove_trusted_app(self, app_name: str) -> bool:
        """Удаляет приложение из белого списка и сохраняет настройки."""
        normalized = self._normalize_app_name(app_name)
        with self._lock:
            if normalized not in self.trusted_apps:
                return False
            self.trusted_apps.remove(normalized)
            self._save_locked()
            return True

    def get_trusted_apps(self) -> list[str]:
        """Возвращает копию списка доверенных приложений."""
        with self._lock:
            return list(self.trusted_apps)

    def get_status_dict(self) -> dict[int, tuple[str, bool]]:
        """Возвращает текущие статусы всех шести переключателей для меню и трея."""
        with self._lock:
            return {
                1: ("Чистка ссылок (utm, fbclid, si)", self.clean_urls),
                2: ("Удаление невидимых символов", self.clean_zero_width),
                3: ("Детекция секретов и карт", self.detect_secrets),
                4: (f"Таймер самоуничтожения ({self.timer_seconds}с)", self.auto_shred_timer),
                5: ("Зачистка истории Win+V", self.shred_win_v),
                6: ("Журнал clipboard_access.log", self.audit_logging),
            }


config = ShieldConfig(settings_path=SETTINGS_FILE_PATH)


def _format_safe_snippet(text: str) -> str:
    """Маскирует секреты и скрывает содержимое обычного текста, оставляя лишь длину."""
    is_secret, secret_type, _ = detect_secret(text)
    if is_secret:
        return f"{mask_secret(text)} [{secret_type}]"

    stripped = text.strip()
    if stripped in AUDIT_STATUS_LABELS:
        return stripped
    return f"[текст, {len(text)} симв.]"


def log_audit(event_type: str, app_name: str, snippet: str, details: str = "") -> None:
    """Записывает событие безопасности в файл журнала с ротацией без утечки данных."""
    if not config.audit_logging:
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_snippet = _format_safe_snippet(snippet)
    log_line = f"[{timestamp}] [{event_type}] [APP: {app_name}] [DATA: {safe_snippet}]"
    if details:
        log_line += f" ({details})"

    with _log_lock:
        try:
            if os.path.exists(LOG_FILE_PATH) and os.path.getsize(LOG_FILE_PATH) >= MAX_LOG_BYTES:
                os.replace(LOG_FILE_PATH, f"{LOG_FILE_PATH}.1")
        except OSError:
            pass
        try:
            with open(LOG_FILE_PATH, "a", encoding="utf-8") as log_file:
                log_file.write(log_line + "\n")
        except Exception as error:
            print(f"[!] Ошибка записи в журнал: {error}")
