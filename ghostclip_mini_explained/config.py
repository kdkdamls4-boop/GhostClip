"""
ghostclip_mini_explained/config.py
Файл 1 из 7: Настройки переключателей [1-6] и журнал аудита (clipboard_access.log).
"""

# Импортируем модуль datetime для получения точного текущего времени (часы, минуты, секунды)
import datetime

# Путь к файлу, куда будут записываться все действия с буфером обмена
LOG_FILE_PATH = "clipboard_access.log"

class ShieldConfig:
    """
    Класс для хранения и управления состоянием функций защиты (включены или выключены).
    """
    def __init__(self):
        # По умолчанию все функции защиты включены (True)
        self.clean_urls = True          # 1. Чистка трекинг-меток в ссылках (utm, fbclid, si)
        self.clean_zero_width = True    # 2. Удаление невидимых знаков Zero-Width
        self.detect_secrets = True      # 3. Детекция паролей, API-ключей и номеров карт
        self.auto_shred_timer = True    # 4. Таймер самоуничтожения секретов
        self.shred_win_v = True         # 5. Принудительная зачистка истории Win+V при панике
        self.audit_logging = True       # 6. Запись событий в файл журнала clipboard_access.log
        self.timer_seconds = 45         # Длительность таймера по умолчанию (45 секунд)

    def toggle(self, opt_id: int):
        """
        Переключает функцию с номером opt_id (от 1 до 6) между True и False.
        Возвращает кортеж: (Название функции, Новое значение True/False).
        """
        # Словарь связывает цифру [1-6] с именем переменной внутри класса
        attrs = {
            1: "clean_urls",
            2: "clean_zero_width",
            3: "detect_secrets",
            4: "auto_shred_timer",
            5: "shred_win_v",
            6: "audit_logging",
        }
        # Человекочитаемые названия функций для отображения в логах и меню
        names = {
            1: "Чистка ссылок",
            2: "Удаление невидимых знаков",
            3: "Детекция секретов",
            4: "Таймер самоуничтожения",
            5: "Зачистка истории Win+V",
            6: "Журнал аудита",
        }
        # Если нажата цифра не от 1 до 6, ничего не делаем
        if opt_id not in attrs:
            return "Неизвестно", False

        attr = attrs[opt_id]                # Получаем имя атрибута (например, "clean_urls")
        val = not getattr(self, attr)       # Инвертируем текущее значение (True -> False или наоборот)
        setattr(self, attr, val)            # Сохраняем новое значение обратно в объект
        return names[opt_id], val           # Возвращаем название и новый статус

    def get_status_dict(self):
        """
        Возвращает текущее состояние всех тумблеров в виде словаря.
        Используется для отрисовки консольного меню и пунктов ПКМ в трее.
        """
        return {
            1: ("Чистка ссылок (utm, fbclid, si)", self.clean_urls),
            2: ("Удаление невидимых символов", self.clean_zero_width),
            3: ("Детекция секретов и карт", self.detect_secrets),
            4: (f"Таймер самоуничтожения ({self.timer_seconds}с)", self.auto_shred_timer),
            5: ("Зачистка истории Win+V", self.shred_win_v),
            6: ("Журнал clipboard_access.log", self.audit_logging),
        }

# Создаём глобальный экземпляр настроек, к которому обращаются все остальные файлы
config = ShieldConfig()

def log_audit(event_type: str, app_name: str, snippet: str, details: str = ""):
    """
    Записывает событие безопасности в файл clipboard_access.log.
    Если тумблер [6] выключен, запись в файл не производится.
    """
    if not config.audit_logging:
        return  # Логирование отключено пользователем

    # Формируем текущую метку времени в формате "ГГГГ-ММ-ДД ЧЧ:ММ:СС"
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Собираем форматированную строку лога
    line = f"[{ts}] [{event_type}] [APP: {app_name}] [DATA: {snippet}] {details}".strip()
    try:
        # Открываем файл в режиме добавления ("a" = append) в кодировке UTF-8
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Если файл заблокирован другой программой, подавляем ошибку, чтобы не ронять основной процесс
        pass
