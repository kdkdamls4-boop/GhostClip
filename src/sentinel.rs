use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};

// Модуль Anti-Loop Sentinel: защита от бесконечного цикла сообщений WM_CLIPBOARDUPDATE.
// Когда GhostClip очищает ссылку или затирает буфер, Windows шлет повторное уведомление.
// Этот модуль позволяет безошибочно определить, что изменение буфера сделано нашей программой,
// и проигнорировать его.

static IS_INTERNAL_UPDATE: AtomicBool = AtomicBool::new(false);
static LAST_WRITTEN_HASH: Mutex<Option<u64>> = Mutex::new(None);

/// Быстрое вычисление хеша строки текста.
fn hash_text(text: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    text.hash(&mut hasher);
    hasher.finish()
}

/// RAII-страж (Guard): пока объект существует, флаг внутренней модификации активен.
/// При выходе из области видимости (Drop) флаг автоматически сбрасывается.
pub struct InternalUpdateGuard;

impl InternalUpdateGuard {
    pub fn new() -> Self {
        IS_INTERNAL_UPDATE.store(true, Ordering::SeqCst);
        Self
    }
}

impl Drop for InternalUpdateGuard {
    fn drop(&mut self) {
        IS_INTERNAL_UPDATE.store(false, Ordering::SeqCst);
    }
}

/// Проверяет, активен ли сейчас флаг внутренней записи в буфер.
pub fn is_internal_update() -> bool {
    IS_INTERNAL_UPDATE.load(Ordering::SeqCst)
}

/// Устанавливает флаг внутренней записи в буфер обмена.
pub fn set_internal_update() {
    IS_INTERNAL_UPDATE.store(true, Ordering::SeqCst);
}

/// Проверяет и атомарно сбрасывает флаг внутренней записи в буфер обмена.
pub fn check_and_clear_internal_update() -> bool {
    IS_INTERNAL_UPDATE.swap(false, Ordering::SeqCst)
}

/// Запоминает хеш текста, который наша программа только что записала в буфер обмена.
pub fn record_written_text(text: &str) {
    let h = hash_text(text);
    if let Ok(mut lock) = LAST_WRITTEN_HASH.lock() {
        *lock = Some(h);
    }
}

/// Проверяет, совпадает ли текст в буфере с тем, что мы сами туда только что положили.
pub fn is_same_as_last_written(text: &str) -> bool {
    let h = hash_text(text);
    if let Ok(lock) = LAST_WRITTEN_HASH.lock()
        && let Some(last_hash) = *lock
    {
        return last_hash == h;
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_internal_guard() {
        assert!(!is_internal_update());
        {
            let _guard = InternalUpdateGuard::new();
            assert!(is_internal_update());
        }
        assert!(!is_internal_update());
    }

    #[test]
    fn test_record_and_check_hash() {
        let text = "https://example.com/clean-link";
        record_written_text(text);
        assert!(is_same_as_last_written(text));
        assert!(!is_same_as_last_written("https://other.com"));
    }

    #[test]
    fn test_check_and_clear() {
        assert!(!check_and_clear_internal_update());
        set_internal_update();
        assert!(check_and_clear_internal_update());
        assert!(!check_and_clear_internal_update());
    }
}
