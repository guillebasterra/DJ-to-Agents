precision highp float;

in vec2 vQ;
flat in vec3 vAxis;
flat in vec2 vScale;
flat in vec3 vCol;
flat in vec3 vGlow;

uniform float uK;

layout(location = 0) out vec4 oColor;   // sum of color * weight, sum of weight
layout(location = 1) out vec4 oField;   // sum of exp(-k * sdf), sum of core * weight, sum of intensity * weight

const vec3 LIGHT = normalize(vec3(-0.45, 0.5, 0.74));

void main() {
  // Undo the squash to get back to the unit sphere.
  vec3 p = vec3(vQ, 0.0);
  p = p * vScale.y + (vScale.x - vScale.y) * dot(p, vAxis) * vAxis;
  float r = length(p);
  float field = exp(-uK * (r - 1.0));
  if (field < 0.004) discard;

  // Analytic sphere shading: soft lambert, and a bright core nudged toward the light.
  vec3 n = vec3(p.xy, sqrt(max(0.0, 1.0 - min(r * r, 1.0))));
  float shade = 0.60 + 0.40 * dot(normalize(n + vec3(0.0, 0.0, 0.12)), LIGHT);
  float rc = length(p.xy - 0.16 * LIGHT.xy);
  float core = vGlow.y * exp(-rc * rc * 4.2) + 0.10 * vGlow.x * exp(-rc * rc * 1.6);

  // The weight saturates just inside the surface, so wherever bodies overlap
  // on screen the nearer one wins by its depth weight and keeps its own shape.
  float w = min(field, 1.5) * vGlow.z;
  oColor = vec4(vCol * shade * w, w);
  oField = vec4(field, core * w, vGlow.x * w, 0.0);
}
