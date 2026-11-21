"""One folder per run: meta.json, session.wav, ticks.jsonl, asks.jsonl (plan section 11)."""
import json
import subprocess
import time
from pathlib import Path

import soundfile as sf

from . import config as C

ROOT = Path(__file__).resolve().parent.parent / "runs"


def _git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True).strip()
    except Exception:
        return ""


class RunLog:
    """Created lazily: the folder appears when the first audio chunk arrives."""

    def __init__(self, world):
        self.world = world
        self.dir = None
        self.wav = None
        self.ticks = None
        self.asks = None

    def _open(self):
        w = self.world
        self.dir = ROOT / f"{time.strftime('%Y%m%d-%H%M%S')}_{w.condition}_{w.seed}"
        self.dir.mkdir(parents=True, exist_ok=True)
        meta = {"source": w.source, "seed": w.seed, "condition": w.condition, "git_sha": _git_sha(),
                "tick_seconds": C.TICK_SECONDS, "constants": C.constants(),
                "agents": [{"id": a.id, "archetype": a.archetype, "lane": a.lane, "k": a.k, "s": a.s}
                           for a in w.agents]}
        (self.dir / "meta.json").write_text(json.dumps(meta, indent=1))
        self.wav = sf.SoundFile(self.dir / "session.wav", "w", samplerate=C.AUDIO_SR, channels=1, subtype="PCM_16")
        self.ticks = open(self.dir / "ticks.jsonl", "a")
        self.asks = open(self.dir / "asks.jsonl", "a")

    def audio(self, pcm):
        if self.dir is None:
            self._open()
        self.wav.write(pcm)
        self.wav.flush()

    def tick(self, line):
        if self.dir is None:
            return
        self.ticks.write(json.dumps(line) + "\n")
        self.ticks.flush()

    def ask(self, line):
        if self.dir is None:
            return
        self.asks.write(json.dumps(line) + "\n")
        self.asks.flush()

    def close(self):
        for f in (self.wav, self.ticks, self.asks):
            if f is not None:
                f.close()
        self.wav = self.ticks = self.asks = None
