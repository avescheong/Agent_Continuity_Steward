"""Desktop HUD Launcher (pywebview primary + isolated Edge --app fallback)."""

import sys
import subprocess
import socket
import time
import threading
from pathlib import Path
from typing import Optional

import uvicorn
from scs_core.config import DEFAULT_DATA_DIR
from scs_host.local_rpc_server import LocalRPCServer
from scs_host import win32_window

try:
    import win32gui
    import win32process
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False


def find_free_port() -> int:
    """Finds an available local port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DesktopHUDLauncher:
    def __init__(self, rpc_server: LocalRPCServer, port: Optional[int] = None):
        self.rpc_server = rpc_server
        self.port = port or find_free_port()
        self.server_thread: Optional[threading.Thread] = None
        self.uvicorn_server: Optional[uvicorn.Server] = None

    def start_background_server(self) -> None:
        """Starts the local Starlette RPC server on 127.0.0.1:<port>."""
        if sys.stdout is None:
            import io
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            import io
            sys.stderr = io.StringIO()

        config = uvicorn.Config(
            app=self.rpc_server.app,
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self.uvicorn_server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self.uvicorn_server.run, daemon=True)
        self.server_thread.start()

        # Wait briefly for server ready
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    break
            except Exception:
                time.sleep(0.05)

    def launch(self, mode: str = "auto") -> None:
        """Launches the desktop HUD window.

        Modes:
        - 'pywebview': Use pywebview WebView2 host
        - 'edge-app': Use native msedge.exe --app isolated window
        - 'auto': Try pywebview first, fall back to edge-app
        """
        win32_window.set_dpi_awareness()
        self.start_background_server()
        url = f"http://127.0.0.1:{self.port}"

        # 1. Check if pywebview available
        if mode in ("auto", "pywebview"):
            try:
                import webview
                # Launch pywebview window with safe launch dimensions & minimum constraints
                window = webview.create_window(
                    title="SCS-HUD",
                    url=url,
                    width=win32_window.DEFAULT_WINDOW_WIDTH,
                    height=win32_window.DEFAULT_WINDOW_HEIGHT,
                    min_size=(win32_window.MIN_WINDOW_WIDTH, win32_window.MIN_WINDOW_HEIGHT_COMPACT),
                    resizable=True,
                    on_top=True,
                    frameless=False,
                )
                webview.start(gui="edgechromium")
                return
            except Exception:
                if mode == "pywebview":
                    raise

        # 2. Fallback: Edge App Mode (guaranteed on Windows 10/11)
        self._launch_edge_app(url)

    def _launch_edge_app(self, url: str) -> None:
        edge_paths = [
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        ]
        edge_bin = next((p for p in edge_paths if p.exists()), None)
        if not edge_bin:
            raise FileNotFoundError("Microsoft Edge executable not found for app mode.")

        profile_dir = DEFAULT_DATA_DIR / "hud_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(edge_bin),
            f"--app={url}",
            f"--user-data-dir={profile_dir}",
            f"--window-size={win32_window.DEFAULT_WINDOW_WIDTH},{win32_window.DEFAULT_WINDOW_HEIGHT}",
            "--window-position=1400,160",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-mode",
            "--disable-extensions",
            "--disable-features=Translate",
        ]

        proc = subprocess.Popen(cmd)

        try:
            # Poll specifically for the Edge window belonging to proc or SCS-HUD
            hwnd = self._find_edge_hwnd(proc.pid, timeout=5.0)
            if hwnd:
                self.rpc_server.set_hwnd(hwnd)
                win32_window.apply_dark_titlebar(hwnd)
                win32_window.make_window_topmost(hwnd, True)
                win32_window.ensure_safe_window_geometry(
                    hwnd,
                    default_width=win32_window.DEFAULT_WINDOW_WIDTH,
                    default_height=win32_window.DEFAULT_WINDOW_HEIGHT,
                    min_width=win32_window.MIN_WINDOW_WIDTH,
                    min_height=win32_window.MIN_WINDOW_HEIGHT_COMPACT,
                )
            proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
            if self.uvicorn_server:
                self.uvicorn_server.should_exit = True

    def _find_edge_hwnd(self, pid: int, timeout: float = 5.0) -> Optional[int]:
        if not PYWIN32_AVAILABLE:
            return None
        start = time.time()
        while time.time() - start < timeout:
            found_hwnd = None

            def enum_cb(h, _):
                nonlocal found_hwnd
                if found_hwnd is not None:
                    return
                if win32gui.IsWindowVisible(h):
                    _, win_pid = win32process.GetWindowThreadProcessId(h)
                    cls = win32gui.GetClassName(h)
                    # Strictly match the Chromium app window belonging to this PID or titled SCS-HUD
                    if cls == "Chrome_WidgetWin_1":
                        if win_pid == pid:
                            found_hwnd = h
                        else:
                            title = win32gui.GetWindowText(h)
                            if title.startswith("SCS-HUD"):
                                found_hwnd = h

            try:
                win32gui.EnumWindows(enum_cb, None)
            except Exception:
                pass

            if found_hwnd:
                return found_hwnd
            time.sleep(0.2)

        return None
