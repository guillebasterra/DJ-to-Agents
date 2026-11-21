# Agent Crowd: a 3D aquarium of 100 Gemini agents

100 Gemini-driven agents float in a 3D aquarium in front of the DJ and compete for the
hot spot at the center of the front glass while a DJ set plays. They only hear the audio.
See `plan.md` for the full design.

## Run

```
uv venv --python 3.11 .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/uvicorn server.main:app --port 8001          # backend
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

## Credits

- [three.js](https://threejs.org) (MIT) for the WebGL renderer.
