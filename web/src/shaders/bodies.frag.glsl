// All bodies in one full-screen pass. Every pixel finds the nearest and the
// second-nearest body in a deformed, depth-biased distance. The nearest one
// paints; the margin to the second leaves a thin paper gap. So bodies flatten
// where they press, slide along each other and never merge, and a body nearer
// the glass takes the space of one behind it.
precision highp float;

#define N 100
uniform int uCount;
uniform vec4 uA[N];   // center x, y (screen heights), radius, depth bias
uniform vec4 uB[N];   // direction of travel on screen (x, y), tail length, pigment density
uniform vec4 uC[N];   // pigment color (sRGB), phase
uniform vec4 uD[N];   // wobble amplitudes for modes 2, 3, 4 and their shared angle
uniform vec2 uRes;
uniform float uTime;

layout(location = 0) out vec4 oPigment;   // rgb: how much light the pigment takes away (1 - transmittance)

const float HALO = 2.6;     // halo radius, in body radii
const float REACH = 1.35;   // a body claims space this far out, so its neighbors keep a gap

void main() {
  vec2 p = gl_FragCoord.xy / uRes.y;
  float f1 = 1e9, f2 = 1e9, inside = 0.0, density = 0.0;
  vec3 color = vec3(1.0), haloColor = vec3(0.0);
  float haloWeight = 0.0;

  for (int i = 0; i < N; i++) {
    if (i >= uCount) break;
    vec4 A = uA[i];
    vec2 q = (p - A.xy) / A.z;
    float d2 = dot(q, q);
    if (d2 > HALO * HALO) continue;
    vec4 B = uB[i], C = uC[i];

    // Halo: pigment bleeding into the paper around the spot.
    float h = 1.0 - d2 / (HALO * HALO);
    h = h * h * h * B.w;
    haloColor += C.rgb * h;
    haloWeight += h;

    float len = sqrt(d2);
    if (len > 2.2) continue;
    vec2 n = q / max(len, 1e-5);
    float th = atan(n.y, n.x), ph = C.w;
    vec4 D = uD[i];
    // Outline: a teardrop tail behind the direction of travel, spring-driven
    // wobble modes, and a slow ambient breathing so no body is ever an ellipse.
    float back = max(0.0, -dot(n, B.xy));
    float shape = 1.0 + B.z * back * back - 0.25 * B.z * (1.0 - back) * abs(n.x * B.y - n.y * B.x)
      + D.x * cos(2.0 * (th - D.w)) + D.y * cos(3.0 * (th - D.w)) + D.z * cos(4.0 * (th - D.w))
      + 0.055 * sin(2.0 * th + ph + uTime * 0.9) + 0.04 * sin(3.0 * th - 1.7 * ph - uTime * 1.3)
      + 0.022 * sin(5.0 * th + 2.3 * ph + uTime * 0.7);
    float d = len / shape;
    if (d > REACH) continue;
    // Past its own edge a body's claim falls off steeply.
    float f = (d < 1.0 ? d : 1.0 + (d - 1.0) * 4.0) + A.w;
    if (f < f1) {
      f2 = f1; f1 = f;
      inside = 1.0 - d; density = B.w; color = C.rgb;
    } else if (f < f2) {
      f2 = f;
    }
  }

  // The body: soft free edge, saturated core, and a paper gap toward whoever is next.
  float edge = smoothstep(0.0, 0.26, inside);
  float gap = smoothstep(0.035, 0.24, f2 - f1);
  float core = smoothstep(0.15, 0.85, inside);
  float alpha = density * edge * gap * (0.82 + 0.18 * core);
  vec3 body = mix(vec3(1.0), color * (1.0 - 0.10 * core), alpha);

  vec3 halo = vec3(1.0);
  if (haloWeight > 1e-4) halo = mix(vec3(1.0), haloColor / haloWeight, 0.30 * (1.0 - exp(-1.6 * haloWeight)));
  oPigment = vec4(1.0 - body * halo, alpha);
}
