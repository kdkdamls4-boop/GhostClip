"""Числовые константы Win32 API, которые используются для окна, меню и иконки в трее."""

# Сообщения окну (WM_ = Window Message)
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20  # Своё сообщение: событие от иконки в трее

WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

# Действия с иконкой в трее (NIM_ = Notify Icon Message)
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

# Какие поля NOTIFYICONDATAW заполнены (NIF_ = Notify Icon Flags)
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIIF_INFO = 0x00000001

# Встроенные иконки Windows
IDI_SHIELD = 32518
IDI_APPLICATION = 32512

# Флаги пунктов меню
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000
MF_BYCOMMAND = 0x00000000

# Флаги всплывающего меню
TPM_LEFTALIGN = 0x0000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

# Показ окна
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9

# Системная команда «Закрыть» (кнопка [X])
SC_CLOSE = 0xF060
