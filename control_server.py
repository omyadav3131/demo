"""
SwarmSync Control Server — wraps mqtt_world.py + mqtt_robot.py as managed subprocesses.
Exposes a REST API that the dashboard calls to Pause/Resume/Stop/Reset the simulation.
Runs on port 8081. The Java backend on port 8080 serves the dashboard and WebSocket.
"""
import os, subprocess, signal, sys, time, json, threading
import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
SIM  = os.path.join(ROOT, "sim")

app = FastAPI(title="SwarmSync Control API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── state ──────────────────────────────────────────────────────────────────────
lock         = threading.Lock()
world_proc   : subprocess.Popen | None = None
robot_procs  : list[subprocess.Popen] = []
_paused      = False
_current_cfg : dict = {}

# ── helpers ────────────────────────────────────────────────────────────────────

def _kill(proc: subprocess.Popen):
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass

def stop_all():
    global world_proc, robot_procs, _paused
    with lock:
        if world_proc:
            _kill(world_proc)
            world_proc = None
        for p in robot_procs:
            _kill(p)
        robot_procs.clear()
        _paused = False

def start_sim(robots: int = 3, tasks: int = 12, seed: int = 1,
              blocks: bool = True, delay: float = 0.25,
              kill_robot: str | None = None):
    """Stop any running sim then start fresh robot processes + world."""
    global world_proc, robot_procs, _paused, _current_cfg
    stop_all()

    _current_cfg = dict(robots=robots, tasks=tasks, seed=seed,
                        blocks=blocks, delay=delay, kill_robot=kill_robot)

    env = {**os.environ, "MQTT_HOST": "127.0.0.1", "PYTHONUNBUFFERED": "1"}

    # start robot processes (one per robot id)
    with lock:
        for rid in range(robots):
            p = subprocess.Popen(
                [sys.executable, "mqtt_robot.py", str(rid)],
                cwd=SIM, env=env
            )
            robot_procs.append(p)

    # wait long enough for all robots to connect and announce themselves
    time.sleep(2.5)

    cmd = [
        sys.executable, "mqtt_world.py",
        "--robots", str(robots),
        "--tasks",  str(tasks),
        "--seed",   str(seed),
        "--delay",  str(delay),
    ]
    if blocks:
        cmd.append("--blocks")
    if kill_robot:
        cmd += ["--kill", kill_robot]

    with lock:
        world_proc = subprocess.Popen(cmd, cwd=SIM, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

# ── request models ─────────────────────────────────────────────────────────────

class ControlCmd(BaseModel):
    action: str                      # pause | play | stop | reset | start
    robots: int    = 3
    tasks: int     = 12
    seed: int      = 1
    blocks: bool   = True
    delay: float   = 0.25
    kill_robot: str | None = None    # e.g. "1@10"

class StatusResp(BaseModel):
    running: bool
    paused: bool
    config: dict

# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/status", response_model=StatusResp)
def status():
    with lock:
        running = world_proc is not None and world_proc.poll() is None
        return StatusResp(running=running, paused=_paused, config=_current_cfg)

@app.post("/api/control")
def control(cmd: ControlCmd):
    global _paused

    if cmd.action in ("start", "reset"):
        # launch in background so the HTTP response returns immediately
        t = threading.Thread(
            target=start_sim,
            kwargs=dict(
                robots=cmd.robots, tasks=cmd.tasks, seed=cmd.seed,
                blocks=cmd.blocks, delay=cmd.delay, kill_robot=cmd.kill_robot
            ),
            daemon=True
        )
        t.start()
        return {"status": "starting"}

    elif cmd.action == "pause":
        with lock:
            if world_proc and world_proc.poll() is None:
                try:
                    psutil.Process(world_proc.pid).suspend()
                    _paused = True
                except Exception as e:
                    return {"status": "error", "detail": str(e)}
        return {"status": "paused"}

    elif cmd.action == "play":
        with lock:
            if world_proc and world_proc.poll() is None:
                try:
                    psutil.Process(world_proc.pid).resume()
                    _paused = False
                except Exception as e:
                    return {"status": "error", "detail": str(e)}
        return {"status": "running"}

    elif cmd.action == "stop":
        stop_all()
        return {"status": "stopped"}

    return {"status": "unknown_action"}

# ── auto-start on launch ───────────────────────────────────────────────────────

@app.on_event("startup")
def _auto_start():
    threading.Thread(
        target=start_sim,
        kwargs=dict(robots=3, tasks=12, seed=1, blocks=True, delay=0.25),
        daemon=True
    ).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081, log_level="info")
