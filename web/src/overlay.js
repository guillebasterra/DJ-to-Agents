// Canvas2D overlay: ask threads (at most three at a time), optional agent ids,
// and the highlight for whoever a hovered chat line is about.
import { INK, NO, PAPER, YES } from './palette.js';

const FADE = 3.0;        // seconds an ask thread stays up
const MAX_THREADS = 3;
const MAX_CHARS = 54;

export class Overlay {
  constructor(canvas, plate) {
    this.canvas = canvas;
    this.plate = plate;
    this.g = canvas.getContext('2d');
    this.labels = false;
    this.highlight = [];        // agent ids to ring
    this.margin = 0;            // CSS pixels on the right covered by the chat panel
    this.threads = new Map();   // ask id -> {from, to, text, answer, born}
    this.resize();
    addEventListener('resize', () => this.resize());
  }

  resize() {
    const dpr = devicePixelRatio || 1;
    this.canvas.width = innerWidth * dpr;
    this.canvas.height = innerHeight * dpr;
    this.g.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  onDecision(frame, now) {
    for (const a of frame.asks || []) {
      if (!this.threads.has(a.id)) this.threads.set(a.id, { ...a, born: now });
    }
    for (const a of frame.answers || []) {
      const th = this.threads.get(a.id);
      if (th) { th.answer = a.answer; th.born = now; }
    }
  }

  draw(agents, byId, now) {
    const g = this.g, plate = this.plate, p = {}, q = {};
    g.clearRect(0, 0, innerWidth, innerHeight);
    g.textBaseline = 'middle';

    if (this.labels) {
      g.font = "9px 'IBM Plex Mono', monospace";
      g.fillStyle = INK;
      for (const a of agents) {
        plate.project(a.x, a.y, a.z, a.r, p);
        if (!p.visible) continue;
        g.globalAlpha = 0.6 * Math.min(1, Math.max(0.35, 2.2 - p.dist));
        g.fillText(`A${a.id}`, p.x + p.r * 0.72 + 2, p.y - p.r * 0.72);
      }
    }

    // Whoever the hovered chat line is about.
    g.lineWidth = 1.5;
    g.strokeStyle = INK;
    for (const id of this.highlight) {
      const a = byId.get(id);
      if (!a) continue;
      plate.project(a.x, a.y, a.z, a.r, p);
      g.globalAlpha = 0.9;
      g.beginPath();
      g.arc(p.x, p.y, p.r + 5, 0, Math.PI * 2);
      g.stroke();
      g.font = "10px 'IBM Plex Mono', monospace";
      g.fillStyle = INK;
      g.fillText(`A${id}`, p.x + p.r + 9, p.y);
    }

    // Ask threads: the newest few, as a short curve with a bubble by the asker.
    for (const [id, th] of this.threads) if (now - th.born > FADE) this.threads.delete(id);
    const live = [...this.threads.values()].sort((a, b) => b.born - a.born).slice(0, MAX_THREADS);
    g.font = "10px 'IBM Plex Mono', monospace";
    const placed = [];
    for (const th of live) {
      const from = byId.get(th.from), to = byId.get(th.to);
      if (!from || !to) continue;
      plate.project(from.x, from.y, from.z, from.r, p);
      plate.project(to.x, to.y, to.z, to.r, q);
      if (!p.visible && !q.visible) continue;
      const alpha = Math.min(1, (FADE - (now - th.born)) / 0.8);
      const color = th.answer === 'yes' ? YES : th.answer === 'no' ? NO : INK;

      // A curve bowed to one side, from asker to blocker.
      const dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy) || 1;
      const bow = Math.min(26, 10 + len * 0.25);
      g.globalAlpha = alpha * 0.85;
      g.strokeStyle = color;
      g.lineWidth = 1.2;
      g.beginPath();
      g.moveTo(p.x, p.y);
      g.quadraticCurveTo((p.x + q.x) / 2 - dy / len * bow, (p.y + q.y) / 2 + dx / len * bow, q.x, q.y);
      g.stroke();
      g.beginPath();
      g.arc(q.x, q.y, 2.5, 0, Math.PI * 2);
      g.fillStyle = color;
      g.fill();

      // The bubble: the sentence while the ask is open, then the verdict.
      const said = th.text.length > MAX_CHARS ? `${th.text.slice(0, MAX_CHARS - 1)}…` : th.text;
      const label = th.answer === 'pending' ? said : th.answer === 'yes' ? '✓ yields' : '✗ holds';
      const tw = g.measureText(label).width + 12;
      const bx = Math.max(8, Math.min(innerWidth - this.margin - tw - 8, p.x + p.r * 0.6 + 6));
      let by = Math.max(14, Math.min(innerHeight - 14, p.y - p.r * 0.6 - 12));
      for (let tries = 0; tries < 6; tries++) {
        const hit = placed.find((b) => Math.abs(b.y - by) < 19 && bx < b.x + b.w + 4 && b.x < bx + tw + 4);
        if (!hit) break;
        by = hit.y + 19;
      }
      placed.push({ x: bx, y: by, w: tw });
      g.globalAlpha = alpha * 0.92;
      g.fillStyle = PAPER;
      g.strokeStyle = color;
      g.lineWidth = 1;
      g.beginPath();
      g.roundRect(bx, by - 8.5, tw, 17, 4);
      g.fill();
      g.stroke();
      g.globalAlpha = alpha;
      g.fillStyle = th.answer === 'pending' ? INK : color;
      g.fillText(label, bx + 6, by + 0.5);
    }
    g.globalAlpha = 1;
  }
}
