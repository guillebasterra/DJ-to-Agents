"""Record short silent clips of given stretches of the track: drive the web
client in headless Chrome and grab frames (ffmpeg makes the mp4s).

usage: record_clips.py URL OUT_PREFIX NAME:START:SECONDS [NAME:START:SECONDS ...]
e.g.   record_clips.py "http://localhost:5174/?track=0&condition=talk&reset=1&t=100" docs/pass3 \
           breakdown:168:7 build:179:7 drop:188:7
Needs the backend (8001) and the client the URL points at. No audio is written."""
import asyncio, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = int(os.environ.get("CDP_PORT", "9398"))
SIZE = os.environ.get("CLIP_SIZE", "1280,720")


async def main(url, prefix, *segments):
    segments = sorted(((n, float(s), float(d)) for n, s, d in (x.split(":") for x in segments)), key=lambda x: x[1])
    proc = subprocess.Popen([CHROME, "--headless=new", "--use-angle=metal", "--enable-gpu", "--hide-scrollbars",
        f"--window-size={SIZE}", "--autoplay-policy=no-user-gesture-required", "--mute-audio",
        f"--remote-debugging-port={PORT}", f"--user-data-dir={tempfile.mkdtemp(prefix='clips-')}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json")); break
            except Exception:
                time.sleep(0.2)
        page = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
        async with websockets.connect(page, max_size=None, ping_interval=None) as ws:
            n = 0
            async def call(method, **params):
                nonlocal n; n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == n:
                        return m.get("result", m)
            async def ev(expr):
                r = await call("Runtime.evaluate", expression=expr, returnByValue=True)
                return r.get("result", {}).get("value")
            await call("Page.navigate", url=url)
            await asyncio.sleep(3)
            for name, start, seconds in segments:
                while (await ev("window.__debug.audio.time") or 0.0) < start:
                    await asyncio.sleep(0.25)
                frames = tempfile.mkdtemp(prefix="clip-frames-")
                t0, i = await ev("window.__debug.audio.time"), 0
                while True:
                    r = await call("Page.captureScreenshot", format="jpeg", quality=90)
                    open(os.path.join(frames, f"{i:05d}.jpg"), "wb").write(base64.b64decode(r["data"]))
                    i += 1
                    t1 = await ev("window.__debug.audio.time")
                    if t1 - t0 >= seconds:
                        break
                info = await ev("JSON.stringify([Math.round(window.__debug.fps), window.__debug.sections, window.__debug.state.section])")
                out = f"{prefix}_{name}.mp4"
                subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-framerate", f"{i / (t1 - t0):.4f}", "-i",
                    os.path.join(frames, "%05d.jpg"), "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "24", "-r", "30", out])
                print(f"{out}: {i} frames, {i / (t1 - t0):.1f} captured fps, track {t0:.1f}-{t1:.1f} s, page {info}")
                shutil.rmtree(frames, ignore_errors=True)
    finally:
        proc.terminate()


asyncio.run(main(*sys.argv[1:]))
