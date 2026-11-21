"""Scripted baseline: the same crowd with no minds (plan section 8.4)."""


def decide(agent, music_energy):
    """Returns (action, pushiness)."""
    if agent.E < 0.2:
        return "rest", agent.pushiness
    if agent.archetype == "diehard":
        return "push", 0.9
    if agent.archetype == "dancer":
        return ("rest" if agent.rho > 0.4 else "dance"), agent.pushiness
    return ("push" if music_energy > 0.6 else "hold"), agent.pushiness


def apply(world):
    for a in world.agents:
        if a.exhausted:
            continue
        a.action, a.pushiness = decide(a, world.music_energy)
