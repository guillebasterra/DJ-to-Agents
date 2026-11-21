"""Drive the real web client in headless Chrome (autoplay allowed, audio muted),
for scripted runs and screenshots. The browser still does all audio capture.

usage: headless_run.py URL WAIT_SECONDS JS_EXPR [screenshot.png] ["WAIT::JS" ...]
e.g.   headless_run.py "http://localhost:5174/?track=0&condition=talk&reset=1" 345 "window.__debug.chunks"
"""
import asyncio, base64, json, subprocess, sys, tempfile, time, urllib.request
import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = int(__import__("os").environ.get("CDP_PORT", "9377"))

async def main(url, wait, expr, shot=None, steps=()):
    prof = tempfile.mkdtemp(prefix="cdp-")
    proc = subprocess.Popen([CHROME, "--headless=new", "--use-angle=metal", "--enable-gpu", "--hide-scrollbars",
        "--window-size=1280,800", "--autoplay-policy=no-user-gesture-required", "--mute-audio",
        f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json")); break
            except Exception: time.sleep(0.2)
        wsurl = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
        async with websockets.connect(wsurl, max_size=None, ping_interval=None) as ws:
            n = 0
            async def call(method, **params):
                nonlocal n; n += 1
                await ws.send(json.dumps({"id": n, "method": method, "params": params}))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == n: return m.get("result", m)
                    if m.get("method") == "Runtime.exceptionThrown": print("EXC", json.dumps(m["params"])[:600])
                    if m.get("method") == "Runtime.consoleAPICalled" and m["params"]["type"] in ("error", "warning"):
                        print("CONSOLE", [a.get("value") or a.get("description") for a in m["params"]["args"]])
            await call("Runtime.enable"); await call("Page.enable")
            await call("Page.navigate", url=url)
            async def ev(e):
                r = await call("Runtime.evaluate", expression=e, returnByValue=True, awaitPromise=True)
                print(json.dumps(r.get("result", {}).get("value", r))[:3000])
            await asyncio.sleep(wait); await ev(expr)
            for st in steps:
                w, e = st.split("::", 1); await asyncio.sleep(float(w)); await ev(e)
            if shot:
                r = await call("Page.captureScreenshot", format="png")
                open(shot, "wb").write(base64.b64decode(r["data"])); print(shot)
    finally:
        proc.terminate()

a = sys.argv
asyncio.run(main(a[1], float(a[2]), a[3], a[4] if len(a) > 4 and a[4] else None, a[5:]))
