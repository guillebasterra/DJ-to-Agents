"""All constants (plan section 3). Tune only the energy constants, KAPPA and MAX_SPEED."""
import os

from dotenv import load_dotenv

load_dotenv()

MODEL_DECISIONS = os.environ.get("MODEL_DECISIONS", "gemini-decision-1")
MODEL_HYDROGEN = os.environ.get("MODEL_HYDROGEN", "gemini-4-hydrogen")
MODEL_NEON = os.environ.get("MODEL_NEON", "gemini-4-neon")

PORT = 8001

# Volume: x left-right, y down-up, z distance from the DJ (z = 0 is the front glass).
# The hot zone is a wide band on the front glass (z = 0), not a single point, so
# the front spreads along the glass instead of making one clump.
HOT_X = (0.15, 0.85)
HOT_Y = (0.2, 0.8)
D_MAX = 1.031             # from the band to the farthest corner of the box
N_AGENTS = 100
N_LANES = 10
AGENT_RADIUS = 0.05      # base radius (plan: 0.06); each agent scales it by archetype, jitter and energy
SIZE = {"diehard": 1.2, "between": 1.0, "dancer": 0.85}   # big and heavy ... small and nimble
SIZE_JITTER = 0.10
DEFLATE = 0.15            # a tired agent shrinks by up to this much
GLASS_PRESS = 0.62        # a body can press this close to the glass, as a share of its radius
PHYSICS_HZ = 30
TICK_SECONDS = 3.0
RING_EDGES = (0.25, 0.45, 0.65, 0.85)
MAX_SPEED = 0.11          # plan: 0.06; raised so movement reads clearly
COLLISION_SUBSTEPS = 4
COLLISION_RATE = 0.28     # share of an overlap resolved per substep (soft springs)
OVERLAP_CAP = 0.14        # bodies never interpenetrate by more than this share of a diameter
DENSITY_RADIUS = 3.2 * AGENT_RADIUS
DENSITY_CAP = 12
CONTAGION_RADIUS = 3.8 * AGENT_RADIUS

# Energy, per second.
# Tuned from the plan's a = 0.022, b = 0.010, d = 0.008, c = 0.033: with those
# the whole crowd was exhausted about 50 s into a track and never recovered.
E_FRONT = 0.012   # a: front crush
E_PUSH = 0.006    # b
E_DANCE = 0.002   # d
E_REST = 0.050    # c: rest recovery
E_RECOVERED = 0.3
E_CALM = 0.02     # everyone catches their breath when the music is calm (scaled by 1 - intensity)

# Liveliness: nobody sits still.
WANDER_TAU = 1.6          # s, Ornstein-Uhlenbeck wander
WANDER_SPEED = 0.06
ARCHETYPE_LIVELINESS = {"dancer": 1.6, "between": 1.0, "diehard": 0.55}
STALL_SPEED = 0.006       # slower than this for STALL_SECONDS earns a nudge
STALL_SECONDS = 1.25
NUDGE_SPEED = 0.05
NUDGE_TAU = 0.45
WALL_MARGIN = 0.09        # soft quadratic push away from the box walls
WALL_PUSH = 0.05
SLIP = 0.7                # tangential slip of anyone blocked on the way forward, as a share of max speed

# Crowd intensity: one smoothed 0..1 number from the house ear's section weight
# and the 5 s loudness. It scales movement, spacing and vibration; it never
# chooses an action.
INTENSITY_W = (0.8, 1.7)      # house weight w mapped to 0..1 (breakdown ~0.8, drop ~1.75)
INTENSITY_E = (0.2, 0.65)     # energy_5s mapped to 0..1
INTENSITY_RISE = 1.5          # s
INTENSITY_FALL = 3.0          # s
SECTION_TAU = 2.5             # s, smoothing of the section probabilities sent to the renderer
# The depth band the crowd settles into: back and deep when calm, at the glass at the peak.
BAND_CALM = (0.74, 0.20)      # (center z, half-thickness) at intensity 0
BAND_PEAK = (0.20, 0.16)      # at intensity 1
PLACE_KEEN = 1.0              # keen agents sit toward the front of the band: (k - 0.5) * this
PLACE_ACTION = {"push": 0.9, "hold": 0.0, "dance": -0.1, "yield": 0.0, "rest": -0.6}
ARC_GAIN = 1.0                # 1/s, how hard an agent is drawn to its place in the band
ARC_SPEED = 0.08              # cap on that draw
PERSONAL_SPACE = 0.30         # extra distance everyone keeps at intensity 0 (share of a diameter)
SQUEEZE = 0.18                # at intensity 1 bodies press into each other by this share instead
# Flow: a curl-noise field everyone rides, a lateral push out from behind
# whoever blocks the view, and a convective churn at the front at the peak.
FLOW_SPEED = 0.09
SIGHTLINE = 0.08
SIGHT_CALM = 1.1              # extra sideways clearance at intensity 0 (in summed radii)
CHURN = 0.08
CHURN_DEPTH = 0.36
PEAK_FROM = 0.65              # churn starts above this intensity

H_TAU = 4.0               # plan: 10; shortened so the crowd warms within a drop
U_NORM = 1.1             # H follows u / U_NORM (plan: u / 3, which left mean H at 0.06); calibrated so
                          # typical H spans about 0.1-0.8
KAPPA = 0.15

SECTIONS = ("intro", "build", "drop", "groove", "breakdown", "outro", "other")
SECTION_WEIGHTS = {"drop": 3.0, "build": 1.5, "groove": 1.0, "intro": 0.5,
                   "breakdown": 0.5, "outro": 0.5, "other": 0.5}

AUDIO_SR = 16000
PCM_CHUNK_MS = 250
BUFFER_SECONDS = 30
RING_CLIP_SECONDS = 8
HOUSE_CLIP_SECONDS = 15

MAX_ASKS_PER_TICK = 8
API_CONCURRENCY = 8
API_TIMEOUT = 8.0

ACTIONS = ("hold", "push", "yield", "rest", "dance")
CONDITIONS = ("shove", "silent", "talk")


def constants():
    return {k: v for k, v in globals().items()
            if k.isupper() and not k.startswith("MODEL") and isinstance(v, (int, float, tuple, dict))}


def hot_point(pos):
    """Nearest point of the hot band to each position (numpy, last axis = xyz)."""
    import numpy as np
    pos = np.asarray(pos, dtype=float)
    out = np.zeros_like(pos)
    out[..., 0] = np.clip(pos[..., 0], *HOT_X)
    out[..., 1] = np.clip(pos[..., 1], *HOT_Y)
    return out
