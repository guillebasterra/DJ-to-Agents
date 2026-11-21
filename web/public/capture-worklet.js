// Downsamples whatever is playing to 16 kHz mono Int16 and posts 250 ms chunks.
// Only captures while the main thread says audio is playing.
const OUT_SR = 16000;
const CHUNK = OUT_SR / 4;

class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.active = false;
    this.step = sampleRate / OUT_SR;
    this.acc = 0;      // sum of input samples in the current output sample
    this.count = 0;
    this.phase = 0;
    this.out = new Int16Array(CHUNK);
    this.fill = 0;
    this.port.onmessage = (e) => {
      if ('active' in e.data) this.active = e.data.active;
      if (e.data.flush) { this.fill = 0; this.acc = 0; this.count = 0; this.phase = 0; }
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!this.active || !input || !input.length) return true;
    const n = input[0].length, chans = input.length;
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (let c = 0; c < chans; c++) s += input[c][i];
      this.acc += s / chans;
      this.count++;
      this.phase += 1;
      if (this.phase >= this.step) {
        this.phase -= this.step;
        const v = Math.max(-1, Math.min(1, this.acc / this.count));
        this.out[this.fill++] = v * 32767;
        this.acc = 0;
        this.count = 0;
        if (this.fill === CHUNK) {
          const chunk = this.out;
          this.port.postMessage(chunk.buffer, [chunk.buffer]);
          this.out = new Int16Array(CHUNK);
          this.fill = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('capture', Capture);
