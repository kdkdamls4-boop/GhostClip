/// Модуль CleanClip: очистка ссылок от рекламных и шпионских трекинг-параметров,
/// а также удаление невидимых zero-width символов.

/// Список известных параметров отслеживания (tracking parameters),
/// которые внедряются в URL-ссылки аналитическими системами и соцсетями.
const TRACKING_PARAMS: &[&str] = &[
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",       // Facebook Click ID
    "gclid",        // Google Click ID
    "gclsrc",
    "dclid",
    "yclid",        // Yandex Click ID
    "ym_debug",
    "si",           // YouTube Share Identifier
    "ref",
    "ref_src",
    "ref_url",
    "igshid",       // Instagram Share ID
    "mc_cid",       // MailChimp
    "mc_eid",
    "spm",          // AliExpress tracking
    "scm",
];

/// Набор невидимых Unicode-символов (Zero-Width), которые часто используют
/// для стеганографии, трекинга источника утечки или скрытой разметки текста.
fn is_zero_width_char(c: char) -> bool {
    matches!(
        c,
        '\u{200B}' // Zero-Width Space
        | '\u{200C}' // Zero-Width Non-Joiner
        | '\u{200D}' // Zero-Width Joiner
        | '\u{FEFF}' // Zero-Width No-Break Space (BOM)
        | '\u{200E}' // Left-to-Right Mark
        | '\u{200F}' // Right-to-Left Mark
        | '\u{202A}'..='\u{202E}' // Bidi Overrides
        | '\u{2060}' // Word Joiner
    )
}

/// Удаляет невидимые zero-width символы из текста.
pub fn remove_zero_width(text: &str) -> (String, bool) {
    let mut modified = false;
    let mut result = String::with_capacity(text.len());

    for ch in text.chars() {
        if is_zero_width_char(ch) {
            modified = true;
        } else {
            result.push(ch);
        }
    }

    (result, modified)
}

/// Очищает URL-ссылку от параметров отслеживания.
/// Если текст не является ссылкой или не содержит трекеров, возвращает исходный вид.
pub fn clean_url(url: &str) -> (String, bool) {
    let trimmed = url.trim();

    // Проверяем, похож ли текст на http/https ссылку
    if !(trimmed.starts_with("http://") || trimmed.starts_with("https://")) {
        return (url.to_string(), false);
    }

    // Ищем знак вопроса, разделяющий базовый URL и query-параметры
    let Some(query_pos) = trimmed.find('?') else {
        return (url.to_string(), false);
    };

    let base_url = &trimmed[..query_pos];
    let query_and_fragment = &trimmed[query_pos + 1..];

    // Разделяем query строку и якорь (#fragment), если он есть
    let (query_part, fragment_part) = match query_and_fragment.find('#') {
        Some(hash_pos) => (
            &query_and_fragment[..hash_pos],
            Some(&query_and_fragment[hash_pos..]),
        ),
        None => (query_and_fragment, None),
    };

    let mut kept_params = Vec::new();
    let mut modified = false;

    for param_pair in query_part.split('&') {
        if param_pair.is_empty() {
            continue;
        }

        let key = param_pair.split('=').next().unwrap_or("").to_lowercase();
        if TRACKING_PARAMS.contains(&key.as_str()) {
            modified = true; // Этот параметр является мусорным трекером — отбрасываем
        } else {
            kept_params.push(param_pair);
        }
    }

    if !modified {
        return (url.to_string(), false);
    }

    let mut cleaned_url = base_url.to_string();
    if !kept_params.is_empty() {
        cleaned_url.push('?');
        cleaned_url.push_str(&kept_params.join("&"));
    }

    if let Some(fragment) = fragment_part {
        cleaned_url.push_str(fragment);
    }

    (cleaned_url, true)
}

/// Комплексная очистка скопированного текста.
/// Возвращает очищенную строку и флаг, произошли ли какие-то изменения.
pub fn sanitize_text(text: &str, clean_urls_enabled: bool, clean_zw_enabled: bool) -> (String, bool) {
    let mut current = text.to_string();
    let mut any_change = false;

    // 1. Очистка от невидимых символов
    if clean_zw_enabled {
        let (zw_cleaned, zw_changed) = remove_zero_width(&current);
        if zw_changed {
            current = zw_cleaned;
            any_change = true;
        }
    }

    // 2. Очистка от URL трекеров (если текст представляет собой ссылку)
    if clean_urls_enabled {
        let (url_cleaned, url_changed) = clean_url(&current);
        if url_changed {
            current = url_cleaned;
            any_change = true;
        }
    }

    (current, any_change)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_clean_youtube_share_url() {
        let raw = "https://youtu.be/dQw4w9WgXcQ?si=abcdef123456";
        let (cleaned, changed) = clean_url(raw);
        assert!(changed);
        assert_eq!(cleaned, "https://youtu.be/dQw4w9WgXcQ");
    }

    #[test]
    fn test_clean_utm_params_keeping_useful() {
        let raw = "https://example.com/search?q=rust&utm_source=google&utm_medium=cpc&page=2";
        let (cleaned, changed) = clean_url(raw);
        assert!(changed);
        assert_eq!(cleaned, "https://example.com/search?q=rust&page=2");
    }

    #[test]
    fn test_remove_zero_width_chars() {
        let with_stealth = "My\u{200B}Secret\u{FEFF}Password";
        let (cleaned, changed) = remove_zero_width(with_stealth);
        assert!(changed);
        assert_eq!(cleaned, "MySecretPassword");
    }

    #[test]
    fn test_unaltered_text() {
        let normal = "Просто обычный текст без ссылок и скрытых символов.";
        let (cleaned, changed) = sanitize_text(normal, true, true);
        assert!(!changed);
        assert_eq!(cleaned, normal);
    }
}
