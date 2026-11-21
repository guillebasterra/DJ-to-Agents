// Dev mode (?fake=1): random-walk agents and fake decisions, no backend.
// Emits the same init / physics / decision messages as the server.
const N = 100, R = 0.06, HZ = 30;
const ACTIONS = ['hold', 'push', 'yield', 'rest', 'dance'];
const LINES = ['let me in, this drop is everything to me', 'can I squeeze past? I have waited all night',
  'please, one step, I need the front', 'you look tired, swap with me?', 'I yielded to you before, my turn'];

export function connect(handlers) {
  const rand = (a, b) => a + Math.random() * (b - a);
  const agents = [];
  for (let i = 0; i < N; i++) {
    agents.push({ id: i, x: rand(0.05, 0.95), y: rand(0.05, 0.95), z: rand(0.05, 0.95), vx: 0, vy: 0, vz: 0,
      E: rand(0.2, 1), H: Math.random(), action: ACTIONS[i % 5], pressure: 0, nx: 0, ny: 0, nz: 0,
      pull: Math.random() });
  }
  handlers.init({ type: 'init', n_lanes: 10, agents: agents.map((a) => ({ id: a.id, archetype: 'between',
    lane: a.id % 10, k: 0.5, s: 0.5 })) });

  let t = 0, tick = 0, qid = 0, pending = [];
  const step = () => {
    const dt = 1 / HZ;
    t += dt;
    for (const a of agents) {
      // Random walk with a pull toward the hot spot, stronger for keen agents.
      a.vx += (rand(-1, 1) * 0.08 + (0.5 - a.x) * 0.05 * a.pull - a.vx) * dt * 2;
      a.vy += (rand(-1, 1) * 0.08 + (0.5 - a.y) * 0.05 * a.pull - a.vy) * dt * 2;
      a.vz += (rand(-1, 1) * 0.08 + (0.0 - a.z) * 0.06 * a.pull - a.vz) * dt * 2;
      a.x += a.vx * dt; a.y += a.vy * dt; a.z += a.vz * dt;
      a.H = Math.min(1, Math.max(0, a.H + rand(-1, 1) * 0.01));
      a.E = Math.min(1, Math.max(0.05, a.E + rand(-1, 1) * 0.005));
      a.pressure = 0; a.best = 0;
    }
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const a = agents[i], b = agents[j];
        const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
        const d = Math.hypot(dx, dy, dz) || 1e-6, over = 2 * R - d;
        if (over <= 0) continue;
        const ux = dx / d, uy = dy / d, uz = dz / d, h = over * 0.25;
        a.x -= ux * h; a.y -= uy * h; a.z -= uz * h;
        b.x += ux * h; b.y += uy * h; b.z += uz * h;
        const p = over / (2 * R);
        a.pressure += p; b.pressure += p;
        if (over > a.best) { a.best = over; a.nx = ux; a.ny = uy; a.nz = uz; }
        if (over > b.best) { b.best = over; b.nx = -ux; b.ny = -uy; b.nz = -uz; }
      }
    }
    for (const a of agents) {
      a.x = Math.min(1 - R, Math.max(R, a.x));
      a.y = Math.min(1 - R, Math.max(R, a.y));
      a.z = Math.min(1 - R, Math.max(R, a.z));
    }
    const r = (x) => Math.round(x * 1000) / 1000;
    handlers.physics({ type: 'physics', t, agents: agents.map((a) => [a.id, r(a.x), r(a.y), r(a.z), r(a.vx),
      r(a.vy), r(a.vz), r(a.E), 0, r(a.H), a.action, r(a.pressure), r(a.nx), r(a.ny), r(a.nz)]) });
  };

  const decide = () => {
    tick++;
    for (const a of agents) if (Math.random() < 0.3) a.action = ACTIONS[(Math.random() * 5) | 0];
    const answers = pending.map((id) => ({ id, answer: Math.random() < 0.5 ? 'yes' : 'no' }));
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
      const id = `q${++qid}`;
      pending.push(id);
      asks.push({ id, from: from.id, to: to.id, text: LINES[qid % LINES.length], answer: 'pending' });
    }
    handlers.decision({ type: 'decision', t, condition: 'talk', tick, house: { section: tick % 8 > 5 ? 'drop' : 'groove', w: 1 },
      rings: { 1: { section: 'build', drop_eta: 'next_8_bars', p: 0.72 } }, asks, answers });
  };

  setInterval(step, 1000 / HZ);
  setInterval(decide, 3000);
  return { open: true, fake: true, send() {}, sendBinary() {} };
}

// Stand-in music features while no track is playing, so the crowd still pulses.
export function fakeMusic(f, now) {
  const beat = (now * 2) % 1;
  f.energy = 0.55 + 0.4 * Math.sin(now * 0.3);
  f.kickEnv = f.energy > 0.4 ? Math.exp(-beat * 0.5 / 0.06) : 0;
  return f;
}
