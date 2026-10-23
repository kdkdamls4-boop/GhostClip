"""Иконка в системном трее: создание, всплывающие уведомления, удаление."""

import ctypes
from ctypes import wintypes

from .win32_api import user32, shell32, NOTIFYICONDATAW
from .win32_constants import (
    IDI_SHIELD, IDI_APPLICATION, WM_TRAYICON,
    NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIIF_INFO,
    NIM_ADD, NIM_MODIFY, NIM_DELETE,
)

TRAY_TOOLTIP = "GhostClip Shield — Защита буфера (ПКМ — меню)"


def load_shield_icon() -> int:
    """Загружает системную иконку щита (или стандартную, если щита нет)."""
    hicon = user32.LoadIconW(None, ctypes.cast(IDI_SHIELD, wintypes.LPCWSTR))
    if not hicon:
        hicon = user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))
    return hicon


def add_tray_icon(hwnd: int, hicon: int) -> NOTIFYICONDATAW:
    """Добавляет иконку в трей и возвращает её структуру NOTIFYICONDATAW."""
    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAYICON
    nid.hIcon = hicon
    nid.szTip = TRAY_TOOLTIP
    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
    return nid


def show_balloon(nid: NOTIFYICONDATAW, title: str, text: str) -> None:
    """Показывает всплывающее уведомление у иконки."""
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
    nid.szInfoTitle = title[:63]
    nid.szInfo = text[:255]
    nid.dwInfoFlags = NIIF_INFO
    shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))


def delete_tray_icon(nid: NOTIFYICONDATAW) -> None:
    """Убирает иконку из трея."""
    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
