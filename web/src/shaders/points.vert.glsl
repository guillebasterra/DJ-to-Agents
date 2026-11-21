// One dot of one agent's point cloud. All shading is by dot density:
// a dot is either drawn in one palette color or not drawn at all.
attribute vec2 aRnd;
attribute vec3 iPos;
attribute vec3 iVel;
attribute vec4 iSquash;   // contact normal xyz, pressure
attribute vec4 iState;    // E, H, seed, flags

uniform float uRadius, uEnergy, uKick, uDpr, uLod, uFaces, uPx;
uniform vec3 uLight, uBg, uBlue, uRed, uWhite;

varying vec3 vColor;

#include deform

void main() {
  float E = iState.x, H = iState.y, seed = iState.z, flags = iState.w;
  // Turn the half-sphere of dots to face the camera.
  vec3 fwd = normalize(cameraPosition - iPos);
  vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), fwd));
  vec3 up = cross(fwd, right);
  float halo = step(1.0, length(position.xy));
  vec3 nrm = normalize(position);
  nrm = nrm.x * right + nrm.y * up + nrm.z * fwd;
  vec3 local = position.x * right + position.y * up + position.z * fwd;

#ifdef GHOST
  // Trail ghosts: flags carries the fade (1 = fresh, 0 = gone); no pulse, no hop.
  vec3 world = iPos + deform(local, iSquash, iVel) * uRadius * 0.9;
#else
  vec3 world = iPos + hop(flags, E) + deform(local, iSquash, iVel) * pulsedRadius(E);
#endif
  vec4 mv = viewMatrix * vec4(world, 1.0);
  float dist = -mv.z;

  vec3 nv = normalize(mat3(viewMatrix) * nrm);
  float lam = max(dot(nv, uLight), 0.0);
  float rim = pow(1.0 - position.z, 3.0);
  float fog = smoothstep(0.45, 1.5, dist);

  // Stipple: lit sides dense, shadow sides sparse, a speckled rim, a thin halo.
  float dens = 0.03 + 0.97 * pow(smoothstep(0.0, 0.9, lam), 1.3) + 0.08 * rim;
  dens *= mix(1.0, 0.45, halo);
  dens *= 0.35 + 0.65 * E;                        // tired agents are ghostly
  dens *= 0.6 + 0.4 * smoothstep(0.0, 0.5, H);   // unhappy agents are sparse
  dens *= 1.0 - 0.6 * fog;
#ifdef GHOST
  dens *= 0.5 * flags;
#else
  dens *= clamp(uLod / (dist * dist), 0.0, 1.0); // even screen coverage near and far

  // Face: two eyes, brows and a mouth carved out of the density on the
  // camera-facing side, turning toward the agent's motion. The mouth curves
  // with happiness.
  vec2 look = clamp(vec2(dot(iVel, right), dot(iVel, up)) * 7.0, -0.25, 0.25);
  vec2 fp = position.xy - look;
  float ex = abs(fp.x) - 0.27;
  float eyes = step(length(vec2(ex, fp.y - 0.13) / vec2(0.105, 0.075)), 1.0);
  float brow = step(abs(fp.y - 0.29 - 0.35 * ex), 0.028) * step(abs(ex), 0.15);
  float my = fp.y + 0.30 - (H - 0.4) * 1.6 * fp.x * fp.x;
  float mouth = step(abs(fp.x), 0.25) * step(abs(my), 0.035);
  float face = max(max(eyes, brow), mouth) * (1.0 - halo) * uFaces * smoothstep(1.35, 0.95, dist);
  dens *= 1.0 - 0.96 * face;
#endif

  if (fract(aRnd.x + seed * 0.731) > dens) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    return;
  }

  // Happiness picks the color of each dot; colors mix by count, never blend.
  float wB = mix(1.0, 0.12, smoothstep(0.0, 0.7, H)) + 0.25 * rim;
  float wR = smoothstep(0.12, 0.65, H) * (1.0 - 0.55 * smoothstep(0.8, 1.0, H));
  float wW = smoothstep(0.5, 1.0, H) * 2.4 * (0.15 + lam);
  float c = fract(aRnd.y + seed * 0.377) * (wB + wR + wW);
  vec3 col = c < wB ? uBlue : (c < wB + wR ? uRed : uWhite);
  vColor = mix(col, uBg, 0.45 * fog);

  gl_Position = projectionMatrix * mv;
#ifdef GHOST
  gl_PointSize = uDpr;
#else
  gl_PointSize = uDpr * clamp(0.85 / dist, 1.0, 2.4);

  // Chromatic fringe: at the edges some dots split into a red one nudged one
  // way and a blue one nudged the other, like misregistered print.
  float edge = max(halo, step(position.z, 0.5));
  float fr = fract(aRnd.x * 57.31 + aRnd.y * 13.7 + seed);
  if (edge > 0.5 && fr < 0.14 + 0.3 * H) {
    float side = fr < 0.5 * (0.14 + 0.3 * H) ? 1.0 : -1.0;
    vColor = mix(side > 0.0 ? uBlue : uRed, uBg, 0.45 * fog);
    gl_Position.x += side * 2.5 * uPx * clamp(0.85 / dist, 1.0, 2.4) * gl_Position.w;
  }
#endif
}
