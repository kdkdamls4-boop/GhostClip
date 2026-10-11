use crossterm::{
    cursor::{Hide, MoveTo, Show},
    event::{self, Event, KeyCode, KeyEventKind},
    execute,
    style::{Color, Print, ResetColor, SetBackgroundColor, SetForegroundColor},
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use std::io::{stdout, Write};

use crate::config::AppConfig;

/// Действие, выбранное пользователем в интерактивном CLI.
#[derive(Debug, PartialEq, Eq)]
pub enum CliAction {
    /// Сохранить настройки и запустить защиту в трее
    LaunchDaemon,
    /// Сохранить в config.toml и выйти
    SaveAndExit,
    /// Выйти без сохранения
    ExitWithoutSaving,
}

/// RAII-страж терминала: гарантирует возврат стандартного режима консоли
/// даже при внезапном выходе или ошибке.
struct TerminalGuard;

impl TerminalGuard {
    fn new() -> Self {
        let _ = enable_raw_mode();
        let _ = execute!(stdout(), EnterAlternateScreen, Hide);
        Self
    }
}

impl Drop for TerminalGuard {
    fn drop(&mut self) {
        let _ = execute!(stdout(), Show, LeaveAlternateScreen);
        let _ = disable_raw_mode();
    }
}

/// Список доступных таймаутов жизни секрета в секундах
const TTL_PRESETS: &[u64] = &[15, 30, 45, 60, 120, 300];

/// Запускает интерактивный дашборд настройки в терминале с управлением стрелочками.
pub fn run_interactive_menu(cfg: &mut AppConfig) -> CliAction {
    let _guard = TerminalGuard::new();

    let mut selected_index = 0;
    let total_items = 12;

    loop {
        render_menu(cfg, selected_index);

        if let Ok(Event::Key(key_event)) = event::read() {
            if key_event.kind != KeyEventKind::Press {
                continue;
            }

            match key_event.code {
                KeyCode::Up | KeyCode::Char('k') => {
                    if selected_index == 0 {
                        selected_index = total_items - 1;
                    } else {
                        selected_index -= 1;
                    }
                }
                KeyCode::Down | KeyCode::Char('j') => {
                    if selected_index + 1 >= total_items {
                        selected_index = 0;
                    } else {
                        selected_index += 1;
                    }
                }
                KeyCode::Left | KeyCode::Char('h') => {
                    toggle_or_adjust(cfg, selected_index, false);
                }
                KeyCode::Right | KeyCode::Char('l') => {
                    toggle_or_adjust(cfg, selected_index, true);
                }
                KeyCode::Char(' ') => {
                    toggle_or_adjust(cfg, selected_index, true);
                }
                KeyCode::Enter => {
                    match selected_index {
                        9 => return CliAction::LaunchDaemon,
                        10 => return CliAction::SaveAndExit,
                        11 => return CliAction::ExitWithoutSaving,
                        _ => {
                            // На обычных пунктах Enter переключает значение
                            toggle_or_adjust(cfg, selected_index, true);
                        }
                    }
                }
                KeyCode::Esc | KeyCode::Char('q') => {
                    return CliAction::ExitWithoutSaving;
                }
                _ => {}
            }
        }
    }
}

fn toggle_or_adjust(cfg: &mut AppConfig, index: usize, forward: bool) {
    match index {
        0 => cfg.general.clean_urls = !cfg.general.clean_urls,
        1 => cfg.general.clean_zero_width = !cfg.general.clean_zero_width,
        2 => cfg.detector.check_api_keys = !cfg.detector.check_api_keys,
        3 => cfg.detector.check_credit_cards = !cfg.detector.check_credit_cards,
        4 => cfg.firewall.enabled = !cfg.firewall.enabled,
        5 => cfg.firewall.intent_aware_bypass = !cfg.firewall.intent_aware_bypass,
        6 => cfg.firewall.use_honeypot = !cfg.firewall.use_honeypot,
        7 => cfg.panic.lock_workstation = !cfg.panic.lock_workstation,
        8 => {
            // Изменение TTL секрета
            let current = cfg.general.secret_ttl_seconds;
            let current_pos = TTL_PRESETS.iter().position(|&t| t == current).unwrap_or(2);
            let next_pos = if forward {
                (current_pos + 1) % TTL_PRESETS.len()
            } else if current_pos == 0 {
                TTL_PRESETS.len() - 1
            } else {
                current_pos - 1
            };
            cfg.general.secret_ttl_seconds = TTL_PRESETS[next_pos];
        }
        _ => {}
    }
}

fn render_menu(cfg: &AppConfig, selected: usize) {
    let mut out = stdout();
    let _ = execute!(out, MoveTo(0, 0));

    // Заголовок
    println_colored(Color::Cyan, "╔══════════════════════════════════════════════════════════════════════════════╗");
    println_colored(Color::Cyan, "║              🛡️  GHOSTCLIP SHIELD (GCB) — ИНТЕРАКТИВНЫЙ ЦЕНТР УПРАВЛЕНИЯ     ║");
    println_colored(Color::Cyan, "╚══════════════════════════════════════════════════════════════════════════════╝");
    println_colored(
        Color::DarkGrey,
        "  [↑ / ↓] Навигация   [Пробел / ← / →] Вкл/Выкл   [Enter] Выбор   [Esc] Выход\n",
    );

    // Список модулей с их текущим статусом
    let items = [
        ("CleanClip URLs (Очистка ссылок)", cfg.general.clean_urls),
        ("CleanClip Zero-Width (Скрытые символы)", cfg.general.clean_zero_width),
        ("Детектор API-токенов и SSH-ключей", cfg.detector.check_api_keys),
        ("Проверка карт (Алгоритм Луна)", cfg.detector.check_credit_cards),
        ("Clipboard Firewall (Файрвол буфера)", cfg.firewall.enabled),
        ("Intent-Aware Auto-Pass (Коридор 500мс)", cfg.firewall.intent_aware_bypass),
        ("Honeypot Disinformation (Подмена фейком)", cfg.firewall.use_honeypot),
        ("Panic Lock Workstation (Win+L при сбросе)", cfg.panic.lock_workstation),
    ];

    for (i, (name, enabled)) in items.iter().enumerate() {
        render_toggle_row(i == selected, name, *enabled);
    }

    // Пункт 8: TTL таймер
    let ttl_text = format!("Время жизни секрета (TTL): [ {} сек ]", cfg.general.secret_ttl_seconds);
    render_custom_row(selected == 8, &ttl_text, Color::Yellow);

    println!();
    // Пункты действий 9, 10, 11
    render_action_row(selected == 9, "🚀  [ СОХРАНИТЬ И ЗАПУСТИТЬ ЗАЩИТУ В ТРЕЕ ]", Color::Green);
    render_action_row(selected == 10, "💾  [ Сохранить в config.toml и выйти ]", Color::White);
    render_action_row(selected == 11, "❌  [ Выйти без сохранения ]", Color::Red);

    println!("\n");
    // Информационный блок с описанием выбранной функции
    render_description_box(selected);

    let _ = out.flush();
}

fn render_toggle_row(is_selected: bool, label: &str, enabled: bool) {
    let prefix = if is_selected { " ▶ " } else { "   " };
    let status_str = if enabled { "[ ВКЛ  ]" } else { "[ ВЫКЛ ]" };
    let status_color = if enabled { Color::Green } else { Color::DarkGrey };

    if is_selected {
        let _ = execute!(
            stdout(),
            SetForegroundColor(Color::Black),
            SetBackgroundColor(Color::White),
            Print(format!("{} {:<45}", prefix, label)),
            ResetColor,
            Print(" "),
            SetForegroundColor(status_color),
            Print(format!("{}\n", status_str)),
            ResetColor
        );
    } else {
        let _ = execute!(
            stdout(),
            SetForegroundColor(Color::White),
            Print(format!("{} {:<45} ", prefix, label)),
            SetForegroundColor(status_color),
            Print(format!("{}\n", status_str)),
            ResetColor
        );
    }
}

fn render_custom_row(is_selected: bool, text: &str, color: Color) {
    let prefix = if is_selected { " ▶ " } else { "   " };
    if is_selected {
        let _ = execute!(
            stdout(),
            SetForegroundColor(Color::Black),
            SetBackgroundColor(Color::White),
            Print(format!("{} {:<55}\n", prefix, text)),
            ResetColor
        );
    } else {
        let _ = execute!(
            stdout(),
            SetForegroundColor(color),
            Print(format!("{} {:<55}\n", prefix, text)),
            ResetColor
        );
    }
}

fn render_action_row(is_selected: bool, text: &str, color: Color) {
    let prefix = if is_selected { " ▶ " } else { "   " };
    if is_selected {
        let _ = execute!(
            stdout(),
            SetForegroundColor(Color::Black),
            SetBackgroundColor(color),
            Print(format!("{} {:<55}\n", prefix, text)),
            ResetColor
        );
    } else {
        let _ = execute!(
            stdout(),
            SetForegroundColor(color),
            Print(format!("{} {:<55}\n", prefix, text)),
            ResetColor
        );
    }
}

fn render_description_box(selected: usize) {
    let desc: (&str, &[&str]) = match selected {
        0 => (
            "CleanClip URLs (Очистка ссылок)",
            &[
                "Мгновенно вырезает маркетинговые метки: utm_source, fbclid, gclid, si=, ref=.",
                "Ссылка становится короткой, чистой и приватной при каждом копировании.",
            ],
        ),
        1 => (
            "CleanClip Zero-Width (Невидимые символы)",
            &[
                "Удаляет невидимые Unicode-символы (Zero-Width Space, Joiner, BOM).",
                "Исключает скрытый трекинг источника утечек текста (водяные знаки стеганографии).",
            ],
        ),
        2 => (
            "Детектор API-токенов и SSH-ключей",
            &[
                "Распознает ключи OpenAI (sk-), GitHub (ghp_), AWS (AKIA), JWT и SSH приватные ключи.",
                "При обнаружении секрета автоматически включает таймер самоуничтожения.",
            ],
        ),
        3 => (
            "Проверка карт (Алгоритм Луна)",
            &[
                "Проверяет валидность номеров карт Visa, MasterCard, МИР математическим алгоритмом.",
                "Не срабатывает на обычные длинные числа, реагируя только на реальные реквизиты.",
            ],
        ),
        4 => (
            "Clipboard Firewall (Файрвол буфера)",
            &[
                "Перехватывает попытки фонового чтения буфера сторонними программами.",
                "Если софт читает буфер втихую — открывает всплывающий диалог с 5 опциями доступа.",
            ],
        ),
        5 => (
            "Intent-Aware Auto-Pass (Осознанная вставка)",
            &[
                "Если вы САМИ нажали Ctrl+V в активном окне — доступ дается мгновенно на 500 мс.",
                "Никаких раздражающих окон при обычной работе! Окна появляются только на шпионов.",
            ],
        ),
        6 => (
            "Honeypot Disinformation (Подмена фейком)",
            &[
                "При блокировке доступа возвращает безопасную пустышку вместо системной ошибки.",
                "Программы-шпионы думают, что буфер пуст, и не догадываются о блокировке.",
            ],
        ),
        7 => (
            "Panic Lock Workstation (Win+L)",
            &[
                "При нажатии тревожной комбинации Ctrl+Shift+Alt+P помимо затирки памяти буфера",
                "и истории Win+V также принудительно блокирует экран Windows (LockWorkStation).",
            ],
        ),
        8 => (
            "Время жизни секрета (Secret TTL)",
            &[
                "Интервал времени в секундах до гарантированного затирания секрета нулями.",
                "Используйте стрелочки [←] и [→] для выбора: 15, 30, 45, 60, 120 или 300 секунд.",
            ],
        ),
        9 => (
            "Запуск защиты в трее",
            &[
                "Сохраняет изменения в config.toml и запускает фоновый процесс в трее Windows.",
                "Иконка возле часов: 🟢 Зеленый = Спокойно, 🟡 Желтый = Таймер, 🔴 Красный = Блок.",
            ],
        ),
        10 => (
            "Сохранить и выйти",
            &[
                "Записывает выбранные настройки в файл config.toml и завершает работу CLI.",
            ],
        ),
        _ => (
            "Выход без сохранения",
            &[
                "Закрывает интерактивное меню, оставив файл config.toml без изменений.",
            ],
        ),
    };

    println_colored(Color::Cyan, "┌──────────────────────── СПРАВКА И ОПИСАНИЕ МОДУЛЯ ───────────────────────────┐");
    let title_line = format!("│  Функция: {:<67} │", desc.0);
    println_colored(Color::Yellow, &title_line);
    println_colored(Color::Cyan, "├──────────────────────────────────────────────────────────────────────────────┤");
    for line in desc.1 {
        let text_line = format!("│  {:<76} │", line);
        println_colored(Color::White, &text_line);
    }
    println_colored(Color::Cyan, "└──────────────────────────────────────────────────────────────────────────────┘");
}

fn println_colored(color: Color, text: &str) {
    let _ = execute!(
        stdout(),
        SetForegroundColor(color),
        Print(text),
        Print("\n"),
        ResetColor
    );
}
