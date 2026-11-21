// Turns the summed fields into glowing blobs and folds them into the trail
// buffer. Summing exp(-k * sdf) and taking -log / k is a smooth-min of the
// distance fields: touching blobs bulge into each other and share their glow,
// but each keeps its own body, color and core.
precision highp float;

in vec2 vUv;
uniform sampler2D tColor, tField, tPrev;
uniform float uK, uDecay;

layout(location = 0) out vec4 oTrail;

void main() {
  vec4 c = texture(tColor, vUv);
  vec4 f = texture(tField, vUv);
  float wsum = max(c.a, 1e-6);
  vec3 col = c.rgb / wsum;
  float core = clamp(f.g / wsum, 0.0, 1.0);
  float glow = clamp(f.b / wsum, 0.0, 1.0);

  float sd = -log(max(f.r, 1e-6)) / uK;                 // smooth-min distance, in radii
  float body = smoothstep(0.16, -0.10, sd);             // soft edge
  float halo = 0.34 * exp(-max(sd, 0.0) * 5.0);          // spills into the background as grain
  float alpha = max(body * (0.88 + 0.12 * glow), halo * (0.3 + 0.7 * glow));
  alpha *= step(1e-5, c.a);

  // Tired agents are dim: their color sinks toward the background grey.
  col = mix(vec3(0.21), col, 0.55 + 0.45 * glow) * (0.94 + 0.14 * glow);
  col = mix(col, vec3(1.0, 0.98, 0.94), core);
  vec4 cur = vec4(col * alpha, alpha);

  // Accumulation with decay: whatever was here fades instead of vanishing.
  vec4 prev = texture(tPrev, vUv) * uDecay;
  oTrail = max(cur, prev);
}
