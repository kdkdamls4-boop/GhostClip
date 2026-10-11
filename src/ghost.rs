use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::thread;
use std::time::Duration;

use crate::shredder;

/// Модуль GhostClip: таймер самоуничтожения секретов.
/// Когда пользователь копирует токен, пароль или номер карты,
/// запускается обратный отсчет. По истечении времени буфер гарантированно затирается.

static TIMER_ARMED: AtomicBool = AtomicBool::new(false);
static REMAINING_SECS: AtomicU64 = AtomicU64::new(0);
static CURRENT_EPOCH: AtomicU64 = AtomicU64::new(0);

/// Взводит таймер самоуничтожения на указанное количество секунд.
/// Если таймер уже тикал, он плавно перезапускается с новым временем.
pub fn arm_timer(seconds: u64, secret_desc: &'static str) {
    let new_epoch = CURRENT_EPOCH.fetch_add(1, Ordering::SeqCst) + 1;
    REMAINING_SECS.store(seconds, Ordering::SeqCst);
    TIMER_ARMED.store(true, Ordering::SeqCst);

    println!(
        "[GhostClip] ⏳ Обнаружен {}. Таймер самоуничтожения установлен на {} сек.",
        secret_desc, seconds
    );

    // Запускаем фоновый поток отсчета
    thread::spawn(move || {
        for _ in 0..seconds {
            thread::sleep(Duration::from_secs(1));

            // Если за это время таймер был отменен или перезапущен новым копированием
            if CURRENT_EPOCH.load(Ordering::SeqCst) != new_epoch || !TIMER_ARMED.load(Ordering::SeqCst) {
                return;
            }

            let left = REMAINING_SECS.fetch_sub(1, Ordering::SeqCst);
            if left <= 1 {
                break;
            }
        }

        // Проверяем актуальность эпохи перед затиркой
        if CURRENT_EPOCH.load(Ordering::SeqCst) == new_epoch && TIMER_ARMED.load(Ordering::SeqCst) {
            TIMER_ARMED.store(false, Ordering::SeqCst);
            REMAINING_SECS.store(0, Ordering::SeqCst);
            println!("[GhostClip] 💥 Время жизни секрета истекло! Затираем память...");
            shredder::wipe_all();
        }
    });
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
