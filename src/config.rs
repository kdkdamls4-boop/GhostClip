use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

/// Главная структура конфигурации приложения GhostClip Shield.
/// Содержит все настройки программы, разделенные по логическим секциям.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub general: GeneralConfig,
    pub detector: DetectorConfig,
    pub firewall: FirewallConfig,
    pub panic: PanicConfig,
}

/// Общие настройки работы утилиты.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeneralConfig {
    /// Время жизни секрета до самоуничтожения (в секундах)
    pub secret_ttl_seconds: u64,
    /// Очищать ли URL-адреса от трекинг-параметров
    pub clean_urls: bool,
    /// Очищать ли невидимые zero-width символы
    pub clean_zero_width: bool,
}

/// Настройки обнаружения конфиденциальных данных.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectorConfig {
    /// Порог энтропии Шеннона для обнаружения сложных паролей
    pub entropy_threshold: f64,
    /// Минимальная длина текста для анализа энтропии
    pub entropy_min_length: usize,
    /// Проверять ли номера кредитных карт (алгоритм Луна)
    pub check_credit_cards: bool,
    /// Проверять ли распространенные форматы API-ключей и токенов
    pub check_api_keys: bool,
}

/// Настройки интерактивного файрвола буфера обмена.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FirewallConfig {
    /// Включен ли файрвол
    pub enabled: bool,
    /// Автоматическое разрешение, если пользователь сам нажал Ctrl+V
    pub intent_aware_bypass: bool,
    /// Таймаут ожидания выбора пользователя в секундах
    pub dialog_timeout_seconds: u32,
    /// Возвращать ли безопасный фейк (honeypot) вместо ошибки при отказе
    pub use_honeypot: bool,
    /// Список приложений, которым всегда разрешен доступ
    pub whitelist: Vec<String>,
    /// Список приложений, которым доступ всегда заблокирован
    pub blacklist: Vec<String>,
}

/// Настройки экстренной кнопки сброса (PanicFlush).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PanicConfig {
    /// Блокировать ли рабочую станцию (Win+L) при сбросе
    pub lock_workstation: bool,
}

impl Default for GeneralConfig {
    fn default() -> Self {
        Self {
            secret_ttl_seconds: 45,
            clean_urls: true,
            clean_zero_width: true,
        }
    }
}

impl Default for DetectorConfig {
    fn default() -> Self {
        Self {
            entropy_threshold: 3.8,
            entropy_min_length: 12,
            check_credit_cards: true,
            check_api_keys: true,
        }
    }
}

impl Default for FirewallConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            intent_aware_bypass: true,
            dialog_timeout_seconds: 7,
            use_honeypot: true,
            whitelist: vec![
                "devenv.exe".to_string(),
                "code.exe".to_string(),
                "notepad.exe".to_string(),
                "keepassxc.exe".to_string(),
                "keepass.exe".to_string(),
                "1password.exe".to_string(),
                "bitwarden.exe".to_string(),
            ],
            blacklist: Vec::new(),
        }
    }
}

impl Default for PanicConfig {
    fn default() -> Self {
        Self {
            lock_workstation: false,
        }
    }
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            general: GeneralConfig::default(),
            detector: DetectorConfig::default(),
            firewall: FirewallConfig::default(),
            panic: PanicConfig::default(),
        }
    }
}

impl AppConfig {
    /// Загружает настройки из файла config.toml.
    /// Если файл отсутствует, создает его с настройками по умолчанию.
    pub fn load_or_create<P: AsRef<Path>>(path: P) -> Self {
        let path_ref = path.as_ref();
        if path_ref.exists() {
            match fs::read_to_string(path_ref) {
                Ok(content) => match toml::from_str::<AppConfig>(&content) {
                    Ok(cfg) => return cfg,
                    Err(err) => {
                        eprintln!("Ошибка парсинга config.toml (используются умолчания): {}", err);
                    }
                },
                Err(err) => {
                    eprintln!("Ошибка чтения config.toml: {}", err);
                }
            }
        }

        // Если файла нет или была ошибка, создаем дефолтный
        let default_cfg = AppConfig::default();
        if let Ok(toml_str) = toml::to_string_pretty(&default_cfg) {
            let _ = fs::write(path_ref, toml_str);
        }
        default_cfg
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let cfg = AppConfig::default();
        assert_eq!(cfg.general.secret_ttl_seconds, 45);
        assert!(cfg.general.clean_urls);
        assert!(cfg.firewall.intent_aware_bypass);
        assert_eq!(cfg.firewall.dialog_timeout_seconds, 7);
    }
}
