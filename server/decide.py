"""Ring calls to the Decisions API (plan section 8.1): each ring hears its own
filtered clip and answers for itself and for every agent standing in it."""
import numpy as np

from . import config as C, wordofmouth
from .audio import features_text, ring_clip, wav_b64
from .sections import ear_questions, parse_ear

ACTION_CRITERIA = {
    "hold": "stay where you are",
    "push": "move toward the DJ; costs energy",
    "yield": "step aside so someone behind can pass",
    "rest": "drift to open space and recover energy",
    "dance": "use the room you have to dance; costs a little energy",
}
PUSH_LEVELS = ["gently", "firmly", "hard"]
DOING = {"hold": "holding", "push": "pushing", "yield": "yielding", "rest": "resting", "dance": "dancing",
         "retreat": "retreating"}
AGENTS_PER_CALL = 50      # a crowded ring is split over parallel calls


def who(a, ring):
    """An agent's own state and traits. Questions are isolated, so every question carries this."""
    kind = ("You live for the front row." if a.k > 0.7 else
            "You came to dance and need room." if a.s > 0.7 else
            "You like the front, and you like room to move.")
    return (f"You are A{a.id} in a packed crowd at a DJ set, ring {ring} of 5 from the DJ (1 = front, 5 = back wall).\n"
            f"Traits: keen {a.k:.1f} (how much you want the front), space {a.s:.1f} (how much room you need). {kind}\n"
            "Being near the DJ pays off most at the drop. Pushing, dancing and the crush drain energy; resting in "
            "open space restores it. At energy 0 you collapse and are carried to the back.\n"
            f"Now: energy {a.E:.2f}, proximity {a.v:.2f}, crowding {a.rho:.2f}, happiness {a.H:.2f}.")


def neighbors_line(a, agents, pos):
    d = np.linalg.norm(pos - np.array(a.pos), axis=1)
    near = [agents[j] for j in np.argsort(d)[1:4]]
    return "Neighbors: " + ", ".join(f"A{n.id} {DOING[n.action]}" for n in near) + "."


def build_questions(ring, members, world, memo, first):
    """Questions for one ring call. `first` carries the ring-level ear questions."""
    agents = world.agents
    pos = np.array([a.pos for a in agents])
    word_text, word = wordofmouth.line_for(memo, ring) if world.condition != "shove" else ("", {})
    q = ear_questions(f"r{ring}") if first else {}
    pending = memo.get("asking", {})
    for a in members:
        a.last_heard = word
        me = who(a, ring)
        q[f"a{a.id}_action"] = {"type": "choice", "criteria": ACTION_CRITERIA, "instructions": (
            f"{me}\n{neighbors_line(a, agents, pos)}{' ' + word_text if word_text else ''}\n"
            "Given what you hear, what do you do now?")}
        q[f"a{a.id}_push"] = {"type": "score", "criteria": PUSH_LEVELS, "instructions": (
            f"{me}\nGiven what you hear, if you moved toward the DJ now, how hard would you push past the people in front?")}
        for ask in pending.get(a.id, []):
            asker = agents[ask["from"]]
            q[f"a{a.id}_ans_{asker.id}"] = {
                "type": "noul",
                "criteria": {"true_description": "you step aside and let them through",
                             "false_description": "you stay put"},
                "instructions": (
                    f"{me} You are {DOING[a.action]}.\n"
                    f"A{asker.id}, right behind you, asks to get past: \"{ask['text']}\" "
                    f"They say they care {ask['claimed_keenness']:.1f} out of 1.\n"
                    f"You have yielded to them {int(world.yielded_to[a.id][asker.id])} times; "
                    f"they have yielded to you {int(world.yielded_to[asker.id][a.id])} times.\n"
                    "Stepping aside takes about two seconds; then you are free to move again. "
                    "Do you let them through?")}
    return q


async def ring_call(gemini, world, memo, ring, members, pcm, kick_rate):
    """All calls for one ring. Returns (merged answers or None, parsed ear)."""
    import asyncio
    audio = wav_b64(ring_clip(ring, pcm))
    text = features_text(ring, world.t, world.dsp, kick_rate)
    groups = [members[i:i + AGENTS_PER_CALL] for i in range(0, len(members), AGENTS_PER_CALL)]
    results = await asyncio.gather(*[
        gemini.decisions(f"ring{ring}" + (f"_{i}" if i else ""), audio, text,
                         build_questions(ring, g, world, memo, first=(i == 0)))
        for i, g in enumerate(groups)])
    if all(r is None for r in results):
        return None, None
    answers = {}
    for r in results:
        answers.update(r or {})
    return answers, parse_ear(answers, f"r{ring}")


def apply(world, answers):
    """Set action and pushiness from the answers. An agent with no answer keeps its previous action."""
    for a in world.agents:
        if a.exhausted:
            continue          # forced retreat; never asked
        act = answers.get(f"a{a.id}_action")
        if act and act.get("choice") in ACTION_CRITERIA:
            a.action_probs = {k: round(v, 3) for k, v in (act.get("probabilities") or {}).items()}
            if world.sim_t >= a.yield_until:      # an accepted ask keeps its 2 s of yielding
                a.action = act["choice"]
        push = answers.get(f"a{a.id}_push")
        if push and push.get("score") is not None:
            a.pushiness = float(np.clip(push["score"] / 2.0, 0.0, 1.0))
