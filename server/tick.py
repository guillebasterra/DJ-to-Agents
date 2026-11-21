"""The tick loop body (plan section 8). Phase C: shove only, with a temporary
DSP proxy for the house ear's weight."""
from . import shove


async def run(S):
    world = S.world
    world.tick += 1
    world.w = 0.5 + 2.5 * float(world.dsp.get("energy_5s", 0.0))
    shove.apply(world)
    frame = {"type": "decision", "t": round(world.t, 2), "condition": world.condition, "tick": world.tick,
             "rings": {}, "asks": [], "answers": []}
    await S.broadcast(frame)
    S.run.tick({"t": world.t, "tick": world.tick, "condition": world.condition, "dsp": world.dsp, "w": world.w})
