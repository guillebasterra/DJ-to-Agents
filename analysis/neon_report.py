"""Post-run report by Gemini 4 Neon (thinking high). Sends summary.json plus 15
sampled asks (stratified by outcome and asker archetype) and writes report.md.
Usage: python analysis/neon_report.py runs/<talk run> [--out out]"""
import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_run
from server import config as C
from server.gemini_client import Gemini

SYSTEM = ("You are writing the results section for an experiment: 100 LLM-driven agents in a simulated crowd "
          "compete for the spot in front of a DJ. Three conditions on the same track and seed: 'shove' (scripted "
          "rules, no model), 'silent' (each agent's action chosen by a model from the audio it hears), 'talk' "
          "(silent, plus blocked agents ask in natural language to get past). Section labels come from a model "
          "listening to the audio (the 'house ear'), not from ground truth. Be specific and skeptical: every "
          "claim must rest on a number in the summary, quotes must be copied exactly from the sampled asks, "
          "and say plainly when the data does not support a conclusion.")


class Takeaway(BaseModel):
    claim: str      # one sentence
    number: str     # the figure from the summary that supports it
    quote: str      # an ask copied verbatim from the sample that illustrates it, or ""


class Report(BaseModel):
    takeaways: list[Takeaway]   # exactly 5
    caveats: list[str]


def sample_asks(asks, n=15, seed=0):
    """Stratified by outcome and asker archetype, round-robin across the strata."""
    rng = random.Random(seed)
    strata = {}
    for a in asks:
        strata.setdefault((a["answer"], a["asker_archetype"]), []).append(a)
    for group in strata.values():
        rng.shuffle(group)
    picked = []
    while len(picked) < n and any(strata.values()):
        for key in sorted(strata):
            if strata[key] and len(picked) < n:
                picked.append(strata[key].pop())
    keys = ("from", "to", "asker_archetype", "blocker_archetype", "text", "claimed_keenness", "true_k", "answer",
            "p_yes", "asker_yielded_before", "t")
    return [{k: a[k] for k in keys} for a in picked]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("talk_run")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    out = Path(args.out)
    summary = json.loads((out / "summary.json").read_text())
    asks = sample_asks(load_run(args.talk_run)["asks"])
    prompt = ("summary.json:\n" + json.dumps(summary, indent=1) + "\n\nSampled asks (talk condition):\n"
              + json.dumps(asks, indent=1) + "\n\nWrite exactly 5 takeaways and the caveats a careful reader needs.")
    gemini = Gemini()
    report = await gemini.structured("neon", C.MODEL_NEON, SYSTEM, prompt, Report, thinking="high", timeout=180)
    if report is None:
        sys.exit("Neon call failed")
    lines = ["# Run report (written by Gemini 4 Neon)", "",
             "Runs: " + ", ".join(f"{c}: `{r}`" for c, r in summary["runs"].items()), "", "## Takeaways", ""]
    for i, t in enumerate(report.takeaways, 1):
        lines += [f"{i}. **{t.claim}**", f"   - Number: {t.number}"] + ([f"   - Quote: \"{t.quote}\""] if t.quote else []) + [""]
    lines += ["## Caveats", ""] + [f"- {c}" for c in report.caveats] + [""]
    (out / "report.md").write_text("\n".join(lines))
    (out / "report.json").write_text(report.model_dump_json(indent=1))
    print("\n".join(lines))
    print(gemini.drain())


if __name__ == "__main__":
    asyncio.run(main())
