precision highp float;

in vec2 vQ;
flat in vec3 vAxis1, vAxis2;
flat in vec2 vScale1, vScale2;
flat in vec3 vAbs, vModeA, vModeP;
flat in vec2 vInk;

layout(location = 0) out vec4 oPigment;   // absorbance per channel

vec3 unscale(vec3 p, vec3 axis, vec2 s) {
  return p * s.y + (s.x - s.y) * dot(p, axis) * axis;
}

void main() {
  // Back to the unit blob: undo stretch and squash, then the surface wobble.
  vec3 p = unscale(unscale(vec3(vQ, 0.0), vAxis2, vScale2), vAxis1, vScale1);
  float th = atan(p.y, p.x);
  float wobble = 1.0 + vModeA.x * cos(2.0 * th - vModeP.x) + vModeA.y * cos(3.0 * th - vModeP.y)
    + vModeA.z * cos(4.0 * th - vModeP.z);
  float r = length(p) / wobble;
  if (r > 1.0) discard;

  // Pigment: a feathered edge, a little pooling just inside it, and a thin
  // unpainted rim. The rim still covers what is behind, so bodies that touch
  // or overlap keep a thin paper gap between them and never merge.
  float body = smoothstep(0.95, 0.80, r);
  float pool = 0.24 * exp(-pow((r - 0.76) / 0.10, 2.0));
  float wash = 0.80 + 0.20 * (1.0 - r * r);
  // Pressed against the glass: more pigment where it touches.
  float contact = vInk.y * 0.75 * exp(-r * r * 2.2);
  oPigment = vec4(vAbs * vInk.x * body * (wash + pool + contact), 1.0);
}
