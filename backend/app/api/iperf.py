from fastapi import APIRouter, HTTPException
import shutil
import subprocess
import json
import threading
import os
from typing import Optional

router = APIRouter()

# Module-level storage for server process
_server_proc: Optional[subprocess.Popen] = None


def _check_iperf():
    return shutil.which("iperf3") is not None


@router.get("/installed")
async def iperf_installed():
    """Check if iperf3 is installed on the host."""
    return {"installed": _check_iperf()}


@router.post("/server/start")
async def start_server(port: int = 5201):
    """Start a local iperf3 server in the background on the given port."""
    global _server_proc
    if not _check_iperf():
        raise HTTPException(status_code=400, detail="iperf3 not installed on server")
    if _server_proc and _server_proc.poll() is None:
        return {"ok": True, "message": "server already running", "pid": _server_proc.pid}
    cmd = ["iperf3", "-s", "-p", str(port)]
    # start detached process
    _server_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "pid": _server_proc.pid}


@router.post("/server/stop")
async def stop_server():
    """Stop the local iperf3 server if it was started by this process."""
    global _server_proc
    if not _server_proc:
        return {"ok": True, "message": "no server process tracked"}
    try:
        _server_proc.terminate()
        _server_proc.wait(timeout=5)
    except Exception:
        try:
            _server_proc.kill()
        except Exception:
            pass
    pid = _server_proc.pid
    _server_proc = None
    return {"ok": True, "stopped_pid": pid}


@router.get("/run")
async def run_iperf(server: str, port: int = 5201, time: int = 10, reverse: bool = False):
    """Run iperf3 client to a server and return parsed JSON result.

    Example: /api/iperf/run?server=iperf.he.net&time=10
    """
    if not _check_iperf():
        raise HTTPException(status_code=400, detail="iperf3 not installed on server")

    cmd = ["iperf3", "-c", server, "-p", str(port), "-t", str(time), "--json"]
    if reverse:
        cmd.append("-R")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=(time + 15))
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="iperf3 timed out")

    if proc.returncode != 0:
        raise HTTPException(status_code=502, detail=f"iperf3 failed: {proc.stderr.strip()}")

    try:
        data = json.loads(proc.stdout)
    except Exception:
        raise HTTPException(status_code=502, detail="failed to parse iperf3 output")

    return data
