use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::System::Shutdown::LockWorkStation;
use windows::Win32::UI::Input::KeyboardAndMouse::{
    GetAsyncKeyState, RegisterHotKey, UnregisterHotKey, HOT_KEY_MODIFIERS, MOD_ALT, MOD_CONTROL,
    MOD_NOREPEAT, MOD_SHIFT, VK_CONTROL, VK_INSERT, VK_SHIFT,
};
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, GetForegroundWindow, GetWindowThreadProcessId, SetWindowsHookExW,
    UnhookWindowsHookEx, HHOOK, KBDLLHOOKSTRUCT, WH_KEYBOARD_LL, WM_KEYDOWN,
};

use crate::firewall;
use crate::shredder;

/// Уникальный идентификатор горячей клавиши PanicFlush в системе Windows.
pub const PANIC_HOTKEY_ID: i32 = 0x7001;

/// Глобальный дескриптор клавиатурного хука для отслеживания осознанной вставки (Ctrl+V).
static mut KEYBOARD_HOOK: HHOOK = HHOOK(std::ptr::null_mut());

/// Регистрирует глобальную тревожную комбинацию клавиш: Ctrl + Shift + Alt + P.
pub fn register_panic_hotkey(hwnd: HWND) -> bool {
    unsafe {
        // MOD_NOREPEAT предотвращает множественные вызовы при удержании клавиши
        let modifiers = HOT_KEY_MODIFIERS(MOD_CONTROL.0 | MOD_SHIFT.0 | MOD_ALT.0 | MOD_NOREPEAT.0);
        // Код клавиши 'P' = 0x50
        RegisterHotKey(hwnd, PANIC_HOTKEY_ID, modifiers, 0x50).is_ok()
    }
}

/// Снимает регистрацию горячей клавиши при закрытии программы.
pub fn unregister_panic_hotkey(hwnd: HWND) {
    unsafe {
        let _ = UnregisterHotKey(hwnd, PANIC_HOTKEY_ID);
    }
}

/// Выполняет экстренный сброс приватности (PanicFlush).
pub fn execute_panic_flush(lock_workstation: bool) {
    println!("[PanicFlush] Активирован экстренный сброс!");
    shredder::wipe_all();

    if lock_workstation {
        println!("[PanicFlush] Блокировка экрана...");
        unsafe {
            let _ = LockWorkStation();
        }
    }
}

/// Низкоуровневая процедура перехвата клавиатуры (WH_KEYBOARD_LL).
/// Реагирует исключительно на нажатие Ctrl+V или Shift+Insert,
/// чтобы активировать 500-миллисекундный «зеленый коридор» для активного окна.
unsafe extern "system" fn low_level_keyboard_proc(
    n_code: i32,
    w_param: WPARAM,
    l_param: LPARAM,
) -> LRESULT {
    unsafe {
        if n_code >= 0 && w_param.0 == WM_KEYDOWN as usize {
            let kbd_struct = *(l_param.0 as *const KBDLLHOOKSTRUCT);
            let vk_code = kbd_struct.vkCode as i32;

            // Проверяем: зажат ли Ctrl + нажата 'V' (0x56) ИЛИ зажат Shift + нажат Insert (VK_INSERT)
            let ctrl_down = (GetAsyncKeyState(VK_CONTROL.0 as i32) as u16 & 0x8000) != 0;
            let shift_down = (GetAsyncKeyState(VK_SHIFT.0 as i32) as u16 & 0x8000) != 0;

            let is_paste = (ctrl_down && vk_code == 0x56) || (shift_down && vk_code == VK_INSERT.0 as i32);

            if is_paste {
                // Пользователь прямо сейчас намеренно вставляет данные в активное окно
                let foreground_hwnd = GetForegroundWindow();
                if !foreground_hwnd.0.is_null() {
                    let mut pid: u32 = 0;
                    GetWindowThreadProcessId(foreground_hwnd, Some(&mut pid));
                    if pid > 0 {
                        firewall::record_user_paste_intent(pid);
                    }
                }
            }
        }

        CallNextHookEx(KEYBOARD_HOOK, n_code, w_param, l_param)
    }
}

/// Запускает легковесный клавиатурный хук для распознавания намерения вставки (Intent-Aware).
pub fn install_paste_intent_hook() {
    unsafe {
        if KEYBOARD_HOOK.0.is_null() {
            let hook = SetWindowsHookExW(
                WH_KEYBOARD_LL,
                Some(low_level_keyboard_proc),
                windows::Win32::Foundation::HMODULE(std::ptr::null_mut()),
                0,
            );
            if let Ok(h) = hook {
                KEYBOARD_HOOK = h;
            }
        }
    }
}

/// Снимает клавиатурный хук при выходе из программы.
pub fn uninstall_paste_intent_hook() {
    unsafe {
        if !KEYBOARD_HOOK.0.is_null() {
            let _ = UnhookWindowsHookEx(KEYBOARD_HOOK);
            KEYBOARD_HOOK = HHOOK(std::ptr::null_mut());
        }
    }
}
