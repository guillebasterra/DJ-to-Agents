// Cool -> warm: teal for the least happy, warm orange for the happy, and a
// white-hot core on top (added in the shader).
export const BG = '#2a2a2a';
export const WHITE = '#e8e6e2';
export const RED = '#ff5a3c';
export const YES = '#9fd8c4';   // accepted asks

const STOPS = [
  [0.00, [0.04, 0.58, 0.64]],   // deep teal
  [0.38, [0.08, 0.86, 0.84]],   // cyan
  [0.50, [0.78, 0.76, 0.62]],   // a narrow pale band where cool meets warm
  [0.62, [1.00, 0.58, 0.10]],   // warm orange
  [1.00, [0.97, 0.26, 0.02]],   // red-orange
];

function ramp(t) {
  t = Math.min(1, Math.max(0, t));
  for (let i = 1; i < STOPS.length; i++) {
    if (t <= STOPS[i][0]) {
      const [t0, a] = STOPS[i - 1], [t1, b] = STOPS[i], u = (t - t0) / (t1 - t0);
      return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
    }
  }
  return STOPS[STOPS.length - 1][1];
}

// Rotate a color's hue by `deg` (Rodrigues rotation about the grey axis).
function rotateHue([r, g, b], deg) {
  const a = (deg * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a), k = (1 - c) / 3, q = s / Math.sqrt(3);
  return [
    Math.min(1, Math.max(0, r * (c + k) + g * (k - q) + b * (k + q))),
    Math.min(1, Math.max(0, r * (k + q) + g * (c + k) + b * (k - q))),
    Math.min(1, Math.max(0, r * (k - q) + g * (k + q) + b * (c + k))),
  ];
}

// t: 0..1 position on the happiness scale; jitter: -1..1, worth +-8 degrees of hue.
export function happinessColor(t, jitter) {
  return rotateHue(ramp(t), 8 * jitter);
}

// Stretches happiness over the crowd's current spread, so the crowd always
// uses the whole scale: smoothed p05-p95 (55%) blended with an absolute anchor
// (45%), then a gentle S-curve.
export class HappinessScale {
  constructor() { this.lo = 0.03; this.hi = 0.17; }

  update(values, dt) {
    if (values.length < 5) return;
    const s = [...values].sort((a, b) => a - b);
    const at = (p) => s[Math.min(s.length - 1, Math.floor(p * s.length))];
    const k = 1 - Math.exp(-dt / 1.5);
    this.lo += (at(0.05) - this.lo) * k;
    this.hi += (at(0.95) - this.hi) * k;
  }

  map(h) {
    const rel = (h - this.lo) / Math.max(0.02, this.hi - this.lo);
    const abs = (h - 0.03) / 0.14;
    const t = Math.min(1, Math.max(0, 0.55 * rel + 0.45 * abs));
    return t + 0.7 * (t * t * (3 - 2 * t) - t);
  }
}
