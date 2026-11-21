import { Plate } from './plate.js';
import { Overlay } from './overlay.js';
import { AudioEngine } from './audio.js';
import { initUI } from './ui.js';
import * as ws from './ws.js';
import * as fake from './fake.js';

const FAKE = new URLSearchParams(location.search).has('fake');

const plate = new Plate(document.getElementById('plate'));
const overlay = new Overlay(document.getElementById('overlay'), plate);
const state = { condition: 'talk', tick: 0, asksPerTick: 0, section: '' };

// Last two physics frames, keyed by agent id, for interpolation.
let prev = new Map(), cur = new Map(), curAt = 0, frameGap = 1 / 30;
let sections = [0, 0, 0, 0];   // smoothed p(build), p(drop), p(breakdown) from the house ear, and crowd intensity
const view = [];            // interpolated agents, reused every frame
const byId = new Map();
let ui = null;

const handlers = {
  init(frame) {
    prev = new Map(); cur = new Map();
    if (frame.condition && ui) ui.setMode(frame.condition);
    else if (frame.condition) state.condition = frame.condition;
  },
  physics(frame) {
    const now = performance.now() / 1000;
    frameGap = Math.min(0.25, Math.max(1 / 60, 0.8 * frameGap + 0.2 * (now - curAt)));
    curAt = now;
    prev = cur;
    cur = new Map();
    for (const a of frame.agents) cur.set(a[0], a);
    if (frame.m) sections = frame.m;
  },
  asks(frame) {
    overlay.onDecision(frame, performance.now() / 1000);
    for (const a of frame.asks) ui.say({ k: 'ask', a: a.from, b: a.to, text: a.text });
  },
  decision(frame) {
    ui.setMode(frame.condition);
    ui.newTick();
    state.tick = frame.tick;
    state.asksPerTick = (frame.asks || []).length;
    state.section = frame.house ? frame.house.section : '';
    plate.pushTarget = state.section === 'drop' ? 1 : 0;   // slow push-in on the drop
    overlay.onDecision(frame, performance.now() / 1000);
    for (const line of frame.chat || []) ui.say(line);
  },
};

const net = (FAKE ? fake : ws).connect(handlers);
const audio = new AudioEngine({
  onChunk: (buf) => net.sendBinary(buf),
  onSeek: () => net.send({ type: 'control', action: 'seek' }),
});
ui = initUI({ audio, net, overlay, plate, state });
setInterval(() => { if (audio.source) net.send(audio.clock()); }, 250);

const lerp = (a, b, t) => a + (b - a) * t;
let fps = 60, last = performance.now() / 1000, slowSince = 0;

function frame() {
  const now = performance.now() / 1000;
  const dt = now - last;
  last = now;
  fps += (1 / Math.max(dt, 1e-3) - fps) * 0.05;

  let music = audio.update(now);
  if (FAKE && !audio.playing) music = fake.fakeMusic(music, now);
  music.sec = sections;

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
    v.H = lerp(p[9], c[9], alpha);
    v.action = c[10];
    v.pressure = lerp(p[11], c[11], alpha);
    v.nx = c[12]; v.ny = c[13]; v.nz = c[14];
    v.r = lerp(p[15] || 0.05, c[15] || 0.05, alpha);
    sumH += v.H; sumE += v.E;
    byId.set(id, v);
    n++;
  }
  view.length = n;

  plate.render(view, music, now);
  overlay.draw(view, byId, now);

  // Performance fallback: lower the pigment resolution if we sit below 50 fps for 3 s.
  if (fps < 50 && now > 5) {
    slowSince ||= now;
    if (now - slowSince > 3) { plate.degrade(); slowSince = 0; }
  } else slowSince = 0;

  ui.stats([
    `${state.condition}  tick ${state.tick}  ${state.section}`,
    `mean H ${(sumH / (n || 1)).toFixed(2)}  mean E ${(sumE / (n || 1)).toFixed(2)}`,
    `intensity ${(sections[3] || 0).toFixed(2)}  build ${sections[0].toFixed(2)}  drop ${sections[1].toFixed(2)}  breakdown ${sections[2].toFixed(2)}`,
    `asks/tick ${state.asksPerTick}  energy ${music.energy.toFixed(2)}  pcm chunks ${audio.chunks}`,
    `${fps.toFixed(0)} fps  pigment x${plate.quality.toFixed(2)}${net.open ? '' : '  (no backend)'}`,
  ]);
  window.__debug = { fps, n, chunks: audio.chunks, music, quality: plate.quality, audio, sections, state };
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
