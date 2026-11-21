# Agent Crowd: a 3D aquarium of 100 Gemini agents

100 Gemini-driven agents float in a 3D aquarium in front of the DJ and compete for the
hot spot at the center of the front glass while a DJ set plays. They only hear the audio: no track labels,
no reading ahead. Built at the Gemini 4 NYC hackathon. See `plan.md` for the full design.

- **Decisions API** (`gemini-decision-1`): every ~3 s each ring of the crowd hears its own filtered 8 s clip
  (loud and bassy at the front, quiet and muffled at the back) and every agent in it picks an action. A
  separate "house ear" call on the unfiltered audio guesses the section and sets the reward; agents never see it.
- **Gemini 4 Hydrogen**: a blocked agent asks the one in its way to let it past, in its own words. The blocker
  answers in its next Decisions call. Nobody is told to lie or to be honest; claims are logged against traits.
- **Gemini 4 Neon**: reads the run summary and sampled asks after the runs and writes `out/report.md`.
- Three conditions on the same audio: `shove` (scripted, no model), `silent` (Decisions only), `talk` (all).

The screen is the DJ's view into the box, drawn as pigment on warm paper: each agent is a soft blob. Hue is
happiness (grey-violet, blue-violet, purple, magenta, red-orange), pigment density is energy, size is
archetype, and bodies squash, wobble and flatten against the glass. A chat panel on the right shows who is
asking whom, the answers, and what each ring and the booth think they hear.

![breakdown, build and drop](docs/pass2_moments.png)

Top to bottom: a breakdown (170 s), the build (182 s) and the drop (188 s) of the same talk run.

## Run

```
uv venv --python 3.11 .venv && uv pip install -p .venv/bin/python -r requirements.txt
.venv/bin/python -m server.main --seed 1 --condition talk   # backend, port 8001
cd web && npm install && npm run dev                     # http://localhost:5174
```

Then press `I`, pick a track (or a live input) and watch. `1/2/3` switches shove / silent / talk mid-track.

```
(cd web && npx vite build --base=/app/) && tools/run_all.sh      # one full run per condition
.venv/bin/python analysis/analyze.py runs/* --out out             # plots + summary.json
.venv/bin/python analysis/neon_report.py runs/<talk run> --out out
.venv/bin/python analysis/highlights.py runs/<talk run> --out out
.venv/bin/python tools/record_demo.py tracks/<file>.mp3 140 60    # demo clip -> runs/demo.mp4
```

`.env` needs `GEMINI_API_KEY`, `MODEL_DECISIONS`, `MODEL_HYDROGEN`, `MODEL_NEON`.
Put MP3s in `tracks/` (gitignored). `web/?fake=1` runs the renderer with no backend.

## Live input (Rekordbox)

1. Install BlackHole 2ch. In Audio MIDI Setup create a Multi-Output Device (speakers + BlackHole 2ch) and set
   Rekordbox's output to it (or plug in the mixer's USB audio).
2. Open http://localhost:5174, press `I`, click "allow audio input to list devices...", then pick
   "BlackHole 2ch" (or the mixer). Nothing else changes: the same analyser and capture worklet feed the backend.
3. If the crowd doesn't react, check that the Multi-Output Device is Rekordbox's output and that macOS gave
   the browser microphone permission. Every live session is recorded to `runs/<run>/session.wav` and can be
   replayed from the picker under "Recorded sessions".

Keys: `space` play/pause, `1/2/3` shove/silent/talk, `C` chat, `L` labels, `D` stats, `I` input picker, `R` reset crowd.

## API check (phase 0)

`python -m server.api_check clip.wav` prints the raw responses.

| Call | Latency |
| --- | --- |
| Decisions, 8 s audio clip + 3 questions | 1.3 s |
| Hydrogen structured JSON, with 8 s audio | 2.8 s |

Decisions accepts raw audio directly, so the Hydrogen perception fallback is not needed.

## Results (one run per condition, same track, seed 1)

`tools/run_all.sh` recorded shove, silent and talk on the same 340 s track; `analysis/analyze.py runs/*`
wrote `out/` (plots, `summary.json`), `analysis/neon_report.py` wrote `out/report.md` (Gemini 4 Neon) and
`analysis/highlights.py` wrote `out/highlights.json`. Zero API failures in all three runs; tick latency
p50 1.3 s, p95 3.0 s with 100 agents.

Three headline numbers:

1. **The back of the room hears the drop late.** Agreement with the house ear on *when the drop lands* falls
   from 83% in ring 1 to 53% in ring 5 (silent run; 75% to 50% in talk), while agreement on the current
   section stays flat at about 84%. The only difference between rings is the filtered audio they hear.
2. **Agents ask politely and honestly, and one ask in four works.** 337 asks, 25.8% accepted. Claimed
   keenness minus true keenness averaged +0.004; nobody overclaimed by more than 0.3.
3. **Minds pace themselves, but don't end up happier.** 79% (silent) and 89% (talk) of agents rested during
   a breakdown against 60% under scripted shoving, with zero exhaustion events. Mean happiness was no better
   than shove, though (0.065 vs 0.071), at about 65 times the tokens.

These three runs were recorded before the two rework passes below (single hot spot, smaller and slower
agents, hard collisions, H = u / 3); they have not been re-recorded, so the numbers describe the old physics. One run per condition, so small differences are noise; `out/report.md` lists the caveats. Reciprocity could
not be measured (only 11 asks came from someone who had yielded to the blocker before).

![anticipation](out/anticipation.png)
![ring agreement](out/ring_agreement.png)

## Decisions made

### Visual + feel pass 2 (latest; replaces the renderer notes of the first rework)

- Look: pigment on paper. The paper is #f6ebe6 with drifting +-3.5% grain and a slight vignette; blobs
  write absorbance and the final pass composites `paper * exp(-A)`. Pigment also gets a slow per-pixel
  "tooth" (0.78-1.22) so washes look granular. There was no image of the other build's TLC plate in this
  repo, so the look follows the written spec.
- Palette: #b9b3c9 -> #6b6eb8 -> #8a3fa0 -> #d12f7a -> #d9481c interpolated in OKLab, +-8 degrees of hue
  jitter (a rotation in the OKLab a/b plane). Mapping: 56% smoothed crowd p05-p95 (tau 1.4 s) + 44% absolute
  anchor (H 0.1-0.8), half-strength smoothstep. Density = 0.18 + 1.32 * E.
- "Touching blobs keep a thin paper gap, never merge": bodies are depth-tested billboards, and the outer 5%
  of each body is an unpainted rim that still covers what is behind it. That gives the paper gap wherever
  two bodies touch or overlap on screen. The blobs are not blended with a smooth-min any more: pressing is
  shown by each body's own deformation (squash along the contact normal with perpendicular bulge, stretch
  along velocity, three wobble modes).
- Soft bodies: wobble modes 2, 3 and 4 around the outline, each a spring-damper (13 / 19 / 26 rad/s,
  damping ratio 0.16-0.22), kicked by impacts (rise in contact pressure), changes of velocity and the kick.
  Squash and glass press have their own spring-dampers. All of this lives in the renderer.
- Glass: physics lets a body press to 0.62 of its radius from z = 0; the renderer then widens it up to 30%
  and adds pigment at the center of the contact. It springs back by 1.2 radii from the glass.
- Depth: on top of real perspective (camera z = -1.12, 54 degrees), size is scaled 1.28x at the glass down
  to 0.74x at the back, and pigment fades to 30% at the back, i.e. toward the paper.
- Trails: `max(current * 0.5, previous * 0.985)` per 1/60 s, with the previous frame scaled 0.16% toward
  the center of the screen (the vanishing point), so smears drift away from the glass.
- Happiness: H follows u / 0.75 instead of u / 3 (u / 1.5 still gave a 5-95% range of only 0.06-0.39; with
  0.75 the headless run spans 0.14-0.83). Logged H and u are the raw values. Agents see their H in the
  prompt, so decisions can shift with this change.
- Hot zone: the band x 0.3-0.7, y 0.35-0.65 on the glass. Proximity, rings, push direction, the blocked
  cone and the tide all use the nearest point of the band. D_MAX is 1.101.
- Sizes: radius = 0.07 x archetype (diehard 1.2, between 1.0, dancer 0.85) x +-10% jitter x (1 - 0.15 (1 - E)).
  Collisions use each pair's own radii, mass is multiplied by size squared, and "blocked" means within
  1.1 x the two radii. The size jitter uses its own RNG stream, so traits and start positions are unchanged.
- Music scales movement, never decisions: the house ear's section probabilities (smoothed, tau 2.5 s) add
  forward drift with p(build), a pull to the glass with p(drop), drift back and extra personal space with
  p(breakdown), and raise max speed by up to 50% (build) / 30% (drop). The renderer adds the bob and sway:
  everyone bobs on the kick with p(drop), pushers included; sway is slow and gentle in a breakdown.
- Chat panel: asks appear when Hydrogen returns; each tick adds up to three answers, two notable moves
  (pushes hard = pushiness >= 0.75, gives up the push, exhausted), one ring's hearing (a different ring each
  tick) and the booth. The client shows at most 6 lines per tick. Agent ids take the agent's pigment color at
  the time the line is written.
- Plate: at most 3 ask threads at once, as a bowed line with a bubble by the asker (sentence cut at 54
  characters), fading after 3 s. With the chat open the plate is centered in the space left of it.
- Headless check (`python -m server.headless`, shove, synthetic loud / quiet): mean proximity 0.66 loud vs
  0.45 quiet (gap 0.21); diehards 0.66, between 0.58, dancers 0.48.

### Visual + physics rework (replaces the renderer and collision notes further down)

- Renderer: one billboard per agent (a screen-space sphere impostor) instead of point clouds. Pass 1 adds
  every blob's `exp(-k * sdf)` into a half-float field; pass 2 takes `-log / k` of the sum, which is a
  smooth-min of the distance fields, so touching blobs bulge into each other and share glow and halo while
  each keeps its body; pass 3 turns alpha into fine 1 px grain at device resolution. Faces, trail ghosts,
  the chromatic fringe and the occluder bodies are gone. 60 fps; if it drops below 50 the field resolution
  steps down (the grain stays 1 px).
- Where blobs overlap on screen, color is a weighted average with weight `exp(-14 * depth)`, so the nearer
  body wins and stays readable. That is ordering by weight, not a depth buffer.
- Grain: each pixel has a fixed hash threshold that drifts at its own slow rate. It shimmers, never flickers,
  and no shape is resampled per frame.
- Trails: the resolved image is kept in an accumulation buffer, `max(current, previous * decay)` with a
  0.55 s time constant, so stationary blobs don't thicken and moving ones leave a fading grainy smear.
- Color: happiness is mapped over the crowd's own spread (smoothed p05-p95, 55%) blended with an absolute
  anchor (45%), then an S-curve, onto teal -> cyan -> a narrow pale band -> orange -> red-orange, with +-8
  degrees of hue jitter per agent. A straight hue sweep from teal to orange would pass through green.
  Energy sets glow: tired agents fade toward the background grey and their halo thins.
- Camera sits at z = -1.2 with a 50 degree lens (plan: -0.35, 60 degrees), so the whole box fits with margin.
- Squash is a spring-damper per agent in the renderer (stiffness 150, damping 9, underdamped), driven by
  the backend's contact pressure and normal, so blobs wobble after impacts.
- Dancers' kick bob (140 ms envelope) is done in the renderer, not the backend: the backend only sees kicks
  through the 4 Hz clock, which is too coarse to bob on.
- Physics: agent radius 0.075 (was 0.06), max speed 0.11 (was 0.06). Always-on Ornstein-Uhlenbeck wander
  (tau 1.6 s; dancer 1.6x, between 1.0x, diehard 0.55x), anti-stall nudge, soft quadratic wall push (half
  strength at the front glass), soft spring collisions (0.14 per substep, 3 substeps, overlap capped at 25%
  of a diameter), mass = 0.08 + 2.5 * pushiness^2 * E, and a tangential shoulder slip for a pusher blocked
  by a lighter agent.
- To get a clear loud / quiet contrast, three rules were added that apply equally in every condition: a
  "tide" (everyone leans toward the glass when loud and eases back when quiet, scaled by keenness), pushing
  at 55% strength in silence, and 16% extra personal space in quiet passages. On the synthetic schedule
  (`python -m server.headless`) mean proximity is 0.57 loud vs 0.48 quiet (gap 0.10) and diehards hold the
  front (0.61 vs 0.53 between, 0.46 dancers). Agents' rewards and prompts are unchanged.
- Overlay: an ask's sentence shows while it is open; once answered only `[yes]` / `[no]` stays, and texts
  step down instead of printing over each other.

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
- Display only: happiness is stretched for color (`((H - 0.03) / 0.14) ^ 0.7`, clamped) because real H sat
  between 0.03 and 0.2 in the full runs (median 0.06). Logs and analysis use the raw H.
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
- Analysis: per-agent mean happiness skips the first 30 s (every agent starts at H = 0.5). Lead time = how
  long mean proximity had been rising without a break when the house ear called the drop. The contagion
  number is the correlation of an agent's H with its neighbors' mean H after removing each tick's crowd mean.
- Neon runs as a plain single call (Interactions API, thinking high), not a Managed Agent.
- Extended visuals: faces are carved in the vertex shader (eyes, brows, a mouth that curves with happiness)
  and turn toward the agent's velocity; trails are 3 ghosts per agent at 0.9 s spacing, drawn from the first
  2,500 dots; the chromatic fringe recolors and offsets 14-44% of edge dots by 2.5 px; the camera pushes in
  0.07 while the house ear says "drop".
- Live input: the picker lists audio inputs after a one-time permission prompt. Tested with Chrome's fake
  capture device only; BlackHole / Rekordbox still needs a human at the machine (see "Live input").

## What was built today, and what broke

Everything in `server/`, `web/`, `analysis/` and `tools/` was written during the event.

What broke or surprised us along the way (details under "Decisions made"):

- Decisions probabilities are soft. With seven section options the top one rarely passes 0.5, so the plan's
  thresholds for drop onsets and for accepting an ask never fired and had to change.
- With the plan's bare prompt all 100 agents chose `dance` forever; traits only mattered once the prompt
  said what they mean.
- The plan's energy costs exhausted the whole crowd in under a minute.
- The first renderer (stippled point clouds, 20,000 dots per sphere) read as noisy and was replaced by the
  field-based glow renderer.
- The house ear is not ground truth: on identical audio it called three drops in two runs and one in the third.
- Not done: live Rekordbox input is wired and tested against a fake device only, the demo video link is not
  in the repo (the clip contains the track), and Neon is a single call rather than a Managed Agent.

## Credits

- [three.js](https://threejs.org) (MIT) for the WebGL renderer.
