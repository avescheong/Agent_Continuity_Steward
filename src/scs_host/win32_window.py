"""Windows native window utilities via PyWin32 and ctypes."""

import sys
import time
import ctypes
from ctypes import wintypes
from typing import Optional

try:
    import win32gui
    import win32con
    import win32clipboard
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False


# Window Geometry Constraints (430px Companion Form Factor)
MIN_WINDOW_WIDTH = 430
MIN_WINDOW_HEIGHT_COMPACT = 220
MIN_WINDOW_HEIGHT_DRAWER = 620
DEFAULT_WINDOW_WIDTH = 430
DEFAULT_WINDOW_HEIGHT = 680
COMPACT_WINDOW_HEIGHT = 220


def set_dpi_awareness() -> None:
    """Enables per-monitor DPI awareness to prevent Windows bitmap scaling and coordinate clipping."""
    if sys.platform != "win32":
        return
    try:
        # Per-monitor V2 awareness (Windows 10 1703+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def apply_dark_titlebar(hwnd: int) -> None:
    """Enables Windows 10/11 immersive dark mode on window titlebar."""
    if sys.platform != "win32":
        return
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        val = ctypes.c_int(1)
        set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def make_window_topmost(hwnd: int, topmost: bool = True) -> None:
    """Pins or unpins window to always-on-top."""
    if not PYWIN32_AVAILABLE:
        return
    try:
        flag = win32con.HWND_TOPMOST if topmost else win32con.HWND_NOTOPMOST
        win32gui.SetWindowPos(
            hwnd, flag, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
        )
    except Exception:
        pass


def set_window_opacity(hwnd: int, alpha: float) -> None:
    """Sets window opacity (0.1 to 1.0)."""
    if not PYWIN32_AVAILABLE:
        return
    try:
        alpha_byte = int(max(0.1, min(1.0, alpha)) * 255)
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style | win32con.WS_EX_LAYERED)
        win32gui.SetLayeredWindowAttributes(hwnd, 0, alpha_byte, win32con.LWA_ALPHA)
    except Exception:
        pass


def set_tool_window(hwnd: int, is_tool: bool = True) -> None:
    """Hides/shows window from Alt+Tab task switcher using WS_EX_TOOLWINDOW."""
    if not PYWIN32_AVAILABLE:
        return
    try:
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if is_tool:
            ex_style = (ex_style | win32con.WS_EX_TOOLWINDOW) & ~win32con.WS_EX_APPWINDOW
        else:
            ex_style = (ex_style | win32con.WS_EX_APPWINDOW) & ~win32con.WS_EX_TOOLWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
    except Exception:
        pass


def ensure_safe_window_geometry(
    hwnd: int,
    default_width: int = DEFAULT_WINDOW_WIDTH,
    default_height: int = DEFAULT_WINDOW_HEIGHT,
    min_width: int = MIN_WINDOW_WIDTH,
    min_height: int = MIN_WINDOW_HEIGHT_COMPACT,
) -> None:
    """Enforces minimum window constraints and positions safely on the monitor."""
    if not PYWIN32_AVAILABLE and sys.platform != "win32":
        return
    try:
        if PYWIN32_AVAILABLE:
            rect = win32gui.GetWindowRect(hwnd)
            curr_x, curr_y = rect[0], rect[1]
            curr_w = rect[2] - rect[0]
            curr_h = rect[3] - rect[1]
        else:
            r = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            curr_x, curr_y = r.left, r.top
            curr_w = r.right - r.left
            curr_h = r.bottom - r.top

        target_w = max(curr_w, default_width, min_width)
        target_h = max(curr_h, default_height, min_height)

        user32 = ctypes.windll.user32
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)

        target_x = max(0, min(curr_x, screen_w - target_w))
        target_y = max(0, min(curr_y, screen_h - target_h))

        if PYWIN32_AVAILABLE:
            win32gui.SetWindowPos(
                hwnd, 0, target_x, target_y, target_w, target_h,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
        else:
            user32.SetWindowPos(
                hwnd, 0, target_x, target_y, target_w, target_h,
                0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
            )
    except Exception:
        pass


def resize_window(
    hwnd: int,
    width: int,
    height: int,
    min_width: int = MIN_WINDOW_WIDTH,
    min_height: int = MIN_WINDOW_HEIGHT_COMPACT,
    preserve_width: bool = False,
) -> None:
    """Resizes window while enforcing minimum constraints and preserving position and width if requested."""
    curr_w = width
    if preserve_width:
        if PYWIN32_AVAILABLE:
            try:
                rect = win32gui.GetWindowRect(hwnd)
                curr_w = max(rect[2] - rect[0], min_width)
            except Exception:
                pass
        elif sys.platform == "win32":
            try:
                r = wintypes.RECT()
                if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
                    curr_w = max(r.right - r.left, min_width)
            except Exception:
                pass

    safe_w = max(curr_w, min_width)
    safe_h = max(height, min_height)
    if PYWIN32_AVAILABLE:
        try:
            rect = win32gui.GetWindowRect(hwnd)
            win32gui.SetWindowPos(
                hwnd, 0, rect[0], rect[1], safe_w, safe_h,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
            return
        except Exception:
            pass
    if sys.platform == "win32":
        try:
            r = wintypes.RECT()
            user32 = ctypes.windll.user32
            if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                user32.SetWindowPos(
                    hwnd, 0, r.left, r.top, safe_w, safe_h,
                    0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
                )
        except Exception:
            pass


def _get_clipboard_ctypes() -> str:
    """Fallback clipboard read via ctypes user32 with retry and cleanup."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    for attempt in range(5):
        if user32.OpenClipboard(None):
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if handle:
                    ptr = kernel32.GlobalLock(handle)
                    if ptr:
                        try:
                            val = ctypes.c_wchar_p(ptr).value
                            return str(val or "")
                        finally:
                            kernel32.GlobalUnlock(handle)
                return ""
            finally:
                user32.CloseClipboard()
        if attempt < 4:
            time.sleep(0.04)
    return ""


def _set_clipboard_ctypes(text: str) -> bool:
    """Fallback clipboard write via ctypes user32 with retry and cleanup."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    data = (text + "\x00").encode("utf-16le")
    for attempt in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if h_mem:
                    ptr = kernel32.GlobalLock(h_mem)
                    if ptr:
                        ctypes.memmove(ptr, data, len(data))
                        kernel32.GlobalUnlock(h_mem)
                        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                        return True
                return False
            finally:
                user32.CloseClipboard()
        if attempt < 4:
            time.sleep(0.04)
    return False


def set_clipboard_text(text: str) -> bool:
    """Writes text to native Windows clipboard with retry loop and guaranteed CloseClipboard."""
    if PYWIN32_AVAILABLE:
        for attempt in range(5):
            opened = False
            try:
                win32clipboard.OpenClipboard()
                opened = True
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                return True
            except Exception:
                if attempt < 4:
                    time.sleep(0.04)
            finally:
                if opened:
                    try:
                        win32clipboard.CloseClipboard()
                    except Exception:
                        pass
    if sys.platform == "win32":
        return _set_clipboard_ctypes(text)
    return False


def get_clipboard_text() -> str:
    """Reads text from native Windows clipboard with retry loop and guaranteed CloseClipboard."""
    if PYWIN32_AVAILABLE:
        for attempt in range(5):
            opened = False
            try:
                win32clipboard.OpenClipboard()
                opened = True
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                else:
                    data = ""
                return str(data or "")
            except Exception:
                if attempt < 4:
                    time.sleep(0.04)
            finally:
                if opened:
                    try:
                        win32clipboard.CloseClipboard()
                    except Exception:
                        pass
    if sys.platform == "win32":
        return _get_clipboard_ctypes()
    return ""


class _BROWSEINFOW(ctypes.Structure):
    _fields_ = [
        ("hwndOwner", wintypes.HWND),
        ("pidlRoot", wintypes.LPCVOID),
        ("pszDisplayName", wintypes.LPWSTR),
        ("lpszTitle", wintypes.LPCWSTR),
        ("ulFlags", wintypes.UINT),
        ("lpfn", wintypes.LPCVOID),
        ("lParam", wintypes.LPARAM),
        ("iImage", ctypes.c_int),
    ]


def _pick_folder_win32_shell(title: str) -> Optional[str]:
    """Invokes native Win32 SHBrowseForFolderW dialog with CoTaskMem cleanup."""
    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    hr = ole32.CoInitializeEx(None, 2)
    need_uninit = (hr in (0, 1))
    try:
        bi = _BROWSEINFOW()
        bi.hwndOwner = 0
        bi.pidlRoot = None
        bi.pszDisplayName = None
        bi.lpszTitle = title
        bi.ulFlags = 0x0001 | 0x0040  # BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
        bi.lpfn = None
        bi.lParam = 0
        bi.iImage = 0

        shell32.SHBrowseForFolderW.argtypes = [ctypes.POINTER(_BROWSEINFOW)]
        shell32.SHBrowseForFolderW.restype = wintypes.LPVOID
        shell32.SHGetPathFromIDListW.argtypes = [wintypes.LPVOID, wintypes.LPWSTR]
        shell32.SHGetPathFromIDListW.restype = wintypes.BOOL
        ole32.CoTaskMemFree.argtypes = [wintypes.LPVOID]
        ole32.CoTaskMemFree.restype = None

        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return None

        path_buf = ctypes.create_unicode_buffer(32768)
        success = shell32.SHGetPathFromIDListW(pidl, path_buf)
        ole32.CoTaskMemFree(pidl)

        if success and path_buf.value:
            return path_buf.value
        return None
    finally:
        if need_uninit:
            ole32.CoUninitialize()


def pick_folder_dialog(title: str = "Select Project Folder") -> Optional[str]:
    """Opens a native Windows folder browser dialog preferring Win32 SHBrowseForFolderW with Tkinter fallback."""
    if sys.platform == "win32":
        try:
            return _pick_folder_win32_shell(title)
        except Exception:
            pass

    # Fallback to tkinter if native Win32 shell fails or on non-Windows
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title=title)
        root.destroy()
        return folder if folder else None
    except Exception:
        return None
