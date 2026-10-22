# ⚡ Производительность

---

## PERF-001: Двойной линейный подсчёт символов `chars().count()` в `audit::log_access`

| Поле | Значение |
|---|---|
| **Идентификатор** | PERF-001 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/audit.rs:67-72`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/audit.rs#L67-L72) |
| **Категория** | Вычислительная сложность / Избыточные проходы по строке |

### ❌ Проблема
В UTF-8 кодировке количество символов (Unicode Scalar Values) не совпадает с количеством байт. Функция `content.chars().count()` выполняет полный линейный обход всей строки со сложностью $O(N)$.
В текущем коде `chars().count()` вызывается дважды подряд для текста длиннее 500 символов: сначала при проверке `if content.chars().count() > 500`, а затем внутри макроса `format!("... [всего {} симв.]", ..., content.chars().count())`.

### 📍 Текущий код
```rust
// src/audit.rs:67-72
let display_content = if content.chars().count() > 500 {
    let snippet: String = content.chars().take(500).collect();
    format!("{}... [всего {} симв.]", snippet, content.chars().count()) // ВТОРОЙ ПОЛНЫЙ ОБХОД!
} else {
    content.trim().to_string()
};
```

### 💥 Последствия
Если пользователь копирует большой объём текста (например, исходный код на 2–5 МБ, базу данных или книгу), приложение дважды декодирует весь массив UTF-8 байтов в UI-потоке, вызывая заметные микрофризы (до 10–50 мс на больших текстах).

### ✅ Решение
Сохранить результат первого вычисления в локальную переменную либо ограничиться подсчётом первых 501 символа:

```rust
// Оптимальный вариант с ранним выходом:
let mut chars_iter = content.chars();
let snippet: String = chars_iter.by_ref().take(500).collect();

let display_content = if let Some(first_overflow) = chars_iter.next() {
    // Длина превышает 500: добираем оставшийся счетчик без повторного сканирования начала
    let remaining = 1 + chars_iter.count();
    let total = 500 + remaining;
    format!("{}... [всего {} симв.]", snippet, total)
} else {
    content.trim().to_string()
};
```

### 💡 Объяснение
Вызов итератора `by_ref().take(500)` извлекает срез за константное время $O(\min(N, 500))$. Если остатка нет, полный обход длинного текста вообще не производится.

### ⏱ Сложность исправления
Низкая (5 минут).

---

## PERF-002: Глубокое копирование `AppConfig.clone()` в цикле обработки каждого события буфера

| Поле | Значение |
|---|---|
| **Идентификатор** | PERF-002 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/main.rs:139-143`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L139-L143) |
| **Категория** | Избыточные аллокации памяти в Hot-Path |

### ❌ Проблема
При каждом срабатывании системного сообщения `WM_CLIPBOARDUPDATE` оконная процедура блокирует `APP_STATE` и выполняет полное глубокое клонирование структуры `AppConfig`. Внутри структуры содержатся динамические векторы строк `whitelist: Vec<String>` и `blacklist: Vec<String>`.

### 📍 Текущий код
```rust
// src/main.rs:139-143
let cfg = {
    let lock = APP_STATE.lock().unwrap();
    lock.as_ref().map(|s| s.config.clone()).unwrap_or_default()
};
```

### 💥 Последствия
Лишние аллокации в системной куче Windows на каждое копирование или переключение фокуса. В сценариях активного редактирования текста или пакетных скриптов это создаёт дополнительную фрагментацию кучи и избыточную нагрузку на CPU.

### ✅ Решение
Обернуть `AppConfig` в атомарный умный указатель `std::sync::Arc`:

```rust
// src/main.rs
struct AppState {
    config: std::sync::Arc<AppConfig>,
    tray_icon_raw: usize,
    current_state: TrayState,
}

// src/main.rs:139-143
let cfg = {
    let lock = APP_STATE.lock().unwrap_or_else(|p| p.into_inner());
    lock.as_ref()
        .map(|s| std::sync::Arc::clone(&s.config))
        .unwrap_or_else(|| std::sync::Arc::new(AppConfig::default()))
};
```

### 💡 Объяснение
Клонирование `Arc` состоит из единственной атомарной инструкции инкремента счётчика ссылок (`fetch_add`) без каких-либо обращений к системному аллокатору памяти.

### ⏱ Сложность исправления
Низкая (10 минут).

---

## PERF-003: Неоптимальный линейный поиск $O(N)$ с аллокацией строк в файрволе

| Поле | Значение |
|---|---|
| **Идентификатор** | PERF-003 |
| **Серьёзность** | 🟢 Low |
| **Файл и строки** | [`src/firewall.rs:115`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/firewall.rs#L115), [`src/firewall.rs:125`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/firewall.rs#L125) |
| **Категория** | Алгоритмическая неэффективность |

### ❌ Проблема
В `evaluate_access` проверка принадлежности списку выполняется линейным поиском:
`config.whitelist.iter().any(|w| w.to_lowercase() == lower_name)`.
На каждом элементе создаётся новая строка на куче через `w.to_lowercase()`. При большом списке разрешённых приложений это приводит к множественным аллокациям строк.

### 📍 Текущий код
```rust
// src/firewall.rs:115, 125
if config.blacklist.iter().any(|b| b.to_lowercase() == lower_name) { ... }
if config.whitelist.iter().any(|w| w.to_lowercase() == lower_name) { ... }
```

### ✅ Решение
Хранить списки `whitelist` и `blacklist` сразу в нижнем регистре в структуре `std::collections::HashSet<String>`:

```rust
if config.blacklist_set.contains(&lower_name) { ... }
if config.whitelist_set.contains(&lower_name) { ... }
```

Сложность поиска снизится с $O(N \cdot M)$ до $O(1)$ без единой дополнительной аллокации при проверке.

### ⏱ Сложность исправления
Низкая (15 минут).
