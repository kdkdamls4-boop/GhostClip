use windows::Win32::Foundation::HWND;
use windows::Win32::UI::Shell::{
    NIF_INFO, NIIF_INFO, NIIF_WARNING, NIM_MODIFY, NOTIFYICONDATAW, Shell_NotifyIconW,
};

/// Отображает нативное системное всплывающее уведомление Windows (Toast / Balloon notification).
pub fn show_notification(hwnd: HWND, title: &str, message: &str, is_warning: bool) {
    let flag = if is_warning { NIIF_WARNING } else { NIIF_INFO };
    let mut nid = NOTIFYICONDATAW {
        cbSize: std::mem::size_of::<NOTIFYICONDATAW>() as u32,
        hWnd: hwnd,
        uID: 1,
        uFlags: NIF_INFO,
        dwInfoFlags: flag,
        ..Default::default()
    };

    // Копируем заголовок в UTF-16 буфер (макс 64 символа)
    let title_utf16: Vec<u16> = title.encode_utf16().chain(std::iter::once(0)).collect();
    let max_title = nid.szInfoTitle.len().min(title_utf16.len());
    nid.szInfoTitle[..max_title].copy_from_slice(&title_utf16[..max_title]);

    // Копируем текст сообщения в UTF-16 буфер (макс 256 символов)
    let msg_utf16: Vec<u16> = message.encode_utf16().chain(std::iter::once(0)).collect();
    let max_msg = nid.szInfo.len().min(msg_utf16.len());
    nid.szInfo[..max_msg].copy_from_slice(&msg_utf16[..max_msg]);

    unsafe {
        let _ = Shell_NotifyIconW(NIM_MODIFY, &nid);
    }
}
