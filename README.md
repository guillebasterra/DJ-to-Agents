# Agent Crowd: a 3D aquarium of 100 Gemini agents

100 Gemini-driven agents float in a 3D aquarium in front of the DJ and compete for the
hot spot at the center of the front glass while a DJ set plays. They only hear the audio.
See `plan.md` for the full design.

## Run

```
uv venv --python 3.11 .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m server.main --seed 1 --condition talk   # backend, port 8001
cd web && npm install && npm run dev                     # http://localhost:5174
```

`.env` needs `GEMINI_API_KEY`, `MODEL_DECISIONS`, `MODEL_HYDROGEN`, `MODEL_NEON`.
Put MP3s in `tracks/` (gitignored). `web/?fake=1` runs the renderer with no backend.

## API check (phase 0)

`python -m server.api_check clip.wav` prints the raw responses.

| Call | Latency |
| --- | --- |
| Decisions, 8 s audio clip + 3 questions | 1.3 s |
| Hydrogen structured JSON, with 8 s audio | 2.8 s |

Decisions accepts raw audio directly, so the Hydrogen perception fallback is not needed.

## Decisions made

- Python venv is created with `uv` (Python 3.11); the plan assumed it already existed.
- Renderer: one set of 20,000 dots per sphere instead of four sets of 3,000. The dots are sampled over the
  camera-facing disc and turned toward the camera in the shader, and each agent offsets the dither hash, so no
  two spheres share a pattern. 3,000 dots were far too sparse for spheres near the glass. Runs at 60 fps; if the
  frame rate sits below 50 for 3 s the dot count halves (down to the plan's 1,500).
- A background-colored body is drawn inside each point cloud so nearer spheres cover farther ones.
- Dots are 1 px far away and grow to 2.4 px near the glass (plan: 1-1.5 px), so near spheres stay dense.
- Tracks are listed and served by Vite (`import.meta.glob` on `../tracks`), so the backend never touches files.
- `clock.dsp` carries an extra `kicks` count (kicks since the last clock message) next to the `kick` flag,
  so the backend can compute kick_rate from a 4 Hz stream.
- Dev hook: `?track=0` starts the first track without the picker (only works where autoplay is allowed).
- Physics: `retreat` counts as resting for energy recovery (otherwise an exhausted agent could never get back
  to E >= 0.3). `pressure` is the summed overlap with a 12% soft margin, so agents in resting contact still
  flatten a little. `Agent.target` is a 3D point.
- Physics, energy and happiness only advance while audio is playing; frames keep streaming while paused.
- Phase B check: `python -m server.headless` runs physics + shove on a synthetic loud / quiet schedule.
- Runs: a new run folder starts when the condition, the source, or the crowd (R = reset) changes. Switching
  condition keeps the crowd where it is, so the demo can flip minds on and off mid-track. Seed and starting
  condition come from the CLI: `python -m server.main --seed 1 --condition talk`.
- `GET /status` on the backend reports playback, tick and run state (for debugging).
- Ring 3's low-pass is 6 kHz, because the plan's 8 kHz is the Nyquist frequency of the 16 kHz stream.
- Band features are peak-hold envelopes (0.4 s release) of linear band amplitude, so `energy` reads as a
  loudness level instead of dipping to zero between kicks.
- Display only: happiness is stretched for color (`1 - exp(-6H)`) because the plan's u / 3 keeps real H mostly
  below 0.5. Logs and analysis use the raw H.
- Energy constants tuned (the plan allows it): a = 0.012, b = 0.006, d = 0.002, c = 0.050. With the plan's
  values the whole crowd was exhausted about 50 s into the track and never recovered.
- Agent prompt: the plan's template plus one line saying what the traits mean and one line of game rules
  (the front pays off at the drop; pushing, dancing and the crush drain energy; rest restores it; at energy 0
  you are carried to the back). Without it every agent chose `dance` on every tick, whatever its traits.
- Crowded rings are split into calls of at most 50 agents, run in parallel.
- Drop onset = "drop" becomes the house ear's top section after build or breakdown was the top section.
  The plan's p > 0.5 thresholds never fired: with seven options the top probability sits around 0.35-0.5.
  For the same reason w tops out near 1.8 instead of 3.
- Ask answers are sampled: the blocker says yes with probability p (seeded RNG) instead of the plan's
  p >= 0.5 cut-off. With the cut-off, 0 of 108 asks got a yes, although p clearly moved with traits, wording
  and yield history (0.11 to 0.41). The answer prompt also states that stepping aside takes about 2 s.
- Asks are also pushed to the client the moment Hydrogen returns (`{"type":"asks"}`), not only in the next
  decision frame. An asker waits for its answer before asking again; a pair waits 3 ticks before a repeat.
- Hydrogen asks have their own concurrency lane (8) so they never queue in front of the ring calls.
- Scripted runs: `tools/headless_run.py` drives the real web client in headless Chrome against a built copy
  served by the backend at `/app` (`cd web && npx vite build --base=/app/`), so dev-server hot reloads can't
  restart a run. `tools/run_all.sh` records shove, silent and talk back to back on the same track and seed.

## Credits

- [three.js](https://threejs.org) (MIT) for the WebGL renderer.
