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
    const src = await audio.setSource(kind, arg, label);
    net.send({ type: 'control', source: kind, label });
    if (src.el) src.el.play();
    hint.style.display = 'none';
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

  // Dev hook: ?track=0 starts the first track without the picker (needs a
  // browser that allows autoplay, e.g. headless test runs).
  const auto = new URLSearchParams(location.search).get('track');
  if (auto !== null) {
    const [path, url] = Object.entries(trackUrls)[+auto] || [];
    if (url) choose('file', url, path.split('/').slice(-1)[0]);
  }

  return {
    stats(lines) { if (stats.style.display === 'block') stats.textContent = lines.join('\n'); },
  };
}
