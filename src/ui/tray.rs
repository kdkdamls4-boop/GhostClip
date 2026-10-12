use windows::core::PCWSTR;
use windows::Win32::Foundation::{HWND, POINT};
use windows::Win32::Graphics::Gdi::{CreateBitmap, DeleteObject};
use windows::Win32::UI::Shell::{
    Shell_NotifyIconW, NIF_ICON, NIF_MESSAGE, NIF_TIP, NIM_ADD, NIM_DELETE, NIM_MODIFY,
    NOTIFYICONDATAW,
};
use windows::Win32::UI::WindowsAndMessaging::{
    AppendMenuW, CreateIconIndirect, CreatePopupMenu, DestroyIcon, DestroyMenu, GetCursorPos,
    SetForegroundWindow, TrackPopupMenu, HICON, ICONINFO, MF_SEPARATOR, MF_STRING, TPM_RIGHTBUTTON,
};

/// Состояния иконки в системном трее Windows.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrayState {
    /// 🟢 Зеленый щит: Защита активна, угроз нет
    Green,
    /// 🟡 Желтый призрак: Тикает таймер самоуничтожения секрета
    Yellow,
    /// 🔴 Красный радар: Зафиксирована попытка неавторизованного доступа
    #[allow(dead_code)]
    Red,
}

pub const WM_TRAY_CALLBACK: u32 = windows::Win32::UI::WindowsAndMessaging::WM_USER + 101;
pub const ID_TRAY_PANIC: usize = 2001;
pub const ID_TRAY_OPEN_LOG: usize = 2002;
pub const ID_TRAY_EXIT: usize = 2003;

/// Генерирует в оперативной памяти круглую 16x16 иконку нужного цвета.
/// Это избавляет программу от внешних зависимостей и необходимости таскать за собой файлы .ico.
fn create_colored_icon(state: TrayState) -> HICON {
    let color: u32 = match state {
        TrayState::Green => 0x002ECC71,  // Приятный изумрудно-зеленый
        TrayState::Yellow => 0x00F1C40F, // Янтарно-желтый
        TrayState::Red => 0x00E74C3C,    // Тревожный красный
    };

    let mut pixels = [0u32; 16 * 16];
    let mut mask_bits = [0xFFu8; 16 * 2]; // 16 строк по 16 бит (2 байта на строку)

    for y in 0..16 {
        for x in 0..16 {
            let dx = x as f32 - 7.5;
            let dy = y as f32 - 7.5;
            let dist_sq = dx * dx + dy * dy;

            // Рисуем кружок радиусом 6.5 пикселей
            if dist_sq <= 42.0 {
                pixels[y * 16 + x] = color;
                // Сбрасываем бит в маске (0 = пиксель виден, 1 = прозрачный)
                let byte_idx = y * 2 + (x / 8);
                let bit_idx = 7 - (x % 8);
                mask_bits[byte_idx] &= !(1 << bit_idx);
            }
        }
    }

    unsafe {
        let color_bm = CreateBitmap(16, 16, 1, 32, Some(pixels.as_ptr() as *const _));
        let mask_bm = CreateBitmap(16, 16, 1, 1, Some(mask_bits.as_ptr() as *const _));

        let icon_info = ICONINFO {
            fIcon: true.into(),
            xHotspot: 0,
            yHotspot: 0,
            hbmMask: mask_bm,
            hbmColor: color_bm,
        };

        let hicon = CreateIconIndirect(&icon_info).unwrap_or(HICON(std::ptr::null_mut()));

        let _ = DeleteObject(color_bm);
        let _ = DeleteObject(mask_bm);

        hicon
    }
}

/// Инициализирует иконку в системном трее Windows.
pub fn init_tray_icon(hwnd: HWND, state: TrayState) -> HICON {
    let hicon = create_colored_icon(state);

    let mut nid = NOTIFYICONDATAW::default();
    nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
    nid.hWnd = hwnd;
    nid.uID = 1;
    nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    nid.uCallbackMessage = WM_TRAY_CALLBACK;
    nid.hIcon = hicon;

    let tip = match state {
        TrayState::Green => "GhostClip Shield: Активен (Все спокойно)",
        TrayState::Yellow => "GhostClip Shield: Тикает таймер секрета!",
        TrayState::Red => "GhostClip Shield: Попытка неавторизованного чтения!",
    };

    let tip_utf16: Vec<u16> = tip.encode_utf16().chain(std::iter::once(0)).collect();
    let max_tip = nid.szTip.len().min(tip_utf16.len());
    nid.szTip[..max_tip].copy_from_slice(&tip_utf16[..max_tip]);

    unsafe {
        let _ = Shell_NotifyIconW(NIM_ADD, &nid);
    }

    hicon
}

/// Динамически обновляет цвет иконки и всплывающую подсказку в трее.
pub fn update_tray_state(hwnd: HWND, old_icon: HICON, new_state: TrayState, tooltip_extra: Option<&str>) -> HICON {
    let new_icon = create_colored_icon(new_state);

    let mut nid = NOTIFYICONDATAW::default();
    nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
    nid.hWnd = hwnd;
    nid.uID = 1;
    nid.uFlags = NIF_ICON | NIF_TIP;
    nid.hIcon = new_icon;

    let tip = match (new_state, tooltip_extra) {
        (TrayState::Yellow, Some(extra)) => format!("GhostClip: {}", extra),
        (TrayState::Yellow, None) => "GhostClip: Уничтожение секрета...".to_string(),
        (TrayState::Red, Some(extra)) => format!("Внимание: {}", extra),
        (TrayState::Red, None) => "GhostClip: Перехвачен шпион!".to_string(),
        (TrayState::Green, _) => "GhostClip Shield: Защита активна".to_string(),
    };

    let tip_utf16: Vec<u16> = tip.encode_utf16().chain(std::iter::once(0)).collect();
    let max_tip = nid.szTip.len().min(tip_utf16.len());
    nid.szTip[..max_tip].copy_from_slice(&tip_utf16[..max_tip]);

    unsafe {
        let _ = Shell_NotifyIconW(NIM_MODIFY, &nid);
        if !old_icon.0.is_null() {
            let _ = DestroyIcon(old_icon);
        }
    }

    new_icon
}

/// Удаляет иконку из трея при закрытии приложения.
pub fn remove_tray_icon(hwnd: HWND, icon: HICON) {
    let mut nid = NOTIFYICONDATAW::default();
    nid.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
    nid.hWnd = hwnd;
    nid.uID = 1;

    unsafe {
        let _ = Shell_NotifyIconW(NIM_DELETE, &nid);
        if !icon.0.is_null() {
            let _ = DestroyIcon(icon);
        }
    }
}

/// Показывает контекстное меню при правом клике мыши по иконке в трее.
pub fn show_tray_menu(hwnd: HWND) {
    unsafe {
        let Ok(menu) = CreatePopupMenu() else { return };

        let panic_text: Vec<u16> = "Экстренно очистить буфер (PanicFlush)\0".encode_utf16().collect();
        let log_text: Vec<u16> = "Открыть лог доступа (clipboard_access.log)\0".encode_utf16().collect();
        let exit_text: Vec<u16> = "Выход из GhostClip Shield\0".encode_utf16().collect();

        let _ = AppendMenuW(menu, MF_STRING, ID_TRAY_PANIC, PCWSTR(panic_text.as_ptr()));
        let _ = AppendMenuW(menu, MF_STRING, ID_TRAY_OPEN_LOG, PCWSTR(log_text.as_ptr()));
        let _ = AppendMenuW(menu, MF_SEPARATOR, 0, PCWSTR(std::ptr::null()));
        let _ = AppendMenuW(menu, MF_STRING, ID_TRAY_EXIT, PCWSTR(exit_text.as_ptr()));

        let mut pt = POINT::default();
        let _ = GetCursorPos(&mut pt);

        let _ = SetForegroundWindow(hwnd);
        let _ = TrackPopupMenu(menu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, None);
        let _ = DestroyMenu(menu);
    }
}
