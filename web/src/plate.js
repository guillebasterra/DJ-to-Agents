// The plate renderer (three.js): pigment on warm paper. Three full-screen
// passes: (1) all bodies at once, as soft cells that flatten against each other
// with a paper gap (shaders/bodies.frag.glsl); (2) a decaying trail buffer keeps
// smears of where they have been; (3) the paper pass composites
// out = paper * (1 - pigment) with grain.
import * as THREE from 'three';
import { PAPER, HappinessScale, happinessColor } from './palette.js';
import screenVert from './shaders/screen.vert.glsl?raw';
import bodiesFrag from './shaders/bodies.frag.glsl?raw';
import trailFrag from './shaders/trail.frag.glsl?raw';
import paperFrag from './shaders/paper.frag.glsl?raw';

// A long lens from well back: little perspective, so the box reads as a plate
// and the calm crowd at the back still spreads across the frame.
const CAMERA = new THREE.Vector3(0.5, 0.5, -5.0);
const LOOK_AT = new THREE.Vector3(0.5, 0.5, 0.5);
const FOV = 13.2;
const DRIFT = 0.06;
const PUSH_IN = 0.35;         // camera creeps toward the glass on the drop
const TRAIL_DECAY = 0.985;    // per 1/60 s
const TRAIL_ADVECT = 0.0012;  // per 1/60 s, toward the vanishing point
const NEAR_SCALE = 1.6, FAR_SCALE = 0.62;    // drawn larger than the physical radius (soft edges overlap and flatten); bigger by the glass
const DEPTH_BIAS = 7.0;       // a body one diameter nearer the glass fully covers the one behind
const HOT = { x: [0.15, 0.85], y: [0.2, 0.8] };   // server/config.py HOT_X, HOT_Y

// Spring-dampers (all underdamped, so bodies jiggle and settle).
const GLASS = { k: 110, c: 10 };
const MODES = [                       // surface wobble modes 2, 3, 4
  { n: 2, w: 13, z: 0.16 }, { n: 3, w: 19, z: 0.18 }, { n: 4, w: 26, z: 0.22 },
];
const MODE_MAX = 0.14;

export class Plate {
  constructor(canvas, maxAgents = 100) {
    this.canvas = canvas;
    this.max = maxAgents;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: 'high-performance' });
    this.renderer.autoClear = false;
    this.camera = new THREE.PerspectiveCamera(FOV, 1, 0.5, 12);
    this.pushIn = 0;
    this.pushTarget = 0;
    this.quality = 1;              // pigment resolution, relative to CSS pixels (the pigment is soft; the grain is added at device resolution)
    this.scale = new HappinessScale();
    this.bodies = new Map();      // agent id -> spring state
    this.colors = new Map();      // agent id -> css color (for the chat panel)
    this.lastTime = 0;
    this.lastKick = 0;
    this.margin = 0;              // CSS pixels on the right covered by the chat panel

    const pass = (fragmentShader, uniforms) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3, uniforms, vertexShader: screenVert, fragmentShader, depthTest: false, depthWrite: false,
      }));
      mesh.frustumCulled = false;
      return new THREE.Scene().add(mesh);
    };
    const arr = () => ({ value: new Float32Array(maxAgents * 4) });
    this.bodyUniforms = { uCount: { value: 0 }, uA: arr(), uB: arr(), uC: arr(), uD: arr(),
      uRes: { value: new THREE.Vector2(1, 1) }, uTime: { value: 0 } };
    this.bodyScene = pass(bodiesFrag, this.bodyUniforms);
    this.trailUniforms = { tPigment: { value: null }, tPrev: { value: null }, uDecay: { value: TRAIL_DECAY },
      uAdvect: { value: TRAIL_ADVECT } };
    this.paperUniforms = { tPigment: { value: null }, tTrail: { value: null }, uTime: { value: 0 }, uAspect: { value: 1 },
      uPaper: { value: new THREE.Color(PAPER).convertLinearToSRGB() } };
    this.trailScene = pass(trailFrag, this.trailUniforms);
    this.paperScene = pass(paperFrag, this.paperUniforms);

    this.resize();
    addEventListener('resize', () => this.resize());
  }

  resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const w = innerWidth, h = innerHeight;
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    // Keep the whole front face of the box in view on narrow windows too.
    this.camera.fov = w / h < 1.25 ? 2 * Math.atan(Math.tan((FOV * Math.PI) / 360) * 1.25 / (w / h)) * 180 / Math.PI : FOV;
    // Center the plate in the space left of the chat panel.
    if (this.margin) this.camera.setViewOffset(w, h, this.margin / 2, 0, w, h);
    else this.camera.clearViewOffset();
    this.camera.updateProjectionMatrix();
    this.paperUniforms.uAspect.value = w / h;

    const fw = Math.max(2, Math.round(w * this.quality)), fh = Math.max(2, Math.round(h * this.quality));
    const opts = { type: THREE.HalfFloatType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter };
    for (const rt of [this.pigment, this.trailA, this.trailB]) if (rt) rt.dispose();
    this.pigment = new THREE.WebGLRenderTarget(fw, fh, { ...opts, depthBuffer: false });
    this.bodyUniforms.uRes.value.set(fw, fh);
    this.trailA = new THREE.WebGLRenderTarget(fw, fh, { ...opts, depthBuffer: false });
    this.trailB = new THREE.WebGLRenderTarget(fw, fh, { ...opts, depthBuffer: false });
  }

  setMargin(px) {
    if (px === this.margin) return;
    this.margin = px;
    this.resize();
  }

  // Performance fallback: render the pigment at lower resolution (the grain stays 1 px).
  degrade() {
    if (this.quality <= 0.5) return false;
    this.quality = Math.max(0.5, this.quality * 0.75);
    this.resize();
    return true;
  }

  // Per-agent soft-body state: glass press and three wobble modes, each on its
  // own spring-damper, plus a smoothed direction of travel so nothing pops.
  body(a, dt, kick) {
    let b = this.bodies.get(a.id);
    if (!b) {
      this.bodies.set(a.id, b = { g: 0, gv: 0, dx: 0, dy: 0, st: 0, ang: 0,
        pressure: a.pressure, vx: a.vx, vy: a.vy, vz: a.vz, phase: (a.id * 2.399) % 6.283,
        modes: MODES.map(() => ({ x: 0, v: 0 })) });
    }
    const steps = Math.max(1, Math.ceil(dt / 0.008)), h = dt / steps;
    // Pressed against the glass: fully flat at 0.62 r from it, round again by 1.2 r.
    const glassTo = Math.min(1, Math.max(0, 1 - (a.z - 0.62 * a.r) / (0.58 * a.r)));

    // What excites the wobble: impacts, changes of velocity, and the kick.
    const impact = Math.max(0, a.pressure - b.pressure);
    const jolt = Math.hypot(a.vx - b.vx, a.vy - b.vy, a.vz - b.vz);
    if (impact > 0.02) b.ang = Math.atan2(a.ny, -a.nx);      // screen x runs opposite to world x
    else if (kick > 0) b.ang = Math.PI / 2;
    b.pressure = a.pressure; b.vx = a.vx; b.vy = a.vy; b.vz = a.vz;

    for (let i = 0; i < MODES.length; i++) {
      const m = b.modes[i], { n, w, z } = MODES[i];
      m.v += (impact * 2.2 + kick * 0.9 + jolt * 1.5) * w / n;
      for (let k = 0; k < steps; k++) {
        m.v += (-w * w * m.x - 2 * z * w * m.v) * h;
        m.x += m.v * h;
      }
      m.x = Math.min(MODE_MAX, Math.max(-MODE_MAX, m.x));
    }
    for (let k = 0; k < steps; k++) {
      b.gv += (GLASS.k * (glassTo - b.g) - GLASS.c * b.gv) * h;
      b.g += b.gv * h;
    }
    // Direction of travel on screen, eased; the tail grows with speed.
    const ease = Math.min(1, dt * 6);
    const speed = Math.hypot(a.vx, a.vy);
    if (speed > 1e-4) {
      b.dx += (-a.vx / speed - b.dx) * ease; b.dy += (a.vy / speed - b.dy) * ease;
    }
    b.st += (Math.min(0.4, speed * 3.0) - b.st) * Math.min(1, dt * 4);
    return b;
  }

  // agents: [{id, x, y, z, vx, vy, vz, r, E, H, pressure, nx, ny, nz, action}], H is raw happiness.
  // music: {energy, bass, sub, kickEnv, kickBob, sec: [p(build), p(drop), p(breakdown), intensity]}.
  render(agents, music, time) {
    const dt = Math.min(0.05, Math.max(0.001, time - this.lastTime));
    this.lastTime = time;
    const kicked = music.kickEnv > this.lastKick + 0.4;
    this.lastKick = music.kickEnv;
    const U = this.bodyUniforms, A = U.uA.value, B = U.uB.value, C = U.uC.value, D = U.uD.value;
    const n = Math.min(agents.length, this.max);
    this.scale.update(agents.map((a) => a.H), dt);
    const I = music.sec[3] ?? 0.5;
    const bass = Math.max(music.bass || 0, music.sub || 0);
    const p = this._p ||= {};

    // Camera first: bodies are placed in screen space.
    this.pushIn += ((this.pushTarget ? PUSH_IN : 0) - this.pushIn) * Math.min(1, dt * 0.6);
    this.camera.position.set(
      CAMERA.x + DRIFT * Math.sin(time * 0.11),
      CAMERA.y + DRIFT * Math.sin(time * 0.077 + 1.3),
      CAMERA.z + this.pushIn,
    );
    this.camera.lookAt(LOOK_AT);
    this.camera.updateMatrixWorld();

    for (let i = 0; i < n; i++) {
      const a = agents[i], o = i * 4;
      const jitter = ((a.id * 0.6180339) % 1) * 2 - 1;
      const [r, g, bl] = happinessColor(this.scale.map(a.H), jitter);
      this.colors.set(a.id, `rgb(${(r * 255) | 0},${(g * 255) | 0},${(bl * 255) | 0})`);

      // How hard the bass shakes this body: loud bass, close to the booth, energy to spare.
      const hx = Math.min(HOT.x[1], Math.max(HOT.x[0], a.x)), hy = Math.min(HOT.y[1], Math.max(HOT.y[0], a.y));
      const prox = Math.max(0, 1 - Math.hypot(a.x - hx, a.y - hy, a.z) / 1.03);
      const shake = bass * prox * prox * a.E * (0.25 + 0.75 * I);
      const dancer = a.action === 'dance' ? 1 : 0;
      const b = this.body(a, dt, kicked ? music.energy * a.E * (0.25 + 0.75 * prox) * (0.3 + 0.7 * I) * (1 + 0.5 * dancer) : 0);

      // Vibration: a fast buzz with the bass and a bounce and a pulse on every
      // kick, strongest at the front on a drop. Calm crowds only sway, slowly.
      const buzz = a.r * 0.085 * shake;
      const bounce = a.r * music.kickBob * a.E * (0.06 + 0.10 * dancer + 0.50 * shake);
      const sway = a.r * Math.sin(time * (0.9 + 1.5 * I) + b.phase) * (0.16 * (1 - I) + 0.10 * dancer * I);
      const pulse = 1 + music.kickEnv * (0.05 * music.energy * a.E + 0.20 * shake);

      this.project(a.x + sway + buzz * Math.sin(time * 107 + b.phase * 3), a.y + bounce + buzz * Math.sin(time * 131 + b.phase * 5),
        a.z, a.r, p);
      const press = Math.min(1.15, Math.max(0, b.g));
      A[o] = p.x / innerHeight; A[o + 1] = 1 - p.y / innerHeight;
      A[o + 2] = p.r / innerHeight * pulse * (1 + 0.22 * press); A[o + 3] = a.z * DEPTH_BIAS;
      // Energy sets how much pigment there is; far bodies fade toward the paper.
      const depth = Math.min(1, Math.max(0, a.z));
      B[o] = b.dx; B[o + 1] = b.dy; B[o + 2] = b.st;
      B[o + 3] = (0.34 + 0.66 * a.E) * (1 - 0.68 * depth * depth * (3 - 2 * depth)) * (1 + 0.12 * press);
      C[o] = r; C[o + 1] = g; C[o + 2] = bl; C[o + 3] = b.phase;
      D[o] = b.modes[0].x; D[o + 1] = b.modes[1].x; D[o + 2] = b.modes[2].x; D[o + 3] = b.ang;
    }
    U.uCount.value = n;
    U.uTime.value = time % 1000;

    const gl = this.renderer, frames = dt * 60;
    // 1. Bodies.
    gl.setRenderTarget(this.pigment);
    gl.render(this.bodyScene, this.camera);
    // 2. Trails (ping-pong).
    this.trailUniforms.tPigment.value = this.pigment.texture;
    this.trailUniforms.tPrev.value = this.trailA.texture;
    this.trailUniforms.uDecay.value = TRAIL_DECAY ** frames;
    this.trailUniforms.uAdvect.value = TRAIL_ADVECT * frames;
    gl.setRenderTarget(this.trailB);
    gl.render(this.trailScene, this.camera);
    [this.trailA, this.trailB] = [this.trailB, this.trailA];
    // 3. Paper.
    this.paperUniforms.tPigment.value = this.pigment.texture;
    this.paperUniforms.tTrail.value = this.trailA.texture;
    this.paperUniforms.uTime.value = time % 1000;
    gl.setRenderTarget(null);
    gl.render(this.paperScene, this.camera);
  }

  // World position -> CSS pixels (+ on-screen radius for a body of world radius r), for the overlay.
  project(x, y, z, r = 0.05, out = {}) {
    const v = (this._v ||= new THREE.Vector3()).set(x, y, z);
    const dist = v.distanceTo(this.camera.position);
    v.project(this.camera);
    out.x = (v.x * 0.5 + 0.5) * innerWidth;
    out.y = (-v.y * 0.5 + 0.5) * innerHeight;
    out.visible = v.z > -1 && v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    out.dist = dist;
    const boost = NEAR_SCALE + (FAR_SCALE - NEAR_SCALE) * Math.min(1, Math.max(0, z));
    out.r = r * boost / dist / Math.tan((this.camera.fov * Math.PI) / 360) * innerHeight * 0.5;
    return out;
  }
}
