"""Record a demo clip: drive the web client in headless Chrome, grab frames for a
stretch of the track and mux them with that stretch of audio (ffmpeg).

usage: record_demo.py TRACK_FILE [start=140] [seconds=60] [condition=talk] [out=runs/demo.mp4]
Needs the backend (8001) and the dev server (5174). The clip contains the track's
audio, so it is written under runs/ (gitignored): don't commit it."""
import asyncio, base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9399


async def main(track, start=140.0, seconds=60.0, condition="talk", out="runs/demo.mp4"):
    start, seconds = float(start), float(seconds)
    frames = tempfile.mkdtemp(prefix="demo-frames-")
    proc = subprocess.Popen([CHROME, "--headless=new", "--use-angle=metal", "--enable-gpu", "--hide-scrollbars",
        "--window-size=1280,720", "--autoplay-policy=no-user-gesture-required", "--mute-audio",
        f"--remote-debugging-port={PORT}", f"--user-data-dir={tempfile.mkdtemp(prefix='demo-')}", "about:blank"],
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
            async def now():
                r = await call("Runtime.evaluate", expression="window.__debug.audio.time", returnByValue=True)
                return r["result"].get("value", 0.0)
            await call("Page.navigate", url=f"http://localhost:5174/?track=0&condition={condition}&reset=1")
            await asyncio.sleep(3)
            while await now() < start:
                await asyncio.sleep(0.5)
            t0, i = await now(), 0
            while True:
                r = await call("Page.captureScreenshot", format="jpeg", quality=88)
                open(os.path.join(frames, f"{i:05d}.jpg"), "wb").write(base64.b64decode(r["data"]))
                i += 1
                t1 = await now()
                if t1 - t0 >= seconds:
                    break
        fps = i / (t1 - t0)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-framerate", f"{fps:.4f}", "-i",
            os.path.join(frames, "%05d.jpg"), "-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", track,
            "-map", "0:v", "-map", "1:a", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "27", "-r", "30", "-c:a", "aac", "-shortest", out])
        print(f"{out}: {i} frames at {fps:.1f} fps, track {t0:.1f}-{t1:.1f} s")
        shutil.rmtree(frames, ignore_errors=True)
    finally:
        proc.terminate()


asyncio.run(main(*sys.argv[1:]))
