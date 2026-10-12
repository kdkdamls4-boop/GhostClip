use std::path::Path;
use windows::core::PWSTR;
use windows::Win32::Foundation::{CloseHandle, HWND};
use windows::Win32::System::DataExchange::GetOpenClipboardWindow;
use windows::Win32::System::Threading::{
    OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_FORMAT, PROCESS_QUERY_LIMITED_INFORMATION,
};
use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};

/// Информация о процессе, который обратился к буферу обмена.
#[derive(Debug, Clone)]
pub struct ProcessInfo {
    /// Идентификатор процесса в Windows (PID)
    pub pid: u32,
    /// Имя исполняемого файла (например, "discord.exe" или "chrome.exe")
    #[allow(dead_code)]
    pub exe_name: String,
    /// Полный путь к файлу на диске
    pub full_path: String,
}

/// Получает имя и путь к исполняемому файлу по его PID.
pub fn get_process_info_by_pid(pid: u32) -> Option<ProcessInfo> {
    if pid == 0 {
        return None;
    }

    unsafe {
        // Открываем процесс с минимально необходимыми правами на чтение имени (PROCESS_QUERY_LIMITED_INFORMATION)
        let handle_res = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid);
        let Ok(process_handle) = handle_res else {
            return None;
        };

        let mut buffer = [0u16; 1024];
        let mut size = buffer.len() as u32;

        // Запрашиваем полный путь к исполняемому файлу
        let success = QueryFullProcessImageNameW(
            process_handle,
            PROCESS_NAME_FORMAT(0),
            PWSTR(buffer.as_mut_ptr()),
            &mut size,
        );

        let _ = CloseHandle(process_handle);

        if success.is_ok() && size > 0 {
            let path_str = String::from_utf16_lossy(&buffer[..size as usize]);
            let exe_name = Path::new(&path_str)
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| path_str.clone());

            return Some(ProcessInfo {
                pid,
                exe_name,
                full_path: path_str,
            });
        }
    }

    None
}

/// Определяет, какое приложение прямо сейчас держит или только что открывало буфер обмена.
pub fn detect_clipboard_reader() -> Option<ProcessInfo> {
    unsafe {
        // 1. Сначала пробуем получить окно, которое держит буфер прямо в этот миг
        let mut target_hwnd = GetOpenClipboardWindow().unwrap_or(HWND(std::ptr::null_mut()));

        // 2. Если чужой процесс уже успел закрыть буфер за 1 мс, берем активное окно на переднем плане
        if target_hwnd.0.is_null() {
            target_hwnd = GetForegroundWindow();
        }

        if target_hwnd.0.is_null() {
            return None;
        }

        // Получаем PID процесса по дескриптору окна (HWND)
        let mut pid: u32 = 0;
        GetWindowThreadProcessId(target_hwnd, Some(&mut pid));

        get_process_info_by_pid(pid)
    }
}
