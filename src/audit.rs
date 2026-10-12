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

/// Записывает событие обращения к буферу обмена в текстовый лог-файл.
/// Формат записи строго по запросу:
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

    // Фильтр частых повторов (если тот же процесс читает тот же текст чаще раза в 3 секунды)
    if let Ok(mut last_lock) = LAST_ENTRY.lock() {
        if let Some(ref last) = *last_lock {
            if last.path == file_path
                && last.content_hash == content_hash
                && last.timestamp.elapsed().as_secs() < 3
            {
                return;
            }
        }
        *last_lock = Some(LastLogEntry {
            path: file_path.to_string(),
            content_hash,
            timestamp: Instant::now(),
        });
    }

    let timestamp = get_local_timestamp();

    // Обрезаем текст, если скопирован огромный том книги, чтобы лог оставался читаемым
    let display_content = if content.chars().count() > 500 {
        let snippet: String = content.chars().take(500).collect();
        format!("{}... [всего {} симв.]", snippet, content.chars().count())
    } else {
        content.trim().to_string()
    };

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
    if !std::path::Path::new(LOG_FILE_NAME).exists() {
        if let Ok(mut file) = OpenOptions::new()
            .create(true)
            .write(true)
            .open(LOG_FILE_NAME)
        {
            let _ = file.write_all(b"=== GhostClip Shield: Clipboard Access Log ===\n\n");
        }
    }

    let _ = Command::new("notepad.exe").arg(LOG_FILE_NAME).spawn();
}
