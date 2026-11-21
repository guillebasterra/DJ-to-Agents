// Audio input and features. The source is the only swappable part: everything
// after it (analyser for the visuals, capture worklet for the models) is shared.
const FFT = 2048;
const KICK_REFRACTORY = 0.12;
const KICK_DECAY = 0.06;

// Each source maker returns {node, monitor, label, time(), playing(), stop()}.
export const sources = {
  // Dev / replay: a file played out loud.
  file(ctx, url, label) {
    const el = new Audio(url);
    el.crossOrigin = 'anonymous';
    el.preload = 'auto';
    return {
      kind: 'file', label, el,
      node: ctx.createMediaElementSource(el),
      monitor: true,
      time: () => el.currentTime,
      playing: () => !el.paused && !el.ended && el.readyState > 2,
      toggle: () => (el.paused ? el.play() : el.pause()),
      stop: () => { el.pause(); el.src = ''; },
    };
  },
  // Live: an input device (BlackHole 2ch, the mixer's USB). Not played back:
  // the DJ setup already feeds the speakers.
  async live(ctx, deviceId, label) {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { deviceId: deviceId ? { exact: deviceId } : undefined,
        echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    const start = ctx.currentTime;
    let on = true;
    return {
      kind: 'live', label,
      node: ctx.createMediaStreamSource(stream),
      monitor: false,
      time: () => ctx.currentTime - start,
      playing: () => on,
      toggle: () => { on = !on; },
      stop: () => stream.getTracks().forEach((t) => t.stop()),
    };
  },
};

export class AudioEngine {
  constructor({ onChunk, onSeek }) {
    this.onChunk = onChunk;
    this.onSeek = onSeek;
    this.source = null;
    this.chunks = 0;
    this.wasPlaying = false;
    this.max = { sub: 1e-4, bass: 1e-4, mid: 1e-4, high: 1e-4, rms: 1e-4, low: 1e-4 };
    this.lowHist = [0, 0, 0];
    this.fluxAvg = 0;
    this.lastKick = -1;
    this.lastBass = 0;
    this.history = [];   // [audio time, energy], last 10 s of playback
    this.kicks = 0;      // kicks since the last clock message
    this.features = { sub: 0, bass: 0, mid: 0, high: 0, rms: 0, kick: false, kickEnv: 0,
      energy: 0, energy_5s: 0, trend: 0, bass_gap: 0 };
  }

  async init() {
    if (this.ctx) return;
    const ctx = this.ctx = new AudioContext();
    this.analyser = new AnalyserNode(ctx, { fftSize: FFT, smoothingTimeConstant: 0 });
    this.freq = new Float32Array(FFT / 2);
    this.wave = new Float32Array(FFT);
    await ctx.audioWorklet.addModule('/capture-worklet.js');
    this.worklet = new AudioWorkletNode(ctx, 'capture', { numberOfOutputs: 1 });
    this.worklet.port.onmessage = (e) => {
      if (!this.playing) return;
      this.chunks++;
      this.onChunk(e.data);
    };
    // Keep the worklet pulled by the graph without making sound.
    this.worklet.connect(new GainNode(ctx, { gain: 0 })).connect(ctx.destination);
  }

  // The single swap point: sources.file or sources.live.
  async setSource(kind, arg, label) {
    await this.init();
    await this.ctx.resume();
    if (this.source) {
      this.source.node.disconnect();
      this.source.stop();
    }
    const src = this.source = await sources[kind](this.ctx, arg, label);
    src.node.connect(this.analyser);
    src.node.connect(this.worklet);
    if (src.monitor) src.node.connect(this.ctx.destination);
    if (src.el) {
      src.el.addEventListener('seeked', () => {
        this.worklet.port.postMessage({ flush: true });
        this.history.length = 0;
        this.onSeek();
      });
    }
    this.worklet.port.postMessage({ flush: true });
    return src;
  }

  get playing() { return !!this.source && this.source.playing(); }
  get time() { return this.source ? this.source.time() : 0; }

  toggle() {
    if (!this.source) return;
    this.ctx.resume();
    this.source.toggle();
  }

  // Call once per animation frame.
  update(now) {
    const f = this.features;
    const playing = this.playing;
    if (playing !== this.wasPlaying) {
      this.worklet.port.postMessage({ active: playing });
      this.wasPlaying = playing;
    }
    f.kick = false;
    f.kickEnv = this.lastKick < 0 ? 0 : Math.exp(-(now - this.lastKick) / KICK_DECAY);
    if (!playing) return f;

    const { analyser, freq, wave, max } = this;
    analyser.getFloatFrequencyData(freq);
    analyser.getFloatTimeDomainData(wave);
    const hz = this.ctx.sampleRate / FFT;
    const band = (lo, hi) => {
      const a = Math.max(1, Math.round(lo / hz)), b = Math.min(freq.length, Math.round(hi / hz));
      let p = 0;
      for (let i = a; i < b; i++) p += 10 ** (freq[i] / 10);
      return Math.sqrt(p / Math.max(1, b - a));
    };
    let sq = 0;
    for (let i = 0; i < wave.length; i++) sq += wave[i] * wave[i];
    const raw = { sub: band(20, 60), bass: band(60, 250), mid: band(250, 2000), high: band(2000, 12000),
      rms: Math.sqrt(sq / wave.length), low: band(30, 150) };
    // Normalize each by a decaying running max.
    const norm = {};
    for (const k in raw) {
      max[k] = Math.max(max[k] * 0.9997, raw[k]);
      norm[k] = raw[k] / max[k];
    }
    for (const k of ['sub', 'bass', 'mid', 'high', 'rms']) f[k] += (norm[k] - f[k]) * 0.35;

    // Kick: onset on the low band (flux over threshold, 120 ms refractory).
    const flux = Math.max(0, norm.low - this.lowHist[0]);
    this.lowHist.shift();
    this.lowHist.push(norm.low);
    this.fluxAvg += (flux - this.fluxAvg) * 0.05;
    if (flux > 0.22 && flux > 2.2 * this.fluxAvg && now - this.lastKick > KICK_REFRACTORY) {
      this.lastKick = now;
      this.kicks++;
      f.kick = true;
      f.kickEnv = 1;
    }

    f.energy = 0.6 * f.bass + 0.4 * f.rms;
    const t = this.time;
    if (f.bass > 0.35) this.lastBass = t;
    f.bass_gap = Math.max(0, t - this.lastBass);
    const h = this.history;
    h.push([t, f.energy]);
    while (h.length && (h[0][0] < t - 10 || h[0][0] > t)) h.shift();
    let a = 0, an = 0, b = 0, bn = 0;
    for (const [ht, e] of h) {
      if (ht >= t - 5) { a += e; an++; } else { b += e; bn++; }
    }
    f.energy_5s = an ? a / an : 0;
    f.trend = bn ? f.energy_5s - b / bn : 0;
    return f;
  }

  // The 4 Hz clock message for the backend.
  clock() {
    const f = this.features, r = (x) => Math.round(x * 1000) / 1000;
    const kicks = this.kicks;
    this.kicks = 0;
    return {
      type: 'clock', t: r(this.time), playing: this.playing, source: this.source ? this.source.kind : 'none',
      dsp: { sub: r(f.sub), bass: r(f.bass), mid: r(f.mid), high: r(f.high), rms: r(f.rms), kick: kicks > 0, kicks,
        energy: r(f.energy), energy_5s: r(f.energy_5s), trend: r(f.trend), bass_gap: r(f.bass_gap) },
    };
  }
}
