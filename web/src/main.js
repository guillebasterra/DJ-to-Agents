import { Plate } from './plate.js';
import { Overlay } from './overlay.js';
import { AudioEngine } from './audio.js';
import { initUI } from './ui.js';
import * as ws from './ws.js';
import * as fake from './fake.js';

const FAKE = new URLSearchParams(location.search).has('fake');
const FLAG = { dance: 1 };

const plate = new Plate(document.getElementById('plate'), document.getElementById('grain'));
const overlay = new Overlay(document.getElementById('overlay'), plate);
const state = { condition: 'talk', tick: 0, asksPerTick: 0, section: '' };

// Last two physics frames, keyed by agent id, for interpolation.
let prev = new Map(), cur = new Map(), curAt = 0, frameGap = 1 / 30;
const view = [];          // interpolated agents, reused every frame
const byId = new Map();

const handlers = {
  init() { prev = new Map(); cur = new Map(); },
  physics(frame) {
    const now = performance.now() / 1000;
    frameGap = Math.min(0.25, Math.max(1 / 60, 0.8 * frameGap + 0.2 * (now - curAt)));
    curAt = now;
    prev = cur;
    cur = new Map();
    for (const a of frame.agents) cur.set(a[0], a);
  },
  decision(frame) {
    state.condition = frame.condition;
    state.tick = frame.tick;
    state.asksPerTick = (frame.asks || []).length;
    state.section = frame.house ? frame.house.section : '';
    overlay.onDecision(frame, performance.now() / 1000);
  },
};

const net = (FAKE ? fake : ws).connect(handlers);
const audio = new AudioEngine({
  onChunk: (buf) => net.sendBinary(buf),
  onSeek: () => net.send({ type: 'control', action: 'seek' }),
});
const ui = initUI({ audio, net, overlay, state });
setInterval(() => { if (audio.source) net.send(audio.clock()); }, 250);

// Real happiness mostly lives in 0..0.5 (u is divided by 3), so stretch it
// over the whole blue -> red -> white range for display only.
const showH = (h) => 1 - Math.exp(-4 * h);
const lerp = (a, b, t) => a + (b - a) * t;
let fps = 60, last = performance.now() / 1000, slowSince = 0;

function frame() {
  const now = performance.now() / 1000;
  const dt = now - last;
  last = now;
  fps += (1 / Math.max(dt, 1e-3) - fps) * 0.05;

  let music = audio.update(now);
  if (FAKE && !audio.playing) music = fake.fakeMusic(music, now);

  // Linear interpolation between the last two physics frames.
  const alpha = Math.min(1, (now - curAt) / frameGap);
  let n = 0, sumH = 0, sumE = 0;
  byId.clear();
  for (const [id, c] of cur) {
    const p = prev.get(id) || c;
    const v = view[n] || (view[n] = {});
    v.id = id;
    v.x = lerp(p[1], c[1], alpha); v.y = lerp(p[2], c[2], alpha); v.z = lerp(p[3], c[3], alpha);
    v.vx = c[4]; v.vy = c[5]; v.vz = c[6];
    v.E = lerp(p[7], c[7], alpha);
    v.rawH = lerp(p[9], c[9], alpha);
    v.H = FAKE ? v.rawH : showH(v.rawH);
    v.action = c[10];
    v.pressure = lerp(p[11], c[11], alpha);
    v.nx = c[12]; v.ny = c[13]; v.nz = c[14];
    v.flags = FLAG[c[10]] || 0;
    sumH += v.rawH; sumE += v.E;
    byId.set(id, v);
    n++;
  }
  view.length = n;

  plate.render(view, music, now);
  overlay.draw(view, byId, now);

  // Performance fallback: halve the dots if we sit below 50 fps for 3 s.
  if (fps < 50 && now > 5) {
    slowSince ||= now;
    if (now - slowSince > 3) { plate.halvePoints(); slowSince = 0; }
  } else slowSince = 0;

  ui.stats([
    `${state.condition}  tick ${state.tick}  ${state.section}`,
    `mean H ${(sumH / (n || 1)).toFixed(2)}  mean E ${(sumE / (n || 1)).toFixed(2)}`,
    `asks/tick ${state.asksPerTick}`,
    `energy ${music.energy.toFixed(2)}  pcm chunks ${audio.chunks}`,
    `${fps.toFixed(0)} fps  ${plate.pointBudget} dots${net.open ? '' : '  (no backend)'}`,
  ]);
  window.__debug = { fps, n, chunks: audio.chunks, music, points: plate.pointBudget, audio };
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
