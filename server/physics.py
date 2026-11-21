"""30 Hz physics in the 3D aquarium: the single source of truth for positions,
density, energy, happiness and contagion (plan section 5)."""
import numpy as np

from . import config as C

R = C.AGENT_RADIUS
GRID = 6
_g = (np.arange(GRID) + 0.5) / GRID
CELLS = np.stack(np.meshgrid(_g, _g, _g, indexing="ij"), -1).reshape(-1, 3)
RETARGET_SECONDS = 0.5
REST_RADIUS = 0.3
STEP = 0.08
PRESSURE_GAIN = 2.5      # summed overlap (in diameters) -> the renderer's squash amount


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-9)


class Physics:
    def __init__(self, world):
        self.world = world
        n = len(world.agents)
        self.target_age = np.full(n, 1e9)
        self.target_action = [""] * n
        self.rng = np.random.default_rng(world.seed + 7)
        self.wander = self.rng.normal(size=(n, 3))     # OU state, unit variance
        self.nudge = np.zeros((n, 3))
        self.slow = np.zeros(n)                        # seconds spent below STALL_SPEED
        self.lively = np.array([C.ARCHETYPE_LIVELINESS[a.archetype] for a in world.agents])
        self.sec = np.zeros(3)                         # smoothed p(build), p(drop), p(breakdown)

    def _targets(self, agents, pos, dt):
        """Target by action; recomputed when the action changes or every 0.5 s."""
        self.target_age += dt
        cell_counts = None
        for i, a in enumerate(agents):
            if a.action == self.target_action[i] and self.target_age[i] < RETARGET_SECONDS:
                continue
            self.target_age[i] = 0.0
            self.target_action[i] = a.action
            p = pos[i]
            if a.action == "push":
                t = p + STEP * _unit(C.hot_point(p) - p)
            elif a.action == "yield":
                # Sidestep perpendicular to the way to the hot spot, toward the emptiest side.
                fwd = _unit(C.hot_point(p) - p + [0.0, 0.0, -1e-6])
                side = _unit(np.cross(fwd, [0.0, 1.0, 0.0]) if abs(fwd[1]) < 0.95 else np.cross(fwd, [1.0, 0.0, 0.0]))
                up = np.cross(fwd, side)
                ang = np.arange(6) * np.pi / 3
                cand = p + STEP * (np.cos(ang)[:, None] * side + np.sin(ang)[:, None] * up)
                cand = np.clip(cand, a.radius, 1 - a.radius)
                crowd = (np.linalg.norm(cand[:, None] - pos[None], axis=-1) < C.DENSITY_RADIUS).sum(1)
                moved = np.linalg.norm(cand - p, axis=-1)
                t = cand[np.argmin(crowd - moved)]     # least dense; prefer sides not cut off by a wall
            elif a.action == "rest":
                if cell_counts is None:
                    idx = np.clip((pos * GRID).astype(int), 0, GRID - 1)
                    cell_counts = np.bincount(idx[:, 0] * GRID * GRID + idx[:, 1] * GRID + idx[:, 2],
                                              minlength=GRID ** 3)
                dist = np.linalg.norm(CELLS - p, axis=-1)
                score = np.where(dist < REST_RADIUS, cell_counts + dist, 1e9)
                t = CELLS[np.argmin(score)]
            elif a.action == "retreat":
                t = np.array([p[0], p[1], 0.95])
            else:   # hold, dance
                t = p
            a.target = tuple(float(c) for c in t)

    def step(self, dt):
        w = self.world
        agents = w.agents
        n = len(agents)
        pos = np.array([a.pos for a in agents])
        vel = np.array([(a.vx, a.vy, a.vz) for a in agents])
        E = np.array([a.E for a in agents])
        H = np.array([a.H for a in agents])
        k = np.array([a.k for a in agents])
        s = np.array([a.s for a in agents])
        push = np.array([a.pushiness for a in agents])
        for a in agents:
            # An accepted ask means stepping aside for 2 s, then holding.
            if a.action == "yield" and a.yield_until and w.sim_t >= a.yield_until:
                a.action, a.yield_until = "hold", 0.0
        act = np.array([a.action for a in agents])

        # 1. targets
        self._targets(agents, pos, dt)
        target = np.array([a.target for a in agents])

        # 2. integrate: steer toward the target, clamp to max speed.
        # The house ear's section probabilities, smoothed, scale how much everyone
        # moves. They never choose an action.
        sp = w.section_p
        goal = np.array([sp.get("build", 0.0), sp.get("drop", 0.0), sp.get("breakdown", 0.0)])
        self.sec += (goal - self.sec) * min(1.0, dt / C.SECTION_TAU)
        p_build, p_drop, p_break = self.sec
        rad = np.array([a.radius for a in agents])
        vmax = C.MAX_SPEED * (0.4 + 0.6 * E) * (1.0 + 0.5 * p_build + 0.3 * p_drop)
        to = target - pos
        dist = np.linalg.norm(to, axis=1)
        want = _unit(to) * (vmax * np.minimum(1.0, dist / 0.03))[:, None]
        # Tide: the crowd leans toward the glass when it is loud and eases back when quiet.
        music = w.music_energy
        loud = float(np.clip(0.6 * music + 0.4 * (w.w - 0.5) / 1.3, 0.0, 1.0))
        want *= np.where(act == "push", 0.55 + 0.45 * loud, 1.0)[:, None]    # pushing is half-hearted when it is quiet
        # build: drift forward; drop: closest; breakdown: loosen and drift back.
        lean = C.TIDE * (2.0 * loud - 1.0) + C.BUILD_DRIFT * p_build + C.DROP_PULL * p_drop - C.BREAK_DRIFT * p_break
        tide = lean * (0.4 + 0.6 * k)
        tide = np.where((act == "rest") | (act == "retreat"), np.minimum(tide, 0.0), tide)
        fwd = _unit(C.hot_point(pos) - pos + [0.0, 0.0, -1e-6])
        want += fwd * tide[:, None]
        vel += (want - vel) * min(1.0, 4.0 * dt)
        speed = np.linalg.norm(vel, axis=1)
        vel *= np.minimum(1.0, vmax / np.maximum(speed, 1e-9))[:, None]

        # Nobody sits still: Ornstein-Uhlenbeck wander, livelier with the music and with energy.
        self.wander += -self.wander * (dt / C.WANDER_TAU) + np.sqrt(2 * dt / C.WANDER_TAU) * self.rng.normal(size=(n, 3))
        live = np.maximum(0.30, 0.30 + 0.70 * (0.65 * music + 0.35 * E)) * self.lively * (1.0 + 0.4 * p_drop - 0.25 * p_break)
        drift = C.WANDER_SPEED * live[:, None] * self.wander + self.nudge
        self.nudge *= np.exp(-dt / C.NUDGE_TAU)
        # Soft quadratic push away from the walls (half strength at the front glass).
        m = C.WALL_MARGIN
        lo = np.clip((m - (pos - rad[:, None])) / m, 0.0, 1.0) ** 2
        hi = np.clip((m - (1 - rad[:, None] - pos)) / m, 0.0, 1.0) ** 2
        lo[:, 2] *= 0.5
        drift += C.WALL_PUSH * (lo - hi)

        start = pos.copy()
        pos = pos + (vel + drift) * dt

        # 3. collide: soft springs. Each substep resolves a share of every overlap,
        # split by inverse mass, so bodies compress and bulge instead of snapping apart.
        size = np.array([a.size for a in agents])
        mass = (0.08 + 2.5 * push ** 2 * E) * size ** 2      # big bodies are heavy and win shoves
        touch = rad[:, None] + rad[None, :]                  # each pair collides at its own radii
        floor = np.stack([rad, rad, C.GLASS_PRESS * rad], 1)  # bodies can press flat against the glass
        share = mass[None, :] / (mass[:, None] + mass[None, :])   # i moves by j's share of the mass
        pressure = np.zeros(n)
        normal = np.zeros((n, 3))
        eye = np.eye(n, dtype=bool)
        pushing = act == "push"
        # Loosen up when it is quiet: bodies keep a little extra distance, which
        # the next loud passage squeezes back out.
        reach = touch * (1.0 + C.PERSONAL_SPACE * max(1.0 - loud, p_break))
        for it in range(C.COLLISION_SUBSTEPS):
            diff = pos[:, None] - pos[None]
            dd = np.linalg.norm(diff, axis=-1)
            dd[eye] = 1.0
            away = diff / dd[..., None]                 # unit vector from j to i
            over = np.where(eye, 0.0, np.maximum(0.0, reach - dd))
            if it == 0:
                pressure = PRESSURE_GAIN * (np.where(eye, 0.0, np.maximum(0.0, touch - dd)) / touch).sum(1)
                j = over.argmax(1)
                hit = over.max(1) > 0
                normal[hit] = -away[np.arange(n), j][hit]
                # Shoulder slip: a pusher blocked by a lighter agent slides around it
                # instead of deadlocking against it.
                ahead = -(away * fwd[:, None, :]).sum(-1)                 # how squarely j sits in i's way
                block = (over > 0) & (ahead > 0.3) & pushing[:, None] & (mass[None, :] < mass[:, None])
                tang = fwd[:, None, :] + ahead[..., None] * away          # fwd minus its part along the contact
                tl = np.linalg.norm(tang, axis=-1, keepdims=True)
                side = np.cross(away, [0.0, 1.0, 0.0]) * np.where(np.arange(n) % 2 == 0, 1.0, -1.0)[:, None, None]
                tang = np.where(tl > 0.2, tang / np.maximum(tl, 1e-9), _unit(side))
                slip = (tang * (block * np.minimum(1.0, over / (0.2 * R)))[..., None]).sum(1)
                sl = np.linalg.norm(slip, axis=1, keepdims=True)
                slip /= np.maximum(sl, 1.0)
                pos = pos + slip * (C.SLIP * vmax * dt)[:, None]
            # Past the cap an overlap is resolved at once: squishy, but still bodies.
            fix = over * C.COLLISION_RATE + np.maximum(0.0, over * (1 - C.COLLISION_RATE) - C.OVERLAP_CAP * touch)
            pos = pos + (away * (fix * share)[..., None]).sum(1)
            pos = np.clip(pos, floor, 1 - rad[:, None])      # box walls; the front glass is a wall
        moved = (pos - start) / dt
        # Collisions bleed into velocity so blocked agents actually slow down.
        vel = 0.5 * vel + 0.5 * (moved - drift)

        # Anti-stall: anyone nearly motionless for a while gets a decaying nudge.
        self.slow = np.where(np.linalg.norm(moved, axis=1) < C.STALL_SPEED, self.slow + dt, 0.0)
        stuck = self.slow > C.STALL_SECONDS
        if stuck.any():
            self.nudge[stuck] = _unit(self.rng.normal(size=(int(stuck.sum()), 3))) * C.NUDGE_SPEED
            self.slow[stuck] = 0.0

        # 4. density and proximity
        diff = pos[:, None] - pos[None]
        dd = np.linalg.norm(diff, axis=-1)
        dd[eye] = 9.0
        rho = np.minimum((dd < C.DENSITY_RADIUS).sum(1), C.DENSITY_CAP) / C.DENSITY_CAP
        v = 1.0 - np.linalg.norm(pos - C.hot_point(pos), axis=1) / C.D_MAX

        # 5. energy
        resting = (act == "rest") | (act == "retreat") | ((act == "hold") & (rho < 0.2))
        dE = (-C.E_FRONT * v * rho - C.E_PUSH * (act == "push") - C.E_DANCE * (act == "dance")
              + C.E_REST * (1 - v) * (1 - rho) * resting)
        E = np.clip(E + dE * dt, 0.0, 1.0)

        # 6. happiness: utility, EMA, contagion from neighbors.
        u = E * (k * v * w.w + s * (1 - rho) * w.music_energy) / (k + s)
        H = H + (u / C.U_NORM - H) * (dt / C.H_TAU)
        near = dd < C.CONTAGION_RADIUS
        cnt = near.sum(1)
        mean_h = (near * H[None]).sum(1) / np.maximum(cnt, 1)
        H = np.clip(H + np.where(cnt > 0, C.KAPPA * (mean_h - H) * dt, 0.0), 0.0, 1.0)

        w.sim_t += dt
        for i, a in enumerate(agents):
            a.x, a.y, a.z = (float(c) for c in pos[i])
            a.vx, a.vy, a.vz = (float(c) for c in moved[i])    # what the eye sees, wander included
            a.E, a.H, a.u = float(E[i]), float(H[i]), float(u[i])
            a.rho, a.v = float(rho[i]), float(v[i])
            a.pressure = 0.6 * a.pressure + 0.4 * float(pressure[i])
            if pressure[i] > 0:
                a.normal = tuple(float(c) for c in normal[i])
            # Exhaustion: forced retreat at E <= 0 until E >= 0.3.
            if not a.exhausted and a.E <= 0.0:
                a.exhausted = True
                a.action = "retreat"
                w.exhaustion_events += 1
            elif a.exhausted and a.E >= C.E_RECOVERED:
                a.exhausted = False
                a.action = "rest"

    def frame(self):
        r = lambda x: round(x, 3)
        w = self.world
        return {"type": "physics", "t": round(w.t, 2), "m": [r(float(x)) for x in self.sec], "agents": [
            [a.id, r(a.x), r(a.y), r(a.z), r(a.vx), r(a.vy), r(a.vz), r(a.E), r(a.rho), r(a.H), a.action,
             r(a.pressure), r(a.normal[0]), r(a.normal[1]), r(a.normal[2]), r(a.radius)] for a in w.agents]}
