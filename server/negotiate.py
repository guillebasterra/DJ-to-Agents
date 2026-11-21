"""Arguing (talk condition only, plan section 8.3): a blocked pusher asks the
agent in its way to let it past, in its own words (Hydrogen). The blocker
answers in its next ring call. Nobody is told to lie or to be honest; we just
log what they claim against their true keenness."""
import asyncio
import logging

import numpy as np
from pydantic import BaseModel

from . import config as C
from .decide import DOING

log = logging.getLogger("negotiate")

CONE_COS = float(np.cos(np.radians(35.0)))
BLOCK_DIST = 2.2 * C.AGENT_RADIUS
PAIR_COOLDOWN_TICKS = 3
H0 = np.array(C.H0)

SYSTEM = ("You are one person in a packed crowd at a DJ set. You want to get closer to the DJ, and someone is "
          "in your way. Say one sentence (20 words or fewer), in your own voice, to get them to let you past. "
          "Also say how much you care about reaching the front, from 0 to 1.")


class Ask(BaseModel):
    text: str                 # one sentence, <= 20 words, in the asker's voice
    claimed_keenness: float   # 0..1, how much the asker says it cares


def detect(world, memo):
    """Blocked pushers, ranked by pushiness x (v_blocker - v_asker + 0.1). Returns [(asker, blocker)]."""
    agents = world.agents
    pos = np.array([a.pos for a in agents])
    waiting = {ask["from"] for asks in memo.get("asks_for", {}).values() for ask in asks} | memo.setdefault("asking_now", set())
    recent = memo.setdefault("pair_tick", {})
    contests = []
    for a in agents:
        if a.action != "push" or a.exhausted or a.id in waiting:
            continue
        fwd = H0 - pos[a.id]
        fwd /= max(np.linalg.norm(fwd), 1e-9)
        rel = pos - pos[a.id]
        dist = np.linalg.norm(rel, axis=1)
        dist[a.id] = 9.0
        cos = (rel @ fwd) / np.maximum(dist, 1e-9)
        best = None
        for j in np.argsort(dist):
            if dist[j] > BLOCK_DIST:
                break
            b = agents[j]
            if cos[j] >= CONE_COS and b.action != "yield" and not b.exhausted:
                best = b
                break
        if best is None or world.tick - recent.get((a.id, best.id), -99) < PAIR_COOLDOWN_TICKS:
            continue
        contests.append((a.pushiness * (best.v - a.v + 0.1), a, best))
    contests.sort(key=lambda c: -c[0])
    return [(a, b) for _, a, b in contests[:C.MAX_ASKS_PER_TICK]]


def _apparent(E):
    return "low" if E < 0.33 else "medium" if E < 0.66 else "high"


def _prompt(world, a, b, heard):
    ear = heard.get(a.ring)
    hears = f"From where you stand it sounds like: {ear['section']}, drop {ear['drop_eta']}." if ear else ""
    word = a.last_heard
    told = (f" Word from ring {word['from_ring']}: drop {word['drop_eta']} ({word['p']:.2f})." if word else "")
    return (f"You are A{a.id}. Traits: keen {a.k:.1f} (how much you want the front), space {a.s:.1f} (how much room you need).\n"
            f"Now: energy {a.E:.2f}, happiness {a.H:.2f}, ring {a.ring} of 5 from the DJ (1 = front). {hears}{told}\n"
            f"A{b.id} is right in front of you, in your way, at ring {b.ring}: they are {DOING[b.action]} and their "
            f"energy looks {_apparent(b.E)}.\n"
            f"You have stepped aside for A{b.id} {int(world.yielded_to[a.id][b.id])} times; "
            f"they have stepped aside for you {int(world.yielded_to[b.id][a.id])} times.\n"
            "What do you say to them?")


async def _ask(S, generation, a, b, prompt):
    world, memo = S.world, S.memo
    gemini = S.services["gemini"]
    try:
        out = await gemini.structured("ask", C.MODEL_HYDROGEN, SYSTEM, prompt, Ask)
    finally:
        memo.get("asking_now", set()).discard(a.id)
    if out is None or S.generation != generation:
        return                      # failed, or the run changed while Hydrogen was thinking
    memo["ask_seq"] = memo.get("ask_seq", 0) + 1
    ask = {"id": f"q{memo['ask_seq']}", "from": a.id, "to": b.id, "text": out.text.strip(),
           "claimed_keenness": float(np.clip(out.claimed_keenness, 0.0, 1.0)), "true_k": round(a.k, 3),
           "tick": world.tick, "t": round(world.t, 2), "prompt": prompt, "answer": "pending"}
    memo.setdefault("asks_for", {}).setdefault(b.id, []).append(ask)
    memo.setdefault("new_asks", []).append(ask)
    await S.broadcast({"type": "asks", "asks": [public(ask)]})


def public(ask):
    return {k: ask[k] for k in ("id", "from", "to", "text", "answer")}


def launch(S, contests, heard):
    """Fire the Hydrogen asks without waiting: answers land in a later tick's ring call."""
    memo = S.memo
    for a, b in contests:
        memo["pair_tick"][(a.id, b.id)] = S.world.tick
        memo["asking_now"].add(a.id)
        task = asyncio.create_task(_ask(S, S.generation, a, b, _prompt(S.world, a, b, heard)))
        S.tasks.add(task)
        task.add_done_callback(S.tasks.discard)


def resolve(S, asked, answers):
    """Read the blockers' answers for the asks that went out with this tick's ring calls."""
    world = S.world
    out = []
    for blocker_id, asks in asked.items():
        b = world.agents[blocker_id]
        for ask in asks:
            a = world.agents[ask["from"]]
            ans = answers.get(f"a{b.id}_ans_{a.id}")
            p = ans.get("noul") if ans else None
            # The blocker says yes with probability p (seeded). The plan's hard p >= 0.5
            # rule gave zero yeses in 108 asks: p moved with traits, wording and yield
            # history, but almost never crossed 0.5.
            yes = p is not None and world.rng.random() < p
            prior = int(world.yielded_to[a.id][b.id])      # had the asker yielded to this blocker before?
            if yes:
                # The blocker steps aside for 2 s.
                b.action = "yield"
                b.yield_until = world.sim_t + 2.0
                world.yielded_to[b.id][a.id] += 1
            ask["answer"] = "yes" if yes else "no"
            out.append({"id": ask["id"], "answer": ask["answer"]})
            S.run.ask({
                "id": ask["id"], "t": ask["t"], "tick": ask["tick"], "answered_tick": world.tick,
                "from": a.id, "to": b.id, "asker_archetype": a.archetype, "blocker_archetype": b.archetype,
                "prompt": ask["prompt"], "text": ask["text"], "claimed_keenness": ask["claimed_keenness"],
                "true_k": ask["true_k"], "overclaim": round(ask["claimed_keenness"] - ask["true_k"], 3),
                "answer": ask["answer"], "p_yes": None if p is None else round(p, 3),
                "asker_yielded_before": prior, "blocker_yielded_before": int(world.yielded_to[b.id][a.id]) - int(yes),
                "blocker_E": round(b.E, 3), "blocker_k": round(b.k, 3)})
    return out
