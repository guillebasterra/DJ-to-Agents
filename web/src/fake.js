// Dev mode (?fake=1): random-walk agents and fake decisions, no backend.
// Emits the same init / physics / asks / decision messages as the server.
const N = 100, R = 0.05, HZ = 30;
const ACTIONS = ['hold', 'push', 'yield', 'rest', 'dance'];
const SIZE = [1.2, 1.0, 0.85];
const LINES = ['let me in, this drop is everything to me', 'can I squeeze past? I have waited all night',
  'please, one step, I need the front', 'you look tired, swap with me?', 'I yielded to you before, my turn'];
// name, [p(build), p(drop), p(breakdown), intensity]
const SECTIONS = [['groove', [0.1, 0.1, 0.1, 0.6]], ['build', [0.6, 0.15, 0.05, 0.75]], ['drop', [0.15, 0.7, 0, 1]],
  ['breakdown', [0.05, 0, 0.7, 0.05]]];

export function connect(handlers) {
  const rand = (a, b) => a + Math.random() * (b - a);
  const agents = [];
  for (let i = 0; i < N; i++) {
    const size = SIZE[i % 3] * rand(0.9, 1.1);
    agents.push({ id: i, x: rand(0.1, 0.9), y: rand(0.1, 0.9), z: rand(0.1, 0.9), vx: 0, vy: 0, vz: 0,
      E: rand(0.1, 1), H: rand(0.05, 0.9), action: ACTIONS[i % 5], pressure: 0, nx: 0, ny: 0, nz: 0,
      pull: Math.random(), size, r: R * size });
  }
  handlers.init({ type: 'init', n_lanes: 10, condition: 'talk', agents: agents.map((a) => ({ id: a.id,
    archetype: 'between', lane: a.id % 10, k: 0.5, s: 0.5, size: a.size })) });

  let t = 0, tick = 0, qid = 0, pending = [], section = SECTIONS[0];
  const m = [0, 0, 0, 0.3];
  const step = () => {
    const dt = 1 / HZ;
    t += dt;
    for (let i = 0; i < 4; i++) m[i] += (section[1][i] - m[i]) * dt / 2.5;
    const zc = 0.74 - 0.59 * m[3];
    for (const a of agents) {
      // Random walk around a place in the crowd's depth band, nearer the glass for keen agents.
      const zt = zc - 0.2 * (2 * a.pull - 1), live = 0.05 + 0.08 * m[3];
      a.vx += (rand(-1, 1) * live - a.vx) * dt * 2;
      a.vy += (rand(-1, 1) * live - a.vy) * dt * 2;
      a.vz += (rand(-1, 1) * live + Math.max(-0.07, Math.min(0.07, (zt - a.z) * 0.6)) - a.vz) * dt * 2;
      a.x += a.vx * dt; a.y += a.vy * dt; a.z += a.vz * dt;
      a.H = Math.min(0.95, Math.max(0.03, a.H + rand(-1, 1) * 0.004 + (0.15 + 0.7 * m[3] * (1 - a.z) - a.H) * dt / 4));
      a.E = Math.min(1, Math.max(0.05, a.E + rand(-1, 1) * 0.004));
      a.r = R * a.size * (0.85 + 0.15 * a.E);
      a.pressure = 0; a.best = 0;
    }
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const a = agents[i], b = agents[j];
        const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
        const d = Math.hypot(dx, dy, dz) || 1e-6, over = a.r + b.r - d;
        if (over <= 0) continue;
        const ux = dx / d, uy = dy / d, uz = dz / d, h = over * 0.12;
        a.x -= ux * h; a.y -= uy * h; a.z -= uz * h;
        b.x += ux * h; b.y += uy * h; b.z += uz * h;
        const p = 2.5 * over / (a.r + b.r);
        a.pressure += p; b.pressure += p;
        if (over > a.best) { a.best = over; a.nx = ux; a.ny = uy; a.nz = uz; }
        if (over > b.best) { b.best = over; b.nx = -ux; b.ny = -uy; b.nz = -uz; }
      }
    }
    for (const a of agents) {
      a.x = Math.min(1 - a.r, Math.max(a.r, a.x));
      a.y = Math.min(1 - a.r, Math.max(a.r, a.y));
      a.z = Math.min(1 - a.r, Math.max(0.62 * a.r, a.z));
    }
    const r = (x) => Math.round(x * 1000) / 1000;
    handlers.physics({ type: 'physics', t, m: m.map(r), agents: agents.map((a) => [a.id, r(a.x), r(a.y), r(a.z),
      r(a.vx), r(a.vy), r(a.vz), r(a.E), 0, r(a.H), a.action, r(a.pressure), r(a.nx), r(a.ny), r(a.nz), r(a.r)]) });
  };

  const decide = () => {
    tick++;
    section = SECTIONS[Math.floor(tick / 4) % SECTIONS.length];
    for (const a of agents) if (Math.random() < 0.3) a.action = ACTIONS[(Math.random() * 5) | 0];
    const answers = pending.map((q) => ({ id: q.id, from: q.from, to: q.to, answer: Math.random() < 0.4 ? 'yes' : 'no' }));
    pending = [];
    const asks = [];
    for (let i = 0; i < 3; i++) {
      // Ask the nearest agent in front, like a blocked pusher would.
      const from = agents[(Math.random() * N) | 0];
      let to = null, best = 1e9;
      for (const b of agents) {
        const d = Math.hypot(b.x - from.x, b.y - from.y, b.z - from.z);
        if (b !== from && b.z < from.z && d < best) { best = d; to = b; }
      }
      if (!to) continue;
      const ask = { id: `q${++qid}`, from: from.id, to: to.id, text: LINES[qid % LINES.length], answer: 'pending' };
      pending.push(ask);
      asks.push(ask);
    }
    const chat = answers.map((a) => ({ k: 'answer', a: a.to, b: a.from, text: a.answer === 'yes' ? '✓ yields' : '✗ holds' }));
    chat.push({ k: 'move', a: (Math.random() * N) | 0, text: 'pushes hard' });
    chat.push({ k: 'ring', text: `ring ${1 + (tick % 5)} hears: ${section[0]} · drop next 8 bars (0.72)` });
    chat.push({ k: 'booth', text: `BOOTH: ${section[0]} (0.81)` });
    handlers.decision({ type: 'decision', t, condition: 'talk', tick, house: { section: section[0], w: 1 },
      rings: {}, asks: [], answers, chat });
    setTimeout(() => handlers.asks({ type: 'asks', asks }), 800);
  };

  setInterval(step, 1000 / HZ);
  setInterval(decide, 3000);
  return { open: true, fake: true, send() {}, sendBinary() {} };
}

// Stand-in music features while no track is playing, so the crowd still pulses.
export function fakeMusic(f, now) {
  const beat = (now * 2) % 1;
  f.energy = 0.55 + 0.4 * Math.sin(now * 0.3);
  f.bass = f.sub = f.energy;
  f.kickEnv = f.energy > 0.4 ? Math.exp(-beat * 0.5 / 0.06) : 0;
  f.kickBob = f.energy > 0.4 ? Math.exp(-beat * 0.5 / 0.14) : 0;
  return f;
}
