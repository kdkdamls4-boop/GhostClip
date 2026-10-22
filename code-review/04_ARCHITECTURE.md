# 🏗 Архитектура и качество кода

---

## ARCH-001: Наличие 394 строк мёртвого кода в `firewall.rs` и `ui/dialog.rs`

| Поле | Значение |
|---|---|
| **Идентификатор** | ARCH-001 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/firewall.rs:1-185`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/firewall.rs#L1-L185), [`src/ui/dialog.rs:1-209`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/ui/dialog.rs#L1-L209) |
| **Категория** | Dead Code / Нарушение принципа YAGNI |

### ❌ Проблема
После коммита `e9f7edb` проект отказался от навязчивой блокировки доступа к буферу в пользу прозрачного журналирования (`audit.rs`). Модули `firewall.rs` (185 строк) и `ui/dialog.rs` (209 строк) были помечены `#![allow(dead_code)]`.
Функции `evaluate_access`, `prompt_firewall_decision`, `grant_timed_access` и оконная процедура диалога больше нигде не вызываются в основном цикле программы. При этом они продолжают компилироваться, усложняя понимание кодовой базы для джуниор-разработчиков и раздувая размер итогового артефакта.

### 📍 Текущий код
```rust
// src/firewall.rs:1
#![allow(dead_code)]

// src/ui/dialog.rs:1
#![allow(dead_code)]
```

### 💥 Последствия
1. Заблуждение разработчиков относительно того, какие механизмы защиты реально функционируют в приложении.
2. Необходимость сопровождать и обновлять неиспользуемые модули при миграциях API.

### ✅ Решение
1. **Вариант А (Рекомендуемый):** Вынести неиспользуемые интерактивные модули под опциональную Cargo-фичу (Feature Gate):
   ```toml
   # Cargo.toml
   [features]
   default = []
   interactive-firewall = []
   ```
   В коде: `#[cfg(feature = "interactive-firewall")] mod firewall;`.
2. **Вариант Б:** Полностью удалить неиспользуемые файлы и связанные с ними пункты в TUI-меню, сохранив их в истории Git.

### ⏱ Сложность исправления
Низкая (15 минут).

---

## ARCH-002: Использование магического литерала `13` вместо `CF_UNICODETEXT`

| Поле | Значение |
|---|---|
| **Идентификатор** | ARCH-002 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/main.rs:62`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L62), [`src/main.rs:117`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L117) |
| **Категория** | Читаемость кода / Magic Numbers |

### ❌ Проблема
Для формата данных буфера обмена Windows напрямую передаётся число `13`:
`GetClipboardData(13)` и `SetClipboardData(13, ...)`.
Это нарушает читаемость кода для начинающих разработчиков и противоречит идиоматическому стилю Rust.

### 📍 Текущий код
```rust
// src/main.rs:61-63
// 13 = CF_UNICODETEXT
let handle_res = GetClipboardData(13);

// src/main.rs:116-118
// 13 = CF_UNICODETEXT
let set_res = SetClipboardData(13, HANDLE(handle.0));
```

### ✅ Решение
Объявить глобальную типизированную константу или импортировать её:

```rust
const CF_UNICODETEXT: u32 = 13;

let handle_res = GetClipboardData(CF_UNICODETEXT);
let set_res = SetClipboardData(CF_UNICODETEXT, HANDLE(handle.0));
```

### ⏱ Сложность исправления
Низкая (2 минуты).

---

## ARCH-003: Обход системы типов Rust через приведение `HICON` к целому числу `usize`

| Поле | Значение |
|---|---|
| **Идентификатор** | ARCH-003 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/main.rs:36-50`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L36-L50) |
| **Категория** | Типобезопасность / Type Safety Smells |

### ❌ Проблема
Тип `HICON` в `windows-rs` содержит сырой указатель `*mut c_void` и не реализует маркерные типажи `Send` и `Sync`. Чтобы поместить его в `Mutex<Option<AppState>>`, автор применил приведение дескриптора к `usize` (`self.tray_icon_raw = icon.0 as usize`).
Такой подход маскирует назначение поля и обходит контроль компилятора без явного декларирования инвариантов безопасности.

### 📍 Текущий код
```rust
// src/main.rs:36-50
struct AppState {
    config: AppConfig,
    tray_icon_raw: usize, // <-- Сырое число вместо дескриптора иконки
    current_state: TrayState,
}

impl AppState {
    fn tray_icon(&self) -> HICON {
        HICON(self.tray_icon_raw as *mut _)
    }

    fn set_tray_icon(&mut self, icon: HICON) {
        self.tray_icon_raw = icon.0 as usize;
    }
}
```

### ✅ Решение
Создать прозрачную безопасную Newtype-обёртку с явным документированным подтверждением безопасности передачи дескриптора между потоками:

```rust
/// Потокобезопасная обертка над системным дескриптором иконки Windows.
/// Дескрипторы GDI/User32 в Windows валидны в контексте всего сеанса пользователя.
#[repr(transparent)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SafeHicon(pub HICON);

unsafe impl Send for SafeHicon {}
unsafe impl Sync for SafeHicon {}

struct AppState {
    config: std::sync::Arc<AppConfig>,
    tray_icon: SafeHicon,
    current_state: TrayState,
}
```

### ⏱ Сложность исправления
Низкая (10 минут).

---

## ARCH-004: Избыточная ручная реализация `Default` для `PanicConfig`

| Поле | Значение |
|---|---|
| **Идентификатор** | ARCH-004 |
| **Серьёзность** | 🟢 Low |
| **Файл и строки** | [`src/config.rs:57-61`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/config.rs#L57-L61), [`src/config.rs:105-111`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/config.rs#L105-L111) |
| **Категория** | Стиль кода / Clippy Warning (`derivable_impls`) |

### ❌ Проблема
Структура `PanicConfig` содержит единственное поле `lock_workstation: bool`, для которого реализован трейт `Default` вручную со значением `false`. Это идентично поведению автоматического макроса `#[derive(Default)]`.

### 📍 Текущий код
```rust
// src/config.rs:105-111
impl Default for PanicConfig {
    fn default() -> Self {
        Self {
            lock_workstation: false,
        }
    }
}
```

### ✅ Решение
Добавить `Default` в список автодериваций структуры и удалить ручную реализацию:

```rust
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PanicConfig {
    pub lock_workstation: bool,
}
```

### ⏱ Сложность исправления
Низкая (1 минута).
