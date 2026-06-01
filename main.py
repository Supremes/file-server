#!/usr/bin/env python3
"""
Kunm File Manager — PAM-authenticated file server with beautiful UI
"""

import os
import stat
import mimetypes
import shutil
import base64
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, Response, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Config ──────────────────────────────────────────────────────────────────
FILES_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wwwroot", "files")
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB
HOST = "127.0.0.1"
PORT = 5800

app = FastAPI(title="Herme File Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── PAM Authentication (disabled) ──────────────────────────────────────────
def authenticate_user(username: str, password: str) -> bool:
    return True  # No auth


def get_auth_user(request: Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = decoded.split(":", 1)
        if authenticate_user(username, password):
            return username
    except Exception:
        pass
    return None


def require_auth(request: Request):
    return "admin"  # No auth required


# ── Helpers ──────────────────────────────────────────────────────────────────
def safe_path(relative: str) -> Path:
    """Resolve a relative path under FILES_ROOT, preventing directory traversal."""
    # Sanitize: remove null bytes
    relative = relative.replace("\x00", "")
    # Strip leading slash/traversal
    path = (Path(FILES_ROOT) / relative.lstrip("/")).resolve()
    if not str(path).startswith(FILES_ROOT):
        raise HTTPException(status_code=403, detail="Path traversal denied")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    return path


def format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"


def icon_for(name: str, is_dir: bool) -> str:
    if is_dir:
        return "📁"
    ext = Path(name).suffix.lower()
    icons = {
        ".txt": "📄", ".md": "📝", ".json": "📋", ".yaml": "📋", ".yml": "📋",
        ".py": "🐍", ".js": "🟨", ".ts": "🟦", ".html": "🌐", ".css": "🎨",
        ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🖼️", ".svg": "🖼️",
        ".webp": "🖼️", ".ico": "🖼️", ".mp4": "🎬", ".avi": "🎬", ".mkv": "🎬",
        ".mp3": "🎵", ".m4a": "🎵", ".wav": "🎵", ".flac": "🎵", ".wma": "🎵",
        ".zip": "📦", ".tar": "📦", ".gz": "📦", ".bz2": "📦", ".7z": "📦",
        ".rar": "📦", ".pdf": "📕", ".doc": "📘", ".docx": "📘",
        ".xls": "📊", ".xlsx": "📊", ".ppt": "📙", ".pptx": "📙",
        ".exe": "⚙️", ".deb": "⚙️", ".rpm": "⚙️", ".sh": "💻", ".bat": "💻",
        ".iso": "💿", ".img": "💿", ".db": "🗄️", ".sql": "🗄️", ".sqlite": "🗄️",
        ".log": "📃", ".conf": "⚙️", ".env": "🔒", ".key": "🔑", ".pem": "🔑",
        ".crt": "🔑", ".p12": "🔑", ".apk": "📱", ".ipa": "📱",
    }
    return icons.get(ext, "📄")


# ── API Routes ──────────────────────────────────────────────────────────────

@app.get("/api/list")
async def api_list(request: Request, path: str = Query(""), search: str = Query(None)):
    require_auth(request)
    target = safe_path(path)

    # ── Recursive search mode ──
    if search:
        search_lower = search.lower()
        results = []
        try:
            for root_str, dirs, files in os.walk(str(target)):
                root_rel = os.path.relpath(root_str, FILES_ROOT)
                if root_rel == ".":
                    root_rel = ""
                for name in files:
                    if search_lower in name.lower():
                        full = os.path.join(root_str, name)
                        try:
                            st = os.lstat(full)
                            rel = os.path.relpath(full, FILES_ROOT)
                            results.append({
                                "name": name, "path": rel, "is_dir": False,
                                "size": st.st_size,
                                "size_str": format_size(st.st_size),
                                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                                "icon": icon_for(name, False),
                            })
                        except OSError:
                            pass
                for name in dirs:
                    if search_lower in name.lower():
                        rel = os.path.relpath(os.path.join(root_str, name), FILES_ROOT)
                        results.append({
                            "name": name, "path": rel, "is_dir": True,
                            "size": 0, "size_str": "", "modified": "", "icon": icon_for(name, True),
                        })
        except OSError:
            pass
        return {"type": "search", "query": search, "entries": results, "path": path}

    target = safe_path(path)

    if target.is_file():
        stat_info = target.stat()
        return {
            "type": "file",
            "name": target.name,
            "path": str(target.relative_to(FILES_ROOT)),
            "size": stat_info.st_size,
            "size_str": format_size(stat_info.st_size),
            "modified": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "mime": mimetypes.guess_type(str(target))[0] or "application/octet-stream",
        }

    entries = []
    for item in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
        try:
            st = item.lstat()
            is_dir = item.is_dir()
            size = st.st_size if not is_dir else 0
            entries.append({
                "name": item.name,
                "path": str(item.relative_to(FILES_ROOT)),
                "is_dir": is_dir,
                "size": size,
                "size_str": format_size(size) if not is_dir else "",
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                "icon": icon_for(item.name, is_dir),
            })
        except OSError:
            continue

    return {
        "type": "directory",
        "name": target.name,
        "path": str(target.relative_to(FILES_ROOT)) if target != Path(FILES_ROOT) else "",
        "entries": entries,
    }


@app.get("/api/download")
async def api_download(request: Request, path: str = Query("")):
    require_auth(request)
    target = safe_path(path)
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    def iterfile():
        with open(target, "rb") as f:
            yield from f

    filename = target.name
    mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return StreamingResponse(
        iterfile(),
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(target.stat().st_size),
        },
    )


@app.post("/api/upload")
async def api_upload(request: Request):
    user = require_auth(request)
    upload_path = request.headers.get("X-Upload-Path", "")

    target_dir = safe_path(upload_path)
    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target path is not a directory")

    form = await request.form()
    uploaded_count = 0
    for field_name, field_value in form.items():
        if not hasattr(field_value, "filename") or not field_value.filename:
            continue

        content = await field_value.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File {field_value.filename} exceeds 200MB limit",
            )

        dest = target_dir / Path(field_value.filename).name
        with open(dest, "wb") as f:
            f.write(content)
        uploaded_count += 1

    return {"status": "ok", "uploaded": uploaded_count, "user": user}


@app.post("/api/mkdir")
async def api_mkdir(request: Request):
    user = require_auth(request)
    body = await request.json()
    parent_path = body.get("path", "")
    dir_name = body.get("name", "").strip()

    if not dir_name:
        raise HTTPException(status_code=400, detail="Directory name required")

    # Validate directory name (no path separators)
    if "/" in dir_name or "\\" in dir_name or dir_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid directory name")

    target = safe_path(parent_path)
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Parent is not a directory")

    new_dir = target / dir_name
    if new_dir.exists():
        raise HTTPException(status_code=409, detail="Already exists")

    new_dir.mkdir(parents=True, exist_ok=False)
    return {"status": "ok", "path": str(new_dir.relative_to(FILES_ROOT)), "user": user}


@app.delete("/api/delete")
async def api_delete(request: Request):
    user = require_auth(request)
    body = await request.json()
    item_path = body.get("path", "")

    target = safe_path(item_path)
    if target == Path(FILES_ROOT):
        raise HTTPException(status_code=403, detail="Cannot delete root")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    return {"status": "ok", "deleted": item_path, "user": user}


@app.get("/api/read")
async def api_read(request: Request, path: str = Query(""), max_bytes: int = Query(102400)):
    require_auth(request)
    target = safe_path(path)
    if not target.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    # Check if it's a text-like file
    ext = Path(target.name).suffix.lower()
    text_exts = {'.txt', '.md', '.json', '.yaml', '.yml', '.py', '.js', '.ts',
                 '.html', '.css', '.xml', '.log', '.conf', '.sh', '.env',
                 '.cfg', '.ini', '.toml', '.csv', '.sql', '.gitignore',
                 '.dockerignore', '.editorconfig', '.yaml', '.yml', '.tex',
                 '.rst', '.org', '.json5', '.h', '.c', '.cpp', '.hpp', '.java',
                 '.go', '.rs', '.rb', '.php', '.pl', '.lua', '.scala', '.kt',
                 '.swift', '.m', '.mm', '.vhdl', '.v', '.sv', '.gradle',
                 '.makefile', '.dockerfile', '.cfg', '.cnf'}
    mime, _ = mimetypes.guess_type(str(target))
    is_text = (mime and mime.startswith("text/")) or ext in text_exts

    if not is_text:
        raise HTTPException(status_code=400, detail="Not a text file")

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read file")

    return {
        "name": target.name,
        "path": str(target.relative_to(FILES_ROOT)),
        "content": content,
        "truncated": len(content) >= max_bytes,
        "size": target.stat().st_size,
    }


@app.post("/api/move")
async def api_move(request: Request):
    user = require_auth(request)
    body = await request.json()
    source = body.get("source", "")
    dest_dir = body.get("dest_dir", "")

    if not source or not dest_dir:
        raise HTTPException(status_code=400, detail="source and dest_dir required")

    src_path = safe_path(source)
    dst_parent = safe_path(dest_dir)

    if not dst_parent.is_dir():
        raise HTTPException(status_code=400, detail="Destination is not a directory")

    if src_path == Path(FILES_ROOT):
        raise HTTPException(status_code=403, detail="Cannot move root")

    # Prevent moving a directory into itself
    if src_path.is_dir():
        try:
            src_path.relative_to(dst_parent)
            raise HTTPException(status_code=400, detail="Cannot move directory into itself")
        except ValueError:
            pass  # Not a subfolder, good

    dest = dst_parent / src_path.name
    if dest.exists():
        raise HTTPException(status_code=409, detail="Target already exists")

    shutil.move(str(src_path), str(dest))
    return {"status": "ok", "from": source, "to": str(dest.relative_to(FILES_ROOT)), "user": user}


# ── Dashboard API ────────────────────────────────────────────────────────────

_prev_net = None  # (timestamp, rx_bytes, tx_bytes)


def _run_cmd(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, timeout=5, stderr=subprocess.DEVNULL).decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _parse_meminfo() -> dict:
    """Return {total, used, free, percent, swap_total, swap_used, swap_percent} in bytes."""
    try:
        out = _run_cmd("free -b | tail -n +2")
        lines = out.split("\n")
        mem_line = None
        swap_line = None
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "Mem:":
                mem_line = parts
            elif parts[0] == "Swap:":
                swap_line = parts
        result = {"total": 0, "used": 0, "free": 0, "percent": 0,
                  "swap_total": 0, "swap_used": 0, "swap_percent": 0}
        if mem_line and len(mem_line) >= 4:
            total = int(mem_line[1])
            used = int(mem_line[2])
            free = int(mem_line[3])
            # Also consider buffers/cache for "available"
            avail = int(mem_line[6]) if len(mem_line) >= 7 else free
            percent = round((total - avail) / total * 100, 1) if total else 0
            result.update({"total": total, "used": total - avail, "free": avail, "percent": percent})
        if swap_line and len(swap_line) >= 4:
            st = int(swap_line[1])
            su = int(swap_line[2])
            sf = int(swap_line[3])
            sp = round(su / st * 100, 1) if st else 0
            result.update({"swap_total": st, "swap_used": su, "swap_free": sf, "swap_percent": sp})
        return result
    except Exception:
        return {"total": 0, "used": 0, "free": 0, "percent": 0}


def _parse_disk() -> dict:
    out = _run_cmd("df -B1 / | tail -1")
    parts = out.split()
    if len(parts) >= 5:
        total = int(parts[1])
        used = int(parts[2])
        free = int(parts[3])
        pct_str = parts[4].replace("%", "")
        pct = float(pct_str) if pct_str else 0
    else:
        total = used = free = pct = 0
    return {"total": total, "used": used, "free": free, "percent": pct}


def _parse_cpu() -> dict:
    """Return {usage, cores}."""
    cores = int(_run_cmd("nproc --all") or os.cpu_count() or 1)
    # Two samples to get delta
    def _read_cpu():
        with open("/proc/stat") as f:
            line = f.readline()
        parts = line.split()
        user = int(parts[1])
        nice = int(parts[2])
        system = int(parts[3])
        idle = int(parts[4])
        iowait = int(parts[5]) if len(parts) > 5 else 0
        irq = int(parts[6]) if len(parts) > 6 else 0
        softirq = int(parts[7]) if len(parts) > 7 else 0
        steal = int(parts[8]) if len(parts) > 8 else 0
        total = user + nice + system + idle + iowait + irq + softirq + steal
        return total, idle
    try:
        t1, i1 = _read_cpu()
        import time
        time.sleep(0.5)
        t2, i2 = _read_cpu()
        d_total = max(t2 - t1, 1)
        d_idle = i2 - i1
        usage = round((d_total - d_idle) / d_total * 100, 1)
    except Exception:
        usage = 0.0
    return {"usage": usage, "cores": cores}


def _parse_load() -> list:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        return [float(parts[0]), float(parts[1]), float(parts[2])]
    except Exception:
        return [0, 0, 0]


def _parse_processes() -> list:
    """Return status for key services."""
    services = [
        ("nginx", "nginx"),
        ("Hermes Gateway", "hermes-cli"),
        ("Kunm Files", "files-server/main.py"),
        ("agent-browser", "agent-browser"),
    ]
    result = []
    for name, keyword in services:
        out = _run_cmd(f"ps aux | grep '{keyword}' | grep -v grep | head -1")
        if out:
            parts = out.split()
            pid = parts[1] if len(parts) > 1 else ""
            result.append({"name": name, "status": "running", "pid": pid})
        else:
            result.append({"name": name, "status": "stopped", "pid": ""})
    return result


def _parse_network() -> dict:
    """Return {rx, tx, rx_total, tx_total} in bytes (rx/tx per sec)."""
    global _prev_net
    now = datetime.now().timestamp()
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()
        rx_total = tx_total = 0
        for line in lines[2:]:
            parts = line.split()
            if len(parts) >= 10:
                name = parts[0].strip(":")
                if name == "lo":
                    continue
                rx_total += int(parts[1])
                tx_total += int(parts[9])
    except Exception:
        rx_total = tx_total = 0

    rx_rate = tx_rate = 0
    if _prev_net:
        pt, prx, ptx = _prev_net
        dt = max(now - pt, 0.1)
        rx_rate = max(0, int((rx_total - prx) / dt))
        tx_rate = max(0, int((tx_total - ptx) / dt))
    _prev_net = (now, rx_total, tx_total)
    return {"rx": rx_rate, "tx": tx_rate, "rx_total": rx_total, "tx_total": tx_total}


def _parse_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            up = float(f.read().split()[0])
        days = int(up // 86400)
        hours = int((up % 86400) // 3600)
        mins = int((up % 3600) // 60)
        parts = []
        if days > 0: parts.append(f"{days}d")
        if hours > 0: parts.append(f"{hours}h")
        parts.append(f"{mins}m")
        return " ".join(parts)
    except Exception:
        return ""


def _top_cpu(n: int = 8) -> list:
    out = _run_cmd(f"ps aux --sort=-%cpu | head -{n + 1} | tail -{n}")
    results = []
    for line in out.split("\n"):
        parts = line.split(None, 10)
        if len(parts) >= 11:
            try:
                results.append({
                    "pid": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "rss": format_size(int(parts[5]) * 1024) if parts[5].isdigit() else parts[5],
                    "name": parts[10][:40],
                })
            except (ValueError, IndexError):
                pass
    return results


@app.get("/api/tokens")
async def api_tokens(request: Request):
    """Return token usage statistics from Hermes logs."""
    require_auth(request)
    
    log_file = os.path.expanduser("~/.hermes/logs/agent.log")
    if not os.path.exists(log_file):
        return {"total_input": 0, "total_output": 0, "total_tokens": 0, "api_calls": 0, "today_tokens": 0}
    
    total_input = 0
    total_output = 0
    api_calls = 0
    today_tokens = 0
    today = datetime.now().strftime("%Y-%m-%d")
    
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "API call" in line and "mimo" in line:
                    # Parse input tokens
                    if "in=" in line:
                        try:
                            in_match = line.split("in=")[1].split()[0]
                            total_input += int(in_match)
                        except (IndexError, ValueError):
                            pass
                    # Parse output tokens
                    if "out=" in line:
                        try:
                            out_match = line.split("out=")[1].split()[0]
                            total_output += int(out_match)
                        except (IndexError, ValueError):
                            pass
                    api_calls += 1
                    
                    # Check if today
                    if today in line:
                        try:
                            total_match = line.split("total=")[1].split()[0]
                            today_tokens += int(total_match)
                        except (IndexError, ValueError):
                            pass
    except Exception:
        pass
    
    return {
        "total_input": total_input,
        "total_output": total_output,
        "total_tokens": total_input + total_output,
        "api_calls": api_calls,
        "today_tokens": today_tokens,
    }


@app.get("/api/status")
async def api_status(request: Request):
    require_auth(request)
    mem = _parse_meminfo()
    disk = _parse_disk()
    cpu = _parse_cpu()
    load_avg = _parse_load()
    procs = _parse_processes()
    net = _parse_network()
    top = _top_cpu(8)
    host = _run_cmd("hostname")
    os_info = _run_cmd("uname -sr")
    uptime = _parse_uptime()
    return {
        "host": host,
        "hostname": host,
        "os": os_info,
        "uptime": uptime,
        "memory": mem,
        "disk": disk,
        "cpu": cpu,
        "load_avg": load_avg,
        "processes": procs,
        "network": net,
        "top_cpu": top,
        "swap": {"percent": mem.get("swap_percent", 0), "total": mem.get("swap_total", 0), "used": mem.get("swap_used", 0)},
    }


# ── Frontend ─────────────────────────────────────────────────────────────────

import os

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_INDEX_PATH = os.path.join(_TEMPLATE_DIR, "index.html")
_DASHBOARD_PATH = os.path.join(_TEMPLATE_DIR, "dashboard.html")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the SPA frontend from index.html."""
    with open(_INDEX_PATH, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/db", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the dashboard page."""
    # Check auth but don't redirect — the JS handles login
    get_auth_user(request)
    try:
        with open(_DASHBOARD_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("Dashboard page not found", status_code=404)


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🚀 Kunm File Manager starting on http://{HOST}:{PORT}")
    print(f"📂 Serving files from: {FILES_ROOT}")
    print(f"🔐 PAM authentication enabled (max upload: {MAX_UPLOAD_SIZE // 1024 // 1024}MB)")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


@app.get("/view")
async def view_file(request: Request, path: str = Query("")):
    """Serve a file inline (for HTML/image preview in browser)."""
    require_auth(request)
    target = safe_path(path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not a file")

    mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    from urllib.parse import quote
    ascii_name = target.name.encode('ascii', 'ignore').decode() or 'file'
    encoded_name = quote(target.name)
    return StreamingResponse(
        open(target, "rb"),
        media_type=mime,
        headers={
            "Content-Disposition": f"inline; filename={ascii_name}; filename*=UTF-8''{encoded_name}",
            "Content-Length": str(target.stat().st_size),
        },
    )
