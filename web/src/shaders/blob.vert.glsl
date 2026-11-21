// One billboard per agent: a screen-space sphere impostor. The fragment shader
// writes a density field, not a surface, so touching blobs can merge softly.
in vec3 iPos;
in vec4 iAxis;    // squash axis (world), squash amount (spring-damped, can overshoot)
in vec3 iCol;
in vec4 iParam;   // glow intensity, white-hot core, radius scale, unused

uniform float uRadius, uExtent, uNear;

out vec2 vQ;            // offset from the center, in radii
flat out vec3 vAxis;    // squash axis in view space
flat out vec2 vScale;   // inverse scale along the axis, inverse scale across it
flat out vec3 vCol;
flat out vec3 vGlow;    // intensity, core, depth weight

void main() {
  vec4 mv = viewMatrix * vec4(iPos, 1.0);
  float dist = -mv.z;
  vQ = position.xy * uExtent;
  mv.xy += vQ * uRadius * iParam.z;
  gl_Position = projectionMatrix * mv;

  // Volume-preserving ellipsoid: scale q along the contact normal, 1 / sqrt(q) across it.
  float q = 1.0 / (1.0 + 2.0 * clamp(iAxis.w, -0.18, 0.45));
  vAxis = normalize(mat3(viewMatrix) * iAxis.xyz + vec3(1e-5, 0.0, 0.0));
  vScale = vec2(1.0 / q, sqrt(q));

  // Depth fog: far agents are dimmer, and nearer agents win where blobs overlap.
  float fog = smoothstep(uNear, uNear + 1.25, dist);
  vCol = iCol;
  vGlow = vec3(iParam.x * (1.0 - 0.6 * fog), iParam.y * (1.0 - 0.7 * fog), exp(-14.0 * (dist - uNear)));
}
