// One dot of one agent's point cloud. All shading is by dot density:
// a dot is either drawn in one palette color or not drawn at all.
attribute vec2 aRnd;
attribute vec3 iPos;
attribute vec3 iVel;
attribute vec4 iSquash;   // contact normal xyz, pressure
attribute vec4 iState;    // E, H, seed, flags

uniform float uRadius, uEnergy, uKick, uDpr, uLod;
uniform vec3 uLight, uBg, uBlue, uRed, uWhite;

varying vec3 vColor;

#include deform

void main() {
  float E = iState.x, H = iState.y, seed = iState.z;
  // Turn the half-sphere of dots to face the camera.
  vec3 fwd = normalize(cameraPosition - iPos);
  vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), fwd));
  vec3 up = cross(fwd, right);
  float halo = step(1.0, length(position.xy));
  vec3 nrm = normalize(position);
  nrm = nrm.x * right + nrm.y * up + nrm.z * fwd;
  vec3 local = position.x * right + position.y * up + position.z * fwd;

  vec3 world = iPos + deform(local, iSquash, iVel) * pulsedRadius(E);
  vec4 mv = viewMatrix * vec4(world, 1.0);
  float dist = -mv.z;

  vec3 nv = normalize(mat3(viewMatrix) * nrm);
  float lam = max(dot(nv, uLight), 0.0);
  float rim = pow(1.0 - position.z, 3.0);
  float fog = smoothstep(0.45, 1.5, dist);

  // Stipple: lit sides dense, shadow sides sparse, a speckled rim, a thin halo.
  float dens = 0.03 + 0.97 * pow(smoothstep(0.0, 0.9, lam), 1.3) + 0.08 * rim;
  dens *= mix(1.0, 0.45, halo);
  dens *= 0.2 + 0.8 * E;                         // tired agents are ghostly
  dens *= 0.6 + 0.4 * smoothstep(0.0, 0.5, H);   // unhappy agents are sparse
  dens *= 1.0 - 0.6 * fog;
  dens *= clamp(uLod / (dist * dist), 0.0, 1.0); // even screen coverage near and far

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
  gl_PointSize = uDpr * clamp(0.85 / dist, 1.0, 2.4);
}
