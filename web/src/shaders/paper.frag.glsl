// Final pass at device resolution: pigment on paper. The pigment buffers hold
// how much light is taken away, so out = paper * (1 - pigment). Thin pigment is
// a tint toward the paper, never a shift of hue.
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
  // Each pixel's grain value drifts at its own slow rate: it is alive but
  // never flickers, and stays evenly distributed at every instant.
  vec2 px = floor(gl_FragCoord.xy);
  float grain = fract(hash(px) + uTime * (0.20 + 0.45 * hash(px + 17.0)));
  float tooth = fract(hash(px + 71.0) + uTime * (0.10 + 0.25 * hash(px + 113.0)));

  vec3 body = texture(tPigment, vUv).rgb;
  // Trails are grainier than bodies: pigment caught in the tooth of the paper.
  vec3 trail = texture(tTrail, vUv).rgb * (0.6 + 0.6 * tooth);
  vec3 D = max(body * (0.86 + 0.28 * tooth), trail);

  vec3 paper = uPaper * (1.0 + 0.035 * (2.0 * grain - 1.0));
  float edge = length((vUv - 0.5) * vec2(min(uAspect, 1.6), 1.0));
  paper *= 1.0 - 0.10 * smoothstep(0.35, 0.95, edge);      // slight vignette
  oScreen = vec4(paper * (1.0 - min(D, 0.97)), 1.0);
}
