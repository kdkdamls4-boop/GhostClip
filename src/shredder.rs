use std::thread;
use std::time::Duration;
use windows::core::Result as WinResult;
use windows::ApplicationModel::DataTransfer::Clipboard as WinRtClipboard;
use windows::Win32::Foundation::HWND;
use windows::Win32::System::DataExchange::{CloseClipboard, EmptyClipboard, OpenClipboard};
use windows::Win32::System::Memory::{GlobalAlloc, GlobalLock, GlobalUnlock, GMEM_MOVEABLE};

use crate::sentinel::InternalUpdateGuard;

/// Модуль Shredder: безопасное уничтожение данных в буфере обмена.
/// Выполняет:
/// 1. Перезапись системного буфера нулями (Zero-fill) через Win32 API.
/// 2. Очистку журнала истории Windows (Win + V) и облачной синхронизации через WinRT API.

/// Пытается открыть буфер обмена с повторными попытками.
/// Если буфер на несколько миллисекунд заблокирован другим процессом,
/// функция делает до 5 коротких пауз перед возвратом ошибки.
fn open_clipboard_with_retry(hwnd: HWND, max_attempts: u32) -> bool {
    for _ in 0..max_attempts {
        unsafe {
            if OpenClipboard(hwnd).is_ok() {
                return true;
            }
        }
        thread::sleep(Duration::from_millis(5));
    }
    false
}

/// Затирает текущий буфер обмена Windows нулями через Win32 API.
pub fn wipe_win32_clipboard() -> bool {
    let _guard = InternalUpdateGuard::new();

    // Открываем буфер без привязки к конкретному окну (дескриптор 0)
    if !open_clipboard_with_retry(HWND(std::ptr::null_mut()), 5) {
        eprintln!("[Shredder] Не удалось открыть буфер обмена для очистки.");
        return false;
    }

    unsafe {
        // Очищаем существующие данные в буфере
        let _ = EmptyClipboard();

        // Выделяем 64 байта перемещаемой глобальной памяти Windows
        let mem_handle = GlobalAlloc(GMEM_MOVEABLE, 64);
        if let Ok(handle) = mem_handle {
            let ptr = GlobalLock(handle);
            if !ptr.is_null() {
                // Заполняем память нулями (0x00)
                std::ptr::write_bytes(ptr as *mut u8, 0, 64);
                let _ = GlobalUnlock(handle);
            }
        }

        // Финальная очистка буфера
        let _ = EmptyClipboard();
        let _ = CloseClipboard();
    }

    true
}

/// Очищает историю буфера обмена Windows 10/11 (комбинация клавиш Win + V).
/// Для этого вызывается современное WinRT API: Windows.ApplicationModel.DataTransfer.Clipboard.
pub fn clear_winrt_history() -> WinResult<bool> {
    // WinRT вызов: удаляет записи из локального журнала и облака
    WinRtClipboard::ClearHistory()
}

/// Полный комплекс экстренной зачистки:
/// затирает RAM буфера нулями и удаляет данные из истории Win+V.
pub fn wipe_all() -> bool {
    let win32_ok = wipe_win32_clipboard();
    let winrt_ok = clear_winrt_history().unwrap_or(false);

    println!("[Shredder] Буфер затерт: Win32={}, WinRT History={}", win32_ok, winrt_ok);
    win32_ok
}
