"""FastAPI + WebSocket server for the FoamPilot Web UI."""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="FoamPilot Web UI", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"

# ---------------------------------------------------------------------------
# Module-level singleton state (single-user local tool)
# ---------------------------------------------------------------------------
_runner = None          # SimulationRunner | None
_active_send = None     # Latest async WS send callable
_main_loop = None       # asyncio event loop of the active WS handler


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def api_status():
    if _runner:
        return {
            "running": _runner.is_running,
            "session_id": _runner.session_id,
            "phase": _runner.current_phase,
            "case_dir": _runner.case_dir,
        }
    return {"running": False, "session_id": None, "phase": "idle", "case_dir": None}


@app.get("/api/case-log")
async def api_case_log():
    if not _runner or not _runner.case_dir:
        return JSONResponse({"content": ""})
    log_path = Path(_runner.case_dir) / "case.log"
    if not log_path.exists():
        return JSONResponse({"content": ""})
    content = log_path.read_text(encoding="utf-8", errors="replace")
    return JSONResponse({"content": content[-120_000:]})


@app.get("/api/system-log")
async def api_system_log():
    try:
        from foampilot import config
        log_path = config.PROJECT_ROOT / "logs" / "foampilot.log"
        if not log_path.exists():
            return JSONResponse({"content": ""})
        content = log_path.read_text(encoding="utf-8", errors="replace")
        return JSONResponse({"content": content[-80_000:]})
    except Exception as exc:
        return JSONResponse({"content": f"Error reading log: {exc}"})


@app.get("/api/file")
async def api_file(path: str):
    """Read a case file for preview. Restricted to the cases directory."""
    try:
        from foampilot import config
        cases_dir = config.CASES_DIR.resolve()
        fp = Path(path).resolve()
        if not str(fp).startswith(str(cases_dir)):
            return JSONResponse({"error": "Access denied — path outside cases directory"}, status_code=403)
        if not fp.exists() or not fp.is_file():
            return JSONResponse({"error": "File not found"}, status_code=404)
        size = fp.stat().st_size
        raw = fp.read_bytes()[:500_000]
        content = raw.decode("utf-8", errors="replace")
        if size > 500_000:
            content += "\n\n… (file truncated at 500 KB)"
        return JSONResponse({"content": content, "name": fp.name, "size": size})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _runner, _active_send, _main_loop
    await ws.accept()
    _main_loop = asyncio.get_running_loop()

    async def send(event: dict) -> None:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            pass

    _active_send = send
    await send({"type": "connected"})

    # On reconnect send current runner state so the UI can restore itself
    if _runner:
        await send({
            "type": "status",
            "data": {
                "running": _runner.is_running,
                "session_id": _runner.session_id,
                "phase": _runner.current_phase,
                "case_dir": _runner.case_dir,
            },
        })
        if _runner.case_dir:
            from foampilot.ui.web.runner import build_file_tree
            p = Path(_runner.case_dir)
            if p.exists():
                await send({"type": "file_tree", "data": {"tree": build_file_tree(p)}})

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if msg["type"] == "start":
                if _runner and _runner.is_running:
                    await send({"type": "error", "message": "Simulation already running"})
                    continue

                from foampilot.ui.web.runner import SimulationRunner

                def _make_emit(loop):
                    """Return a thread-safe emit that always uses latest _active_send."""
                    def _emit(event: dict) -> None:
                        current = _active_send
                        if current and loop:
                            fut = asyncio.run_coroutine_threadsafe(current(event), loop)
                            # Swallow exceptions so the agent thread never crashes on send
                            fut.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
                    return _emit

                _runner = SimulationRunner(
                    emit_fn=_make_emit(_main_loop),
                    auto_approve=msg.get("auto_approve", False),
                )

                # Immediately ACK so the UI knows the server got the message
                await send({
                    "type": "session_starting",
                    "data": {"prompt": msg["prompt"]},
                })

                _runner.start(msg["prompt"])

            elif msg["type"] == "approval":
                if _runner:
                    _runner.resolve_approval(msg.get("approved", False))

            elif msg["type"] == "set_auto_approve":
                if _runner:
                    _runner.auto_approve = msg.get("enabled", False)

            elif msg["type"] == "clarify_reply":
                if _runner:
                    _runner.set_clarify_reply(msg.get("text", ""))

            elif msg["type"] == "stop":
                if _runner:
                    _runner.stop()
                await send({"type": "session_stopped"})

            elif msg["type"] == "get_files":
                if _runner and _runner.case_dir:
                    from foampilot.ui.web.runner import build_file_tree
                    p = Path(_runner.case_dir)
                    tree = build_file_tree(p) if p.exists() else None
                    await send({"type": "file_tree", "data": {"tree": tree}})
                else:
                    await send({"type": "file_tree", "data": {"tree": None}})

    except WebSocketDisconnect:
        _active_send = None
    except Exception as exc:
        await send({"type": "error", "message": str(exc)})
        _active_send = None


# ---------------------------------------------------------------------------
# Serve the built frontend (production)
# ---------------------------------------------------------------------------

def _setup_static() -> None:
    if not FRONTEND_DIST.exists():
        return

    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/")
    async def _root():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{path:path}")
    async def _spa(path: str):
        if path.startswith(("api/", "ws")):
            return JSONResponse({"error": "not found"}, status_code=404)
        fp = FRONTEND_DIST / path
        if fp.exists() and fp.is_file():
            return FileResponse(str(fp))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


_setup_static()
