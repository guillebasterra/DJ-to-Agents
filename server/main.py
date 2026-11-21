"""FastAPI backend: one WebSocket, a 30 Hz physics loop and the ~3 s tick loop.
Run: python -m server.main --seed 1 --condition talk   (port 8001)"""
import argparse
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config as C, tick
from .audio import AudioBuffer
from .log import RunLog
from .physics import Physics
from .state import World

log = logging.getLogger("crowd")
CLOCK_TIMEOUT = 1.0   # no clock message for this long means playback stopped


class Session:
    def __init__(self, seed, condition):
        self.world = World(seed=seed, condition=condition)
        self.physics = Physics(self.world)
        self.audio = AudioBuffer()
        self.run = RunLog(self.world)
        self.clients = set()
        self.last_clock = 0.0
        self.driver = None    # the client whose audio is playing; other tabs' paused clocks are ignored
        self.tasks = set()    # in-flight Hydrogen asks
        self.generation = 0   # bumped when the run changes, so stale asks are dropped
        self.services = {}    # long-lived helpers (the Gemini client)
        self.memo = {}        # scratch state for the tick modules (word of mouth, pending asks)

    @property
    def playing(self):
        return self.world.playing and time.time() - self.last_clock < CLOCK_TIMEOUT

    def new_run(self):
        self.generation += 1
        self.run.close()
        self.run = RunLog(self.world)

    def reset(self):
        self.world.reset()
        self.physics = Physics(self.world)
        self.audio.clear()
        self.memo.clear()
        self.new_run()

    async def broadcast(self, frame):
        text = json.dumps(frame, separators=(",", ":"))
        # A stalled tab (backgrounded, or killed without closing its socket) must
        # not block the physics and tick loops: give each send a moment, then drop it.
        async def send(sock):
            try:
                await asyncio.wait_for(sock.send_text(text), 0.5)
            except Exception:
                self.clients.discard(sock)
                try:
                    await asyncio.wait_for(sock.close(), 0.5)    # so the tab reconnects
                except Exception:
                    pass
        await asyncio.gather(*(send(sock) for sock in list(self.clients)))

    def on_clock(self, msg, sock=None):
        w = self.world
        # Several tabs may be open. The first one that plays drives the clock and
        # the audio until it stops; other tabs only watch.
        if self.driver is not sock:
            if self.playing or not msg.get("playing"):
                return
            self.driver = sock
        self.last_clock = time.time()
        w.playing = bool(msg.get("playing"))
        w.t = float(msg.get("t", 0.0))
        w.dsp = msg.get("dsp") or {}
        kicks = int(w.dsp.get("kicks", 1 if w.dsp.get("kick") else 0))
        w.kick_times = [k for k in w.kick_times if 0 <= w.t - k < 5.0] + [w.t] * kicks

    async def on_control(self, msg):
        w = self.world
        if msg.get("condition") in C.CONDITIONS and msg["condition"] != w.condition:
            w.condition = msg["condition"]
            self.memo.clear()
            self.new_run()
        if "source" in msg:
            w.source = {"kind": msg["source"], "label": msg.get("label", "")}
            self.audio.clear()
            self.new_run()
        action = msg.get("action")
        if action == "reset":
            self.reset()
            await self.broadcast(w.init_frame())
        elif action == "seek":
            self.audio.clear()
            self.memo.pop("word", None)
        elif action == "pause":
            w.playing = False


S: Session = None


async def physics_loop():
    dt = 1.0 / C.PHYSICS_HZ
    loop = asyncio.get_running_loop()
    due = loop.time()
    i = 0
    while True:
        i += 1
        try:
            playing = S.playing
            if playing:
                S.physics.step(dt)
            # Keep frames flowing while paused (slower), so late joiners see the crowd.
            if S.clients and (playing or i % 6 == 0):
                await S.broadcast(S.physics.frame())
        except Exception:
            log.exception("physics step failed")
        due = max(due + dt, loop.time() - 0.1)
        await asyncio.sleep(max(0.0, due - loop.time()))


async def tick_loop():
    last = 0.0
    while True:
        await asyncio.sleep(0.05)
        if not S.playing or time.time() - last < C.TICK_SECONDS:
            continue
        last = time.time()
        try:
            await tick.run(S)
        except Exception:
            log.exception("tick failed")   # never crash the loop


@asynccontextmanager
async def lifespan(app):
    global S
    S = Session(int(os.environ.get("CROWD_SEED", "1")), os.environ.get("CROWD_CONDITION", "talk"))
    tasks = [asyncio.create_task(physics_loop()), asyncio.create_task(tick_loop())]
    yield
    for t in tasks:
        t.cancel()
    S.run.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"])


@app.get("/status")
def status():
    w = S.world
    return {"playing": S.playing, "t": w.t, "tick": w.tick, "condition": w.condition, "seed": w.seed,
            "buffer_seconds": round(S.audio.seconds, 2), "w": round(w.w, 3), "clients": len(S.clients),
            "run": S.run.dir.name if S.run.dir else None, "source": w.source}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    S.clients.add(sock)
    await sock.send_text(json.dumps(S.world.init_frame()))
    try:
        while True:
            msg = await sock.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                # Raw Int16 PCM, 16 kHz mono: only ever audio that is actually playing.
                if S.world.playing and S.driver is sock:
                    S.run.audio(S.audio.push(msg["bytes"]))
            elif msg.get("text"):
                data = json.loads(msg["text"])
                if data.get("type") == "clock":
                    S.on_clock(data, sock)
                elif data.get("type") == "control" and (S.driver is sock or not S.playing):
                    await S.on_control(data)
    except WebSocketDisconnect:
        pass
    finally:
        S.clients.discard(sock)


# A built copy of the web client (cd web && npx vite build --base=/app/), used by
# scripted runs so they don't reload when the dev server hot-updates.
_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "dist")
if os.path.isdir(_dist):
    app.mount("/app", StaticFiles(directory=_dist, html=True), name="app")


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--condition", choices=C.CONDITIONS, default="talk")
    args = ap.parse_args()
    os.environ["CROWD_SEED"] = str(args.seed)
    os.environ["CROWD_CONDITION"] = args.condition
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    uvicorn.run(app, host="127.0.0.1", port=C.PORT, log_level="warning")
