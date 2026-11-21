// WebSocket to the backend. Reconnects forever; rendering never waits on it.
export function connect(handlers) {
  const api = { open: false, send() {}, sendBinary() {} };
  let sock;
  const open = () => {
    sock = new WebSocket(`ws://${location.hostname}:8001/ws`);
    sock.onopen = () => { api.open = true; handlers.open && handlers.open(); };
    sock.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      const h = handlers[msg.type];
      if (h) h(msg);
    };
    sock.onclose = () => { api.open = false; setTimeout(open, 1000); };
    sock.onerror = () => sock.close();
  };
  api.send = (obj) => { if (api.open) sock.send(JSON.stringify(obj)); };
  api.sendBinary = (buf) => { if (api.open) sock.send(buf); };
  open();
  return api;
}
