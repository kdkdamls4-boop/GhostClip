# 🧪 Покрытие тестами

---

## 1. Текущий статус покрытия кодовой базы

По результатам запуска `cargo test` успешно выполняются **16 юнит-тестов** из 16. Однако покрытие распределено крайне неравномерно:

| Модуль | Кол-во тестов | Критичность модуля для безопасности | Текущий статус покрытия |
|---|---|---|---|
| `detector.rs` | 5 | 🔴 Критическая | ✅ Хорошее покрытие (Luhn, OpenAI, AWS, энтропия) |
| `cleaner.rs` | 4 | 🟠 Высокая | ✅ Базовое покрытие (UTM, Zero-Width, YouTube) |
| `firewall.rs` | 4 | 🟢 Низкая (мёртвый код) | ⚠️ Покрыт тестами, но не используется в `main` |
| `sentinel.rs` | 2 | 🟠 Высокая | ⚠️ Покрыты только локальные функции хеша |
| `config.rs` | 1 | 🟡 Средняя | ⚠️ Проверяются только дефолтные значения |
| `shredder.rs` | **0** | 🔴 Критическая | ❌ **Тесты полностью отсутствуют** |
| `ghost.rs` | **0** | 🔴 Критическая | ❌ **Тесты полностью отсутствуют** |
| `audit.rs` | **0** | 🟠 Высокая | ❌ **Тесты полностью отсутствуют** |
| `radar.rs` | **0** | 🟠 Высокая | ❌ **Тесты полностью отсутствуют** |
| `hotkeys.rs` | **0** | 🟠 Высокая | ❌ **Тесты полностью отсутствуют** |
| `main.rs` | **0** | 🔴 Критическая | ❌ **Тесты полностью отсутствуют** |

---

## TEST-001: Критические модули зачистки, таймеров и аудита не покрыты тестами

| Поле | Значение |
|---|---|
| **Идентификатор** | TEST-001 |
| **Серьёзность** | 🟠 High |
| **Файл и строки** | [`src/shredder.rs`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/shredder.rs), [`src/ghost.rs`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/ghost.rs), [`src/audit.rs`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/audit.rs) |
| **Категория** | Слепые зоны автоматизированного тестирования |

### ❌ Проблема
Модули, отвечающие за физическое уничтожение конфиденциальной информации (`shredder.rs`), запуск и отмену таймеров самоуничтожения (`ghost.rs`), а также журналирование инцидентов (`audit.rs`), не имеют ни одного юнит-теста. Из-за этого баги с утечкой памяти (BUG-004), спавном потоков (BUG-003) и записью открытых секретов (SEC-002) не были обнаружены автотестами при сборке.

### 💥 Последствия
1. Риск регрессии при любом рефакторинге ключевых подсистем безопасности.
2. Невозможность верифицировать корректность работы механизма смены эпох (`CURRENT_EPOCH`) в таймере при конкурентных вызовах.

### ✅ Решение
Реализовать модульные тесты для чистых функций и изолированных сценариев.

#### Пример теста для `audit.rs` (дедупликация и форматирование):
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_timestamp_format_validity() {
        let ts = get_local_timestamp();
        // Проверяем формат "ГГГГ-ММ-ДД ЧЧ:ММ:СС" (19 символов)
        assert_eq!(ts.len(), 19);
        assert_eq!(&ts[4..5], "-");
        assert_eq!(&ts[7..8], "-");
        assert_eq!(&ts[10..11], " ");
        assert_eq!(&ts[13..14], ":");
        assert_eq!(&ts[16..17], ":");
    }

    #[test]
    fn test_audit_ignores_empty_strings() {
        // Проверяем, что пустые пути и текст не приводят к записи
        log_access("", "секрет");
        log_access("C:\\test.exe", "   ");
    }
}
```

#### Пример теста для `ghost.rs` (логика взвода и деактивации таймера):
```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ghost_timer_arm_disarm_lifecycle() {
        assert!(!is_armed());
        arm_timer(60, "Тестовый токен");
        assert!(is_armed());
        assert!(remaining_seconds().unwrap() <= 60);

        disarm_timer();
        assert!(!is_armed());
        assert_eq!(remaining_seconds(), None);
    }
}
```

### ⏱ Сложность исправления
Средняя (1–2 часа).

---

## TEST-002: Отсутствие сквозных интеграционных тестов (Clipboard Round-Trip)

| Поле | Значение |
|---|---|
| **Идентификатор** | TEST-002 |
| **Серьёзность** | 🟡 Medium |
| **Категория** | Интеграционное тестирование |

### ❌ Проблема
В проекте отсутствуют тесты каталога `tests/`, проверяющие взаимодействие компонентов в связке:
«Помещение текста со скрытыми UTM-метками в буфер → срабатывание санитайзера → детекция API-токена → проверка отсутствия зацикливания через sentinel».

### ✅ Решение
Создать интеграционный тестовый файл `tests/clipboard_pipeline_test.rs`, тестирующий пайплайн обработки текста без необходимости открывать реальное окно Windows:

```rust
// tests/pipeline_test.rs
use ghostclip::cleaner::sanitize_text;
use ghostclip::detector::{detect_secret, DetectorConfig, SecretKind};

#[test]
fn test_full_sanitization_and_detection_pipeline() {
    let dirty_input = "https://api.openai.com/v1?token=sk-1234567890abcdef1234567890abcdef&utm_source=tracker\u{200B}";
    
    // 1. Очистка URL и скрытых символов
    let (cleaned, modified) = sanitize_text(dirty_input, true, true);
    assert!(modified);
    assert!(!cleaned.contains("utm_source"));
    assert!(!cleaned.contains('\u{200B}'));

    // 2. Детекция секрета
    let secret = detect_secret(&cleaned, &DetectorConfig::default());
    assert!(secret.is_some());
    assert_eq!(secret.unwrap(), SecretKind::ApiKey("API-ключ OpenAI"));
}
```

### ⏱ Сложность исправления
Средняя (1 час).
