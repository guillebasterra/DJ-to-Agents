// The aquarium renderer (three.js): every agent is one billboard with analytic
// sphere shading. Three passes: (1) blobs add into a density field, (2) the
// field is resolved into glowing, softly merged bodies and folded into a
// decaying trail buffer, (3) a fine per-pixel grain pass draws it to the screen.
import * as THREE from 'three';
import { BG, HappinessScale, happinessColor } from './palette.js';
import blobVert from './shaders/blob.vert.glsl?raw';
import blobFrag from './shaders/blob.frag.glsl?raw';
import screenVert from './shaders/screen.vert.glsl?raw';
import resolveFrag from './shaders/resolve.frag.glsl?raw';
import grainFrag from './shaders/grain.frag.glsl?raw';

export const AGENT_RADIUS = 0.075;
const CAMERA = new THREE.Vector3(0.5, 0.5, -1.2);   // pulled back: the whole box fits with margin
const LOOK_AT = new THREE.Vector3(0.5, 0.5, 0.5);
const FOV = 50;
const DRIFT = 0.03;
const PUSH_IN = 0.10;         // camera creeps toward the glass on the drop
const SMOOTH_K = 5.5;         // smooth-min sharpness (per radius): lower is gooier
const EXTENT = 2.7;           // billboard half-size in radii (body + halo + squash bulge)
const TRAIL_TAU = 0.55;       // seconds for a smear to fade to 1/e
// Squash spring-damper: underdamped, so blobs wobble after an impact.
const SPRING = 150, DAMPING = 9;

export class Plate {
  constructor(canvas, maxAgents = 100) {
    this.canvas = canvas;
    this.max = maxAgents;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: 'high-performance' });
    this.renderer.autoClear = false;
    this.camera = new THREE.PerspectiveCamera(FOV, 1, 0.05, 6);
    this.pushIn = 0;
    this.pushTarget = 0;
    this.quality = 1;             // field resolution, relative to CSS pixels
    this.scale = new HappinessScale();
    this.springs = new Map();     // agent id -> {s, v, nx, ny, nz}
    this.lastTime = 0;

    const inst = this.inst = {
      iPos: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 3), 3),
      iAxis: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 4), 4),
      iCol: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 3), 3),
      iParam: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 4), 4),
    };
    const quads = this.quads = new THREE.InstancedBufferGeometry().copy(new THREE.PlaneGeometry(2, 2));
    for (const [name, attr] of Object.entries(inst)) {
      attr.setUsage(THREE.DynamicDrawUsage);
      quads.setAttribute(name, attr);
    }
    quads.instanceCount = 0;

    const one = THREE.OneFactor;
    this.blobUniforms = { uRadius: { value: AGENT_RADIUS }, uExtent: { value: EXTENT }, uK: { value: SMOOTH_K },
      uNear: { value: 0.9 } };
    const blobs = new THREE.Mesh(quads, new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3, uniforms: this.blobUniforms, vertexShader: blobVert, fragmentShader: blobFrag,
      depthTest: false, depthWrite: false, transparent: true, blending: THREE.CustomBlending,
      blendEquation: THREE.AddEquation, blendSrc: one, blendDst: one, blendSrcAlpha: one, blendDstAlpha: one,
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
    this.resolveUniforms = { tColor: { value: null }, tField: { value: null }, tPrev: { value: null },
      uK: { value: SMOOTH_K }, uDecay: { value: 0.95 } };
    this.grainUniforms = { tTrail: { value: null }, uTime: { value: 0 },
      uBg: { value: new THREE.Color(BG).convertLinearToSRGB() } };
    this.resolveScene = pass(resolveFrag, this.resolveUniforms);
    this.grainScene = pass(grainFrag, this.grainUniforms);

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
    this.camera.updateProjectionMatrix();

    // The fields are smooth, so they render at CSS resolution; only the grain needs device pixels.
    const fw = Math.max(2, Math.round(w * this.quality)), fh = Math.max(2, Math.round(h * this.quality));
    const opts = { type: THREE.HalfFloatType, depthBuffer: false, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter };
    for (const rt of [this.field, this.trailA, this.trailB]) if (rt) rt.dispose();
    this.field = new THREE.WebGLRenderTarget(fw, fh, { ...opts, count: 2 });
    this.trailA = new THREE.WebGLRenderTarget(fw, fh, opts);
    this.trailB = new THREE.WebGLRenderTarget(fw, fh, opts);
  }

  // Performance fallback: render the fields at lower resolution (the grain stays 1 px).
  degrade() {
    if (this.quality <= 0.5) return false;
    this.quality = Math.max(0.5, this.quality * 0.75);
    this.resize();
    return true;
  }

  // Spring-damper on the squash, so bodies jiggle after impacts instead of snapping.
  spring(a, dt) {
    let sp = this.springs.get(a.id);
    if (!sp) this.springs.set(a.id, sp = { s: 0, v: 0, nx: 1, ny: 0, nz: 0 });
    const target = Math.min(0.42, a.pressure * 0.8);
    const steps = Math.max(1, Math.ceil(dt / 0.008));
    for (let i = 0; i < steps; i++) {
      const h = dt / steps;
      sp.v += (SPRING * (target - sp.s) - DAMPING * sp.v) * h;
      sp.s += sp.v * h;
    }
    // Ease the axis toward the current contact normal (an axis has no sign).
    if (a.nx || a.ny || a.nz) {
      const sign = sp.nx * a.nx + sp.ny * a.ny + sp.nz * a.nz < 0 ? -1 : 1, k = Math.min(1, dt * 7);
      sp.nx += (sign * a.nx - sp.nx) * k; sp.ny += (sign * a.ny - sp.ny) * k; sp.nz += (sign * a.nz - sp.nz) * k;
      const len = Math.hypot(sp.nx, sp.ny, sp.nz) || 1;
      sp.nx /= len; sp.ny /= len; sp.nz /= len;
    }
    return sp;
  }

  // agents: [{id, x, y, z, E, H, pressure, nx, ny, nz, action}], H is raw happiness.
  render(agents, music, time) {
    const dt = Math.min(0.05, Math.max(0.001, time - this.lastTime));
    this.lastTime = time;
    const { iPos, iAxis, iCol, iParam } = this.inst;
    const n = Math.min(agents.length, this.max);
    this.scale.update(agents.map((a) => a.H), dt);

    for (let i = 0; i < n; i++) {
      const a = agents[i];
      const jitter = ((a.id * 0.6180339) % 1) * 2 - 1;
      const t = this.scale.map(a.H);
      const [r, g, b] = happinessColor(t, jitter);
      const sp = this.spring(a, dt);
      // Dancers bob on the kick; everyone swells a little with the music.
      const bob = a.action === 'dance' ? 0.3 * AGENT_RADIUS * music.kickBob * (0.4 + 0.6 * a.E) : 0;
      const pulse = 1 + 0.08 * music.energy * a.E + 0.12 * music.kickEnv * a.E;
      iPos.setXYZ(i, a.x, a.y + bob, a.z);
      iAxis.setXYZW(i, sp.nx, sp.ny, sp.nz, sp.s);
      iCol.setXYZ(i, r, g, b);
      // Energy is glow: tired agents are dim and sparse. The happiest, most energetic burn white-hot.
      const hot = Math.max(0, (t - 0.45) / 0.55) ** 1.3 * (0.35 + 0.65 * a.E);
      const glow = Math.min(1, (0.22 + 0.78 * Math.sqrt(a.E)) * (0.85 + 0.25 * music.energy));
      iParam.setXYZW(i, glow, Math.min(1, hot * 1.15), pulse, 0);
    }
    for (const a of [iPos, iAxis, iCol, iParam]) a.needsUpdate = true;
    this.quads.instanceCount = n;

    this.pushIn += ((this.pushTarget ? PUSH_IN : 0) - this.pushIn) * Math.min(1, dt * 0.6);
    this.camera.position.set(
      CAMERA.x + DRIFT * Math.sin(time * 0.11),
      CAMERA.y + DRIFT * Math.sin(time * 0.077 + 1.3),
      CAMERA.z + this.pushIn,
    );
    this.camera.lookAt(LOOK_AT);
    this.blobUniforms.uNear.value = -this.camera.position.z;

    const gl = this.renderer;
    // 1. Blobs add into the field.
    gl.setRenderTarget(this.field);
    gl.setClearColor(0x000000, 0);
    gl.clear();
    gl.render(this.blobScene, this.camera);
    // 2. Resolve + trails (ping-pong).
    this.resolveUniforms.tColor.value = this.field.textures[0];
    this.resolveUniforms.tField.value = this.field.textures[1];
    this.resolveUniforms.tPrev.value = this.trailA.texture;
    this.resolveUniforms.uDecay.value = Math.exp(-dt / TRAIL_TAU);
    gl.setRenderTarget(this.trailB);
    gl.render(this.resolveScene, this.camera);
    [this.trailA, this.trailB] = [this.trailB, this.trailA];
    // 3. Grain to the screen.
    this.grainUniforms.tTrail.value = this.trailA.texture;
    this.grainUniforms.uTime.value = time % 1000;
    gl.setRenderTarget(null);
    gl.render(this.grainScene, this.camera);
  }

  // World position -> CSS pixels (+ distance and on-screen radius), for the overlay.
  project(x, y, z, out = {}) {
    const v = (this._v ||= new THREE.Vector3()).set(x, y, z);
    const dist = v.distanceTo(this.camera.position);
    v.project(this.camera);
    out.x = (v.x * 0.5 + 0.5) * innerWidth;
    out.y = (-v.y * 0.5 + 0.5) * innerHeight;
    out.visible = v.z > -1 && v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    out.dist = dist;
    out.r = AGENT_RADIUS / dist / Math.tan((this.camera.fov * Math.PI) / 360) * innerHeight * 0.5;
    return out;
  }
}
