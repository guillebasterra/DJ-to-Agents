"""Moments worth showing, with timestamps. Usage: python analysis/highlights.py runs/<run> [--out out]"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import drop_onsets, load_run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    run = load_run(args.run)
    ticks, asks = run["ticks"], run["asks"]
    out = {"run": run["dir"].name, "condition": run["condition"]}

    # Biggest single-agent happiness swing over any 30 s window.
    t = np.array([tk["t"] for tk in ticks])
    H = np.array([[a["H"] for a in sorted(tk["agents"], key=lambda a: a["id"])] for tk in ticks])
    best = None
    for i in range(len(ticks)):
        j = int(np.searchsorted(t, t[i] + 30))
        if j >= len(ticks):
            break
        d = H[j] - H[i]
        k = int(np.abs(d).argmax())
        if best is None or abs(d[k]) > abs(best["delta_H"]):
            best = {"agent": k, "from_t": float(t[i]), "to_t": float(t[j]), "delta_H": round(float(d[k]), 3),
                    "archetype": run["traits"][k]["archetype"]}
    out["biggest_H_swing"] = best

    # Asks that overstated keenness by > 0.3 and still got a yes.
    out["overclaims_that_worked"] = [
        {k: a[k] for k in ("t", "from", "to", "text", "claimed_keenness", "true_k", "overclaim")}
        for a in asks if a["overclaim"] > 0.3 and a["answer"] == "yes"]

    asked = Counter(a["to"] for a in asks)
    yielded = Counter(a["to"] for a in asks if a["answer"] == "yes")
    out["most_asked"] = [{"agent": i, "asks": n, "archetype": run["traits"][i]["archetype"]} for i, n in asked.most_common(3)]
    out["most_yielding"] = [{"agent": i, "yields": n, "archetype": run["traits"][i]["archetype"]} for i, n in yielded.most_common(3)]

    # Maximum compression (mean crowding of the front 20 agents) in the 30 s before each drop.
    comp = []
    for onset in drop_onsets(run):
        window = [tk for tk in ticks if onset - 30 <= tk["t"] <= onset]
        if not window:
            continue
        front = lambda tk: float(np.mean(sorted(a["rho"] for a in tk["agents"])[-20:]))
        peak = max(window, key=front)
        comp.append({"drop_onset_t": onset, "t": peak["t"], "front20_crowding": round(front(peak), 3),
                     "mean_proximity": round(float(np.mean([a["v"] for a in peak["agents"]])), 3)})
    out["max_compression_before_drop"] = max(comp, key=lambda c: c["front20_crowding"]) if comp else None
    out["compression_by_drop"] = comp

    path = Path(args.out)
    path.mkdir(parents=True, exist_ok=True)
    (path / "highlights.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
