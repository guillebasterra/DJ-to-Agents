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

## Credits

- [three.js](https://threejs.org) (MIT) for the WebGL renderer.
