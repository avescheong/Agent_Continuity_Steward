"""Local Starlette/Uvicorn server hosting UI static assets and /api/invoke."""

import secrets
import json
from pathlib import Path
from typing import Optional, Callable

from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response, FileResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from scs_core.ipc.dispatcher import SCSDispatcher
from scs_host import win32_window


UI_DIR = Path(__file__).resolve().parent.parent / "ui"


class LocalRPCServer:
    def __init__(self, dispatcher: SCSDispatcher, session_token: Optional[str] = None):
        self.dispatcher = dispatcher
        self.session_token = session_token or secrets.token_hex(16)
        self.hwnd: Optional[int] = None
        self.app = self._build_app()

    def set_hwnd(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def _build_app(self) -> Starlette:
        routes = [
            Route("/", endpoint=self._serve_index, methods=["GET"]),
            Route("/api/invoke", endpoint=self._handle_invoke, methods=["POST"]),
            Mount("/styles", app=StaticFiles(directory=str(UI_DIR / "styles")), name="styles"),
            Mount("/js", app=StaticFiles(directory=str(UI_DIR / "js")), name="js"),
        ]
        return Starlette(debug=False, routes=routes)

    async def _serve_index(self, request):
        index_file = UI_DIR / "index.html"
        content = index_file.read_text(encoding="utf-8")
        # Inject per-run session token into frontend
        injected = content.replace(
            "<!-- __SCS_TOKEN_INJECTION__ -->",
            f'<script>window.__SCS_SESSION_TOKEN__ = "{self.session_token}";</script>',
        )
        return Response(
            content=injected,
            media_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    async def _handle_invoke(self, request):
        # Security Guard: verify session token
        token_header = request.headers.get("X-SCS-Token")
        if token_header != self.session_token:
            return JSONResponse(
                {"ok": False, "error": {"code": "UNAUTHORIZED", "message": "Invalid session token"}},
                status_code=403,
            )

        try:
            body = await request.json()
            cmd = body.get("command")
            payload = body.get("payload", {})

            # Intercept host/window commands
            if cmd == "window_control":
                return JSONResponse({"ok": True, "data": self._handle_window_control(payload)})

            # Dispatch domain commands
            res = self.dispatcher.invoke(cmd, payload)
            return JSONResponse(res)
        except Exception as e:
            return JSONResponse(
                {"ok": False, "error": {"code": "BAD_REQUEST", "message": str(e)}},
                status_code=400,
            )

    def _handle_window_control(self, p: dict) -> dict:
        action = p.get("action")
        hwnd = self.hwnd

        if action == "toggle_pin":
            topmost = bool(p.get("topmost", True))
            if hwnd:
                win32_window.make_window_topmost(hwnd, topmost)
            return {"topmost": topmost}

        elif action == "toggle_ghost":
            alpha = float(p.get("opacity", 0.55 if p.get("ghost") else 1.0))
            if hwnd:
                win32_window.set_window_opacity(hwnd, alpha)
            return {"opacity": alpha}

        elif action == "set_view_mode":
            mode = p.get("mode", "drawer")
            req_h = p.get("height")
            # Presets: compact / pill: 430x220, drawer: 430x680, inspector: 880x680
            dims = {
                "compact": (win32_window.DEFAULT_WINDOW_WIDTH, req_h or win32_window.COMPACT_WINDOW_HEIGHT),
                "pill": (win32_window.DEFAULT_WINDOW_WIDTH, req_h or win32_window.COMPACT_WINDOW_HEIGHT),
                "drawer": (win32_window.DEFAULT_WINDOW_WIDTH, win32_window.DEFAULT_WINDOW_HEIGHT),
                "inspector": (880, 680),
            }
            w, h = dims.get(mode, (win32_window.DEFAULT_WINDOW_WIDTH, win32_window.DEFAULT_WINDOW_HEIGHT))
            target_hwnd = hwnd
            if not target_hwnd and win32_window.PYWIN32_AVAILABLE:
                try:
                    import win32gui
                    def _find_scs(h_val, _):
                        nonlocal target_hwnd
                        if target_hwnd:
                            return
                        if win32gui.IsWindowVisible(h_val) and win32gui.GetWindowText(h_val).startswith("SCS-HUD"):
                            target_hwnd = h_val
                    win32gui.EnumWindows(_find_scs, None)
                    if target_hwnd:
                        self.set_hwnd(target_hwnd)
                except Exception:
                    pass

            if target_hwnd:
                win32_window.resize_window(target_hwnd, w, h, preserve_width=(mode in ("compact", "pill")))
            return {"mode": mode, "width": w, "height": h}

        elif action == "copy_clipboard":
            text = p.get("text", "")
            ok = win32_window.set_clipboard_text(text)
            return {"copied": ok}

        elif action == "read_clipboard":
            text = win32_window.get_clipboard_text()
            return {"text": text}

        elif action == "pick_folder":
            folder = win32_window.pick_folder_dialog(title=p.get("title", "Select Project Root Folder"))
            return {"folder": folder}

        return {"unsupported_action": action}
