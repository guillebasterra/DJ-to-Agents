// Final pass at device resolution: fine 1 px grain. Alpha becomes dot density,
// so solid bodies stay smooth while falloffs, halos, tired agents and trails
// break up into grain.
precision highp float;

in vec2 vUv;
uniform sampler2D tTrail;
uniform vec3 uBg;
uniform float uTime;

layout(location = 0) out vec4 oScreen;

float hash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

void main() {
  vec4 t = texture(tTrail, vUv);
  float a = clamp(t.a, 0.0, 1.0);
  vec3 col = t.rgb / max(t.a, 1e-4);

  // Each pixel's threshold drifts at its own slow rate: the grain shimmers
  // without flickering, and stays uniformly distributed at every instant.
  vec2 px = floor(gl_FragCoord.xy);
  float n = fract(hash(px) + uTime * (0.25 + 0.5 * hash(px + 17.0)));
  float n2 = hash(px + 71.0);

  float dots = step(n, a * 1.04);
  float cover = mix(dots, a, 0.38 * a);          // a touch of smooth glow under the grain
  vec3 bg = uBg + (n2 - 0.5) * 0.022;            // subtle grain in the background
  oScreen = vec4(mix(bg, col, cover), 1.0);
}
