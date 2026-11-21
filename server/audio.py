"""Rolling PCM buffer fed by the browser, the session recorder, and the
per-ring filtered clips the models hear (plan section 6)."""
import base64
import io
import wave
from collections import deque

import numpy as np
from scipy import signal

from . import config as C

SR = C.AUDIO_SR


class AudioBuffer:
    def __init__(self):
        self.chunks = deque()
        self.samples = 0

    def push(self, data: bytes):
        chunk = np.frombuffer(data[: len(data) // 2 * 2], dtype=np.int16)
        self.chunks.append(chunk)
        self.samples += len(chunk)
        while self.samples - len(self.chunks[0]) >= C.BUFFER_SECONDS * SR:
            self.samples -= len(self.chunks.popleft())
        return chunk

    def clear(self):
        self.chunks.clear()
        self.samples = 0

    @property
    def seconds(self):
        return self.samples / SR

    def clip(self, seconds):
        """The last N seconds that actually played (shorter if less is buffered)."""
        if not self.chunks:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(self.chunks)[-int(seconds * SR):]


def _sos(kind, hz, order=4):
    return signal.butter(order, hz, kind, fs=SR, output="sos")


_LP = {3: _sos("low", 6000), 4: _sos("low", 3000), 5: _sos("low", 1500)}
_SHELF = _sos("low", 120, order=2)
_DB = lambda db: 10 ** (db / 20)


def ring_clip(ring, pcm):
    """What a ring hears: the back gets it quiet and muffled, the front loud and bassy."""
    x = pcm.astype(np.float32) / 32768.0
    if ring == 1:       # +3 dB, low shelf +4 dB below 120 Hz
        x = (x + (_DB(4) - 1) * signal.sosfilt(_SHELF, x)) * _DB(3)
    elif ring == 3:     # low-pass (plan: 8 kHz, which is Nyquist at 16 kHz, so 6 kHz)
        x = signal.sosfilt(_LP[3], x)
    elif ring == 4:     # low-pass 3 kHz, -6 dB
        x = signal.sosfilt(_LP[4], x) * _DB(-6)
    elif ring == 5:     # low-pass 1.5 kHz, -12 dB
        x = signal.sosfilt(_LP[5], x) * _DB(-12)
    return (np.clip(x, -1.0, 1.0) * 32767).astype(np.int16)


def wav_b64(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return base64.b64encode(buf.getvalue()).decode()


def features_text(ring, t, dsp, kick_rate):
    """Supplement sent next to the audio, never instead of it. Coarser at the back."""
    nd = 1 if ring >= 4 else 2
    return (f"t={int(t) // 60}:{int(t) % 60:02d} energy={dsp.get('energy_5s', 0):.{nd}f} "
            f"trend={dsp.get('trend', 0):+.{nd}f} bass_gap={dsp.get('bass_gap', 0):.0f}s "
            f"kick_rate={kick_rate:.1f}/s")
