"""
explained/ghostclip/config.py
Модуль настроек [1-6], сохранения конфигурации в JSON, белого списка и безопасного журнала.
"""

import datetime  # datetime — получение точной даты и времени события
import json  # json — чтение и запись настроек в текстовый формат JSON
import os  # os.path / os.replace — кроссплатформенная работа с путями и атомарная замена файла
import sys  # sys.frozen — проверка, запущена ли программа как собранный .exe (PyInstaller)
import threading  # threading.Lock — защита данных при работе нескольких потоков одновременно
import winreg  # winreg — чтение и запись ключа автозапуска в реестре Windows

from .detector import detect_secret, mask_secret


def get_app_dir() -> str:
    """
    Определяет папку, где должны лежать настройки и журнал.
    Если программа упакована в .exe, берём папку рядом с .exe; иначе — корень проекта.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = get_app_dir()

# Полные пути к файлу журнала и файлу сохранения настроек
LOG_FILE_PATH = os.path.join(APP_DIR, "clipboard_access.log")
SETTINGS_FILE_PATH = os.path.join(APP_DIR, "ghostclip_settings.json")

# Допустимый диапазон времени таймера самоуничтожения (в секундах)
MIN_TIMER_SECONDS = 5
MAX_TIMER_SECONDS = 3600

# Максимальный размер журнала аудита перед ротацией в .log.1 (1 МБ)
MAX_LOG_BYTES = 1_048_576

# Ветка реестра Windows для автозапуска программ текущего пользователя
AUTOSTART_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE_NAME = "GhostClipShield"
AUDIT_STATUS_LABELS = frozenset({"[БУФЕР_ОЧИЩЕН]", "[ПАНИКА]", "[СЕКРЕТ_ЗАТЕРТ]", "[ПРОПУЩЕНО]"})

# Внутренний замок (мьютекс): два потока не смогут писать в один файл в одну и ту же миллисекунду
_log_lock = threading.Lock()


def get_autostart_command() -> str:
    """Собирает командную строку запуска GhostClip (для .exe или python main.py) для реестра."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_script_path = os.path.join(APP_DIR, "main.py")
    return f'"{sys.executable}" "{main_script_path}"'


def is_autostart_enabled() -> bool:
    """Проверяет в реестре HKCU\\...\\Run, включён ли автозапуск при старте Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, AUTOSTART_VALUE_NAME)
            return bool(value)
    except (FileNotFoundError, OSError):
        return False


def set_autostart(enabled: bool) -> bool:
    """Прописывает или удаляет запись автозапуска GhostClip Shield в реестре текущего пользователя."""
    try:
        if enabled:
            # CreateKeyEx создаст раздел Run, если пользователь ещё ни разу не добавлял автозапуск
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
    """Хранит состояние 6 переключателей, время таймера, белый список и синхронизирует их с JSON."""

    # Соответствие номера кнопки [1-6] имени атрибута объекта и подписи
    _OPTION_MAP = {
        1: ("clean_urls", "Чистка ссылок"),
        2: ("clean_zero_width", "Удаление невидимых знаков"),
        3: ("detect_secrets", "Детекция секретов"),
        4: ("auto_shred_timer", "Таймер самоуничтожения"),
        5: ("shred_win_v", "Зачистка истории Win+V"),
        6: ("audit_logging", "Журнал аудита"),
    }

    def __init__(self, settings_path: str | None = None):
        self.clean_urls = True  # [1] Чистка трекинг-меток в URL
        self.clean_zero_width = True  # [2] Удаление невидимых знаков Zero-Width
        self.detect_secrets = True  # [3] Детекция ключей, карт и паролей
        self.auto_shred_timer = True  # [4] Таймер самоуничтожения секретов
        self.shred_win_v = True  # [5] Зачистка истории Windows Win+V
        self.audit_logging = True  # [6] Запись событий в clipboard_access.log
        self.timer_seconds = 45  # Время до автоудаления секрета (в секундах)
        self.trusted_apps: list[str] = []  # Белый список приложений (.exe), которые не проверяются
        self._settings_path = settings_path
        self._lock = threading.Lock()  # Замок для безопасного чтения и изменения настроек
        if self._settings_path:
            self.load()

    @staticmethod
    def _normalize_app_name(app_name: str) -> str:
        """Оставляет только имя .exe-файла в нижнем регистре (например: KeePassXC.exe -> keepassxc.exe)."""
        cleaned = app_name.strip().strip('"').strip("'")
        return os.path.basename(cleaned).lower()

    def load(self) -> bool:
        """Загружает настройки из JSON-файла, игнорируя повреждённые или отсутствующие поля."""
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
            # Проверяем not isinstance(..., bool), потому что в Python bool является подклассом int
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
        """Записывает конфиг во временный файл и атомарно заменяет основной (вызывается под замком)."""
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
        """Устанавливает новое время таймера (5..3600 сек) и сохраняет настройки в файл."""
        if isinstance(seconds, bool) or not isinstance(seconds, int):
            raise ValueError("Время таймера должно быть целым числом секунд.")
        if not (MIN_TIMER_SECONDS <= seconds <= MAX_TIMER_SECONDS):
            raise ValueError(f"Допустимый диапазон таймера: {MIN_TIMER_SECONDS}..{MAX_TIMER_SECONDS} сек.")
        with self._lock:
            self.timer_seconds = seconds
            self._save_locked()
            return self.timer_seconds

    def is_trusted_app(self, app_name: str) -> bool:
        """Проверяет, входит ли программа-источник в белый список доверенных приложений."""
        normalized = self._normalize_app_name(app_name)
        if not normalized or normalized == "unknown":
            return False
        with self._lock:
            return normalized in self.trusted_apps

    def add_trusted_app(self, app_name: str) -> bool:
        """Добавляет приложение (.exe) в белый список и сразу сохраняет его."""
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
        """Удаляет приложение из белого списка и обновляет JSON-файл."""
        normalized = self._normalize_app_name(app_name)
        with self._lock:
            if normalized not in self.trusted_apps:
                return False
            self.trusted_apps.remove(normalized)
            self._save_locked()
            return True

    def get_trusted_apps(self) -> list[str]:
        """Возвращает безопасную копию списка доверенных приложений."""
        with self._lock:
            return list(self.trusted_apps)

    def get_status_dict(self) -> dict[int, tuple[str, bool]]:
        """Возвращает словарь статусов всех 6 функций для вывода в консоль и меню трея."""
        with self._lock:
            return {
                1: ("Чистка ссылок (utm, fbclid, si)", self.clean_urls),
                2: ("Удаление невидимых символов", self.clean_zero_width),
                3: ("Детекция секретов и карт", self.detect_secrets),
                4: (f"Таймер самоуничтожения ({self.timer_seconds}с)", self.auto_shred_timer),
                5: ("Зачистка истории Win+V", self.shred_win_v),
                6: ("Журнал clipboard_access.log", self.audit_logging),
            }


# Единый глобальный объект настроек с автозагрузкой из ghostclip_settings.json
config = ShieldConfig(settings_path=SETTINGS_FILE_PATH)


def _format_safe_snippet(text: str) -> str:
    """
    Готовит фрагмент текста к записи в журнал:
    секрет маскируется (sk-p•••UV), явные системные метки сохраняются,
    а любой обычный текст (включая текст в скобках) заменяется на [текст, N симв.].
    """
    is_secret, secret_type, _ = detect_secret(text)
    if is_secret:
        return f"{mask_secret(text)} [{secret_type}]"

    stripped = text.strip()
    if stripped in AUDIT_STATUS_LABELS:
        return stripped
    return f"[текст, {len(text)} симв.]"


def log_audit(event_type: str, app_name: str, snippet: str, details: str = "") -> None:
    """Потокобезопасно дописывает защищённую строку в clipboard_access.log с ротацией по размеру."""
    if not config.audit_logging:
        return

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    safe_snippet = _format_safe_snippet(snippet)
    log_line = f"[{timestamp}] [{event_type}] [APP: {app_name}] [DATA: {safe_snippet}]"
    if details:
        log_line += f" ({details})"

    with _log_lock:
        # При достижении 1 МБ переносим текущий журнал в .log.1, чтобы диск не переполнялся
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
