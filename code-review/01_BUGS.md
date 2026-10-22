# 🐛 Баги и логические ошибки

---

## BUG-001: Неопределённое поведение (UB) при создании фиктивного среза в `read_clipboard_text`

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-001 |
| **Серьёзность** | 🔴 Critical |
| **Файл и строки** | [`src/main.rs:74-81`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L74-L81) |
| **Категория** | Память и Undefined Behavior |

### ❌ Проблема
В функции `read_clipboard_text` срез `std::slice::from_raw_parts` создаётся с длиной `usize::MAX / 2`. Это делается в предположении, что цикл поиска нуля остановится до выхода за пределы выделенного блока. Однако создание среза, выходящего за пределы фактической аллокации (в данном случае срез заявляет размер более 9 эксабайт), является безусловным нарушением контракта безопасности Rust и приводит к немедленному **Undefined Behavior**, даже если элементы за пределами буфера не разыменовываются.

### 📍 Текущий код
```rust
// src/main.rs:74-81
let slice = std::slice::from_raw_parts(ptr as *const u16, usize::MAX / 2);
let mut len = 0;
while slice[len] != 0 {
    len += 1;
}

let text = String::from_utf16_lossy(&slice[..len]);
```

### 💥 Последствия
1. Компилятор `rustc` и LLVM оптимизируют код, полагаясь на валидность диапазона среза. Это может приводить к произвольной порче соседних структур в стеке или куче, спонтанным сбоям оптимизатора и сегфолтам при релизной сборке.
2. При отсутствии нуль-терминатора в повреждённом буфере цикл приведёт к немедленному Access Violation (чтение невыделенной страницы памяти).

### ✅ Решение
Использовать системный вызов `GlobalSize(hglobal)` для определения точного размера блока памяти, выделенного под буфер обмена:

```rust
// src/main.rs:68-85
let hglobal = HGLOBAL(handle.0);
let ptr = GlobalLock(hglobal);
if ptr.is_null() {
    let _ = CloseClipboard();
    return None;
}

// 1. Получаем реальный физический размер системного блока памяти
let total_bytes = windows::Win32::System::Memory::GlobalSize(hglobal);
let total_u16 = total_bytes / std::mem::size_of::<u16>();

if total_u16 == 0 {
    let _ = GlobalUnlock(hglobal);
    let _ = CloseClipboard();
    return None;
}

// 2. Создаем срез строго в рамках фактической аллокации
let slice = std::slice::from_raw_parts(ptr as *const u16, total_u16);

// 3. Безопасно ищем терминатор либо берем всю длину
let len = slice.iter().position(|&c| c == 0).unwrap_or(total_u16);
let text = String::from_utf16_lossy(&slice[..len]);

let _ = GlobalUnlock(hglobal);
let _ = CloseClipboard();

Some(text)
```

### 💡 Объяснение
Вызов `GlobalSize` возвращает точный размер блока памяти в байтах. Деление на `sizeof::<u16>()` даёт допустимое количество элементов. Метод `iter().position(|&c| c == 0)` гарантирует, что поиск нуль-терминатора никогда не выйдет за границы аллокации.

### ⏱ Сложность исправления
Низкая (10 минут).

---

## BUG-002: Логическая ошибка радара — перехват источника записи вместо читателя

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-002 |
| **Серьёзность** | 🔴 Critical |
| **Файл и строки** | [`src/radar.rs:66-87`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/radar.rs#L66-L87), [`src/main.rs:155-160`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L155-L160) |
| **Категория** | Логика приложения / Архитектурный дефект |

### ❌ Проблема
Событие Windows `WM_CLIPBOARDUPDATE` генерируется операционной системой **в момент изменения (записи)** буфера обмена. В текущей реализации при получении `WM_CLIPBOARDUPDATE` вызывается `radar::detect_clipboard_reader()`, который обращается к `GetOpenClipboardWindow()` и затем фоллбэчится на `GetForegroundWindow()`. В этот момент активным окном является приложение, **из которого пользователь только что скопировал текст**. В результате программа записывает в журнал аудита в графу «Что прочитал» процесс, который на самом деле произвёл запись.

### 📍 Текущий код
```rust
// src/radar.rs:66-76
pub fn detect_clipboard_reader() -> Option<ProcessInfo> {
    unsafe {
        let mut target_hwnd = GetOpenClipboardWindow().unwrap_or(HWND(std::ptr::null_mut()));

        if target_hwnd.0.is_null() {
            target_hwnd = GetForegroundWindow();
        }
        // ... получение имени исполняемого файла
    }
}

// src/main.rs:155-160
if let Some(accessor) = radar::detect_clipboard_reader() {
    let my_pid = std::process::id();
    if accessor.pid != my_pid {
        audit::log_access(&accessor.full_path, &text);
    }
}
```

### 💥 Последствия
1. Журнал аудита `clipboard_access.log` вводит пользователя в заблуждение: вместо шпионских программ пользователь видит легитимные программы, откуда он копировал (браузер, блокнот, IDE).
2. Настоящие программы-шпионы, считывающие буфер вызовом `GetClipboardData` без генерации событий изменения, остаются незамеченными через данный механизм.

### ✅ Решение
1. **Корректировка терминологии и семантики (быстрое решение):** переименовать модуль и лог в фиксацию *авторов записей* (`detect_clipboard_writer` / «Кто поместил в буфер»).
2. **Для истинного перехвата чтения (продвинутое решение):** документировать в архитектуре, что стандартный Win32 API не имеет события `WM_CLIPBOARDREAD`. Для реального обнаружения чтения требуется либо API Hooking (`Detours` / `MinHook` на функции `OpenClipboard`/`GetClipboardData` в целевых процессах), либо фильтр-драйвер Windows.

```rust
// Исправление в audit.rs:74-76
let log_line = format!(
    "[{timestamp}]\nФайл: {file_path}\nКто поместил в буфер: {display_content}\n--------------------------------------------------------------------------------\n"
);
```

### 💡 Объяснение
Механизм `AddClipboardFormatListener` в Win32 уведомляет только об изменениях контента (`WM_CLIPBOARDUPDATE`). Считывание буфера не вызывает системных широковещательных сообщений.

### ⏱ Сложность исправления
Низкая (для исправления текста/семантики) / Высокая (для драйверного перехвата).

---

## BUG-003: Утечка системных потоков в таймере `ghost::arm_timer`

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-003 |
| **Серьёзность** | 🟠 High |
| **Файл и строки** | [`src/ghost.rs:27-51`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/ghost.rs#L27-L51) |
| **Категория** | Утечка ресурсов / Concurrency |

### ❌ Проблема
Каждый раз, когда в буфере обнаруживается секрет, функция `arm_timer` спавнит новый системный поток через `std::thread::spawn`. Потоки не объединяются и не переиспользуются. Если пользователь часто копирует секретные данные (или запущен пакетный процесс), каждый вызов создаёт поток, который висит в цикле сна `for _ in 0..seconds` с шагом в 1 секунду.

### 📍 Текущий код
```rust
// src/ghost.rs:27-36
thread::spawn(move || {
    for _ in 0..seconds {
        thread::sleep(Duration::from_secs(1));

        if CURRENT_EPOCH.load(Ordering::SeqCst) != new_epoch || !TIMER_ARMED.load(Ordering::SeqCst) {
            return;
        }
        // ...
    }
    // ...
});
```

### 💥 Последствия
1. Спавн десятков неконтролируемых потоков ОС при интенсивной работе с паролями.
2. Неоправданный расход памяти на стеки потоков (в Windows стек по умолчанию до 1 МБ).
3. Задержка до 1 секунды перед завершением потока даже после инвалидации эпохи.

### ✅ Решение
Использовать таймер в рамках очереди сообщений Windows (`SetTimer` / `WM_TIMER`), либо выделить ровно один постоянный рабочий поток-таймер с `std::sync::Condvar`:

```rust
use std::sync::{Condvar, Mutex, OnceLock};

struct TimerSignal {
    mutex: Mutex<bool>,
    cvar: Condvar,
}

static TIMER_SIGNAL: OnceLock<TimerSignal> = OnceLock::new();

fn ensure_worker_started() {
    static STARTED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
    if STARTED.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst).is_ok() {
        thread::spawn(|| {
            let sig = TIMER_SIGNAL.get_or_init(|| TimerSignal {
                mutex: Mutex::new(false),
                cvar: Condvar::new(),
            });
            loop {
                let mut lock = sig.mutex.lock().unwrap();
                while !TIMER_ARMED.load(Ordering::SeqCst) {
                    lock = sig.cvar.wait(lock).unwrap();
                }
                drop(lock);

                thread::sleep(Duration::from_secs(1));
                if !TIMER_ARMED.load(Ordering::SeqCst) {
                    continue;
                }

                let left = REMAINING_SECS.fetch_sub(1, Ordering::SeqCst);
                if left <= 1 {
                    TIMER_ARMED.store(false, Ordering::SeqCst);
                    shredder::wipe_all();
                }
            }
        });
    }
}
```

### 💡 Объяснение
Выделение единственного фонового рабочего потока с сигнальной переменной (`Condvar`) гарантирует константное потребление системных ресурсов `O(1)` независимо от частоты копирования секретов.

### ⏱ Сложность исправления
Средняя (30 минут).

---

## BUG-004: Утечка дескриптора памяти `GlobalAlloc` в `shredder::wipe_win32_clipboard`

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-004 |
| **Серьёзность** | 🟠 High |
| **Файл и строки** | [`src/shredder.rs:45-58`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/shredder.rs#L45-L58) |
| **Категория** | Утечка системной памяти (Win32 Memory Leak) |

### ❌ Проблема
В функции `wipe_win32_clipboard` выделяется 64 байта глобальной перемещаемой памяти через `GlobalAlloc(GMEM_MOVEABLE, 64)`. Память блокируется и заполняется нулями (`write_bytes`). Однако дескриптор `handle` **никогда не передаётся** в `SetClipboardData` и **не освобождается** через `GlobalFree`. Затем вызывается повторный `EmptyClipboard()`. Выделенная память безвозвратно утекает в системной куче Windows.

### 📍 Текущий код
```rust
// src/shredder.rs:45-58
let mem_handle = GlobalAlloc(GMEM_MOVEABLE, 64);
if let Ok(handle) = mem_handle {
    let ptr = GlobalLock(handle);
    if !ptr.is_null() {
        std::ptr::write_bytes(ptr as *mut u8, 0, 64);
        let _ = GlobalUnlock(handle);
    }
    // ОШИБКА: handle не передан в SetClipboardData и не освобожден через GlobalFree!
}

// Финальная очистка буфера
let _ = EmptyClipboard();
let _ = CloseClipboard();
```

### 💥 Последствия
1. Утечка дескрипторов глобальной памяти при каждом срабатывании таймера самоуничтожения или хоткея `PanicFlush`.
2. Логическая бесполезность операции: заполненная нулями память даже не публикуется в буфер, так как следом идёт `EmptyClipboard()`.

### ✅ Решение
Для гарантированной зачистки буфера обмена в Win32 достаточно одного успешного вызова `EmptyClipboard()` между `OpenClipboard()` и `CloseClipboard()`. Если требуется явно положить нулевые байты в буфер, дескриптор обязан передаваться в `SetClipboardData`:

```rust
// src/shredder.rs:32-62
pub fn wipe_win32_clipboard() -> bool {
    let _guard = InternalUpdateGuard::new();

    if !open_clipboard_with_retry(HWND(std::ptr::null_mut()), 5) {
        eprintln!("[Shredder] Не удалось открыть буфер обмена для очистки.");
        return false;
    }

    unsafe {
        // Очищает буфер обмена и освобождает все связанные хэндлы данных
        let ok = EmptyClipboard().is_ok();
        let _ = CloseClipboard();
        ok
    }
}
```

### 💡 Объяснение
Вызов `EmptyClipboard()` освобождает дескрипторы всех форматов данных, находившихся в буфере, и передаёт владение текущему окну. Создание отдельного блока `GlobalAlloc`, не переданного системе, приводит лишь к бесцельной утечке дескрипторов глобальной кучи `HGLOBAL`.

### ⏱ Сложность исправления
Низкая (5 минут).

---

## BUG-005: Состояние гонки в `InternalUpdateGuard` из-за асинхронности сообщений Windows

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-005 |
| **Серьёзность** | 🟠 High |
| **Файл и строки** | [`src/sentinel.rs:23-36`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/sentinel.rs#L23-L36), [`src/main.rs:172-175`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L172-L175) |
| **Категория** | Concurrency / Асинхронные события |

### ❌ Проблема
`InternalUpdateGuard` устанавливает флаг `IS_INTERNAL_UPDATE = true` в конструкторе и сбрасывает его в `false` в методе `drop`. В `main.rs` блок очистки ссылки создаёт guard, вызывает `write_clipboard_text`, после чего guard выходит из области видимости и сбрасывает флаг. Однако сообщение `WM_CLIPBOARDUPDATE` рассылается Windows **асинхронно** через системную очередь сообщений. К моменту, когда цикл сообщений доберётся до обработки `WM_CLIPBOARDUPDATE`, флаг `IS_INTERNAL_UPDATE` уже будет сброшен в `false`.

### 📍 Текущий код
```rust
// src/main.rs:170-176
sentinel::record_written_text(&cleaned_text);
let _guard = sentinel::InternalUpdateGuard::new(); // IS_INTERNAL_UPDATE = true
write_clipboard_text(hwnd, &cleaned_text);
println!("[CleanClip] 🧹 Ссылка очищена от трекеров и сохранена в буфер!");
// <-- Здесь _guard сбрасывается в false ДО ТОГО, как очередь обработает WM_CLIPBOARDUPDATE
```

### 💥 Последствия
1. Защита от самосрабатывания опирается исключительно на вторичный механизм хешей `is_same_as_last_written`.
2. Если параллельно произойдёт ещё одно обращение к буферу, логика sentinel даст сбой, вызывая повторные паразитные срабатывания детектора.

### ✅ Решение
Сбрасывать флаг внутренней модификации не по выходу из блока, а атомарно в обработчике `WM_CLIPBOARDUPDATE` при его получении:

```rust
// src/sentinel.rs
pub fn set_internal_update() {
    IS_INTERNAL_UPDATE.store(true, Ordering::SeqCst);
}

pub fn check_and_clear_internal_update() -> bool {
    IS_INTERNAL_UPDATE.swap(false, Ordering::SeqCst)
}

// src/main.rs:134-137
WM_CLIPBOARDUPDATE => {
    if sentinel::check_and_clear_internal_update() {
        return LRESULT(0);
    }
    // ...
```

### 💡 Объяснение
Атомарная замена `swap(false)` позволяет однократно поглотить системное событие, сгенерированное собственной записью, без риска преждевременного сброса флага компилятором или RAII-деструктором.

### ⏱ Сложность исправления
Низкая (15 минут).

---

## BUG-006: Паника при отравлении мьютекса `APP_STATE` в оконной процедуре

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-006 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/main.rs:140`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L140), [`src/main.rs:235`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L235), [`src/main.rs:386`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L386) |
| **Категория** | Устойчивость к сбоям (Error Handling) |

### ❌ Проблема
Вызовы `APP_STATE.lock().unwrap()` в оконной процедуре `window_proc` приведут к немедленной панике процесса, если любой другой поток аварийно завершится с паникой во время удержания блокировки (Poisoned Mutex).

### 📍 Текущий код
```rust
// src/main.rs:140
let cfg = {
    let lock = APP_STATE.lock().unwrap();
    lock.as_ref().map(|s| s.config.clone()).unwrap_or_default()
};
```

### 💥 Последствия
Аварийное завершение фонового демона при любом сбое в фоновых операциях, связанных с конфигурацией или иконкой в трее.

### ✅ Решение
Использовать безопасное извлечение значения из отравленного мьютекса через `unwrap_or_else`:

```rust
let cfg = {
    let lock = APP_STATE.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    lock.as_ref().map(|s| s.config.clone()).unwrap_or_default()
};
```

### ⏱ Сложность исправления
Низкая (5 минут).

---

## BUG-007: Гонка состояния глобальных атомиков диалога в `dialog.rs`

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-007 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/ui/dialog.rs:25-27`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/ui/dialog.rs#L25-L27) |
| **Категория** | Потокобезопасность UI |

### ❌ Проблема
Переменные `DIALOG_CHOICE` и `REMAINING_SECS` объявлены как глобальные статические `AtomicI32`. Если несколько приложений одновременно попытаются обратиться к буферу, вызов `prompt_firewall_decision` перезапишет выбор и таймер предыдущего открытого окна диалога.

### 📍 Текущий код
```rust
static DIALOG_CHOICE: AtomicI32 = AtomicI32::new(0);
static REMAINING_SECS: AtomicI32 = AtomicI32::new(7);
```

### 💥 Последствия
Некорректное завершение одного из окон с таймером другого окна или искажение ответа пользователя при конкурентных запросах.

### ✅ Решение
Защитить отображение диалога глобальным мьютексом очереди (`static DIALOG_MUTEX: Mutex<()> = Mutex::new(());`), либо передавать указатель на структуру состояния окна через `GWLP_USERDATA` дескриптора `HWND`.

### ⏱ Сложность исправления
Средняя (20 минут).

---

## BUG-008: Использование нулевого `HINSTANCE` в `dialog.rs` и `main.rs`

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-008 |
| **Серьёзность** | 🟡 Medium |
| **Файл и строки** | [`src/ui/dialog.rs:100`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/ui/dialog.rs#L100), [`src/main.rs:352`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/main.rs#L352) |
| **Категория** | Корректность вызовов Win32 API |

### ❌ Проблема
Передача `HINSTANCE(std::ptr::null_mut())` в структуры `WNDCLASSW` и вызовы `CreateWindowExW` не является документированным стандартом Win32 для регистрации оконных классов приложения.

### 📍 Текущий код
```rust
let instance = HINSTANCE(std::ptr::null_mut());
```

### ✅ Решение
Получать дескриптор текущего исполняемого модуля через `GetModuleHandleW(None)`:

```rust
use windows::Win32::System::LibraryLoader::GetModuleHandleW;

let instance = HINSTANCE(unsafe { GetModuleHandleW(None) }.unwrap_or_default().0);
```

### ⏱ Сложность исправления
Низкая (5 минут).

---

## BUG-009: Ручная вставка нуль-терминатора в `format!` вместо безопасного итератора

| Поле | Значение |
|---|---|
| **Идентификатор** | BUG-009 |
| **Серьёзность** | 🟢 Low |
| **Файл и строки** | [`src/ui/dialog.rs:50-52`](file:///c:/Users/User/Documents/antigravity/amazing-shannon/src/ui/dialog.rs#L50-L52) |
| **Категория** | Надежность преобразования строк |

### ❌ Проблема
В заголовке окна используется ручная интерполяция `\0`: `format!("...\0", left)`. Если при рефакторинге символ `\0` будет случайно удалён, `PCWSTR` продолжит чтение памяти до случайного нулевого байта.

### ✅ Решение
Применять единообразный паттерн с цепочкой `.chain(std::iter::once(0))`:

```rust
let title = format!("GhostClip Firewall (Авто-отказ через {} сек)", left);
let title_utf16: Vec<u16> = title.encode_utf16().chain(std::iter::once(0)).collect();
let _ = SetWindowTextW(hwnd, PCWSTR(title_utf16.as_ptr()));
```

### ⏱ Сложность исправления
Низкая (2 минуты).
