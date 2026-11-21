"""Agent and world state (plan section 4)."""
from dataclasses import dataclass, field

import numpy as np

from . import config as C


@dataclass
class Agent:
    id: int
    x: float
    y: float
    z: float
    k: float                       # trait: keenness for the front (fixed)
    s: float                       # trait: need for space (fixed)
    archetype: str                 # "diehard" | "dancer" | "between"
    lane: int                      # starting column 0..9 on the back wall
    size: float = 1.0              # body size multiplier (archetype x jitter), fixed
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    E: float = 0.8                 # energy (fatigue reserve)
    action: str = "hold"           # hold | push | yield | rest | dance | retreat
    pushiness: float = 0.3
    target: tuple = (0.0, 0.0, 0.0)
    H: float = 0.5                 # happiness / vibe, smoothed
    u: float = 0.0                 # instantaneous utility
    rho: float = 0.0
    v: float = 0.0
    pressure: float = 0.0
    normal: tuple = (0.0, 0.0, 0.0)   # contact normal with the largest overlap
    exhausted: bool = False
    yield_until: float = 0.0       # sim time until which an accepted ask keeps this agent yielding
    last_heard: dict = field(default_factory=dict)   # word-of-mouth line from last tick
    action_probs: dict = field(default_factory=dict)

    @property
    def pos(self):
        return (self.x, self.y, self.z)

    @property
    def radius(self):
        """Body radius: tired agents deflate."""
        return C.AGENT_RADIUS * self.size * (1.0 - C.DEFLATE * (1.0 - self.E))

    @property
    def d(self):
        """Distance to the hot band on the glass."""
        return float(np.linalg.norm(np.subtract(self.pos, C.hot_point(self.pos))))

    @property
    def ring(self):
        return ring_of(self.d)


def ring_of(d):
    return 1 + sum(d >= e for e in C.RING_EDGES)


ARCHETYPES = (("diehard", 0.30, 0.9, 0.1), ("dancer", 0.30, 0.3, 0.9), ("between", 0.40, 0.5, 0.5))


def make_agents(seed):
    rng = np.random.default_rng(seed)
    size_rng = np.random.default_rng(seed + 31)     # separate stream: traits and start positions stay as before
    kinds = []
    for name, share, k, s in ARCHETYPES:
        kinds += [(name, k, s)] * round(share * C.N_AGENTS)
    order = rng.permutation(C.N_AGENTS)
    per_lane = C.N_AGENTS // C.N_LANES
    agents = []
    for i in range(C.N_AGENTS):
        name, k, s = kinds[order[i]]
        lane, row = i % C.N_LANES, i // C.N_LANES
        x = (lane + 0.5) / C.N_LANES + rng.uniform(-0.02, 0.02)
        y = (row + 0.5) / per_lane + rng.uniform(-0.02, 0.02)
        z = rng.uniform(0.85, 0.97)
        a = Agent(id=i, x=float(x), y=float(y), z=float(z),
                  k=float(np.clip(k + rng.uniform(-0.1, 0.1), 0, 1)),
                  s=float(np.clip(s + rng.uniform(-0.1, 0.1), 0, 1)),
                  archetype=name, lane=lane,
                  size=float(C.SIZE[name] * (1 + size_rng.uniform(-C.SIZE_JITTER, C.SIZE_JITTER))))
        a.target = a.pos
        agents.append(a)
    return agents


class World:
    """Everything the physics and the tick loop share."""

    def __init__(self, seed=0, condition="talk"):
        self.seed = seed
        self.condition = condition
        self.source = {"kind": "none", "label": ""}
        self.reset()

    def reset(self):
        self.agents = make_agents(self.seed)
        self.rng = np.random.default_rng(self.seed + 1000)   # for sampled ask answers
        # yielded_to[a][b]: how many times a yielded to b.
        self.yielded_to = np.zeros((C.N_AGENTS, C.N_AGENTS), dtype=int)
        self.w = 1.0                 # the house ear's expected section weight
        self.section_p = {}          # the house ear's latest section probabilities
        self.intensity = 0.0         # smoothed crowd intensity (physics), 0 calm .. 1 peak
        self.t = 0.0                 # playback clock from the browser
        self.sim_t = 0.0             # seconds of simulated physics
        self.playing = False
        self.dsp = {}
        self.kick_times = []         # playback times of recent kicks
        self.tick = 0
        self.exhaustion_events = 0

    @property
    def music_energy(self):
        return float(self.dsp.get("energy", 0.0))

    def init_frame(self):
        return {"type": "init", "n_lanes": C.N_LANES, "condition": self.condition,
                "agents": [{"id": a.id, "archetype": a.archetype, "lane": a.lane,
                            "k": round(a.k, 3), "s": round(a.s, 3), "size": round(a.size, 3)} for a in self.agents]}
