"""30 Hz physics in the 3D aquarium: the single source of truth for positions,
density, energy, happiness and contagion (plan section 5)."""
import numpy as np

from . import config as C

R = C.AGENT_RADIUS
H0 = np.array(C.H0)
GRID = 6
_g = (np.arange(GRID) + 0.5) / GRID
CELLS = np.stack(np.meshgrid(_g, _g, _g, indexing="ij"), -1).reshape(-1, 3)
RETARGET_SECONDS = 0.5
REST_RADIUS = 0.3
STEP = 0.08
PRESS_MARGIN = 1.12


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-9)


class Physics:
    def __init__(self, world):
        self.world = world
        n = len(world.agents)
        self.target_age = np.full(n, 1e9)
        self.target_action = [""] * n

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
                t = p + STEP * _unit(H0 - p)
            elif a.action == "yield":
                # Sidestep perpendicular to the way to the hot spot, toward the emptiest side.
                fwd = _unit(H0 - p)
                side = _unit(np.cross(fwd, [0.0, 1.0, 0.0]) if abs(fwd[1]) < 0.95 else np.cross(fwd, [1.0, 0.0, 0.0]))
                up = np.cross(fwd, side)
                ang = np.arange(6) * np.pi / 3
                cand = p + STEP * (np.cos(ang)[:, None] * side + np.sin(ang)[:, None] * up)
                cand = np.clip(cand, R, 1 - R)
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
        act = np.array([a.action for a in agents])

        # 1. targets
        self._targets(agents, pos, dt)
        target = np.array([a.target for a in agents])

        # 2. integrate: steer toward the target, clamp to max speed.
        vmax = C.MAX_SPEED * (0.4 + 0.6 * E)
        to = target - pos
        dist = np.linalg.norm(to, axis=1)
        want = _unit(to) * (vmax * np.minimum(1.0, dist / 0.03))[:, None]
        vel += (want - vel) * min(1.0, 4.0 * dt)
        speed = np.linalg.norm(vel, axis=1)
        vel *= np.minimum(1.0, vmax / np.maximum(speed, 1e-9))[:, None]
        start = pos.copy()
        pos = pos + vel * dt

        # 3. collide: spheres, split by inverse mass, 4 iterations.
        mass = 0.2 + push * E
        share = mass[None, :] / (mass[:, None] + mass[None, :])   # i moves by j's share of the mass
        pressure = np.zeros(n)
        normal = np.zeros((n, 3))
        eye = np.eye(n, dtype=bool)
        for it in range(C.COLLISION_ITERS):
            diff = pos[:, None] - pos[None]
            dd = np.linalg.norm(diff, axis=-1)
            dd[eye] = 1.0
            over = np.where(eye, 0.0, np.maximum(0.0, 2 * R - dd))
            if it == 0:
                # Pressure: how hard neighbors press in, with a soft margin so agents
                # resting in contact still flatten a little against each other.
                soft = np.where(eye, 0.0, np.maximum(0.0, PRESS_MARGIN * 2 * R - dd))
                pressure = 0.35 * soft.sum(1) / (2 * R)
                j = soft.argmax(1)
                hit = soft.max(1) > 0
                normal[hit] = -(diff / dd[..., None])[np.arange(n), j][hit]
            pos = pos + ((diff / dd[..., None]) * (over * share)[..., None]).sum(1) * 0.8
            pos = np.clip(pos, R, 1 - R)      # box walls; the front glass is a wall
        # Collisions bleed into velocity so blocked agents actually slow down.
        vel = 0.5 * vel + 0.5 * (pos - start) / dt

        # 4. density and proximity
        diff = pos[:, None] - pos[None]
        dd = np.linalg.norm(diff, axis=-1)
        dd[eye] = 9.0
        rho = np.minimum((dd < C.DENSITY_RADIUS).sum(1), C.DENSITY_CAP) / C.DENSITY_CAP
        v = 1.0 - np.linalg.norm(pos - H0, axis=1) / C.D_MAX

        # 5. energy
        resting = (act == "rest") | (act == "retreat") | ((act == "hold") & (rho < 0.2))
        dE = (-C.E_FRONT * v * rho - C.E_PUSH * (act == "push") - C.E_DANCE * (act == "dance")
              + C.E_REST * (1 - v) * (1 - rho) * resting)
        E = np.clip(E + dE * dt, 0.0, 1.0)

        # 6. happiness: utility, EMA, contagion from neighbors.
        u = E * (k * v * w.w + s * (1 - rho) * w.music_energy) / (k + s)
        H = H + (u / 3.0 - H) * (dt / C.H_TAU)
        near = dd < C.CONTAGION_RADIUS
        cnt = near.sum(1)
        mean_h = (near * H[None]).sum(1) / np.maximum(cnt, 1)
        H = np.clip(H + np.where(cnt > 0, C.KAPPA * (mean_h - H) * dt, 0.0), 0.0, 1.0)

        w.sim_t += dt
        for i, a in enumerate(agents):
            a.x, a.y, a.z = (float(c) for c in pos[i])
            a.vx, a.vy, a.vz = (float(c) for c in vel[i])
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
        return {"type": "physics", "t": round(w.t, 2), "agents": [
            [a.id, r(a.x), r(a.y), r(a.z), r(a.vx), r(a.vy), r(a.vz), r(a.E), r(a.rho), r(a.H), a.action,
             r(a.pressure), r(a.normal[0]), r(a.normal[1]), r(a.normal[2])] for a in w.agents]}
