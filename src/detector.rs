use regex::Regex;
use std::collections::HashMap;
use std::sync::OnceLock;

use crate::config::DetectorConfig;

/// Тип обнаруженного секрета в буфере обмена.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SecretKind {
    /// Токен API (например, OpenAI, GitHub, AWS)
    ApiKey(&'static str),
    /// Приватный криптографический ключ (RSA, SSH, PGP)
    PrivateKey,
    /// JSON Web Token (JWT)
    JwtToken,
    /// Номер банковской карты, прошедший проверку Луна
    CreditCard,
    /// Адрес криптовалютного кошелька (BTC, ETH, TON)
    CryptoWallet(&'static str),
    /// Пароль или секретная фраза с высокой энтропией Шеннона
    HighEntropyPassword,
}

impl SecretKind {
    /// Возвращает понятное пользователю текстовое описание типа секрета.
    pub fn description(&self) -> &'static str {
        match self {
            SecretKind::ApiKey(name) => name,
            SecretKind::PrivateKey => "Приватный ключ (SSH/RSA/PGP)",
            SecretKind::JwtToken => "JWT-токен авторизации",
            SecretKind::CreditCard => "Номер банковской карты",
            SecretKind::CryptoWallet(coin) => coin,
            SecretKind::HighEntropyPassword => "Сложный пароль / случайный токен",
        }
    }
}

/// Набор скомпилированных регулярных выражений для проверки секретов.
/// OnceLock гарантирует, что регулярные выражения компилируются ровно один раз при первом вызове.
struct SecretPatterns {
    openai: Regex,
    github: Regex,
    aws: Regex,
    jwt: Regex,
    private_key: Regex,
    btc: Regex,
    eth: Regex,
    ton: Regex,
    card_candidates: Regex,
}

static PATTERNS: OnceLock<SecretPatterns> = OnceLock::new();

fn get_patterns() -> &'static SecretPatterns {
    PATTERNS.get_or_init(|| SecretPatterns {
        openai: Regex::new(r"(?i)\bsk-[a-zA-Z0-9_\-]{20,}\b").unwrap(),
        github: Regex::new(r"\b(ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36}\b|\bgithub_pat_[a-zA-Z0-9_]{50,}\b").unwrap(),
        aws: Regex::new(r"\b(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b").unwrap(),
        jwt: Regex::new(r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b").unwrap(),
        private_key: Regex::new(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----").unwrap(),
        btc: Regex::new(r"\b(bc1|[13])[a-km-zA-HJ-NP-Z1-9]{25,39}\b").unwrap(),
        eth: Regex::new(r"\b0x[a-fA-F0-9]{40}\b").unwrap(),
        ton: Regex::new(r"\b(EQ|UQ)[a-zA-Z0-9_-]{46}\b").unwrap(),
        card_candidates: Regex::new(r"\b(?:\d[ -]*?){13,19}\b").unwrap(),
    })
}

/// Проверка валидности номера банковской карты с помощью алгоритма Луна (Luhn algorithm).
/// Это стандартная математическая формула, используемая всеми платежными системами (Visa, MasterCard, МИР).
pub fn is_valid_luhn(digits_only: &str) -> bool {
    let len = digits_only.len();
    if len < 13 || len > 19 {
        return false;
    }

    let mut sum = 0;
    let mut alternate = false;

    for ch in digits_only.chars().rev() {
        let Some(digit) = ch.to_digit(10) else {
            return false;
        };

        if alternate {
            let doubled = digit * 2;
            sum += if doubled > 9 { doubled - 9 } else { doubled };
        } else {
            sum += digit;
        }

        alternate = !alternate;
    }

    sum % 10 == 0
}

/// Вычисление информационной энтропии Шеннона для строки.
/// Формула: H = - sum(p * log2(p)).
/// Обычный человеческий текст имеет энтропию около 2.0-3.2.
/// Случайно сгенерированный криптографический пароль или хеш обычно имеет энтропию > 3.8.
pub fn calculate_shannon_entropy(text: &str) -> f64 {
    if text.is_empty() {
        return 0.0;
    }

    let mut frequencies: HashMap<char, usize> = HashMap::new();
    let mut total_chars = 0;

    for ch in text.chars() {
        *frequencies.entry(ch).or_insert(0) += 1;
        total_chars += 1;
    }

    let len_f64 = total_chars as f64;
    let mut entropy = 0.0;

    for &count in frequencies.values() {
        let prob = count as f64 / len_f64;
        entropy -= prob * prob.log2();
    }

    entropy
}

/// Главная функция анализа текста на наличие конфиденциальных данных.
pub fn detect_secret(text: &str, config: &DetectorConfig) -> Option<SecretKind> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return None;
    }

    let patterns = get_patterns();

    // 1. Проверка на приватные ключи
    if patterns.private_key.is_match(trimmed) {
        return Some(SecretKind::PrivateKey);
    }

    // 2. Проверка типовых API-токенов
    if config.check_api_keys {
        if patterns.openai.is_match(trimmed) {
            return Some(SecretKind::ApiKey("API-ключ OpenAI"));
        }
        if patterns.github.is_match(trimmed) {
            return Some(SecretKind::ApiKey("Токен доступа GitHub"));
        }
        if patterns.aws.is_match(trimmed) {
            return Some(SecretKind::ApiKey("Ключ доступа AWS"));
        }
        if patterns.jwt.is_match(trimmed) {
            return Some(SecretKind::JwtToken);
        }
    }

    // 3. Проверка криптовалютных кошельков
    if patterns.eth.is_match(trimmed) {
        return Some(SecretKind::CryptoWallet("Ethereum кошелек"));
    }
    if patterns.btc.is_match(trimmed) {
        return Some(SecretKind::CryptoWallet("Bitcoin кошелек"));
    }
    if patterns.ton.is_match(trimmed) {
        return Some(SecretKind::CryptoWallet("TON кошелек"));
    }

    // 4. Проверка банковских карт алгоритмом Луна
    if config.check_credit_cards {
        for m in patterns.card_candidates.find_iter(trimmed) {
            let digits: String = m.as_str().chars().filter(|c| c.is_ascii_digit()).collect();
            if is_valid_luhn(&digits) {
                return Some(SecretKind::CreditCard);
            }
        }
    }

    // 5. Проверка высокой энтропии (случайные пароли)
    // Условие: нет пробелов внутри, достаточная длина и высокая случайность символов
    if !trimmed.contains(char::is_whitespace) && trimmed.len() >= config.entropy_min_length {
        let entropy = calculate_shannon_entropy(trimmed);
        if entropy >= config.entropy_threshold {
            return Some(SecretKind::HighEntropyPassword);
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_github_token() {
        let cfg = DetectorConfig::default();
        let token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz";
        assert_eq!(
            detect_secret(token, &cfg),
            Some(SecretKind::ApiKey("Токен доступа GitHub"))
        );
    }

    #[test]
    fn test_detect_aws_key() {
        let cfg = DetectorConfig::default();
        let key = "AKIAIOSFODNN7EXAMPLE";
        assert_eq!(
            detect_secret(key, &cfg),
            Some(SecretKind::ApiKey("Ключ доступа AWS"))
        );
    }

    #[test]
    fn test_detect_eth_wallet() {
        let cfg = DetectorConfig::default();
        let eth = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045";
        assert_eq!(
            detect_secret(eth, &cfg),
            Some(SecretKind::CryptoWallet("Ethereum кошелек"))
        );
    }

    #[test]
    fn test_luhn_credit_card() {
        // Тестовый номер карты Visa, валидный по Луну
        assert!(is_valid_luhn("4532015112830366"));
        // Невалидный номер
        assert!(!is_valid_luhn("4532015112830367"));
    }

    #[test]
    fn test_high_entropy_password() {
        let cfg = DetectorConfig::default();
        // Пароль высокой случайности
        let strong_pwd = "X7#mK9$vL2@qP4!";
        assert_eq!(
            detect_secret(strong_pwd, &cfg),
            Some(SecretKind::HighEntropyPassword)
        );

        // Обычный английский текст достаточной длины, но низкой энтропии
        let english_sentence = "thisisalongpasswordwithoutspaces";
        assert_ne!(
            detect_secret(english_sentence, &cfg),
            Some(SecretKind::HighEntropyPassword)
        );
    }
}
