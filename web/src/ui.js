// Keys, the input picker and the stats corner.
const trackUrls = import.meta.glob('../../tracks/*.{mp3,wav,m4a,flac,ogg}', { eager: true, query: '?url', import: 'default' });
const runUrls = import.meta.glob('../../runs/*/session.wav', { eager: true, query: '?url', import: 'default' });

const CONDITIONS = { 1: 'shove', 2: 'silent', 3: 'talk' };

export function initUI({ audio, net, overlay, state }) {
  const picker = document.getElementById('picker');
  const stats = document.getElementById('stats');
  const hint = document.getElementById('hint');
  hint.textContent = 'I input   space play/pause   1/2/3 shove/silent/talk   L labels   D stats';

  const choose = async (kind, arg, label) => {
    picker.hidden = true;
    try {
      const src = await audio.setSource(kind, arg, label);
      net.send({ type: 'control', source: kind, label });
      if (src.el) await src.el.play();
      hint.style.display = 'none';
    } catch (e) {
      hint.style.display = 'block';
      hint.textContent = `could not start ${label}: ${e.message}   (I to pick another input)`;
    }
  };

  const showPicker = async () => {
    picker.innerHTML = '';
    const section = (title) => {
      const h = document.createElement('h1');
      h.textContent = title;
      picker.append(h);
    };
    const item = (text, fn) => {
      const b = document.createElement('button');
      b.textContent = text;
      b.onclick = fn;
      picker.append(b);
    };
    const name = (path) => path.split('/').slice(-1)[0];
    section('Tracks');
    for (const [path, url] of Object.entries(trackUrls)) item(name(path), () => choose('file', url, name(path)));
    if (!Object.keys(trackUrls).length) item('(put an MP3 in tracks/)', () => {});
    if (Object.keys(runUrls).length) section('Recorded sessions');
    for (const [path, url] of Object.entries(runUrls)) {
      const run = path.split('/').slice(-2)[0];
      item(run, () => choose('file', url, run));
    }
    // Live inputs (BlackHole 2ch, the mixer's USB...). Labels only appear once
    // the browser has microphone permission, so ask for it on demand.
    section('Live input');
    let inputs = [];
    try {
      inputs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'audioinput');
    } catch (e) { /* no media devices in this browser */ }
    if (inputs.some((d) => d.label)) {
      for (const d of inputs) item(d.label, () => choose('live', d.deviceId, d.label));
    } else {
      item('allow audio input to list devices...', async () => {
        try {
          const s = await navigator.mediaDevices.getUserMedia({ audio: true });
          s.getTracks().forEach((t) => t.stop());
        } catch (e) { /* denied: the list stays empty */ }
        showPicker();
      });
    }
    picker.hidden = false;
  };

  addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey) return;
    const k = e.key.toLowerCase();
    if (k === ' ') { e.preventDefault(); audio.source ? audio.toggle() : showPicker(); }
    else if (CONDITIONS[k]) { state.condition = CONDITIONS[k]; net.send({ type: 'control', condition: CONDITIONS[k] }); }
    else if (k === 'l') overlay.labels = !overlay.labels;
    else if (k === 'd') stats.style.display = stats.style.display === 'block' ? 'none' : 'block';
    else if (k === 'i') picker.hidden ? showPicker() : (picker.hidden = true);
    else if (k === 'r') net.send({ type: 'control', action: 'reset' });
    else if (k === 'escape') picker.hidden = true;
  });

  // Dev hook for scripted runs: ?track=0 starts the first track without the
  // picker (needs a browser that allows autoplay, e.g. headless Chrome);
  // &condition=silent&reset=1 sets the condition and resets the crowd first.
  const params = new URLSearchParams(location.search);
  if (params.has('track')) {
    const [path, url] = Object.entries(trackUrls)[+params.get('track')] || [];
    const start = () => {
      if (!net.open) return setTimeout(start, 100);
      if (params.has('condition')) net.send({ type: 'control', condition: params.get('condition') });
      if (params.has('reset')) net.send({ type: 'control', action: 'reset' });
      if (url) choose('file', url, path.split('/').slice(-1)[0]);
    };
    start();
  }

  return {
    stats(lines) { if (stats.style.display === 'block') stats.textContent = lines.join('\n'); },
  };
}
