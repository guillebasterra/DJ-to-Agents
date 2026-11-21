# plan.md — Agent Crowd: 3D aquarium build

Build plan for a coding agent. Read this whole file before writing code. Build in the phase order at the bottom; each phase has a definition of done. The repo is already scaffolded (stubs, venv, Vite, .env). Fill in the stubs; files listed in the layout but not used in this plan can stay empty or be deleted.

---

## 0. What we're building

100 Gemini-driven agents float in a 3D aquarium in front of the DJ and compete for the hot spot at the center of the front glass while a live DJ set plays (Rekordbox → audio interface → browser). There are no track labels: everything about the music is deduced from the audio itself by the models. The front is worth most during the drop but drains energy; open space restores it. Agents decide what to do every ~3 s from what they hear (raw audio clips, filtered by their distance from the speakers), their own state and their neighbors. Mood is contagious: an agent's happiness drifts toward its neighbors'. Blocked agents argue in natural language to get past. The screen is the DJ's view into the aquarium: each agent is a stippled point-cloud sphere, colored by happiness, pulsing harder as the music builds to the drop, swelling as it fights its way toward the glass. Every run is logged and compared across three conditions (scripted shoving, silent agents, talking agents).

Hackathon: Gemini 4 NYC (Cerebral Valley + Google DeepMind). Submissions due 17:00.

### Hard rules
- **All project code is written during the event.** Third-party libraries are fine. Any borrowed snippet gets credited in README.md.
- **The repo must be public.**
- **Use at least two Gemini 4 models, each with a clear job:** Hydrogen (arguments between agents) and Neon (post-run report). Plus the Decisions API for per-agent actions.
- **The visual is the main thing on screen.** Stats live in a small toggleable corner panel.
- **Audio is always the model input.** Every Decisions call carries audio clips. Feature text is a supplement next to the audio, never a replacement. No hand-labeled sections anywhere.
- **Build on an MP3, stay live-ready.** Development uses an MP3 played in the browser. The models must never get anything a live set couldn't give them: no labels, no reading the file ahead, no knowledge of the track. The backend only receives audio that is actually playing, captured from playback, so switching to Rekordbox later is a source swap.

---

## 1. Architecture

```
Browser (Vite, plain WebGL2)                         Python backend (FastAPI + asyncio)
──────────────────────────────                      ─────────────────────────────────────
Input: live device (getUserMedia: BlackHole /       audio.py     rolling PCM buffer (30 s), recorder,
       mixer USB) OR file (dev / replay)                         ring filters → WAV clips
  └─ audio.js: FFT features @ 60 fps  ─clock+dsp (4 Hz)──►  physics.py   30 Hz, single source of truth
  └─ capture worklet: 16 kHz mono PCM ─binary PCM (4 Hz)─►  tick.py  every ~3 s:
  └─ plate.js: blob renderer   ◄──physics frames (30 Hz)──    sections.py  house ear: 1 Decisions call, full-quality audio
  └─ overlay.js: ids, threads  ◄──decision frames (/tick)─    decide.py    5 ring Decisions calls, filtered audio
                                                              negotiate.py Hydrogen asks + answers
                                                              log.py       JSONL every tick
                                               analysis/: analyze.py, neon_report.py, highlights.py
```

- **Physics** runs continuously and owns positions, velocity, density, energy, happiness and contagion.
- **The tick loop** (~3 s) asks the Decisions API for every agent's action, runs arguments, and updates targets.
- **No LLM coordinator.** Orchestration is plain Python.

---

## 2. Files in use

```
server/  main.py config.py state.py physics.py audio.py sections.py gemini_client.py
         decide.py wordofmouth.py negotiate.py shove.py tick.py log.py fake_agents.py
web/     index.html  src/main.js audio.js ws.js plate.js overlay.js palette.js ui.js fake.js  src/shaders/*.glsl
analysis/ analyze.py neon_report.py highlights.py
tracks/  (gitignored) dev audio files only, no labels
runs/    (gitignored) one folder per run, including the recorded session audio
```

- Python 3.11 deps already installed (fastapi, uvicorn, numpy, scipy, soundfile, pydantic, google-genai, python-dotenv, pandas, matplotlib).
- Web: Vite, no framework, plain WebGL2, Canvas2D overlay. Font: IBM Plex Mono.
- Model names come from `.env`: `MODEL_DECISIONS`, `MODEL_HYDROGEN`, `MODEL_NEON`.
- Audio path: the browser is the only thing that touches the input. It streams 16 kHz mono PCM to the backend; the backend never reads track files directly.
- `sections.py` is repurposed as the **house ear** (section 6). It does not load labels.
- **Ports:** backend on 8001, Vite on 5174 (another build of this project runs on the default ports).
- Three.js is allowed for the renderer (credit it in README).

---

## 3. Coordinates and constants (all in `config.py`)

- **Volume (the aquarium):** x ∈ [0, 1] left–right, y ∈ [0, 1] down–up, z ∈ [0, 1] distance from the DJ (z = 0 is the front glass). **No gravity:** agents float and can pass over, under and around each other.
- **Hot spot (front center):** H0 = (0.5, 0.5, 0.0). The DJ / camera sits in front of the glass at (0.5, 0.5, −0.35), looking down +z.
- **N_AGENTS = 100**, AGENT_RADIUS = 0.06, PHYSICS_HZ = 30, TICK_SECONDS = 3.0 (fallback 4.0).
- **Distance** d = |p − H0|; max ≈ 1.225.
- **Rings** by d; edges at 0.25, 0.45, 0.65, 0.85 → rings 1 (front) to 5 (back).
- **Max speed:** 0.06 units/s × (0.4 + 0.6 × E).
- **Collision iterations:** 4 per frame.
- **Density ρ** = neighbors within 2.5 × radius, capped at 12, ÷ 12.
- **Proximity v** = 1 − d / 1.225.
- **Energy constants** (per second; tune only these): a = 0.022 (front crush), b = 0.010 (push), d = 0.008 (dance), c = 0.033 (rest recovery).
- **Exhaustion:** at E ≤ 0 the agent is forced into `retreat` until E ≥ 0.3.
- **Happiness smoothing:** EMA with τ = 10 s.
- **Contagion:** κ = 0.15 per second, neighbors within 3 × radius.
- **Section weights:** drop 3.0, build 1.5, groove 1.0, intro / breakdown / outro / other 0.5. The live weight w is the house ear's expected weight: w = Σ p(section) × weight(section).
- **Audio:** AUDIO_SR = 16000, PCM_CHUNK_MS = 250, BUFFER_SECONDS = 30, RING_CLIP_SECONDS = 8, HOUSE_CLIP_SECONDS = 15.
- **MAX_ASKS_PER_TICK = 8** (fallback 4).

---

## 4. Agent state (`state.py`)

```python
@dataclass
class Agent:
    id: int
    x: float; y: float; z: float; vx: float; vy: float; vz: float
    E: float = 0.8                 # energy (fatigue reserve)
    k: float                       # trait: keenness for the front (fixed)
    s: float                       # trait: need for space (fixed)
    archetype: str                 # "diehard" | "dancer" | "between"
    lane: int                      # starting column 0..9 on the back wall (used in the regression)
    action: str = "hold"           # hold | push | yield | rest | dance | retreat
    pushiness: float = 0.3
    target: tuple[float, float]
    H: float = 0.5                 # happiness / vibe, smoothed
    u: float = 0.0                 # instantaneous utility
    rho: float = 0.0; v: float = 0.0; pressure: float = 0.0
    exhausted: bool = False
    last_heard: dict               # word-of-mouth line from last tick
```

**Traits (seeded RNG, seed from the CLI)**
- diehard (30%): k = 0.9, s = 0.1
- dancer (30%): k = 0.3, s = 0.9
- between (40%): k = 0.5, s = 0.5
- Add uniform noise ±0.1 to each, clipped to [0, 1].

**Start positions:** on the back wall (z ∈ [0.85, 0.97]), 10 columns across x, 10 agents per column spread over y, with jitter.

**Yield counters:** `yielded_to[a][b]` (how many times a yielded to b). No promises or ledger.

---

## 5. Physics (`physics.py`, 30 Hz, 3D)

Each frame (dt = 1/30):

1. **Target by action** (recompute when the action changes or every 0.5 s):
   - `hold` / `dance`: current position.
   - `push`: current position + 0.08 × unit vector toward H0.
   - `yield`: sidestep 0.08 perpendicular to the direction to H0; sample 6 perpendicular directions and pick the least dense.
   - `rest`: center of the lowest-density cell within radius 0.3 (6×6×6 density grid).
   - `retreat`: (x, y, 0.95).
2. **Integrate:** velocity steers toward the target, clamped to max speed; position += velocity × dt. Light damping so floating agents settle instead of drifting forever.
3. **Collide:** brute force over all pairs, spheres in 3D; separate along the contact normal, split by inverse mass where **mass = 0.2 + pushiness × E**. Accumulate overlap depth into `pressure` and keep the **contact normal with the largest overlap** (the renderer squashes along it). Clamp to the box walls; the front glass (z < 0) is a wall. 4 iterations.
4. **Derive** ρ and v.
5. **Energy:**
   - dE/dt = −a·v·ρ − b·[push] − d·[dance] + c·(1 − v)·(1 − ρ)·[rest or hold with ρ < 0.2]
   - Clip E to [0, 1]. Apply the exhaustion rule.
6. **Happiness:**
   - u = E · (k · v · w(section) + s · (1 − ρ) · music_energy) / (k + s); u_norm = u / 3
   - H ← EMA(H, u_norm, τ = 10 s)
   - **Contagion:** H ← H + κ · (mean H of neighbors − H) · dt
   - w(section) is the house ear's latest expected weight (section 6); `music_energy` is the latest browser value. **Agents are never told w or the house ear's answers.**
   - If the house ear call fails, keep the previous w; before the first answer, w = 1.0.
7. **Broadcast** a physics frame (section 9).

---

## 6. Audio (`audio.py`, `web/src/audio.js`)

**Browser (60 fps, AnalyserNode, fftSize 2048)**
- Bands: sub < 60 Hz, bass 60–250, mid 250–2k, high > 2k, plus rms. Normalize each by a decaying running max.
- kick: onset on the low band (spectral flux over threshold, 120 ms refractory).
- energy = 0.6 × bass + 0.4 × rms.
- energy_5s = mean energy over the last 5 s; trend = energy_5s − mean of the 5 s before.
- bass_gap = seconds since bass was last above 0.35.
- Send `{type: "clock", t, playing, dsp: {...}}` 4× per second. In live mode, t = seconds since the session started.
- These features drive the visuals (pulse, kick) and the energy term. The models get the audio itself.

**Input sources (`audio.js`, `ui.js`)**
- **File (build with this):** an `<audio>` element playing an MP3 from `tracks/`, wrapped with `createMediaElementSource`. Played out loud.
- **Live (switch at the end, phase L):** `getUserMedia({audio: {deviceId, echoCancellation: false, noiseSuppression: false, autoGainControl: false}})` wrapped with `createMediaStreamSource`. A device picker lists inputs from `enumerateDevices()` (BlackHole 2ch, the mixer's USB). Not played out of the browser (the DJ setup already feeds the speakers).
- Everything after the source node is shared: source → AnalyserNode (features) and → an AudioWorklet that downsamples to 16 kHz mono Int16 and posts 250 ms chunks. **Write audio.js so the source is a single swappable function.**
- Send each chunk to the backend as a **binary** WebSocket message.
- **Follow playback:** chunks only flow while audio is playing. On pause, stop sending and the tick loop pauses. On seek, send `{"type":"control","action":"seek"}` and the backend clears its buffer.

**Backend (`audio.py`)**
- A rolling 30 s PCM buffer, filled from the binary WebSocket messages.
- **Recorder:** append every chunk to `runs/<run>/session.wav`, so a live session can be replayed later through file mode.
- `clip(seconds)` → the last N seconds of the buffer.
- **Ring filters** (scipy butter + gain), applied to an 8 s clip:

| Ring | Filter |
| --- | --- |
| 1 front | +3 dB, low shelf +4 dB below 120 Hz |
| 2 near | unchanged |
| 3 mid | low-pass 8 kHz |
| 4 far | low-pass 3 kHz, −6 dB |
| 5 back | low-pass 1.5 kHz, −12 dB |

- Encode each ring clip as WAV bytes → base64.
- **Features text per ring** (sent alongside the audio, never instead of it): `"t=1:24 energy=0.31 trend=+0.12 bass_gap=6s kick_rate=1.9/s"`. Round to 1 decimal in rings 4–5.

**House ear (`sections.py`)**
- Once per tick, one Decisions call on the **unfiltered** last 15 s of audio, with the same section / drop_eta / rising questions as the rings (section 8.1), keys prefixed `house_`.
- Output: section probabilities → w; `house_drop_eta` and `house_rising` are logged.
- This is the system's best guess at the truth. It drives the reward and the analysis. It is never shown to agents.
- Drop onset (for analysis) = a tick where p(drop) crosses 0.5 after at least one tick of build or breakdown above 0.5.

---

## 7. Gemini calls (`gemini_client.py`)

**Verify these API shapes first** against the current docs and the hackathon Builder Resources, by printing raw responses before writing any parser. The field names below are from third-party guides.
- Decisions: https://ai.google.dev/gemini-api/docs
- Structured output: https://ai.google.dev/gemini-api/docs/generate-content/structured-output

### 7.1 Decisions API (`MODEL_DECISIONS`)

```python
client = genai.Client(http_options={"api_version": "v1beta"})
res = client.decisions.create(          # async client if available; else run in a thread
    model=MODEL_DECISIONS,
    input=[{"type": "audio", "data": b64_wav, "mime_type": "audio/wav"},
           {"type": "text",  "text": features_text}],
    questions={ key: {"type": "choice"|"noul"|"score", "instructions": "...", "criteria": ...} },
)
```

- **noul** (yes/no): returns the probability of yes.
- **choice:** criteria `{option: description}`; returns the top option + per-option probabilities.
- **score:** criteria = list of levels, lowest first; returns a probability-weighted index.
- Questions are isolated, no history. Keys match `[A-Za-z0-9_-]{1,64}`.

**If the Decisions API won't take audio** (check in Phase 0): use Hydrogen with the audio clips as the perception step, one call per ring plus the house ear, asking for section / drop_eta / rising as structured JSON. Then pass those answers as text into the Decisions per-agent questions. Audio stays the source of truth either way.
**If audio calls are slow:** shorten RING_CLIP_SECONDS to 5, then raise TICK_SECONDS to 4. Don't drop the audio.

### 7.2 Hydrogen (`MODEL_HYDROGEN`)
- Thinking level **low**. JSON schema response, parsed with Pydantic.

### 7.3 Neon (`MODEL_NEON`)
- Thinking high. Used once, offline, after runs.

### Client requirements
- asyncio semaphore (8 concurrent); 8 s timeout per call, one retry with backoff.
- **On failure, the agent keeps its previous action.** Log it; never crash the loop.
- Log latency and token usage of every call.

---

## 8. The tick loop (`tick.py`, every TICK_SECONDS)

1. Read the latest t and DSP from the browser; cut the house clip and ring clips from the audio buffer.
2. Bucket agents into rings by current distance.
3. **Condition switch:**
   - **shove:** actions from `shove.py`; skip 4–6 (the house ear still runs, since the reward needs w).
   - **silent:** run 4–5, skip 6.
   - **talk:** run all.
4. **Decisions** (`decide.py` + `sections.py`): the house ear call plus one call per non-empty ring, all in parallel.
5. **Apply actions:** set action and pushiness; update word of mouth.
6. **Argue** (`negotiate.py`): detect contests, run Hydrogen asks (async; answers land in the *next* tick's ring call).
7. Recompute targets.
8. Send a decision frame; write the log line.

### 8.1 Ring call contents (`decide.py`)

**Ring-level questions**
- `r{n}_section`: choice {intro, build, drop, groove, breakdown, outro, other}, one-line description each.
- `r{n}_drop_eta`: choice {now, next_8_bars, within_32_bars, not_soon}.
- `r{n}_rising`: noul, "Is the energy building right now?"

**Per-agent questions**
- `a{id}_action`: choice:
  - hold: "stay where you are"
  - push: "move toward the DJ; costs energy"
  - yield: "step aside so someone behind can pass"
  - rest: "drift to open space and recover energy"
  - dance: "use the room you have to dance; costs a little energy"
- `a{id}_push`: score ["gently", "firmly", "hard"]; pushiness = score / 2.
- `a{id}_ans_{asker}`: noul, only if someone asked this agent last tick.

**Instructions template for `a{id}_action`** (under ~90 tokens):

```
You are A{id} in a packed crowd, ring {r} of 5 from the DJ (1 = front).
Traits: keen {k:.1f}, space {s:.1f}. Now: energy {E:.2f}, proximity {v:.2f}, crowding {rho:.2f}, happiness {H:.2f}.
Neighbors: {A7 pushing, A30 resting}. {Word from ring 2: drop next_8_bars (0.70).}
Given what you hear, what do you do now?
```

- Exhausted agents are skipped; their action is forced to `retreat`.

### 8.2 Word of mouth (`wordofmouth.py`, no LLM)
- After each tick, ring n's message = {drop_eta top option + probability, rising probability}.
- Next tick, agents in ring n+1 get "Word from ring n: ...". One ring per tick.
- Agents also see their 3 nearest neighbors' last actions.
- silent and talk get word of mouth; shove gets none.

### 8.3 Arguing (`negotiate.py`, talk condition only)

**Contest detection**
- A pushing agent is **blocked** if a neighbor sits within 2.2 × radius inside its 3D forward cone (±35° toward H0) and that neighbor isn't yielding.
- Score = pushiness × (v_blocker − v_asker + 0.1). Take the top MAX_ASKS_PER_TICK; the rest just collide.

**Hydrogen ask.** The prompt gives the asker's traits, E, H, ring and what it heard; the blocker's public state (position, apparent energy low/med/high, current action); and how many times each has yielded to the other.

```python
class Ask(BaseModel):
    text: str                 # one sentence, <= 20 words, in the asker's voice
    claimed_keenness: float   # 0..1, how much the asker says it cares
```

The system prompt says the agent wants to get closer to the DJ. **Do not instruct it to lie or to be honest.** Just let it act, and measure.

**Answer:** next tick, add `a{blocker}_ans_{asker}` (noul) to the blocker's ring call, with the ask text, claimed keenness, and the blocker's own state and yield history with the asker.
- p ≥ 0.5 → yes: blocker yields for 2 s; increment `yielded_to[blocker][asker]`.
- No: the asker keeps pushing (physics decides by mass).

**Truth check (logged, never shown):** claimed_keenness vs. the asker's true k.

### 8.4 Shove baseline (`shove.py`)
- E < 0.2 → rest.
- diehard → push (pushiness 0.9).
- dancer → if ρ > 0.4 rest, else dance.
- between → push when music_energy > 0.6, else hold.

---

## 9. WebSocket contract (`/ws`, JSON)

**Server → client, physics frame (30 Hz):**
```json
{"type":"physics","t":84.03,"agents":[[12,0.48,0.52,0.09,0.01,0.0,-0.02,0.62,0.81,0.55,"push",0.12,0.0,0.7,0.7]]}
```
Each agent is `[id, x, y, z, vx, vy, vz, E, rho, H, action, pressure, nx, ny, nz]` (n = main contact normal).

**Server → client, decision frame (each tick):**
```json
{"type":"decision","t":84.0,"condition":"talk","tick":28,
 "rings":{"1":{"section":"build","drop_eta":"next_8_bars","p":0.72}},
 "asks":[{"id":"q91","from":41,"to":12,"text":"let me in, this drop is everything to me","answer":"pending"}],
 "answers":[{"id":"q88","answer":"yes"}]}
```

**Server → client, on connect:** `{"type":"init","agents":[{"id","archetype","lane","k","s"}],"n_lanes":10}`

**Client → server:**
```json
{"type":"clock","t":84.0,"playing":true,"source":"live","dsp":{"sub":0.7,"bass":0.8,"mid":0.4,"high":0.3,"rms":0.61,"kick":true,"energy":0.73,"energy_5s":0.55,"trend":0.12,"bass_gap":0}}
{"type":"control","condition":"talk"}   // also: "reset", "pause", "seek", {"type":"control","source":"file"|"live","label":"..."}
```
Plus **binary messages**: raw Int16 PCM, 16 kHz mono, 250 ms per message.

**Dev mode:** `web/?fake=1` runs `fake.js` (random-walk agents and fake decisions), no backend.

---

## 10. Renderer: stippled spheres in an aquarium (`plate.js`, shaders, `overlay.js`)

**Reference images** (in `docs/ref/`):
- `aquarium.gif` = **the look**: spheres made of crisp dithered dots on a near-black background, a limited red / blue / off-white palette with dots of different colors mixed rather than blended, shading by dot density, soft speckled edges, nearer spheres covering farther ones.
- `packing.gif` = **contact behavior only**: bodies flatten where they press against each other and never merge. Ignore its look.
- `tlc.jpg` is not used in this build.
In phase A and phase H, screenshot `web/?fake=1` after each change and compare against both.

**Camera:** the DJ's view. Perspective camera at (0.5, 0.5, −0.35) looking at (0.5, 0.5, 0.5), FOV ~60°. The hot spot is the center of the screen, nearest the viewer: agents swell as they get closer. Slow camera drift (±0.03) to reveal depth.

**Background:** #1a1214 with faint grain.

**Spheres (point clouds):**
- Precompute 4 unit-sphere point sets of ~3,000 points each, biased toward the surface. Each agent instances one; per-agent data (position, pulsed radius, squash normal + amount, velocity, E, H) comes from a data texture or instanced attributes.
- **Stipple shading:** per point, lambert = dot(normal, light) with the light from upper-left-front. Keep the point if hash(point id) < f(lambert), so lit sides are dense and shadow sides sparse (dithering by density, not by brightness). Add a speckled rim.
- **Dots:** 1–1.5 px squares, DPR-aware, no smoothing. Depth test on.
- **Happiness → color, by mixing dots** (each point picks one of the three colors with probabilities set by H, never a blended color):

| H | Dot mix |
| --- | --- |
| 0.0 | mostly blue #1e6fc8, sparse |
| 0.4 | blue + red #e0322e |
| 0.7 | mostly red, some off-white |
| 1.0 | off-white #d8d4d6 core, red and blue dots at the edges |

- **Energy E → point count** (tired agents are sparse and ghostly).
- **Pulse:** radius = r × (1 + 0.15 × music_energy × E + 0.25 × kick_envelope × E), kick_envelope decaying over 120 ms. Pulsing grows into the drop.
- **Squash:** scale down along the main contact normal by 1 / (1 + 2 × pressure), volume-preserving, so packed agents flatten against each other.
- **Stretch:** mild elongation along velocity.
- **Depth fog:** far agents fade toward the background, so the back of the aquarium recedes.

**Overlay** (Canvas2D, DPR-aware, positions projected from 3D):
- agent ids (`A12`, 9 px mono, 55% opacity) beside each sphere;
- ask threads: thin line between asker and blocker with the ask text in 10 px mono, fading after 3 s; yes → grey-green, no → short red tick.

**UI (`ui.js`):** space = play/pause, 1/2/3 = condition, L = labels, D = tiny stats corner (mean H, mean E, asks/tick), I = input picker (file list; live devices once phase L is done). The picker hides itself after selection.

**Interpolation:** render at 60 fps, linear interpolation between the last two physics frames.

**Performance:** 100 × 3,000 = 300k points. If below 60 fps, drop to 1,500 per sphere.

### Extended visual detail (phase H, after the core runs)
- **Faces:** a darker dot pattern (two eyes, a mouth) carved out of the density on the camera-facing side, turning toward the agent's motion. Generic faces only.
- **Dance hop:** agents with action `dance` bob along y on the kick.
- **Trails:** a few previous positions as faint, sparse ghost dots.
- **Chromatic fringe:** red and blue dots offset slightly at sphere edges, as in the reference.
- **Camera drift tuning** and a slow push-in on the drop.

---

## 11. Logging (`log.py`)

`runs/<timestamp>_<condition>_<seed>/`:
- **meta.json:** input source (live device name or file), seed, condition, constants, git sha.
- **session.wav:** the recorded input audio (16 kHz mono), so the run can be replayed.
- **ticks.jsonl:** per tick: `t`, `condition`, `house` (section probs, drop_eta, rising, w), `dsp`, `rings` (answers + probabilities), `agents` (`[{id, lane, x, y, E, v, rho, H, u, action, push, action_probs, ring, exhausted}]`), `asks`, `answers`, `api` (`{latency_ms, tokens, failures}`).
- **asks.jsonl:** one line per ask: prompt summary, Hydrogen output, answer, keenness truth check.

---

## 12. Analysis (`analysis/`)

**Core (phase F):**

**`analyze.py <run_dirs...>`** → `out/` with PNGs + `summary.json`:
1. **Anticipation:** mean proximity over time with shaded section bands from the house ear, one line per condition. Report the lead time (s) between proximity starting to rise and the house-ear drop onset.
2. **Welfare and fairness:** histogram of per-agent mean H by condition. Report mean H and the Gini of per-agent mean H.

**Table in `summary.json`:** ask acceptance rate, reciprocity (P(yes | asker previously yielded to blocker) vs. base rate), mean (claimed_keenness − true k), exhaustion events per condition, API latency p50/p95.

**`neon_report.py`** → sends `summary.json` + 15 sampled asks (stratified by outcome and archetype) to Neon; gets back `{takeaways:[{claim, number, quote}], caveats:[...]}` × 5. Writes `report.md`.

**Full (phase H, after the core runs):**

Add to `analyze.py`:
3. **Anticipation detail:** each ring's `section` and `drop_eta` agreement with the house ear, by ring (does the back really hear late and muffled?).
4. **Pacing:** mean E over time, one line per condition. Report E at drop onset, the share of agents that rested during the breakdown, and exhaustion events.
5. **Who wins:** scatter of per-agent mean H vs. k, colored by archetype. Add an OLS regression (H ~ k + s + start_lane + ask_success_rate + rested_in_breakdown); coefficients go in `summary.json`.
6. **Extra tables:** gridlock = share of push-ticks with < 0.01 progress; contagion = correlation between an agent's H and its neighbors' mean H, per condition.

**`highlights.py`** → `highlights.json` with timestamps for:
- the biggest single-agent H swing;
- asks where claimed_keenness overstated true k by > 0.3 and the blocker still yielded;
- the most-asked and most-yielding agents;
- the crowd's maximum compression before the drop.

**Optional:** run `neon_report.py` as a Gemini Managed Agent so it can compute and plot itself (targets the $5,000 Managed Agents prize).

---

## 13. Build phases (in order; A and B in parallel)

**Human, before Phase 0:** put one or two MP3s in `tracks/` (no labels).

| Time | Phase | Definition of done |
| --- | --- | --- |
| 11:30–12:00 | **0. Skeleton + API check** | Repo public. FastAPI WebSocket echo works (JSON and binary). Raw responses printed for one Decisions call **with an audio block** and one Hydrogen structured call **with audio input**. If Decisions rejects audio, switch to the Hydrogen perception path (section 7.1) now. Latencies noted in README. |
| 12:00–13:15 | **A. Renderer + audio capture** (`?fake=1`) | 100 fake agents (3D random walk) render as stippled spheres from the DJ's view: dot-mixed happiness colors, energy density, pulse, squash, depth fog, overlay ids, kick pulse. MP3 playback through the shared audio graph; the capture worklet produces 16 kHz PCM chunks only while playing. 60 fps. |
| 12:00–13:15 | **B. Physics + shove** | `physics.py` + `shove.py` run headless. Until the house ear exists, drive w with a temporary DSP proxy (w = 0.5 + 2.5 × energy_5s) so you can see compression toward the hot spot on loud sections and dispersal on quiet ones, with agents passing over and under each other. Energy drains and recovers; exhaustion triggers retreat; happiness spreads. Frames streamed. |
| 13:15–13:45 | **C. Wire A + B** | Browser plays the MP3 and streams clock + PCM; pause and seek behave; backend buffers and records `session.wav`; the shove crowd renders and reacts to playback. **First demoable version.** Commit + tag `v0-shove`. |
| 13:45–14:45 | **D. House ear + Decisions loop** | House ear sets w (remove the DSP proxy). Ring clips + filters, parallel calls, parsing, word of mouth, logging. Silent condition runs a whole MP3 without errors; p95 tick latency < TICK_SECONDS. |
| 14:45–15:30 | **E. Arguing** | Contests, Hydrogen asks, answers next tick, yield counters, ask threads on screen. Talk condition runs a whole MP3. |
| 15:30–15:55 | **F. Runs + core analysis** | 3 runs (shove, silent, talk) on the same MP3 and seed. Core `analyze.py` and `neon_report.py` produce outputs. Pick 3 headline numbers. |
| 15:55–16:15 | **H. Extended visuals + full analysis** | Faces, dance hop, trails, chromatic fringe, camera drift (section 10). Pacing, who-wins + OLS, ring-vs-house agreement, extra tables, `highlights.py` (section 12). Re-run `neon_report.py` on the full summary. |
| 16:15–16:30 | **L. Switch to live** | Swap the source to `getUserMedia`, add the device picker. Human setup: install BlackHole 2ch; in Audio MIDI Setup create a Multi-Output Device (speakers + BlackHole) and set Rekordbox's output to it (or use the mixer's USB). Done when the crowd reacts to Rekordbox with nothing else changed. |
| 16:30–16:45 | **G. Polish + video** | Pulse and colors tuned. Record the 1-minute demo video (live Rekordbox if phase L worked, otherwise the MP3). |
| 16:45–17:00 | **Submit** | Repo public, README complete (what it is, how to run incl. BlackHole setup, credits, what was built today, what broke), video link works, teammates on the submission. |

If earlier phases finish early, start phase H sooner; the extended visuals can run in parallel with D or E.

**Cut order if behind:**
1. phase H items, in this order: OLS regression, chromatic fringe, highlights.py, trails, dance hop, faces, pacing plot,
2. points per sphere (down to 1,500),
3. word of mouth,
4. `neon_report.py` as a Managed Agent → plain single call (never drop Neon entirely: it's the second Gemini 4 model).

Phase L is small if audio.js keeps the source swappable; if time is short, demo on the MP3 and say live input is one swap away.

**Never cut** audio as the model input or the shove vs. silent vs. talk comparison.

---

## 14. Risks and fallbacks

- **Decisions API rejects audio:** Hydrogen perception path (section 7.1). Say so in the README.
- **Audio calls are slow:** shorter clips (5 s), then TICK_SECONDS → 4.
- **Live input is silent:** check the BlackHole multi-output device and that the browser's audio constraints disable echo cancellation / noise suppression / AGC. Fall back to the MP3 for the demo.
- **Live runs aren't repeatable:** compare conditions on the same MP3 (or a recorded `session.wav`).
- **Rate limits:** TICK_SECONDS → 4, MAX_ASKS_PER_TICK → 4; trim instruction text.
- **Hydrogen is slow:** asks are async; a late ask is fine. If p95 > 6 s, cap at 4 asks.
- **Too many points for 60 fps:** fewer points per sphere; skip agents fully hidden behind nearer ones.
- **3D packing hides the fight:** keep the camera drift, fog the back, and keep ask threads on top of everything.
- **Physics tuning eats time:** only touch a, b, c, d, κ and max speed.
- **Never block the render loop on the network.** Keep interpolating from the last frames.

---

## 15. Demo script (3 minutes live)

1. **(20 s)** "A house crowd is the purest human collective. What happens when the crowd is 100 copies of Gemini?"
2. **(60 s)** Live from Rekordbox (or the MP3), talk condition. Say up front: no track labels, the agents only hear the audio. Point out: spheres swelling toward the glass during the build; pulsing intensifying into the drop; color spreading through the crowd; spheres squashing and slipping past each other; a few ask threads with their text.
3. **(30 s)** Flip to shove: the same crowd with no minds.
4. **(50 s)** Three headline numbers from `summary.json` (e.g. drop lead time, ask acceptance / reciprocity, welfare vs. shove) plus one quoted ask.
5. **(20 s)** Where it broke and what changed.
