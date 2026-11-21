// Canvas2D overlay: agent ids and ask threads, projected from 3D.
import { RED, WHITE, YES } from './palette.js';

const FADE = 3.0;   // seconds an ask thread stays up

export class Overlay {
  constructor(canvas, plate) {
    this.canvas = canvas;
    this.plate = plate;
    this.g = canvas.getContext('2d');
    this.labels = true;
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
    for (const a of frame.asks || []) this.threads.set(a.id, { ...a, born: now });
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
      g.fillStyle = WHITE;
      for (const a of agents) {
        plate.project(a.x, a.y, a.z, p);
        if (!p.visible) continue;
        g.globalAlpha = 0.55 * Math.min(1, Math.max(0.3, 2.3 - p.dist));
        g.fillText(`A${a.id}`, p.x + p.r * 0.75 + 2, p.y - p.r * 0.75);
      }
    }

    // Ask threads go on top of everything.
    g.font = "10px 'IBM Plex Mono', monospace";
    g.lineWidth = 1;
    const placed = [];     // text boxes drawn this frame, so asks never print over each other
    for (const [id, th] of this.threads) {
      const age = now - th.born;
      const from = byId.get(th.from), to = byId.get(th.to);
      if (age > FADE || !from || !to) { this.threads.delete(id); continue; }
      plate.project(from.x, from.y, from.z, p);
      plate.project(to.x, to.y, to.z, q);
      if (!p.visible && !q.visible) continue;
      const alpha = Math.min(1, (FADE - age) / 0.8);
      const color = th.answer === 'yes' ? YES : th.answer === 'no' ? RED : WHITE;
      g.globalAlpha = alpha * 0.9;
      g.strokeStyle = g.fillStyle = color;
      g.beginPath();
      g.moveTo(p.x, p.y);
      g.lineTo(q.x, q.y);
      if (th.answer === 'no') {
        // A short tick across the thread at the blocker's end.
        const dx = q.x - p.x, dy = q.y - p.y, len = Math.hypot(dx, dy) || 1;
        const mx = q.x - dx / len * 10, my = q.y - dy / len * 10;
        g.moveTo(mx - dy / len * 5, my + dx / len * 5);
        g.lineTo(mx + dy / len * 5, my - dx / len * 5);
      }
      g.stroke();
      // The sentence shows while the ask is open; once answered only the verdict stays.
      const label = th.answer === 'pending' ? th.text : `[${th.answer}]`;
      // Keep the text on screen, and step it down past any text already there.
      const tw = g.measureText(label).width;
      const tx = Math.max(8, Math.min(innerWidth - tw - 8, p.x + 8));
      let ty = Math.max(12, Math.min(innerHeight - 12, p.y + 12));
      for (let tries = 0; tries < 12; tries++) {
        const hit = placed.find((b) => Math.abs(b.y - ty) < 13 && tx < b.x + b.w + 6 && b.x < tx + tw + 6);
        if (!hit) break;
        ty = hit.y + 13;
      }
      placed.push({ x: tx, y: ty, w: tw });
      g.fillText(label, tx, ty);
    }
    g.globalAlpha = 1;
  }
}
