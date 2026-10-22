use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Condvar, Mutex, OnceLock};
use std::thread;
use std::time::Duration;

use crate::shredder;

// Модуль GhostClip: таймер самоуничтожения секретов.
// Когда пользователь копирует токен, пароль или номер карты,
// запускается обратный отсчет. По истечении времени буфер гарантированно затирается.

static TIMER_ARMED: AtomicBool = AtomicBool::new(false);
static REMAINING_SECS: AtomicU64 = AtomicU64::new(0);
static CURRENT_EPOCH: AtomicU64 = AtomicU64::new(0);

struct TimerSignal {
    mutex: Mutex<bool>,
    cvar: Condvar,
}

static TIMER_SIGNAL: OnceLock<TimerSignal> = OnceLock::new();

fn signal() -> &'static TimerSignal {
    TIMER_SIGNAL.get_or_init(|| TimerSignal {
        mutex: Mutex::new(false),
        cvar: Condvar::new(),
    })
}

/// Гарантирует запуск ровно одного рабочего потока-таймера для всего жизненного цикла программы.
fn ensure_worker_started() {
    static STARTED: AtomicBool = AtomicBool::new(false);
    if STARTED
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_ok()
    {
        thread::spawn(|| {
            let sig = signal();
            loop {
                // Если таймер не взведён, ждём сигнала активации
                let mut lock = sig.mutex.lock().unwrap();
                while !TIMER_ARMED.load(Ordering::SeqCst) {
                    lock = sig.cvar.wait(lock).unwrap();
                }
                drop(lock);

                let epoch_at_start = CURRENT_EPOCH.load(Ordering::SeqCst);

                // Цикл отсчёта по секундам
                while TIMER_ARMED.load(Ordering::SeqCst)
                    && CURRENT_EPOCH.load(Ordering::SeqCst) == epoch_at_start
                {
                    thread::sleep(Duration::from_secs(1));

                    if !TIMER_ARMED.load(Ordering::SeqCst)
                        || CURRENT_EPOCH.load(Ordering::SeqCst) != epoch_at_start
                    {
                        break;
                    }

                    let current = REMAINING_SECS.load(Ordering::SeqCst);
                    if current <= 1 {
                        TIMER_ARMED.store(false, Ordering::SeqCst);
                        REMAINING_SECS.store(0, Ordering::SeqCst);
                        println!("[GhostClip] 💥 Время жизни секрета истекло! Затираем память...");
                        shredder::wipe_all();
                        break;
                    } else {
                        REMAINING_SECS.store(current - 1, Ordering::SeqCst);
                    }
                }
            }
        });
    }
}

/// Взводит таймер самоуничтожения на указанное количество секунд.
/// Если таймер уже тикал, он плавно перезапускается с новым временем без создания лишних потоков.
pub fn arm_timer(seconds: u64, secret_desc: &'static str) {
    CURRENT_EPOCH.fetch_add(1, Ordering::SeqCst);
    REMAINING_SECS.store(seconds, Ordering::SeqCst);
    TIMER_ARMED.store(true, Ordering::SeqCst);

    println!(
        "[GhostClip] ⏳ Обнаружен {}. Таймер самоуничтожения установлен на {} сек.",
        secret_desc, seconds
    );

    ensure_worker_started();
    let sig = signal();
    let mut lock = sig.mutex.lock().unwrap();
    *lock = true;
    sig.cvar.notify_one();
}

/// Отменяет текущий таймер самоуничтожения (например, если буфер был очищен вручную).
pub fn disarm_timer() {
    TIMER_ARMED.store(false, Ordering::SeqCst);
    REMAINING_SECS.store(0, Ordering::SeqCst);
    CURRENT_EPOCH.fetch_add(1, Ordering::SeqCst);
    println!("[GhostClip] Таймер самоуничтожения деактивирован.");
}

/// Проверяет, тикает ли сейчас таймер самоуничтожения.
pub fn is_armed() -> bool {
    TIMER_ARMED.load(Ordering::SeqCst)
}

/// Возвращает оставшееся количество секунд (если таймер активен).
pub fn remaining_seconds() -> Option<u64> {
    if is_armed() {
        Some(REMAINING_SECS.load(Ordering::SeqCst))
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_arm_and_disarm_timer() {
        arm_timer(60, "Тестовый токен");
        assert!(is_armed());
        assert_eq!(remaining_seconds(), Some(60));

        disarm_timer();
        assert!(!is_armed());
        assert_eq!(remaining_seconds(), None);
    }
}
