// Absorbance accumulation with decay: where a blob has been, a paler smear of
// pigment stays and slowly fades. The smear is also carried a little away from
// the glass, i.e. toward the vanishing point at the center of the screen.
precision highp float;

in vec2 vUv;
uniform sampler2D tPigment, tPrev;
uniform float uDecay, uAdvect;

layout(location = 0) out vec4 oTrail;

void main() {
  vec3 cur = texture(tPigment, vUv).rgb;
  vec3 prev = texture(tPrev, 0.5 + (vUv - 0.5) * (1.0 + uAdvect)).rgb * uDecay;
  oTrail = vec4(max(cur * 0.5, prev), 1.0);
}
