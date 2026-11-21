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
    for f in range(int(seconds * C.PHYSICS_HZ)):
        t = f * dt
        loud = (t % 120) > 40                      # 40 s quiet, 80 s loud
        e = 0.85 if loud else 0.15
        world.dsp = {"energy": e, "energy_5s": e}
        world.w = 0.5 + 2.5 * e                    # temporary DSP proxy for the house ear
        world.t = t
        if f % int(C.TICK_SECONDS * C.PHYSICS_HZ) == 0:
            shove.apply(world)
        phys.step(dt)
        if f % (10 * C.PHYSICS_HZ) == 0:
            a = world.agents
            acts = {}
            for x in a:
                acts[x.action] = acts.get(x.action, 0) + 1
            print(f"t={t:5.0f} {'LOUD ' if loud else 'quiet'} v={np.mean([x.v for x in a]):.2f} "
                  f"front10_v={np.mean(sorted(x.v for x in a)[-10:]):.2f} E={np.mean([x.E for x in a]):.2f} "
                  f"H={np.mean([x.H for x in a]):.2f} Hmax={max(x.H for x in a):.2f} "
                  f"rho={np.mean([x.rho for x in a]):.2f} press={max(x.pressure for x in a):.2f} "
                  f"exh={world.exhaustion_events} {acts}")
    print(f"{seconds}s simulated in {time.time() - t0:.1f}s "
          f"({(time.time() - t0) / (seconds * C.PHYSICS_HZ) * 1000:.2f} ms/step)")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 240)
