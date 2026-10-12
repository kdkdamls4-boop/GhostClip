#![allow(dead_code)]

use std::sync::atomic::{AtomicI32, Ordering};
use windows::core::{w, PCWSTR};
use windows::Win32::Foundation::{COLORREF, HINSTANCE, HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::Graphics::Gdi::CreateSolidBrush;
use windows::Win32::UI::Input::KeyboardAndMouse::VK_ESCAPE;
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetMessageW,
    KillTimer, PostQuitMessage, RegisterClassW, SetForegroundWindow, SetTimer,
    SetWindowTextW, ShowWindow, TranslateMessage, BS_DEFPUSHBUTTON, BS_PUSHBUTTON, CW_USEDEFAULT,
    MSG, SW_SHOW, WM_COMMAND, WM_CREATE, WM_DESTROY, WM_KEYDOWN, WM_TIMER,
    WNDCLASSW, WS_CAPTION, WS_CHILD, WS_EX_TOPMOST, WS_POPUP, WS_SYSMENU, WS_VISIBLE,
};

use crate::firewall::UserChoice;

const ID_BTN_ALWAYS_ALLOW: usize = 3001;
const ID_BTN_ALLOW_15MIN: usize = 3002;
const ID_BTN_ALLOW_ONCE: usize = 3003;
const ID_BTN_DENY_ONCE: usize = 3004;
const ID_BTN_ALWAYS_DENY: usize = 3005;
const TIMER_ID: usize = 4001;

static DIALOG_CHOICE: AtomicI32 = AtomicI32::new(0);
static REMAINING_SECS: AtomicI32 = AtomicI32::new(7);

/// Оконная процедура для диалога файрвола буфера обмена.
unsafe extern "system" fn dialog_wnd_proc(
    hwnd: HWND,
    msg: u32,
    wparam: WPARAM,
    lparam: LPARAM,
) -> LRESULT {
    unsafe {
        match msg {
            WM_CREATE => {
                // Запускаем секундный таймер на 7 секунд обратного отсчета
                SetTimer(hwnd, TIMER_ID, 1000, None);
                LRESULT(0)
            }
            WM_TIMER => {
                let left = REMAINING_SECS.fetch_sub(1, Ordering::SeqCst) - 1;
                if left <= 0 {
                    // Время вышло: автоматически выбираем отказ и закрываем окно
                    DIALOG_CHOICE.store(4, Ordering::SeqCst);
                    let _ = KillTimer(hwnd, TIMER_ID);
                    let _ = DestroyWindow(hwnd);
                } else {
                    let title = format!("GhostClip Firewall (Авто-отказ через {} сек)\0", left);
                    let title_utf16: Vec<u16> = title.encode_utf16().collect();
                    let _ = SetWindowTextW(hwnd, PCWSTR(title_utf16.as_ptr()));
                }
                LRESULT(0)
            }
            WM_COMMAND => {
                let btn_id = (wparam.0 & 0xFFFF) as usize;
                let choice_val = match btn_id {
                    ID_BTN_ALWAYS_ALLOW => 1,
                    ID_BTN_ALLOW_15MIN => 2,
                    ID_BTN_ALLOW_ONCE => 3,
                    ID_BTN_DENY_ONCE => 4,
                    ID_BTN_ALWAYS_DENY => 5,
                    _ => 0,
                };

                if choice_val > 0 {
                    DIALOG_CHOICE.store(choice_val, Ordering::SeqCst);
                    let _ = KillTimer(hwnd, TIMER_ID);
                    let _ = DestroyWindow(hwnd);
                }
                LRESULT(0)
            }
            WM_KEYDOWN => {
                // Если нажат Escape — считаем как однократный отказ
                if wparam.0 == VK_ESCAPE.0 as usize {
                    DIALOG_CHOICE.store(4, Ordering::SeqCst);
                    let _ = KillTimer(hwnd, TIMER_ID);
                    let _ = DestroyWindow(hwnd);
                }
                LRESULT(0)
            }
            WM_DESTROY => {
                let _ = KillTimer(hwnd, TIMER_ID);
                PostQuitMessage(0);
                LRESULT(0)
            }
            _ => DefWindowProcW(hwnd, msg, wparam, lparam),
        }
    }
}

/// Показывает компактное диалоговое окно безопасности поверх всех окон (TOPMOST)
/// с 5 вариантами решения и 7-секундным таймером обратного отсчета.
pub fn prompt_firewall_decision(app_name: &str, pid: u32, timeout_secs: u32) -> UserChoice {
    DIALOG_CHOICE.store(0, Ordering::SeqCst);
    REMAINING_SECS.store(timeout_secs as i32, Ordering::SeqCst);

    let class_name = w!("GhostClipFirewallDlg");
    let instance = HINSTANCE(std::ptr::null_mut());

    unsafe {
        let wc = WNDCLASSW {
            lpfnWndProc: Some(dialog_wnd_proc),
            hInstance: instance,
            lpszClassName: class_name,
            hbrBackground: CreateSolidBrush(COLORREF(0x00F5F5F5)),
            ..Default::default()
        };
        let _ = RegisterClassW(&wc);

        let title = format!("GhostClip Firewall (Авто-отказ через {} сек)\0", timeout_secs);
        let title_utf16: Vec<u16> = title.encode_utf16().collect();

        // Создаем компактное окно по центру (440 x 320 пикселей)
        let hwnd = CreateWindowExW(
            WS_EX_TOPMOST,
            class_name,
            PCWSTR(title_utf16.as_ptr()),
            WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_VISIBLE,
            CW_USEDEFAULT,
            CW_USEDEFAULT,
            440,
            320,
            HWND(std::ptr::null_mut()),
            windows::Win32::UI::WindowsAndMessaging::HMENU(std::ptr::null_mut()),
            instance,
            None,
        );

        let Ok(dialog_hwnd) = hwnd else {
            return UserChoice::DenyOnce;
        };

        // Текст сообщения
        let msg_text = format!(
            "Внимание! Приложение пытается прочитать буфер обмена:\n\n  • Имя программы: {}\n  • Идентификатор (PID): {}\n\nВыберите действие:",
            app_name, pid
        );
        let msg_utf16: Vec<u16> = msg_text.encode_utf16().chain(std::iter::once(0)).collect();

        let _ = CreateWindowExW(
            windows::Win32::UI::WindowsAndMessaging::WINDOW_EX_STYLE(0),
            w!("STATIC"),
            PCWSTR(msg_utf16.as_ptr()),
            WS_CHILD | WS_VISIBLE,
            20,
            15,
            400,
            85,
            dialog_hwnd,
            windows::Win32::UI::WindowsAndMessaging::HMENU(std::ptr::null_mut()),
            instance,
            None,
        );

        // 5 Кнопок с понятными надписями
        let buttons = [
            (ID_BTN_ALWAYS_ALLOW, "1. Разрешить всегда (в белый список)", 110),
            (ID_BTN_ALLOW_15MIN, "2. Разрешить на 15 минут", 145),
            (ID_BTN_ALLOW_ONCE, "3. Разрешить на один раз", 180),
            (ID_BTN_DENY_ONCE, "4. Отказать (вернуть пустоту)", 215),
            (ID_BTN_ALWAYS_DENY, "5. Отказывать всегда (в черный список)", 250),
        ];

        for (id, text, y) in buttons {
            let btn_utf16: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
            let btn_flag = if id == ID_BTN_DENY_ONCE { BS_DEFPUSHBUTTON } else { BS_PUSHBUTTON };
            let style = WS_CHILD | WS_VISIBLE | windows::Win32::UI::WindowsAndMessaging::WINDOW_STYLE(btn_flag as u32);
            let _ = CreateWindowExW(
                windows::Win32::UI::WindowsAndMessaging::WINDOW_EX_STYLE(0),
                w!("BUTTON"),
                PCWSTR(btn_utf16.as_ptr()),
                style,
                20,
                y,
                390,
                28,
                dialog_hwnd,
                windows::Win32::UI::WindowsAndMessaging::HMENU(id as *mut _),
                instance,
                None,
            );
        }

        let _ = ShowWindow(dialog_hwnd, SW_SHOW);
        let _ = SetForegroundWindow(dialog_hwnd);

        // Вложенный цикл обработки сообщений для модального поведения
        let mut msg = MSG::default();
        while GetMessageW(&mut msg, HWND(std::ptr::null_mut()), 0, 0).as_bool() {
            let _ = TranslateMessage(&msg);
            DispatchMessageW(&msg);
            if DIALOG_CHOICE.load(Ordering::SeqCst) != 0 {
                break;
            }
        }

        let choice_code = DIALOG_CHOICE.load(Ordering::SeqCst);
        match choice_code {
            1 => UserChoice::AlwaysAllow,
            2 => UserChoice::AllowFor15Min,
            3 => UserChoice::AllowOnce,
            5 => UserChoice::AlwaysDeny,
            _ => UserChoice::DenyOnce,
        }
    }
}
