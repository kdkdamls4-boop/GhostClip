# 🔒 Безопасность и уязвимости

---

## SEC-001: Состояние гонки и нарушение правил языка Rust из-за `static mut KEYBOARD_HOOK`

| Поле | Значение |
|---|---|
| **Идентификатор** | SEC-001 |
| **Серьёзность** | 🟠 High |
| **Файл и строки** | [`src/hotkeys.rs:18-20`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/hotkeys.rs#L18-L20), [`src/hotkeys.rs:83`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/hotkeys.rs#L83), [`src/hotkeys.rs:98`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/hotkeys.rs#L98), [`src/hotkeys.rs:107-111`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/hotkeys.rs#L107-L111) |
| **Категория** | Data Race / Memory Safety (Rust 2024 Edition) |

### ❌ Проблема
Переменная `KEYBOARD_HOOK` объявлена как изменяемая статическая переменная: `static mut KEYBOARD_HOOK: HHOOK`.
Она читается внутри колбэка низкоуровневого хука Windows (`low_level_keyboard_proc`), который вызывается диспетчером сообщений, и параллельно модифицируется в основном потоке функциями `install_paste_intent_hook` и `uninstall_paste_intent_hook`. Доступ к ней не защищён никакими примитивами синхронизации.
В Rust 2024 доступ к `static mut` объявлен небезопасным и устаревшим (депрекейтнут по RFC #3560), а конкурентный доступ к нему представляет собой классический **Data Race**, что является гарантированным Undefined Behavior.

### 📍 Текущий код
```rust
// src/hotkeys.rs:18-20
static mut KEYBOARD_HOOK: HHOOK = HHOOK(std::ptr::null_mut());

// Чтение в callback:
CallNextHookEx(KEYBOARD_HOOK, n_code, w_param, l_param)

// Запись в функции установки:
KEYBOARD_HOOK = h;

// Модификация в функции снятия:
UnhookWindowsHookEx(KEYBOARD_HOOK);
KEYBOARD_HOOK = HHOOK(std::ptr::null_mut());
```

### 💥 Последствия
1. Риск считывания частично инициализированного или невалидного дескриптора хука при вызове `CallNextHookEx`, что способно нарушить цепочку клавиатурных хуков в системе Windows или вызвать сбой приложения.
2. Несовместимость с будущими версиями компилятора Rust (ошибка компиляции в редакциях 2024+).

### ✅ Решение
Заменить `static mut` на потокобезопасный атомарный указатель `std::sync::atomic::AtomicPtr`:

```rust
use std::ffi::c_void;
use std::sync::atomic::{AtomicPtr, Ordering};

static KEYBOARD_HOOK: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());

pub fn install_paste_intent_hook() {
    unsafe {
        if KEYBOARD_HOOK.load(Ordering::Acquire).is_null() {
            let hook = SetWindowsHookExW(
                WH_KEYBOARD_LL,
                Some(low_level_keyboard_proc),
                windows::Win32::Foundation::HMODULE(std::ptr::null_mut()),
                0,
            );
            if let Ok(h) = hook {
                KEYBOARD_HOOK.store(h.0, Ordering::Release);
            }
        }
    }
}

pub fn uninstall_paste_intent_hook() {
    unsafe {
        let hook_ptr = KEYBOARD_HOOK.swap(std::ptr::null_mut(), Ordering::AcqRel);
        if !hook_ptr.is_null() {
            let _ = UnhookWindowsHookEx(HHOOK(hook_ptr));
        }
    }
}

unsafe extern "system" fn low_level_keyboard_proc(
    n_code: i32,
    w_param: WPARAM,
    l_param: LPARAM,
) -> LRESULT {
    unsafe {
        // ... логика проверки Ctrl+V ...

        let hook_ptr = KEYBOARD_HOOK.load(Ordering::Relaxed);
        CallNextHookEx(HHOOK(hook_ptr), n_code, w_param, l_param)
    }
}
```

### 💡 Объяснение
`AtomicPtr` обеспечивает полностью корректный с точки зрения модели памяти Rust доступ с гарантиями атомарности без накладных расходов на мьютексы.

### ⏱ Сложность исправления
Низкая (15 минут).

---

## SEC-002: Сохранение паролей, токенов и реквизитов карт в открытом виде в лог-файл

| Поле | Значение |
|---|---|
| **Идентификатор** | SEC-002 |
| **Серьёзность** | 🟠 High |
| **Файл и строки** | [`src/audit.rs:37-85`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/audit.rs#L37-L85) |
| **Категория** | Утечка конфиденциальных данных (CWE-312 / CWE-532) |

### ❌ Проблема
Функция `log_access` записывает полное содержимое текста буфера обмена в открытый текстовый файл `clipboard_access.log` в текущей рабочей директории. Если пользователь копирует пароль, токен OpenAI, закрытый SSH-ключ или номер кредитной карты, эти данные записываются на диск в незашифрованном виде.
Это создаёт **новую уязвимость** на машине пользователя: даже после того, как `ghost.rs` или `shredder.rs` зачистят RAM и историю Win+V, секреты останутся навечно лежать в открытом файле на диске.

### 📍 Текущий код
```rust
// src/audit.rs:66-77
let display_content = if content.chars().count() > 500 {
    let snippet: String = content.chars().take(500).collect();
    format!("{}... [всего {} симв.]", snippet, content.chars().count())
} else {
    content.trim().to_string() // <-- СЕКРЕТ ПОПАДАЕТ В ОТКРЫТЫЙ ЛОГ!
};

let log_line = format!(
    "[{timestamp}]\nФайл: {file_path}\nЧто прочитал: {display_content}\n--------------------------------------------------------------------------------\n"
);
```

### 💥 Последствия
1. Любой процесс или непривилегированное ПО на компьютере пользователя может прочитать файл `clipboard_access.log` и извлечь сохранённые секреты.
2. Противоречие назначению продукта GhostClip: программа позиционируется как средство защиты от утечек, но сама де-факто ведёт журнал перехваченных паролей.

### ✅ Решение
Интегрировать проверку секретов перед записью в лог. Если текст распознан как секрет через `detector::detect_secret`, маскировать его значение, сохраняя лишь метаданные типа секрета:

```rust
// src/audit.rs:37-75
pub fn log_access(file_path: &str, content: &str) {
    if file_path.is_empty() || content.trim().is_empty() {
        return;
    }

    // ... хеширование и проверка дедупликации ...

    // Проверяем, является ли содержимое секретом
    let display_content = if let Some(secret) = crate::detector::detect_secret(
        content,
        &crate::config::DetectorConfig::default(),
    ) {
        format!("[ЗАЩИЩЕНО: {}] Длина: {} симв.", secret.description(), content.chars().count())
    } else {
        let char_count = content.chars().count();
        if char_count > 500 {
            let snippet: String = content.chars().take(500).collect();
            format!("{}... [всего {} симв.]", snippet, char_count)
        } else {
            content.trim().to_string()
        }
    };

    let log_line = format!(
        "[{timestamp}]\nФайл: {file_path}\nСодержимое: {display_content}\n--------------------------------------------------------------------------------\n"
    );
    // ... запись в файл ...
}
```

### 💡 Объяснение
Такой подход сохраняет прозрачность мониторинга процессов, но исключает оседание критических конфиденциальных строк на постоянном накопителе.

### ⏱ Сложность исправления
Низкая (15 минут).

---

## SEC-003: Создание файлов конфигурации без ограничения дескрипторов безопасности (ACL)

| Поле | Значение |
|---|---|
| **Идентификатор** | SEC-003 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/config.rs:146`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/config.rs#L146), [`src/config.rs:155`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/config.rs#L155) |
| **Категория** | Недостаточный контроль доступа к конфигурации (CWE-732) |

### ❌ Проблема
Вызовы `fs::write(path_ref, toml_str)` создают файл `config.toml` со стандартными правами текущего процесса. В многопользовательских системах Windows или при запуске во временных каталогах сторонние непривилегированные приложения могут изменить списки `whitelist`/`blacklist`, добавив себя в белый список и нейтрализовав защиту.

### ✅ Решение
Для конфиденциальных настроек защитного ПО следует создавать конфигурационный файл с явным ограничением DACL (только текущий пользователь и администраторы).

### ⏱ Сложность исправления
Средняя (30 минут).

---

## SEC-004: Использование неколлизионностойкого `DefaultHasher` для дедупликации и контроля цикла

| Поле | Значение |
|---|---|
| **Идентификатор** | SEC-004 |
| **Серьёзность** | 🟢 Low |
| **Файл и строки** | [`src/sentinel.rs:14-19`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/sentinel.rs#L14-L19), [`src/audit.rs:43-46`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/audit.rs#L43-L46) |
| **Категория** | Криптографическая стойкость хеширования |

### ❌ Проблема
В `sentinel.rs` и `audit.rs` применяется `DefaultHasher` стандартной библиотеки Rust (в текущей реализации SipHash-1-3 с ключами по умолчанию). Этот алгоритм не предназначен для сценариев криптографического сопоставления. Хотя в контексте буфера обмена риск намеренной атаки на поиск коллизий низок, случайное совпадение хешей приведёт к ложному срабатыванию sentinel (пропуску чужого скопированного текста).

### ✅ Решение
Добавить комментарий с обоснованием допустимости SipHash для предотвращения рекурсивных циклов либо при необходимости использовать быстрый детерминированный криптографический хеш (например, `blake3`).

### ⏱ Сложность исправления
Низкая (5 минут).
