"""All constants (plan section 3). Tune only the energy constants, KAPPA and MAX_SPEED."""
import os

from dotenv import load_dotenv

load_dotenv()

MODEL_DECISIONS = os.environ.get("MODEL_DECISIONS", "gemini-decision-1")
MODEL_HYDROGEN = os.environ.get("MODEL_HYDROGEN", "gemini-4-hydrogen")
MODEL_NEON = os.environ.get("MODEL_NEON", "gemini-4-neon")

PORT = 8001

# Volume: x left-right, y down-up, z distance from the DJ (z = 0 is the front glass).
H0 = (0.5, 0.5, 0.0)
D_MAX = 1.225
N_AGENTS = 100
N_LANES = 10
AGENT_RADIUS = 0.06
PHYSICS_HZ = 30
TICK_SECONDS = 3.0
RING_EDGES = (0.25, 0.45, 0.65, 0.85)
MAX_SPEED = 0.06
COLLISION_ITERS = 4
DENSITY_RADIUS = 2.5 * AGENT_RADIUS
DENSITY_CAP = 12
CONTAGION_RADIUS = 3.0 * AGENT_RADIUS

# Energy, per second.
# Tuned from the plan's a = 0.022, b = 0.010, d = 0.008, c = 0.033: with those
# the whole crowd was exhausted about 50 s into a track and never recovered.
E_FRONT = 0.012   # a: front crush
E_PUSH = 0.006    # b
E_DANCE = 0.002   # d
E_REST = 0.050    # c: rest recovery
E_RECOVERED = 0.3

H_TAU = 10.0
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
