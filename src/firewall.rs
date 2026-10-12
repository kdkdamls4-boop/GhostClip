#![allow(dead_code)]

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::config::FirewallConfig;

/// Решение файрвола буфера обмена для запрашивающего приложения.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AccessDecision {
    /// Доступ разрешен (белый список, активная временная сессия или осознанная вставка)
    Allow,
    /// Доступ заблокирован (черный список или ручной отказ пользователя).
    /// Возвращается строка для подстановки (пустышка/honeypot)
    DenyHoneypot(&'static str),
    /// Необходимо показать диалоговое окно пользователю с 5 вариантами выбора
    AskUser,
}

/// Выбор пользователя в интерактивном диалоге.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum UserChoice {
    /// 1. Разрешить всегда (добавить в config.toml whitelist)
    AlwaysAllow,
    /// 2. Разрешить на 15 минут
    AllowFor15Min,
    /// 3. Разрешить однократно
    AllowOnce,
    /// 4. Отказать однократно
    DenyOnce,
    /// 5. Отказывать всегда (добавить в config.toml blacklist)
    AlwaysDeny,
}

/// Внутреннее состояние файрвола, хранящее временные разрешения и метки осознанного нажатия Ctrl+V.
pub struct FirewallState {
    /// Программы с временным разрешением: имя процесса -> время истечения
    timed_allowances: HashMap<String, Instant>,
    /// Метки намеренного нажатия вставки пользователем: PID -> время нажатия клавиши Ctrl+V
    user_paste_intents: HashMap<u32, Instant>,
}

static STATE: Mutex<Option<FirewallState>> = Mutex::new(None);

fn with_state<F, R>(f: F) -> R
where
    F: FnOnce(&mut FirewallState) -> R,
{
    let mut lock = STATE.lock().unwrap();
    if lock.is_none() {
        *lock = Some(FirewallState {
            timed_allowances: HashMap::new(),
            user_paste_intents: HashMap::new(),
        });
    }
    f(lock.as_mut().unwrap())
}

/// Фиксирует, что пользователь нажал Ctrl+V в окне процесса с указанным PID.
/// Это активирует «зеленый коридор» (Intent-Aware Bypass) на 500 миллисекунд.
pub fn record_user_paste_intent(pid: u32) {
    with_state(|state| {
        state.user_paste_intents.insert(pid, Instant::now());
    });
}

/// Проверяет, была ли нажата комбинация вставки пользователем в течение последних 500 мс.
pub fn has_recent_user_intent(pid: u32) -> bool {
    with_state(|state| {
        if let Some(&timestamp) = state.user_paste_intents.get(&pid) {
            // Зеленый коридор действует 500 мс с момента нажатия
            if timestamp.elapsed() <= Duration::from_millis(500) {
                return true;
            } else {
                state.user_paste_intents.remove(&pid);
            }
        }
        false
    })
}

/// Сохраняет временное разрешение для процесса на указанный интервал.
pub fn grant_timed_access(process_name: &str, duration: Duration) {
    let lower_name = process_name.to_lowercase();
    with_state(|state| {
        state.timed_allowances.insert(lower_name, Instant::now() + duration);
    });
}

/// Проверяет, действует ли еще временное разрешение для процесса.
pub fn has_active_timed_access(process_name: &str) -> bool {
    let lower_name = process_name.to_lowercase();
    with_state(|state| {
        if let Some(&expires_at) = state.timed_allowances.get(&lower_name) {
            if Instant::now() < expires_at {
                return true;
            } else {
                state.timed_allowances.remove(&lower_name);
            }
        }
        false
    })
}

/// Главная функция проверки доступа приложения к буферу обмена.
pub fn evaluate_access(process_name: &str, pid: u32, config: &FirewallConfig) -> AccessDecision {
    if !config.enabled {
        return AccessDecision::Allow;
    }

    let lower_name = process_name.to_lowercase();

    // 1. Проверка черного списка
    if config.blacklist.iter().any(|b| b.to_lowercase() == lower_name) {
        return AccessDecision::DenyHoneypot(if config.use_honeypot { "" } else { "" });
    }

    // 2. Intent-Aware Auto-Pass: если пользователь сам нажал вставку
    if config.intent_aware_bypass && has_recent_user_intent(pid) {
        return AccessDecision::Allow;
    }

    // 3. Проверка белого списка из config.toml
    if config.whitelist.iter().any(|w| w.to_lowercase() == lower_name) {
        return AccessDecision::Allow;
    }

    // 4. Проверка временного разрешения (например, на 15 мин)
    if has_active_timed_access(&lower_name) {
        return AccessDecision::Allow;
    }

    // 5. Если ни одно правило не сработало — запрашиваем подтверждение у пользователя
    AccessDecision::AskUser
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_whitelist_allows() {
        let mut cfg = FirewallConfig::default();
        cfg.whitelist.push("safeapp.exe".to_string());

        let decision = evaluate_access("SafeApp.exe", 1234, &cfg);
        assert_eq!(decision, AccessDecision::Allow);
    }

    #[test]
    fn test_blacklist_denies() {
        let mut cfg = FirewallConfig::default();
        cfg.blacklist.push("malware.exe".to_string());

        let decision = evaluate_access("malware.exe", 9999, &cfg);
        assert_eq!(decision, AccessDecision::DenyHoneypot(""));
    }

    #[test]
    fn test_intent_aware_bypass() {
        let cfg = FirewallConfig::default();
        let pid = 5555;

        // До нажатия Ctrl+V — должен спросить
        assert_eq!(evaluate_access("unknown.exe", pid, &cfg), AccessDecision::AskUser);

        // Пользователь нажал Ctrl+V в этом окне
        record_user_paste_intent(pid);

        // В течение 500 мс — разрешено сразу
        assert_eq!(evaluate_access("unknown.exe", pid, &cfg), AccessDecision::Allow);
    }

    #[test]
    fn test_timed_access() {
        let cfg = FirewallConfig::default();
        let app = "browser.exe";

        grant_timed_access(app, Duration::from_secs(60));
        assert!(has_active_timed_access(app));
        assert_eq!(evaluate_access(app, 7777, &cfg), AccessDecision::Allow);
    }
}
