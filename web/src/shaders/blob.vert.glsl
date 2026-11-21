// One billboard per agent: a soft pigment blob. Depth-tested, so a nearer body
// covers a farther one.
in vec3 iPos;
in vec4 iAxis;    // contact axis (world), squash amount (spring-damped)
in vec4 iVel;     // direction of travel (world), stretch amount
in vec3 iAbs;     // pigment absorbance per channel at density 1
in vec4 iParam;   // pigment density, world radius, glass press 0..1, unused
in vec3 iModeA;   // wobble amplitudes for modes 2, 3, 4
in vec3 iModeP;   // their phases

uniform float uExtent;

out vec2 vQ;             // offset from the center, in radii
flat out vec3 vAxis1, vAxis2;
flat out vec2 vScale1, vScale2;   // inverse scale along the axis, across it
flat out vec3 vAbs, vModeA, vModeP;
flat out vec2 vInk;      // density, glass press

void main() {
  vec4 mv = viewMatrix * vec4(iPos, 1.0);
  float depth = clamp(iPos.z, 0.0, 1.0);
  float press = iParam.z;

  // Exaggerated perspective: big by the glass, small at the back. A body
  // pressed on the glass is shorter along z, so wider on screen.
  float radius = iParam.y * mix(1.28, 0.74, depth) * (1.0 + 0.30 * press);
  vQ = position.xy * uExtent;
  mv.xy += vQ * radius;
  gl_Position = projectionMatrix * mv;

  // Volume-preserving ellipsoids: squash by q along the contact normal and
  // bulge by 1 / sqrt(q) across it; stretch the other way along the velocity.
  mat3 view = mat3(viewMatrix);
  float q = 1.0 / (1.0 + 2.0 * clamp(iAxis.w, -0.15, 0.45));
  vAxis1 = normalize(view * iAxis.xyz + vec3(1e-5, 0.0, 0.0));
  vScale1 = vec2(1.0 / q, sqrt(q));
  float st = 1.0 + clamp(iVel.w, 0.0, 0.35);
  vAxis2 = normalize(view * iVel.xyz + vec3(0.0, 1e-5, 0.0));
  vScale2 = vec2(1.0 / st, sqrt(st));

  // Far agents are paler and more transparent: they fade toward the paper.
  vInk = vec2(iParam.x * mix(1.0, 0.30, smoothstep(0.0, 1.0, depth)), press);
  vAbs = iAbs;
  vModeA = iModeA;
  vModeP = iModeP;
}
