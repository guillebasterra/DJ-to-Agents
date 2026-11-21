// Final pass at device resolution: pigment on paper. Light passes through the
// pigment and comes back off the paper, so color multiplies: out = paper * exp(-A).
precision highp float;

in vec2 vUv;
uniform sampler2D tPigment, tTrail;
uniform vec3 uPaper;
uniform float uTime, uAspect;

layout(location = 0) out vec4 oScreen;

float hash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

void main() {
  vec3 A = max(texture(tPigment, vUv).rgb, texture(tTrail, vUv).rgb);

  // Each pixel's grain value drifts at its own slow rate: it is alive but
  // never flickers, and stays evenly distributed at every instant.
  vec2 px = floor(gl_FragCoord.xy);
  float grain = fract(hash(px) + uTime * (0.20 + 0.45 * hash(px + 17.0)));
  float tooth = fract(hash(px + 71.0) + uTime * (0.10 + 0.25 * hash(px + 113.0)));

  A *= 0.78 + 0.44 * tooth;                                // pigment settles unevenly into the paper
  vec3 paper = uPaper * (1.0 + 0.035 * (2.0 * grain - 1.0));
  float edge = length((vUv - 0.5) * vec2(min(uAspect, 1.6), 1.0));
  paper *= 1.0 - 0.10 * smoothstep(0.35, 0.95, edge);      // slight vignette
  oScreen = vec4(paper * exp(-A), 1.0);
}
