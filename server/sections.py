"""The house ear: one Decisions call per tick on the unfiltered last 15 s.
The system's best guess at the truth. It sets the reward weight w and feeds the
analysis; agents never see it. No labels are loaded anywhere."""
from . import config as C
from .audio import features_text, wav_b64

SECTION_CRITERIA = {
    "intro": "sparse opening, elements still entering",
    "build": "tension rising toward a drop: risers, rolls, filters opening",
    "drop": "peak energy, kick and bass hit at full force",
    "groove": "steady beat rolling along, no big change coming",
    "breakdown": "kick and bass have dropped out; pads, vocals or melody",
    "outro": "elements leaving, the track winding down",
    "other": "silence, talking or anything else",
}
ETA_CRITERIA = {
    "now": "the drop is hitting right now",
    "next_8_bars": "a drop lands within about 15 seconds",
    "within_32_bars": "a drop is coming within about a minute",
    "not_soon": "no drop in sight",
}


def ear_questions(prefix):
    """The section / drop_eta / rising questions, shared by the house ear and the rings."""
    return {
        f"{prefix}_section": {"type": "choice", "criteria": SECTION_CRITERIA,
                              "instructions": "Listen to the end of this clip of a DJ set. Which part of the track is playing now?"},
        f"{prefix}_drop_eta": {"type": "choice", "criteria": ETA_CRITERIA,
                               "instructions": "Listen to this clip of a DJ set. When does the next drop land?"},
        f"{prefix}_rising": {"type": "noul", "instructions": "Is the energy building right now?"},
    }


def parse_ear(answers, prefix):
    sec = answers.get(f"{prefix}_section") or {}
    eta = answers.get(f"{prefix}_drop_eta") or {}
    rising = answers.get(f"{prefix}_rising") or {}
    if not sec.get("probabilities"):
        return None
    return {"section": sec.get("choice"), "section_probs": {k: round(v, 3) for k, v in sec["probabilities"].items()},
            "drop_eta": eta.get("choice"),
            "drop_eta_probs": {k: round(v, 3) for k, v in (eta.get("probabilities") or {}).items()},
            "rising": round(rising.get("noul", 0.5), 3)}


class HouseEar:
    def __init__(self):
        self.armed = False        # a build or breakdown has been heard since the last drop
        self.in_drop = False

    async def listen(self, gemini, world, pcm, kick_rate):
        """Returns the house record for the tick log, or None if the call failed
        (the previous w stays in force)."""
        answers = await gemini.decisions("house", wav_b64(pcm), features_text(1, world.t, world.dsp, kick_rate),
                                         ear_questions("house"))
        house = parse_ear(answers or {}, "house")
        if house is None:
            return None
        probs = house["section_probs"]
        house["w"] = round(sum(p * C.SECTION_WEIGHTS.get(sec, 0.5) for sec, p in probs.items()), 3)
        # Drop onset: "drop" becomes the top section after a build or breakdown was
        # the top section. (The plan's rule used p > 0.5, but with seven options
        # the top probability rarely gets there.)
        top = house["section"]
        house["drop_onset"] = bool(top == "drop" and not self.in_drop and self.armed)
        if top == "drop":
            self.in_drop, self.armed = True, False
        else:
            self.in_drop = False
            if top in ("build", "breakdown"):
                self.armed = True
        world.w = house["w"]
        world.section_p = probs
        return house
