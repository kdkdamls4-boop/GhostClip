use std::fs::OpenOptions;
use std::io::Write;
use std::process::Command;
use std::sync::Mutex;
use std::time::Instant;
use windows::Win32::System::SystemInformation::GetLocalTime;

/// Имя файла журнала аудита буфера обмена.
pub const LOG_FILE_NAME: &str = "clipboard_access.log";

/// Предотвращение дублирования записей, если одно и то же приложение опрашивает буфер каждую секунду.
struct LastLogEntry {
    path: String,
    content_hash: u64,
    timestamp: Instant,
}

static LAST_ENTRY: Mutex<Option<LastLogEntry>> = Mutex::new(None);

/// Получает текущую локальную дату и время системы в формате "ГГГГ-ММ-ДД ЧЧ:ММ:СС".
pub fn get_local_timestamp() -> String {
    unsafe {
        let st = GetLocalTime();
        format!(
            "{:04}-{:02}-{:02} {:02}:{:02}:{:02}",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond
        )
    }
}

/// Форматирует текст содержимого буфера для записи в лог:
/// маскирует конфиденциальные данные (пароли, ключи, токены) и обрезает гигантские тексты.
pub fn format_log_content(content: &str) -> String {
    let char_count = content.chars().count();

    // SEC-002: Если обнаружен секрет, маскируем его для защиты от утечки в лог
    if let Some(secret) =
        crate::detector::detect_secret(content, &crate::config::DetectorConfig::default())
    {
        return format!(
            "[ЗАЩИЩЕНО: {}] (Длина: {} симв.)",
            secret.description(),
            char_count
        );
    }

    // PERF-001: Если текст длиннее 500 символов, обрезаем с использованием вычисленного char_count
    if char_count > 500 {
        let snippet: String = content.chars().take(500).collect();
        format!("{}... [всего {} симв.]", snippet, char_count)
    } else {
        content.trim().to_string()
    }
}

/// Записывает событие обращения к буферу обмена в текстовый лог-файл.
/// Формат записи строго по запросу пользователя:
/// [Дата и время]
/// Файл: <Полный путь к файлу>
/// Что прочитал: <Текст или ссылка>
/// --------------------------------------------------------------------------------
pub fn log_access(file_path: &str, content: &str) {
    if file_path.is_empty() || content.trim().is_empty() {
        return;
    }

    // Хеш содержимого для фильтрации дубликатов
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    std::hash::Hash::hash(content, &mut hasher);
    let content_hash = std::hash::Hasher::finish(&hasher);

    // Фильтр частых повторов (если тот же процесс обращается к тому же тексту чаще раза в 3 секунды)
    if let Ok(mut last_lock) = LAST_ENTRY.lock() {
        if let Some(ref last) = *last_lock
            && last.path == file_path
            && last.content_hash == content_hash
            && last.timestamp.elapsed().as_secs() < 3
        {
            return;
        }
        *last_lock = Some(LastLogEntry {
            path: file_path.to_string(),
            content_hash,
            timestamp: Instant::now(),
        });
    }

    let timestamp = get_local_timestamp();
    let display_content = format_log_content(content);

    let log_line = format!(
        "[{timestamp}]\nФайл: {file_path}\nЧто прочитал: {display_content}\n--------------------------------------------------------------------------------\n"
    );

    if let Ok(mut file) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(LOG_FILE_NAME)
    {
        let _ = file.write_all(log_line.as_bytes());
    }
}

/// Открывает файл лога в стандартном Блокноте Windows (notepad.exe).
pub fn open_log_file() {
    // Если файла еще нет, создаем пустой с поясняющей строкой
    if !std::path::Path::new(LOG_FILE_NAME).exists()
        && let Ok(mut file) = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(LOG_FILE_NAME)
    {
        let _ = file.write_all(b"=== GhostClip Shield: Clipboard Access Log ===\n\n");
    }

    let _ = Command::new("notepad.exe").arg(LOG_FILE_NAME).spawn();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_timestamp_format() {
        let ts = get_local_timestamp();
        assert_eq!(ts.len(), 19);
        assert_eq!(&ts[4..5], "-");
        assert_eq!(&ts[7..8], "-");
        assert_eq!(&ts[10..11], " ");
        assert_eq!(&ts[13..14], ":");
        assert_eq!(&ts[16..17], ":");
    }

    #[test]
    fn test_secret_masking() {
        let secret = "sk-1234567890abcdef1234567890abcdef";
        let formatted = format_log_content(secret);
        assert!(formatted.starts_with("[ЗАЩИЩЕНО:"));
        assert!(!formatted.contains("sk-1234567890"));
    }

    #[test]
    fn test_long_text_truncation() {
        let long_text = "a".repeat(600);
        let formatted = format_log_content(&long_text);
        assert!(formatted.contains("[всего 600 симв.]"));
        assert!(formatted.starts_with(&"a".repeat(500)));
    }
}
