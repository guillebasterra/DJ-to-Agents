"""Compare runs across conditions. Usage: python analysis/analyze.py runs/<a> runs/<b> ... [--out out]
Writes PNGs and summary.json. All "truth" about the music comes from the house ear's log."""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONDITIONS, drop_onsets, load_runs

# Fixed color per condition / archetype (validated categorical slots 1-3).
COLOR = {"shove": "#2a78d6", "silent": "#eb6834", "talk": "#1baf7a"}
ARCH_COLOR = {"diehard": "#2a78d6", "dancer": "#eb6834", "between": "#1baf7a"}
INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a63", "#e6e5df", "#fcfcfb"
BAND = {"drop": "#d9d8d0", "build": "#ecebe5"}
WARMUP_S = 30    # every agent starts at H = 0.5; skip that transient in per-agent means

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "font.size": 9, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "axes.titlelocation": "left", "legend.frameon": False, "lines.linewidth": 2,
})


def series(run, key, fn=np.mean):
    t = np.array([tk["t"] for tk in run["ticks"]])
    y = np.array([fn([a[key] for a in tk["agents"]]) for tk in run["ticks"]])
    return t, y


def smooth(y, n=3):
    if len(y) < n:
        return y
    pad = np.concatenate([np.full(n // 2, y[0]), y, np.full(n // 2, y[-1])])
    return np.convolve(pad, np.ones(n) / n, mode="valid")


def section_bands(ax, run):
    """Shade the house ear's drop and build sections."""
    ticks = [tk for tk in run["ticks"] if tk.get("house")]
    for i, tk in enumerate(ticks):
        color = BAND.get(tk["house"]["section"])
        if color:
            end = ticks[i + 1]["t"] if i + 1 < len(ticks) else tk["t"] + 3
            ax.axvspan(tk["t"], end, color=color, lw=0, zorder=0)


def end_labels(ax, lines):
    """Direct labels at the line ends, nudged apart so they never collide."""
    lo, hi = ax.get_ylim()
    gap = (hi - lo) * 0.055
    placed = []
    for label, t, y, color in sorted(lines, key=lambda l: l[2][-1]):
        yy = y[-1] if not placed else max(y[-1], placed[-1] + gap)
        placed.append(yy)
        ax.plot([t[-1]], [y[-1]], "o", ms=5, color=color, mec=SURFACE, mew=1.2, zorder=5)
        ax.annotate(label, (t[-1], yy), xytext=(8, 0), textcoords="offset points", color=INK, va="center", fontsize=9)


def time_plot(runs, key, title, ylabel, path, note="shaded: drop (dark) and build (light), as heard by the house ear"):
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ref = runs.get("talk") or next(iter(runs.values()))
    section_bands(ax, ref)
    lines = []
    for cond, run in runs.items():
        t, y = series(run, key)
        ax.plot(t, y, color=COLOR[cond], label=cond)
        lines.append((cond, t, y, COLOR[cond]))
    end_labels(ax, lines)
    ax.set_title(title)
    ax.set_xlabel(f"track time (s)   {note}")
    ax.set_ylabel(ylabel)
    ax.margins(x=0.01)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=3, fontsize=8)
    fig.tight_layout()
    fig.subplots_adjust(right=0.9)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def lead_times(run):
    """Seconds between mean proximity starting its final sustained rise and each house-ear drop onset."""
    t, v = series(run, "v")
    v = smooth(v, 3)
    leads = []
    for onset in drop_onsets(run):
        i = int(np.searchsorted(t, onset))
        i = min(i, len(t) - 1)
        j = i
        while j > 0 and t[i] - t[j - 1] <= 60 and v[j] - v[j - 1] > 0.0005:
            j -= 1
        leads.append(round(float(t[i] - t[j]), 1))
    return leads


def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    if x.sum() <= 0:
        return 0.0
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def per_agent(run):
    """Per-agent aggregates over the whole run."""
    ids = sorted(run["traits"])
    H = {i: [] for i in ids}
    rested = {i: False for i in ids}
    for tk in run["ticks"]:
        breakdown = bool(tk.get("house")) and tk["house"]["section"] == "breakdown"
        for a in tk["agents"]:
            if tk["t"] >= WARMUP_S:
                H[a["id"]].append(a["H"])
            if breakdown and a["action"] == "rest":
                rested[a["id"]] = True
    made = {i: [0, 0] for i in ids}
    for ask in run["asks"]:
        made[ask["from"]][0] += 1
        made[ask["from"]][1] += ask["answer"] == "yes"
    return [{"id": i, **{k: run["traits"][i][k] for k in ("k", "s", "lane", "archetype")},
             "mean_H": float(np.mean(H[i])) if H[i] else 0.0,
             "ask_success_rate": made[i][1] / made[i][0] if made[i][0] else 0.0,
             "rested_in_breakdown": float(rested[i])} for i in ids]


def welfare_plot(agents_by_cond, path):
    conds = list(agents_by_cond)
    fig, axes = plt.subplots(1, len(conds), figsize=(3.1 * len(conds), 3), sharex=True, sharey=True, squeeze=False)
    hi = max(max(a["mean_H"] for a in rows) for rows in agents_by_cond.values()) * 1.05 or 1
    bins = np.linspace(0, hi, 21)
    for ax, cond in zip(axes[0], conds):
        vals = [a["mean_H"] for a in agents_by_cond[cond]]
        ax.hist(vals, bins=bins, color=COLOR[cond], edgecolor=SURFACE, linewidth=1)
        ax.axvline(np.mean(vals), color=INK, lw=1)
        ax.set_title(cond)
        ax.text(0.98, 0.95, f"mean {np.mean(vals):.3f}\nGini {gini(vals):.3f}", transform=ax.transAxes,
                ha="right", va="top", color=INK, fontsize=8)
        ax.set_xlabel("per-agent mean happiness")
    axes[0][0].set_ylabel("agents")
    fig.suptitle("Welfare and fairness: who ends up happy", x=0.01, ha="left", fontsize=11, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def ask_table(run):
    asks = run["asks"]
    if not asks:
        return {"asks": 0}
    yes = [a["answer"] == "yes" for a in asks]
    recip = [a["answer"] == "yes" for a in asks if a["asker_yielded_before"] > 0]
    over = [a["overclaim"] for a in asks]
    return {"asks": len(asks), "acceptance_rate": round(float(np.mean(yes)), 3),
            "reciprocity": {"p_yes_given_asker_yielded_before": round(float(np.mean(recip)), 3) if recip else None,
                            "n": len(recip), "base_rate": round(float(np.mean(yes)), 3)},
            "mean_overclaim": round(float(np.mean(over)), 3),
            "share_overclaiming_by_0.3": round(float(np.mean([o > 0.3 for o in over])), 3),
            "acceptance_when_overclaiming": round(float(np.mean([y for y, o in zip(yes, over) if o > 0.3])), 3)
            if any(o > 0.3 for o in over) else None}


def latency(run):
    tick_ms = [tk["api"]["tick_ms"] for tk in run["ticks"] if tk.get("api")]
    calls = {}
    for tk in run["ticks"]:
        for name, ms in (tk.get("api", {}).get("latency_ms") or {}).items():
            calls.setdefault("ask" if name == "ask" else "house" if name == "house" else "ring", []).append(ms)
    pct = lambda xs: {"p50": int(np.percentile(xs, 50)), "p95": int(np.percentile(xs, 95))} if xs else None
    return {"tick_ms": pct(tick_ms), **{f"{k}_ms": pct(v) for k, v in calls.items()},
            "failures": sum(len(tk.get("api", {}).get("failures") or []) for tk in run["ticks"]),
            "tokens": sum(tk.get("api", {}).get("tokens", 0) for tk in run["ticks"])}


# ---- full analysis (phase H) ----

def ring_agreement(run):
    """How often each ring's ear agrees with the house ear: does the back hear late and muffled?"""
    out = {}
    for ring in "12345":
        sec, eta = [], []
        for tk in run["ticks"]:
            ear, house = (tk.get("rings") or {}).get(ring), tk.get("house")
            if ear and house:
                sec.append(ear["section"] == house["section"])
                eta.append(ear["drop_eta"] == house["drop_eta"])
        if sec:
            out[ring] = {"section": round(float(np.mean(sec)), 3), "drop_eta": round(float(np.mean(eta)), 3), "n": len(sec)}
    return out


def agreement_plot(agree_by_cond, path):
    fig, axes = plt.subplots(1, 2, figsize=(8, 3), sharey=True)
    for ax, key, title in zip(axes, ("section", "drop_eta"), ("Section", "Drop ETA")):
        conds = list(agree_by_cond)
        width = 0.8 / len(conds)
        for i, cond in enumerate(conds):
            rings = sorted(agree_by_cond[cond])
            x = np.array([int(r) for r in rings]) + (i - (len(conds) - 1) / 2) * width
            ax.bar(x, [agree_by_cond[cond][r][key] for r in rings], width * 0.9, color=COLOR[cond], label=cond)
        ax.set_title(f"{title}: agreement with the house ear")
        ax.set_xlabel("ring (1 = front, 5 = back: quiet and low-passed)")
        ax.set_ylim(0, 1)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("share of ticks")
    axes[1].legend(fontsize=8, ncol=3, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def pacing(run):
    t, E = series(run, "E")
    onsets = drop_onsets(run)
    at = [float(E[min(int(np.searchsorted(t, o)), len(E) - 1)]) for o in onsets]
    rows = per_agent(run)
    return {"mean_E_at_drop_onset": round(float(np.mean(at)), 3) if at else None,
            "share_rested_in_breakdown": round(float(np.mean([a["rested_in_breakdown"] for a in rows])), 3),
            "exhaustion_events": run["ticks"][-1].get("exhaustion_events", 0), "final_mean_E": round(float(E[-1]), 3)}


def ols(rows):
    """H ~ k + s + start_lane + ask_success_rate + rested_in_breakdown."""
    names = ["k", "s", "lane", "ask_success_rate", "rested_in_breakdown"]
    X = np.array([[1.0] + [float(r[n]) for n in names] for r in rows])
    y = np.array([r["mean_H"] for r in rows])
    keep = [0] + [i + 1 for i in range(len(names)) if X[:, i + 1].std() > 0]     # drop constant columns
    beta, *_ = np.linalg.lstsq(X[:, keep], y, rcond=None)
    resid = y - X[:, keep] @ beta
    r2 = 1 - resid.var() / y.var() if y.var() > 0 else 0.0
    coef = {(["intercept"] + names)[k]: round(float(b), 5) for k, b in zip(keep, beta)}
    return {"coefficients": coef, "r2": round(float(r2), 3), "n": len(rows)}


def who_wins_plot(agents_by_cond, path):
    conds = list(agents_by_cond)
    fig, axes = plt.subplots(1, len(conds), figsize=(3.1 * len(conds), 3.1), sharex=True, sharey=True, squeeze=False)
    for ax, cond in zip(axes[0], conds):
        for arch, color in ARCH_COLOR.items():
            rows = [a for a in agents_by_cond[cond] if a["archetype"] == arch]
            ax.scatter([a["k"] for a in rows], [a["mean_H"] for a in rows], s=22, color=color, edgecolor=SURFACE,
                       linewidth=0.8, label=arch)
        ax.set_title(cond)
        ax.set_xlabel("keenness for the front (k)")
    axes[0][0].set_ylabel("per-agent mean happiness")
    axes[0][0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Who wins: happiness against keenness", x=0.01, ha="left", fontsize=11, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def gridlock(run):
    """Share of push-ticks in which the pusher gained < 0.01 proximity by the next tick."""
    stuck = total = 0
    for a, b in zip(run["ticks"], run["ticks"][1:]):
        nxt = {x["id"]: x["v"] for x in b["agents"]}
        for x in a["agents"]:
            if x["action"] == "push":
                total += 1
                stuck += nxt[x["id"]] - x["v"] < 0.01
    return round(stuck / total, 3) if total else None


def contagion(run, radius=0.18):
    """Correlation between an agent's H and the mean H of its neighbors, pooled over ticks."""
    own, near = [], []
    for tk in run["ticks"][::3]:
        pos = np.array([[a["x"], a["y"], a["z"]] for a in tk["agents"]])
        H = np.array([a["H"] for a in tk["agents"]])
        d = np.linalg.norm(pos[:, None] - pos[None], axis=-1)
        m = (d < radius) & ~np.eye(len(H), dtype=bool)
        has = m.sum(1) > 0
        # Remove the tick's mean so we measure spatial clustering, not the shared music.
        dev = H - H.mean()
        own += list(dev[has])
        near += list(((m * dev[None]).sum(1) / np.maximum(m.sum(1), 1))[has])
    return round(float(np.corrcoef(own, near)[0, 1]), 3) if len(own) > 2 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runs = load_runs(args.runs)
    if not runs:
        sys.exit("no runs with ticks found")

    agents = {c: per_agent(r) for c, r in runs.items()}
    time_plot(runs, "v", "Anticipation: does the crowd move before the drop?", "mean proximity to the hot spot",
              out / "anticipation.png")
    welfare_plot(agents, out / "welfare.png")
    time_plot(runs, "E", "Pacing: energy over the track", "mean energy", out / "pacing.png")
    who_wins_plot(agents, out / "who_wins.png")
    agree = {c: ring_agreement(r) for c, r in runs.items() if c != "shove" and ring_agreement(r)}
    if agree:
        agreement_plot(agree, out / "ring_agreement.png")

    summary = {"runs": {c: r["dir"].name for c, r in runs.items()}, "conditions": {}}
    for cond, run in runs.items():
        vals = [a["mean_H"] for a in agents[cond]]
        leads = lead_times(run)
        by_arch = {arch: round(float(np.mean([a["mean_H"] for a in agents[cond] if a["archetype"] == arch])), 4)
                   for arch in ARCH_COLOR}
        summary["conditions"][cond] = {
            "ticks": len(run["ticks"]), "seconds": round(run["ticks"][-1]["t"], 1),
            "drop_onsets_s": drop_onsets(run),
            "anticipation": {"lead_times_s": leads, "mean_lead_s": round(float(np.mean(leads)), 1) if leads else None},
            "welfare": {"mean_H": round(float(np.mean(vals)), 4), "gini_H": round(gini(vals), 3),
                        "mean_H_by_archetype": by_arch},
            "asks": ask_table(run) if cond == "talk" else None,
            "exhaustion_events": run["ticks"][-1].get("exhaustion_events", 0),
            "api": latency(run),
            "ring_vs_house_agreement": agree.get(cond),
            "pacing": pacing(run),
            "who_wins_ols": ols(agents[cond]),
            "gridlock": gridlock(run),
            "contagion_corr": contagion(run),
        }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
