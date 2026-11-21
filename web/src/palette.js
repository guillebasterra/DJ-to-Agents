// Pigment on warm paper. Happiness runs grey-violet -> blue-violet -> purple ->
// magenta -> red-orange, interpolated in OKLab.
export const PAPER = '#f6ebe6';
export const INK = '#2b2430';
export const YES = '#3d7a5f';
export const NO = '#b3372a';

const STOPS = ['#b9b3c9', '#6b6eb8', '#8a3fa0', '#d12f7a', '#d9481c'];

const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toSrgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.max(0, c) ** (1 / 2.4) - 0.055);

function hexToOklab(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = toLinear(((n >> 16) & 255) / 255), g = toLinear(((n >> 8) & 255) / 255), b = toLinear((n & 255) / 255);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

function oklabToSrgb([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (x) => Math.min(1, Math.max(0, toSrgb(x)));
  return [clamp(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    clamp(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    clamp(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)];
}

const LAB = STOPS.map(hexToOklab);

// t: 0..1 on the happiness scale; jitter: -1..1, worth +-8 degrees of hue. Returns sRGB 0..1.
export function happinessColor(t, jitter) {
  const x = Math.min(1, Math.max(0, t)) * (LAB.length - 1);
  const i = Math.min(LAB.length - 2, Math.floor(x)), u = x - i;
  const L = LAB[i][0] + (LAB[i + 1][0] - LAB[i][0]) * u;
  const a = LAB[i][1] + (LAB[i + 1][1] - LAB[i][1]) * u;
  const b = LAB[i][2] + (LAB[i + 1][2] - LAB[i][2]) * u;
  const ang = (8 * jitter * Math.PI) / 180, c = Math.cos(ang), s = Math.sin(ang);
  return oklabToSrgb([L, a * c - b * s, a * s + b * c]);
}

// Happiness to palette position. Mostly absolute, so the whole crowd cools in
// a breakdown and warms on a drop; a quarter follows the crowd's own smoothed
// p05-p95 spread (tau 1.4 s) so neighbors still differ. Then a gentle S-curve.
export class HappinessScale {
  constructor() { this.lo = 0.1; this.hi = 0.8; }

  update(values, dt) {
    if (values.length < 5) return;
    const s = [...values].sort((a, b) => a - b);
    const at = (p) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
    const k = 1 - Math.exp(-dt / 1.4);
    this.lo += (at(0.05) - this.lo) * k;
    this.hi += (at(0.95) - this.hi) * k;
  }

  map(h) {
    const rel = (h - this.lo) / Math.max(0.05, this.hi - this.lo);
    const abs = (h - 0.22) / 0.56;
    const t = Math.min(1, Math.max(0, 0.25 * Math.min(1, Math.max(0, rel)) + 0.75 * abs));
    return t + 0.5 * (t * t * (3 - 2 * t) - t);
  }
}
