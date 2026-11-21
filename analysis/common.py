"""Loading runs for the analysis scripts."""
import json
from pathlib import Path

CONDITIONS = ("shove", "silent", "talk")


def _jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_run(run_dir):
    d = Path(run_dir)
    meta = json.loads((d / "meta.json").read_text())
    return {"dir": d, "meta": meta, "condition": meta["condition"], "ticks": _jsonl(d / "ticks.jsonl"),
            "asks": _jsonl(d / "asks.jsonl"), "traits": {a["id"]: a for a in meta["agents"]}}


def load_runs(run_dirs):
    """One run per condition (the longest, if several are given), in a fixed order."""
    best = {}
    for d in run_dirs:
        run = load_run(d)
        if not run["ticks"]:
            continue
        cur = best.get(run["condition"])
        if cur is None or len(run["ticks"]) > len(cur["ticks"]):
            best[run["condition"]] = run
    return {c: best[c] for c in CONDITIONS if c in best}


def drop_onsets(run):
    return [t["t"] for t in run["ticks"] if t.get("house") and t["house"].get("drop_onset")]
