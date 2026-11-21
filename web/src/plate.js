// The plate renderer (three.js): pigment on warm paper. Every agent is one
// billboard carrying a soft blob. Three passes: (1) blobs write pigment
// absorbance, depth-tested; (2) a decaying trail buffer keeps smears of where
// they have been; (3) the paper pass composites out = paper * exp(-A) with grain.
import * as THREE from 'three';
import { PAPER, HappinessScale, happinessColor } from './palette.js';
import blobVert from './shaders/blob.vert.glsl?raw';
import blobFrag from './shaders/blob.frag.glsl?raw';
import screenVert from './shaders/screen.vert.glsl?raw';
import trailFrag from './shaders/trail.frag.glsl?raw';
import paperFrag from './shaders/paper.frag.glsl?raw';

const CAMERA = new THREE.Vector3(0.5, 0.5, -1.12);
const LOOK_AT = new THREE.Vector3(0.5, 0.5, 0.5);
const FOV = 54;
const DRIFT = 0.025;
const PUSH_IN = 0.06;         // camera creeps toward the glass on the drop
const EXTENT = 1.75;          // billboard half-size in radii (body + bulge + wobble)
const TRAIL_DECAY = 0.985;    // per 1/60 s
const TRAIL_ADVECT = 0.0016;  // per 1/60 s, toward the vanishing point
const NEAR_SCALE = 1.28, FAR_SCALE = 0.74;   // must match blob.vert.glsl

// Spring-dampers (all underdamped, so bodies jiggle and settle).
const SQUASH = { k: 150, c: 9 };
const GLASS = { k: 110, c: 10 };
const MODES = [                       // surface wobble modes 2, 3, 4
  { n: 2, w: 13, z: 0.16 }, { n: 3, w: 19, z: 0.18 }, { n: 4, w: 26, z: 0.22 },
];
const MODE_MAX = 0.11;

export class Plate {
  constructor(canvas, maxAgents = 100) {
    this.canvas = canvas;
    this.max = maxAgents;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: 'high-performance' });
    this.renderer.autoClear = false;
    this.camera = new THREE.PerspectiveCamera(FOV, 1, 0.05, 6);
    this.pushIn = 0;
    this.pushTarget = 0;
    this.quality = Math.min(devicePixelRatio || 1, 2);   // pigment resolution, relative to CSS pixels
    this.scale = new HappinessScale();
    this.bodies = new Map();      // agent id -> spring state
    this.colors = new Map();      // agent id -> css color (for the chat panel)
    this.lastTime = 0;
    this.lastKick = 0;
    this.margin = 0;              // CSS pixels on the right covered by the chat panel

    const attr = (size) => new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * size), size);
    const inst = this.inst = { iPos: attr(3), iAxis: attr(4), iVel: attr(4), iAbs: attr(3), iParam: attr(4),
      iModeA: attr(3), iModeP: attr(3) };
    const quads = this.quads = new THREE.InstancedBufferGeometry().copy(new THREE.PlaneGeometry(2, 2));
    for (const [name, a] of Object.entries(inst)) {
      a.setUsage(THREE.DynamicDrawUsage);
      quads.setAttribute(name, a);
    }
    quads.instanceCount = 0;

    const blobs = new THREE.Mesh(quads, new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3, uniforms: { uExtent: { value: EXTENT } }, vertexShader: blobVert,
      fragmentShader: blobFrag, depthTest: true, depthWrite: true,
    }));
    blobs.frustumCulled = false;
    this.blobScene = new THREE.Scene().add(blobs);

    const pass = (fragmentShader, uniforms) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3, uniforms, vertexShader: screenVert, fragmentShader, depthTest: false, depthWrite: false,
      }));
      mesh.frustumCulled = false;
      return new THREE.Scene().add(mesh);
    };
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
    this.pigment = new THREE.WebGLRenderTarget(fw, fh, { ...opts, depthBuffer: true });
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

  // Per-agent soft-body state: squash, glass press and three wobble modes, each
  // on its own spring-damper, plus smoothed axes so nothing pops.
  body(a, dt, kicked, music) {
    let b = this.bodies.get(a.id);
    if (!b) {
      this.bodies.set(a.id, b = { s: 0, sv: 0, g: 0, gv: 0, nx: 1, ny: 0, nz: 0, dx: 0, dy: 0, dz: -1, st: 0,
        pressure: a.pressure, vx: a.vx, vy: a.vy, vz: a.vz, phase: (a.id * 2.399) % 6.283,
        modes: MODES.map(() => ({ x: 0, v: 0, p: 0 })) });
    }
    const steps = Math.max(1, Math.ceil(dt / 0.008)), h = dt / steps;
    const squashTo = Math.min(0.42, a.pressure * 0.8);
    // Pressed against the glass: fully flat at 0.62 r from it, round again by 1.2 r.
    const glassTo = Math.min(1, Math.max(0, 1 - (a.z - 0.62 * a.r) / (0.58 * a.r)));

    // What excites the wobble: impacts, changes of velocity, and the kick.
    const impact = Math.max(0, a.pressure - b.pressure);
    const jolt = Math.hypot(a.vx - b.vx, a.vy - b.vy, a.vz - b.vz);
    const dance = (a.action === 'dance' ? 1 : 0.35) * (0.4 + 0.6 * music.sec[1]);
    const kick = kicked ? music.energy * a.E * (0.35 + 0.65 * dance) : 0;
    const contactAngle = Math.atan2(a.ny, -a.nx);      // screen x runs opposite to world x
    b.pressure = a.pressure; b.vx = a.vx; b.vy = a.vy; b.vz = a.vz;

    for (let i = 0; i < MODES.length; i++) {
      const m = b.modes[i], { n, w, z } = MODES[i];
      if (impact > 0.02) { m.v += impact * 2.2 * w / n; m.p = n * contactAngle; }
      if (kick > 0) { m.v += kick * 0.55 * w / n; if (impact <= 0.02) m.p = n * (Math.PI / 2) + b.phase * (i ? 1 : 0); }
      m.v += jolt * 1.5 * w / n;
      for (let k = 0; k < steps; k++) {
        m.v += (-w * w * m.x - 2 * z * w * m.v) * h;
        m.x += m.v * h;
      }
      m.x = Math.min(MODE_MAX, Math.max(-MODE_MAX, m.x));
    }
    for (let k = 0; k < steps; k++) {
      b.sv += (SQUASH.k * (squashTo - b.s) - SQUASH.c * b.sv) * h;
      b.s += b.sv * h;
      b.gv += (GLASS.k * (glassTo - b.g) - GLASS.c * b.gv) * h;
      b.g += b.gv * h;
    }
    // Ease the contact axis (an axis has no sign) and the direction of travel.
    const ease = Math.min(1, dt * 7);
    if (a.nx || a.ny || a.nz) {
      const sign = b.nx * a.nx + b.ny * a.ny + b.nz * a.nz < 0 ? -1 : 1;
      b.nx += (sign * a.nx - b.nx) * ease; b.ny += (sign * a.ny - b.ny) * ease; b.nz += (sign * a.nz - b.nz) * ease;
      const len = Math.hypot(b.nx, b.ny, b.nz) || 1;
      b.nx /= len; b.ny /= len; b.nz /= len;
    }
    const speed = Math.hypot(a.vx, a.vy, a.vz);
    if (speed > 1e-4) {
      b.dx += (a.vx / speed - b.dx) * ease; b.dy += (a.vy / speed - b.dy) * ease; b.dz += (a.vz / speed - b.dz) * ease;
    }
    b.st += (Math.min(0.3, speed * 2.4) - b.st) * Math.min(1, dt * 5);
    return b;
  }

  // agents: [{id, x, y, z, vx, vy, vz, r, E, H, pressure, nx, ny, nz, action}], H is raw happiness.
  // music: {energy, kickEnv, kickBob, sec: [p(build), p(drop), p(breakdown)]}.
  render(agents, music, time) {
    const dt = Math.min(0.05, Math.max(0.001, time - this.lastTime));
    this.lastTime = time;
    const kicked = music.kickEnv > this.lastKick + 0.4;
    this.lastKick = music.kickEnv;
    const { iPos, iAxis, iVel, iAbs, iParam, iModeA, iModeP } = this.inst;
    const n = Math.min(agents.length, this.max);
    this.scale.update(agents.map((a) => a.H), dt);
    const [pBuild, pDrop, pBreak] = music.sec;

    for (let i = 0; i < n; i++) {
      const a = agents[i];
      const jitter = ((a.id * 0.6180339) % 1) * 2 - 1;
      const [r, g, bl] = happinessColor(this.scale.map(a.H), jitter);
      this.colors.set(a.id, `rgb(${(r * 255) | 0},${(g * 255) | 0},${(bl * 255) | 0})`);
      const b = this.body(a, dt, kicked, music);

      // Dancing follows the music: a bob on the kick (everyone on the drop,
      // pushers included) and a sway that is wide on the drop, slow and gentle
      // in a breakdown.
      const dancer = a.action === 'dance' ? 1 : 0;
      const bob = a.r * music.kickBob * a.E * (0.10 + 0.22 * dancer + 0.34 * pDrop + 0.10 * pBuild);
      const swayRate = 2.6 - 1.4 * pBreak;
      const sway = a.r * Math.sin(time * swayRate + b.phase) * a.E
        * (0.03 + 0.05 * dancer + 0.16 * pDrop + 0.07 * pBreak) * (0.4 + 0.6 * music.energy + 0.4 * pBreak);
      const pulse = 1 + 0.16 * music.kickEnv * music.energy * a.E;

      iPos.setXYZ(i, a.x + sway, a.y + bob, a.z);
      iAxis.setXYZW(i, b.nx, b.ny, b.nz, b.s);
      iVel.setXYZW(i, b.dx, b.dy, b.dz, b.st);
      // Absorbance of this pigment at density 1; energy sets how much pigment there is.
      iAbs.setXYZ(i, -Math.log(Math.max(0.03, r)), -Math.log(Math.max(0.03, g)), -Math.log(Math.max(0.03, bl)));
      iParam.setXYZW(i, 0.18 + 1.32 * a.E, a.r * pulse, Math.min(1.15, Math.max(0, b.g)), 0);
      iModeA.setXYZ(i, b.modes[0].x, b.modes[1].x, b.modes[2].x);
      iModeP.setXYZ(i, b.modes[0].p, b.modes[1].p, b.modes[2].p);
    }
    for (const a of Object.values(this.inst)) a.needsUpdate = true;
    this.quads.instanceCount = n;

    this.pushIn += ((this.pushTarget ? PUSH_IN : 0) - this.pushIn) * Math.min(1, dt * 0.6);
    this.camera.position.set(
      CAMERA.x + DRIFT * Math.sin(time * 0.11),
      CAMERA.y + DRIFT * Math.sin(time * 0.077 + 1.3),
      CAMERA.z + this.pushIn,
    );
    this.camera.lookAt(LOOK_AT);

    const gl = this.renderer, frames = dt * 60;
    // 1. Pigment, nearest body on top.
    gl.setRenderTarget(this.pigment);
    gl.setClearColor(0x000000, 0);
    gl.clear(true, true, false);
    gl.render(this.blobScene, this.camera);
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
  project(x, y, z, r = 0.07, out = {}) {
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
