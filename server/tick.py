"""The tick loop body, every TICK_SECONDS (plan section 8)."""
import asyncio
import time

from . import config as C, decide, negotiate, shove, wordofmouth
from .gemini_client import Gemini
from .sections import HouseEar

MIN_AUDIO_SECONDS = 2.0


def _services(S):
    if "gemini" not in S.services:
        S.services["gemini"] = Gemini()
    return S.services["gemini"]


async def run(S):
    world, memo = S.world, S.memo
    gemini = _services(S)
    house_ear = memo.setdefault("house_ear", HouseEar())
    cond = world.condition
    started = time.time()

    # 1. What is playing: the house clip and the ring clip come from the live buffer only.
    if S.audio.seconds < MIN_AUDIO_SECONDS:
        return
    world.tick += 1
    t, dsp = world.t, dict(world.dsp)
    kick_rate = len(world.kick_times) / 5.0
    house_pcm = S.audio.clip(C.HOUSE_CLIP_SECONDS)
    ring_pcm = S.audio.clip(C.RING_CLIP_SECONDS)

    # 2. Rings by current distance. Exhausted agents are skipped (forced retreat).
    rings = {}
    for a in world.agents:
        if not a.exhausted:
            rings.setdefault(a.ring, []).append(a)

    # Asks that landed since the last tick go out with this tick's ring calls.
    asked = memo["asking"] = memo.pop("asks_for", {}) if cond == "talk" else {}

    # 3-4. The house ear always runs (the reward needs w); ring calls unless shove. All in parallel.
    calls = [house_ear.listen(gemini, world, house_pcm, kick_rate)]
    order = sorted(rings) if cond != "shove" else []
    calls += [decide.ring_call(gemini, world, memo, r, rings[r], ring_pcm, kick_rate) for r in order]
    generation = S.generation
    house, *ring_results = await asyncio.gather(*calls)
    if S.generation != generation:
        return      # the run changed (reset / condition) while we were waiting

    # 5. Apply actions, then pass the word back one ring.
    answers, heard = {}, {}
    for r, (ans, ear) in zip(order, ring_results):
        answers.update(ans or {})
        heard[r] = ear
    if cond == "shove":
        shove.apply(world)
    else:
        decide.apply(world, answers)
        wordofmouth.update(memo, heard)

    # 6. Argue: read the answers to last tick's asks, then let newly blocked pushers ask.
    ask_answers, new_asks = [], []
    if cond == "talk":
        ask_answers = negotiate.resolve(S, asked, answers)
        new_asks = memo.pop("new_asks", [])
        negotiate.launch(S, negotiate.detect(world, memo), heard)
    memo["asking"] = {}

    # 7. Targets follow the new actions on the next physics frame.
    # 8. Decision frame + log line.
    frame = {"type": "decision", "t": round(t, 2), "condition": cond, "tick": world.tick,
             "house": {"section": house["section"], "w": house["w"]} if house else None,
             "rings": {str(r): {"section": e["section"], "drop_eta": e["drop_eta"],
                                "p": e["drop_eta_probs"].get(e["drop_eta"], 0.0)}
                       for r, e in heard.items() if e},
             "asks": [negotiate.public(a) for a in new_asks if a["answer"] == "pending"],
             "answers": ask_answers}
    await S.broadcast(frame)

    api = gemini.drain()
    api["tick_ms"] = round((time.time() - started) * 1000)
    S.run.tick({
        "t": t, "tick": world.tick, "condition": cond, "house": house, "w": world.w, "dsp": dsp,
        "rings": {str(r): e for r, e in heard.items()},
        "agents": [{"id": a.id, "lane": a.lane, "x": round(a.x, 3), "y": round(a.y, 3), "z": round(a.z, 3),
                    "E": round(a.E, 3), "v": round(a.v, 3), "rho": round(a.rho, 3), "H": round(a.H, 4),
                    "u": round(a.u, 3), "action": a.action, "push": round(a.pushiness, 2),
                    "action_probs": a.action_probs if cond != "shove" else {}, "ring": a.ring,
                    "exhausted": a.exhausted, "heard": a.last_heard} for a in world.agents],
        "asks": [{k: a[k] for k in ("id", "from", "to", "text", "claimed_keenness", "true_k")} for a in new_asks],
        "answers": ask_answers, "exhaustion_events": world.exhaustion_events, "api": api,
    })
