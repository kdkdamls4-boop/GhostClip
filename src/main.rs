use std::sync::Mutex;
use windows::core::w;
use windows::Win32::Foundation::{HANDLE, HGLOBAL, HINSTANCE, HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::System::DataExchange::{
    AddClipboardFormatListener, CloseClipboard, EmptyClipboard, GetClipboardData,
    OpenClipboard, RemoveClipboardFormatListener, SetClipboardData,
};
use windows::Win32::System::Memory::{
    GlobalAlloc, GlobalLock, GlobalUnlock, GMEM_MOVEABLE,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetMessageW,
    HICON, KillTimer, PostQuitMessage, RegisterClassW, SetTimer, TranslateMessage, MSG,
    WM_CLIPBOARDUPDATE, WM_COMMAND, WM_DESTROY, WM_HOTKEY, WM_RBUTTONUP, WM_TIMER,
    WNDCLASSW, WS_OVERLAPPEDWINDOW,
};

mod cleaner;
mod cli;
mod config;
mod detector;
mod firewall;
mod ghost;
mod hotkeys;
mod radar;
mod sentinel;
mod shredder;
mod ui;

use config::AppConfig;
use ui::tray::{init_tray_icon, remove_tray_icon, show_tray_menu, update_tray_state, TrayState};

const TIMER_STATUS_CHECK: usize = 5001;

struct AppState {
    config: AppConfig,
    tray_icon_raw: usize,
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

static APP_STATE: Mutex<Option<AppState>> = Mutex::new(None);

/// Безопасное чтение текстового содержимого из буфера обмена Windows (CF_UNICODETEXT).
fn read_clipboard_text(hwnd: HWND) -> Option<String> {
    unsafe {
        if OpenClipboard(hwnd).is_err() {
            return None;
        }

        // 13 = CF_UNICODETEXT
        let handle_res = GetClipboardData(13);
        let Ok(handle) = handle_res else {
            let _ = CloseClipboard();
            return None;
        };

        let hglobal = HGLOBAL(handle.0);
        let ptr = GlobalLock(hglobal);
        if ptr.is_null() {
            let _ = CloseClipboard();
            return None;
        }

        let slice = std::slice::from_raw_parts(ptr as *const u16, usize::MAX / 2);
        let mut len = 0;
        while slice[len] != 0 {
            len += 1;
        }

        let text = String::from_utf16_lossy(&slice[..len]);
        let _ = GlobalUnlock(hglobal);
        let _ = CloseClipboard();

        Some(text)
    }
}

/// Безопасная запись текста в системный буфер обмена Windows.
fn write_clipboard_text(hwnd: HWND, text: &str) -> bool {
    let utf16: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
    let bytes_len = utf16.len() * std::mem::size_of::<u16>();

    unsafe {
        if OpenClipboard(hwnd).is_err() {
            return false;
        }

        let _ = EmptyClipboard();

        let handle_res = GlobalAlloc(GMEM_MOVEABLE, bytes_len);
        let Ok(handle) = handle_res else {
            let _ = CloseClipboard();
            return false;
        };

        let ptr = GlobalLock(handle);
        if ptr.is_null() {
            let _ = CloseClipboard();
            return false;
        }

        std::ptr::copy_nonoverlapping(utf16.as_ptr() as *const u8, ptr as *mut u8, bytes_len);
        let _ = GlobalUnlock(handle);

        // 13 = CF_UNICODETEXT
        let set_res = SetClipboardData(13, HANDLE(handle.0));
        let _ = CloseClipboard();

        set_res.is_ok()
    }
}

/// Главная оконная процедура обработки событий Windows.
unsafe extern "system" fn window_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    unsafe {
        match msg {
            WM_CLIPBOARDUPDATE => {
                // 1. Anti-Loop Sentinel: если изменение сделано нашей программой — игнорируем!
                if sentinel::is_internal_update() {
                    return LRESULT(0);
                }

                let cfg = {
                    let lock = APP_STATE.lock().unwrap();
                    lock.as_ref().map(|s| s.config.clone()).unwrap_or_default()
                };

                // 2. ClipboardRadar & Firewall: проверяем процесс, обратившийся к буферу
                if cfg.firewall.enabled {
                    if let Some(accessor) = radar::detect_clipboard_reader() {
                        let my_pid = std::process::id();
                        if accessor.pid != my_pid {
                            match firewall::evaluate_access(&accessor.exe_name, accessor.pid, &cfg.firewall) {
                                firewall::AccessDecision::Allow => {
                                    // Доступ разрешен (белый список, активная сессия или ручная вставка Ctrl+V)
                                }
                                firewall::AccessDecision::DenyHoneypot(fake_text) => {
                                    println!("[Firewall] ⛔ Приложение '{}' в черном списке! Подмена на пустышку.", accessor.exe_name);
                                    let _guard = sentinel::InternalUpdateGuard::new();
                                    write_clipboard_text(hwnd, fake_text);

                                    if let Ok(mut lock) = APP_STATE.lock() {
                                        if let Some(state) = lock.as_mut() {
                                            state.current_state = TrayState::Red;
                                            let new_icon = update_tray_state(
                                                hwnd,
                                                state.tray_icon(),
                                                TrayState::Red,
                                                Some(&format!("Заблокирован: {}", accessor.exe_name)),
                                            );
                                            state.set_tray_icon(new_icon);
                                        }
                                    }
                                    ui::notify::show_notification(
                                        hwnd,
                                        "GhostClip Firewall: Блокировка!",
                                        &format!("Приложение '{}' заблокировано от чтения буфера.", accessor.exe_name),
                                        true,
                                    );
                                    return LRESULT(0);
                                }
                                firewall::AccessDecision::AskUser => {
                                    let choice = ui::dialog::prompt_firewall_decision(
                                        &accessor.exe_name,
                                        accessor.pid,
                                        cfg.firewall.dialog_timeout_seconds,
                                    );
                                    match choice {
                                        firewall::UserChoice::AlwaysAllow => {
                                            if let Ok(mut lock) = APP_STATE.lock() {
                                                if let Some(state) = lock.as_mut() {
                                                    state.config.firewall.whitelist.push(accessor.exe_name.clone());
                                                }
                                            }
                                        }
                                        firewall::UserChoice::AllowFor15Min => {
                                            firewall::grant_timed_access(&accessor.exe_name, std::time::Duration::from_secs(15 * 60));
                                        }
                                        firewall::UserChoice::AllowOnce => {
                                            // Разово пропускаем чтение
                                        }
                                        firewall::UserChoice::DenyOnce => {
                                            println!("[Firewall] Отказ пользователем для '{}'.", accessor.exe_name);
                                            let _guard = sentinel::InternalUpdateGuard::new();
                                            write_clipboard_text(hwnd, "");
                                            return LRESULT(0);
                                        }
                                        firewall::UserChoice::AlwaysDeny => {
                                            if let Ok(mut lock) = APP_STATE.lock() {
                                                if let Some(state) = lock.as_mut() {
                                                    state.config.firewall.blacklist.push(accessor.exe_name.clone());
                                                }
                                            }
                                            let _guard = sentinel::InternalUpdateGuard::new();
                                            write_clipboard_text(hwnd, "");
                                            return LRESULT(0);
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // 3. Читаем текущий текст
                let Some(text) = read_clipboard_text(hwnd) else {
                    return LRESULT(0);
                };

                // Проверяем, не является ли текст точной копией того, что мы сами записали
                if sentinel::is_same_as_last_written(&text) {
                    return LRESULT(0);
                }

                // 4. CleanClip: санитайзер трекеров ссылок и zero-width символов
                let (cleaned_text, modified) = cleaner::sanitize_text(
                    &text,
                    cfg.general.clean_urls,
                    cfg.general.clean_zero_width,
                );

                let effective_text = if modified {
                    // Запоминаем хеш и перезаписываем буфер чистой версией
                    sentinel::record_written_text(&cleaned_text);
                    let _guard = sentinel::InternalUpdateGuard::new();
                    write_clipboard_text(hwnd, &cleaned_text);
                    println!("[CleanClip] 🧹 Ссылка очищена от трекеров и сохранена в буфер!");
                    cleaned_text
                } else {
                    text
                };

                // 4. GhostClip: проверка на наличие конфиденциальных данных
                if let Some(secret) = detector::detect_secret(&effective_text, &cfg.detector) {
                    let desc = secret.description();
                    println!("[GhostClip] 🛡️ Обнаружен секрет: {}", desc);

                    // Запускаем таймер самоуничтожения
                    ghost::arm_timer(cfg.general.secret_ttl_seconds, desc);

                    // Обновляем иконку в трее на Желтый статус
                    if let Ok(mut lock) = APP_STATE.lock() {
                        if let Some(state) = lock.as_mut() {
                            state.current_state = TrayState::Yellow;
                            let new_icon = update_tray_state(
                                hwnd,
                                state.tray_icon(),
                                TrayState::Yellow,
                                Some(&format!("Самоуничтожение: {} ({} сек)", desc, cfg.general.secret_ttl_seconds)),
                            );
                            state.set_tray_icon(new_icon);
                        }
                    }

                    // Показываем нативный тост
                    ui::notify::show_notification(
                        hwnd,
                        "GhostClip Shield: Секрет защищен",
                        &format!("Обнаружен {}. Буфер будет стерт через {} сек.", desc, cfg.general.secret_ttl_seconds),
                        false,
                    );
                } else {
                    // Если скопирован обычный текст, а таймер еще тикал — сбрасываем его
                    if ghost::is_armed() {
                        ghost::disarm_timer();
                        if let Ok(mut lock) = APP_STATE.lock() {
                            if let Some(state) = lock.as_mut() {
                                state.current_state = TrayState::Green;
                                let new_icon = update_tray_state(
                                    hwnd,
                                    state.tray_icon(),
                                    TrayState::Green,
                                    None,
                                );
                                state.set_tray_icon(new_icon);
                            }
                        }
                    }
                }

                LRESULT(0)
            }

            WM_HOTKEY => {
                // Срабатывание PanicFlush по Ctrl + Shift + Alt + P
                if wparam.0 == hotkeys::PANIC_HOTKEY_ID as usize {
                    let lock_workstation = {
                        let lock = APP_STATE.lock().unwrap();
                        lock.as_ref().map(|s| s.config.panic.lock_workstation).unwrap_or(false)
                    };

                    hotkeys::execute_panic_flush(lock_workstation);

                    // Сбрасываем иконку в трее в нормальное состояние
                    if let Ok(mut lock) = APP_STATE.lock() {
                        if let Some(state) = lock.as_mut() {
                            state.current_state = TrayState::Green;
                            let new_icon = update_tray_state(hwnd, state.tray_icon(), TrayState::Green, None);
                            state.set_tray_icon(new_icon);
                        }
                    }

                    ui::notify::show_notification(
                        hwnd,
                        "GhostClip: Экстренная зачистка!",
                        "Буфер обмена и журнал Win + V полностью стерты.",
                        true,
                    );
                }
                LRESULT(0)
            }

            ui::tray::WM_TRAY_CALLBACK => {
                // Правый клик по иконке в трее открывает меню
                if lparam.0 as u32 == WM_RBUTTONUP {
                    show_tray_menu(hwnd);
                }
                LRESULT(0)
            }

            WM_COMMAND => {
                let item_id = (wparam.0 & 0xFFFF) as usize;
                match item_id {
                    ui::tray::ID_TRAY_PANIC => {
                        hotkeys::execute_panic_flush(false);
                        ui::notify::show_notification(
                            hwnd,
                            "GhostClip",
                            "Буфер обмена и история очищены.",
                            false,
                        );
                    }
                    ui::tray::ID_TRAY_EXIT => {
                        let _ = DestroyWindow(hwnd);
                    }
                    _ => {}
                }
                LRESULT(0)
            }

            WM_TIMER => {
                // Периодическое обновление статуса таймера в трее
                if let Ok(mut lock) = APP_STATE.lock() {
                    if let Some(state) = lock.as_mut() {
                        if ghost::is_armed() {
                            if let Some(secs) = ghost::remaining_seconds() {
                                let text = format!("Таймер секрета: {} сек", secs);
                                let new_icon = update_tray_state(
                                    hwnd,
                                    state.tray_icon(),
                                    TrayState::Yellow,
                                    Some(&text),
                                );
                                state.set_tray_icon(new_icon);
                            }
                        } else if state.current_state == TrayState::Yellow {
                            state.current_state = TrayState::Green;
                            let new_icon = update_tray_state(
                                hwnd,
                                state.tray_icon(),
                                TrayState::Green,
                                None,
                            );
                            state.set_tray_icon(new_icon);
                        }
                    }
                }
                LRESULT(0)
            }

            WM_DESTROY => {
                // Завершение работы: снимаем слушатели и удаляем иконку
                let _ = RemoveClipboardFormatListener(hwnd);
                hotkeys::unregister_panic_hotkey(hwnd);
                hotkeys::uninstall_paste_intent_hook();
                let _ = KillTimer(hwnd, TIMER_STATUS_CHECK);

                if let Ok(mut lock) = APP_STATE.lock() {
                    if let Some(state) = lock.take() {
                        remove_tray_icon(hwnd, state.tray_icon());
                    }
                }

                PostQuitMessage(0);
                LRESULT(0)
            }

            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }
}

/// Запуск фонового демона в трее Windows.
fn run_daemon(config: AppConfig) {
    println!("============================================================");
    println!("       GhostClip Shield (GCB) v0.1.0 - Запущен в трее        ");
    println!("============================================================");
    println!("- Конфигурация config.toml успешно загружена.");

    unsafe {
        let class_name = w!("GhostClipShieldCoreClass");
        let instance = HINSTANCE(std::ptr::null_mut());

        let wc = WNDCLASSW {
            lpfnWndProc: Some(window_proc),
            hInstance: instance,
            lpszClassName: class_name,
            ..Default::default()
        };
        let _ = RegisterClassW(&wc);

        // Создаем скрытое служебное окно для приема системных сообщений
        let hwnd_res = CreateWindowExW(
            windows::Win32::UI::WindowsAndMessaging::WINDOW_EX_STYLE(0),
            class_name,
            w!("GhostClipShieldCore"),
            WS_OVERLAPPEDWINDOW,
            0,
            0,
            0,
            0,
            HWND(std::ptr::null_mut()),
            windows::Win32::UI::WindowsAndMessaging::HMENU(std::ptr::null_mut()),
            instance,
            None,
        );

        let Ok(hwnd) = hwnd_res else {
            eprintln!("Не удалось создать главное служебное окно.");
            return;
        };

        // Создаем иконку в системном трее
        let tray_icon = init_tray_icon(hwnd, TrayState::Green);
        {
            let mut lock = APP_STATE.lock().unwrap();
            *lock = Some(AppState {
                config: config.clone(),
                tray_icon_raw: tray_icon.0 as usize,
                current_state: TrayState::Green,
            });
        }
        println!("- Иконка активна в системном трее (возле часов).");

        // Регистрируем слушатель системных изменений буфера
        let listener_res = AddClipboardFormatListener(hwnd);
        if listener_res.is_ok() {
            println!("- Слушатель буфера обмена (WM_CLIPBOARDUPDATE) подключен.");
        } else {
            eprintln!("Внимание: Не удалось подключить AddClipboardFormatListener.");
        }

        // Регистрируем PanicFlush хоткей (Ctrl+Shift+Alt+P)
        if hotkeys::register_panic_hotkey(hwnd) {
            println!("- Хоткей PanicFlush (Ctrl + Shift + Alt + P) активен.");
        }

        // Подключаем хук для распознавания намерения вставки (Intent-Aware Bypass)
        hotkeys::install_paste_intent_hook();
        println!("- Защита осознанной вставки (Ctrl + V зеленый коридор) активна.");

        // Таймер обновления состояния трея каждую секунду
        SetTimer(hwnd, TIMER_STATUS_CHECK, 1000, None);

        // Показываем стартовое уведомление в Windows
        ui::notify::show_notification(
            hwnd,
            "GhostClip Shield",
            "Защита буфера обмена успешно запущена и работает в трее.",
            false,
        );

        // Главный цикл обработки сообщений Windows
        let mut msg = MSG::default();
        while GetMessageW(&mut msg, HWND(std::ptr::null_mut()), 0, 0).as_bool() {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    }
}

/// Вывод текстовой справки по аргументам командной строки.
fn print_help() {
    println!("GhostClip Shield (GCB) — Защитник буфера обмена Windows\n");
    println!("Использование:");
    println!("  ghostclip                 Запустить интерактивное меню настройки (стрелочки)");
    println!("  ghostclip --daemon        Запустить защиту сразу в трее без меню (флаг: -d)");
    println!("  ghostclip --help          Показать эту справку (флаг: -h)\n");
    println!("Функции:");
    println!("  • CleanClip URLs          Очистка ссылок от UTM, fbclid, gclid трекеров");
    println!("  • CleanClip Zero-Width    Удаление невидимых скрытых символов слежки");
    println!("  • Secrets Detector        Поиск токенов API, JWT, криптокошельков и паролей");
    println!("  • Bank Card Check         Проверка номеров карт по алгоритму Луна");
    println!("  • Clipboard Firewall      Брандмауэр от фоновых программ-шпионов");
    println!("  • Intent-Aware Bypass     Зеленый коридор 500 мс при осознанном Ctrl+V");
    println!("  • PanicFlush              Экстренный сброс памяти по Ctrl+Shift+Alt+P");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut config = AppConfig::load_or_create("config.toml");

    // Прямой запуск демона по флагу --daemon или -d
    if args.iter().any(|a| a == "--daemon" || a == "--tray" || a == "-d") {
        run_daemon(config);
        return;
    }

    // Справка по флагу --help или -h
    if args.iter().any(|a| a == "--help" || a == "-h") {
        print_help();
        return;
    }

    // По умолчанию открываем интерактивный TUI-дашборд с переключением стрелочками
    match cli::run_interactive_menu(&mut config) {
        cli::CliAction::LaunchDaemon => {
            let _ = config.save("config.toml");
            println!("\n[GhostClip Shield] Настройки сохранены. Запуск защиты в трее Windows...");
            run_daemon(config);
        }
        cli::CliAction::SaveAndExit => {
            if let Ok(()) = config.save("config.toml") {
                println!("\n[GhostClip Shield] ✅ Настройки успешно сохранены в config.toml.");
            } else {
                eprintln!("\n[GhostClip Shield] ❌ Ошибка сохранения в config.toml.");
            }
        }
        cli::CliAction::ExitWithoutSaving => {
            println!("\n[GhostClip Shield] Выход без сохранения изменений.");
        }
    }
}
