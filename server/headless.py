"""Phase B check: run physics + shove with a synthetic loud / quiet DSP schedule
and print crowd statistics. Usage: python -m server.headless [seconds]"""
import sys
import time

import numpy as np

from . import config as C, shove
from .physics import Physics
from .state import World


def main(seconds=240):
    world = World(seed=1, condition="shove")
    phys = Physics(world)
    dt = 1 / C.PHYSICS_HZ
    t0 = time.time()
    stats = {True: [], False: []}
    front = {}
    speeds = []
    Hlog = []
    for f in range(int(seconds * C.PHYSICS_HZ)):
        t = f * dt
        loud = (t % 120) > 40                      # 40 s quiet, 80 s loud
        e = 0.85 if loud else 0.15
        world.dsp = {"energy": e, "energy_5s": e}
        world.w = 1.8 if loud else 0.8             # roughly what the house ear gives for drop / breakdown
        world.section_p = {"drop": 0.4, "groove": 0.4, "build": 0.15} if loud else {"breakdown": 0.4, "groove": 0.3}
        world.t = t
        if f % int(C.TICK_SECONDS * C.PHYSICS_HZ) == 0:
            shove.apply(world)
        phys.step(dt)
        a = world.agents
        if f % C.PHYSICS_HZ == 0 and t > 20:
            Hlog += [x.H for x in a] if t > 40 else []
            speeds.append(np.mean([np.linalg.norm((x.vx, x.vy, x.vz)) for x in a]))
            # Compare the settled ends of each phase.
            if (t % 120) > 90 or 20 < (t % 120) <= 40:
                stats[loud].append(np.mean([x.v for x in a]))
                for x in a:
                    front.setdefault(x.archetype, []).append(x.v)
        if f % (10 * C.PHYSICS_HZ) == 0:
            acts = {}
            for x in a:
                acts[x.action] = acts.get(x.action, 0) + 1
            print(f"t={t:5.0f} {'LOUD ' if loud else 'quiet'} v={np.mean([x.v for x in a]):.2f} "
                  f"E={np.mean([x.E for x in a]):.2f} H={np.mean([x.H for x in a]):.3f} "
                  f"rho={np.mean([x.rho for x in a]):.2f} press={np.mean([x.pressure for x in a]):.2f}/"
                  f"{max(x.pressure for x in a):.2f} exh={world.exhaustion_events} {acts}")
    print(f"mean_v loud {np.mean(stats[True]):.3f}  quiet {np.mean(stats[False]):.3f}  "
          f"gap {np.mean(stats[True]) - np.mean(stats[False]):.3f}")
    print("mean_v by archetype:", {k: round(float(np.mean(v)), 3) for k, v in front.items()})
    Hs = np.array(Hlog)
    print("H percentiles 5/25/50/75/95:", np.round(np.percentile(Hs, [5, 25, 50, 75, 95]), 3))
    print(f"mean speed {np.mean(speeds):.3f}, slowest second {np.min(speeds):.3f}")
    print(f"{seconds}s simulated in {time.time() - t0:.1f}s "
          f"({(time.time() - t0) / (seconds * C.PHYSICS_HZ) * 1000:.2f} ms/step)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 240)
