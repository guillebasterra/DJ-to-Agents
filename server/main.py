"""Phase 0 skeleton: WebSocket echo for JSON and binary."""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            msg = await sock.receive()
            if msg.get("bytes") is not None:
                await sock.send_bytes(msg["bytes"])
            elif msg.get("text") is not None:
                await sock.send_text(msg["text"])
            else:
                break
    except WebSocketDisconnect:
        pass
