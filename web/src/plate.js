// The aquarium renderer: every agent is an instanced point cloud (three.js).
import * as THREE from 'three';
import { BG, BLUE, RED, WHITE } from './palette.js';
import deform from './shaders/deform.glsl?raw';
import pointsVert from './shaders/points.vert.glsl?raw';
import pointsFrag from './shaders/points.frag.glsl?raw';
import occluderVert from './shaders/occluder.vert.glsl?raw';
import occluderFrag from './shaders/occluder.frag.glsl?raw';

export const AGENT_RADIUS = 0.06;
const POINTS_PER_SPHERE = 20000;
const CAMERA = new THREE.Vector3(0.5, 0.5, -0.35);
const LOOK_AT = new THREE.Vector3(0.5, 0.5, 0.5);
const DRIFT = 0.03;

const glsl = (src) => src.replace('#include deform', deform);

// Points on the camera-facing half of a unit sphere, sampled evenly over its
// projected disc so no dots are wasted on the limb or the hidden back half
// (the shader turns each cloud to face the camera). A thin halo outside the
// silhouette gives the soft speckled edge. Random order, so any prefix is a
// uniform sample.
function spherePoints(n) {
  const pos = new Float32Array(n * 3);
  const rnd = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2;
    const halo = Math.random() < 0.12;
    const r = halo ? 1.0 - Math.log(1 - Math.random()) * 0.06 : Math.sqrt(Math.random());
    const z = halo ? 0 : Math.sqrt(1 - r * r);
    pos.set([r * Math.cos(a), r * Math.sin(a), z], i * 3);
    rnd.set([Math.random(), Math.random()], i * 2);
  }
  return { pos, rnd };
}

function grain(canvas) {
  const size = 256, g = canvas.getContext('2d');
  canvas.width = canvas.height = size;
  const img = g.createImageData(size, size);
  for (let i = 0; i < size * size; i++) {
    const on = Math.random() < 0.06;
    img.data.set([216, 212, 214, on ? 10 + Math.random() * 18 : 0], i * 4);
  }
  g.putImageData(img, 0, 0);
}

export class Plate {
  constructor(canvas, grainCanvas, maxAgents = 100) {
    this.canvas = canvas;
    this.max = maxAgents;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true });
    this.renderer.setClearColor(0x000000, 0);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(60, 1, 0.02, 4);
    this.pushIn = 0;
    if (grainCanvas) grain(grainCanvas);

    const inst = {
      iPos: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 3), 3),
      iVel: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 3), 3),
      iSquash: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 4), 4),
      iState: new THREE.InstancedBufferAttribute(new Float32Array(maxAgents * 4), 4),
    };
    for (const a of Object.values(inst)) a.setUsage(THREE.DynamicDrawUsage);
    this.inst = inst;

    const rgb = (hex) => new THREE.Color(hex).convertLinearToSRGB();
    this.uniforms = {
      uRadius: { value: AGENT_RADIUS }, uEnergy: { value: 0 }, uKick: { value: 0 },
      uDpr: { value: 1 }, uLod: { value: 0.55 }, uTime: { value: 0 },
      uLight: { value: new THREE.Vector3(-0.55, 0.6, 0.58).normalize() },
      uBg: { value: rgb(BG) }, uBlue: { value: rgb(BLUE) }, uRed: { value: rgb(RED) }, uWhite: { value: rgb(WHITE) },
    };

    const { pos, rnd } = spherePoints(POINTS_PER_SPHERE);
    const dots = new THREE.InstancedBufferGeometry();
    dots.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    dots.setAttribute('aRnd', new THREE.BufferAttribute(rnd, 2));
    const body = new THREE.InstancedBufferGeometry().copy(new THREE.IcosahedronGeometry(1, 4));
    for (const g of [dots, body]) {
      for (const [name, attr] of Object.entries(inst)) g.setAttribute(name, attr);
      g.instanceCount = 0;
    }
    this.dots = dots;
    this.body = body;
    this.pointBudget = POINTS_PER_SPHERE;

    const occluder = new THREE.Mesh(body, new THREE.ShaderMaterial({
      uniforms: this.uniforms, vertexShader: glsl(occluderVert), fragmentShader: occluderFrag,
    }));
    const points = new THREE.Points(dots, new THREE.ShaderMaterial({
      uniforms: this.uniforms, vertexShader: glsl(pointsVert), fragmentShader: pointsFrag,
    }));
    occluder.frustumCulled = points.frustumCulled = false;
    occluder.renderOrder = 0;
    points.renderOrder = 1;
    this.scene.add(occluder, points);

    this.resize();
    addEventListener('resize', () => this.resize());
  }

  resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const w = innerWidth, h = innerHeight;
    this.renderer.setPixelRatio(dpr);
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.uniforms.uDpr.value = dpr * Math.max(1, h / 900);
  }

  // Plan's performance fallback: fewer dots per sphere if the frame rate sags.
  halvePoints() {
    if (this.pointBudget <= 1500) return false;
    this.pointBudget = Math.max(1500, this.pointBudget >> 1);
    this.dots.setDrawRange(0, this.pointBudget);
    this.uniforms.uLod.value *= 1.6;
    return true;
  }

  // agents: [{id, x, y, z, vx, vy, vz, E, H, pressure, nx, ny, nz, flags}]
  render(agents, music, time) {
    const { iPos, iVel, iSquash, iState } = this.inst;
    const n = Math.min(agents.length, this.max);
    for (let i = 0; i < n; i++) {
      const a = agents[i];
      iPos.setXYZ(i, a.x, a.y, a.z);
      iVel.setXYZ(i, a.vx, a.vy, a.vz);
      iSquash.setXYZW(i, a.nx, a.ny, a.nz, a.pressure);
      iState.setXYZW(i, a.E, a.H, (a.id * 0.6180339) % 1, a.flags || 0);
    }
    for (const a of [iPos, iVel, iSquash, iState]) a.needsUpdate = true;
    this.dots.instanceCount = this.body.instanceCount = n;

    this.uniforms.uEnergy.value = music.energy;
    this.uniforms.uKick.value = music.kickEnv;
    this.uniforms.uTime.value = time;

    this.camera.position.set(
      CAMERA.x + DRIFT * Math.sin(time * 0.11),
      CAMERA.y + DRIFT * Math.sin(time * 0.077 + 1.3),
      CAMERA.z + this.pushIn,
    );
    this.camera.lookAt(LOOK_AT);
    this.renderer.render(this.scene, this.camera);
  }

  // World position -> CSS pixels (+ depth and on-screen radius), for the overlay.
  project(x, y, z, out = {}) {
    const v = (this._v ||= new THREE.Vector3()).set(x, y, z);
    const dist = v.distanceTo(this.camera.position);
    v.project(this.camera);
    out.x = (v.x * 0.5 + 0.5) * innerWidth;
    out.y = (-v.y * 0.5 + 0.5) * innerHeight;
    out.visible = v.z > -1 && v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    out.dist = dist;
    out.r = AGENT_RADIUS / dist / Math.tan(Math.PI / 6) * innerHeight * 0.5;
    return out;
  }
}
