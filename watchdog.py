"""
Sports Betting Plus — Keep-Alive Watchdog
==========================================
Monitors Streamlit + ngrok and restarts either process if it dies.
Designed to run via Windows Task Scheduler on system startup.

Setup (run once as Administrator):
    python watchdog.py --install

Manual start:
    python watchdog.py

Logs written to: logs/watchdog.log
"""

import subprocess
import time
import sys
import os
import argparse
import signal
import logging
from pathlib import Path
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
STREAMLIT_PORT  = 8501
STREAMLIT_URL   = f"http://localhost:{STREAMLIT_PORT}"
CHECK_INTERVAL  = 30          # seconds between health checks
RESTART_DELAY   = 5           # seconds to wait before restarting
MAX_RESTARTS    = 20          # safety limit per session
LOG_DIR         = BASE_DIR / "logs"
NGROK_EXE       = BASE_DIR / "ngrok-v3-stable-windows-amd64" / "ngrok.exe"
PYTHON_EXE      = sys.executable

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "watchdog.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("watchdog")

# ── Process handles ───────────────────────────────────────────────────────────
_streamlit_proc: subprocess.Popen | None = None
_ngrok_proc:     subprocess.Popen | None = None
_st_restarts   = 0
_ng_restarts   = 0


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def is_streamlit_healthy() -> bool:
    """Try an HTTP GET to the Streamlit health endpoint."""
    if requests is None:
        # Fallback: check if process is alive
        return _streamlit_proc is not None and _streamlit_proc.poll() is None
    try:
        r = requests.get(f"{STREAMLIT_URL}/_stcore/health", timeout=6)
        return r.status_code == 200
    except Exception:
        return False


def start_streamlit() -> subprocess.Popen:
    log.info("Starting Streamlit on port %d …", STREAMLIT_PORT)
    proc = subprocess.Popen(
        [
            PYTHON_EXE, "-m", "streamlit", "run",
            str(BASE_DIR / "src" / "props_dashboard.py"),
            "--server.address", "0.0.0.0",
            "--server.port", str(STREAMLIT_PORT),
            "--server.headless", "true",
            "--server.runOnSave", "false",
        ],
        cwd=str(BASE_DIR),
        stdout=open(LOG_DIR / "streamlit.log", "a"),
        stderr=subprocess.STDOUT,
    )
    log.info("Streamlit started  PID=%d", proc.pid)
    return proc


def start_ngrok() -> subprocess.Popen | None:
    if not NGROK_EXE.exists():
        log.warning("ngrok not found at %s — skipping tunnel", NGROK_EXE)
        return None
    log.info("Starting ngrok tunnel → localhost:%d …", STREAMLIT_PORT)
    proc = subprocess.Popen(
        [str(NGROK_EXE), "http", str(STREAMLIT_PORT)],
        cwd=str(BASE_DIR),
        stdout=open(LOG_DIR / "ngrok.log", "a"),
        stderr=subprocess.STDOUT,
    )
    log.info("ngrok started  PID=%d", proc.pid)
    return proc


def kill_proc(proc: subprocess.Popen | None, name: str):
    if proc and proc.poll() is None:
        log.info("Stopping %s (PID=%d) …", name, proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


def get_ngrok_url() -> str:
    """Read the public URL from ngrok's local API."""
    if requests is None:
        return ""
    try:
        r = requests.get("http://localhost:4040/api/tunnels", timeout=4)
        tunnels = r.json().get("tunnels", [])
        for t in tunnels:
            if "https" in t.get("public_url", ""):
                return t["public_url"]
        return tunnels[0]["public_url"] if tunnels else ""
    except Exception:
        return ""


def shutdown(signum=None, frame=None):
    log.info("Watchdog shutting down …")
    kill_proc(_streamlit_proc, "Streamlit")
    kill_proc(_ngrok_proc, "ngrok")
    sys.exit(0)


def install_task_scheduler():
    """Register this watchdog as a Windows Task Scheduler task that runs at logon."""
    task_name = "SportsBettingPlusWatchdog"
    script    = str(Path(__file__).resolve())
    cmd = (
        f'schtasks /Create /TN "{task_name}" /TR '
        f'"{PYTHON_EXE} {script}" '
        f'/SC ONLOGON /RL HIGHEST /F'
    )
    log.info("Registering Task Scheduler task: %s", task_name)
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        log.info("✅ Task registered. Watchdog will start automatically on next logon.")
        log.info("   To remove: schtasks /Delete /TN \"%s\" /F", task_name)
    else:
        log.error("Failed: %s", result.stderr)
        log.error("Try running as Administrator.")


def run():
    global _streamlit_proc, _ngrok_proc, _st_restarts, _ng_restarts

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("=" * 60)
    log.info("Sports Betting Plus Watchdog — started %s", datetime.now().isoformat())
    log.info("Base dir : %s", BASE_DIR)
    log.info("Python   : %s", PYTHON_EXE)
    log.info("Check interval: %ds", CHECK_INTERVAL)
    log.info("=" * 60)

    # Initial launch
    _streamlit_proc = start_streamlit()
    time.sleep(6)  # give Streamlit time to bind port
    _ngrok_proc = start_ngrok()
    time.sleep(4)

    url = get_ngrok_url()
    if url:
        log.info("🌐 Public URL: %s", url)

    while True:
        time.sleep(CHECK_INTERVAL)

        # ── Streamlit health check ──
        st_alive = _streamlit_proc is not None and _streamlit_proc.poll() is None
        st_healthy = is_streamlit_healthy()

        if not st_alive or not st_healthy:
            if _st_restarts >= MAX_RESTARTS:
                log.error("Streamlit restarted %d times — giving up.", MAX_RESTARTS)
                break
            log.warning("Streamlit %s — restarting … (attempt %d)",
                        "crashed" if not st_alive else "unhealthy", _st_restarts + 1)
            kill_proc(_streamlit_proc, "Streamlit")
            time.sleep(RESTART_DELAY)
            _streamlit_proc = start_streamlit()
            _st_restarts += 1
            time.sleep(6)

        # ── ngrok health check ──
        ng_alive = _ngrok_proc is not None and _ngrok_proc.poll() is None
        if not ng_alive and NGROK_EXE.exists():
            if _ng_restarts >= MAX_RESTARTS:
                log.error("ngrok restarted %d times — giving up.", MAX_RESTARTS)
            else:
                log.warning("ngrok died — restarting … (attempt %d)", _ng_restarts + 1)
                time.sleep(RESTART_DELAY)
                _ngrok_proc = start_ngrok()
                _ng_restarts += 1
                time.sleep(4)
                url = get_ngrok_url()
                if url:
                    log.info("🌐 New public URL: %s", url)

        # Periodic status log (every 10 checks)
        if (_st_restarts + _ng_restarts) == 0:
            log.debug("✅ All processes healthy  [%s]", _ts())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sports Betting Plus Watchdog")
    parser.add_argument("--install", action="store_true",
                        help="Register as Windows Task Scheduler task (run as Admin)")
    args = parser.parse_args()

    if args.install:
        install_task_scheduler()
    else:
        run()
