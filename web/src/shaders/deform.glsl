// Shared by the dots and the occluder so they stay glued together.
// Squash along the main contact normal by 1 / (1 + 2 * pressure) and stretch
// mildly along velocity; both keep the volume.
vec3 deform(vec3 p, vec4 squash, vec3 vel) {
  float pr = min(squash.w, 0.6);
  float nl = length(squash.xyz);
  if (pr > 0.001 && nl > 0.5) {
    vec3 n = squash.xyz / nl;
    float q = 1.0 / (1.0 + 2.0 * pr);
    float side = inversesqrt(q);
    p = side * p + (q - side) * dot(p, n) * n;
  }
  float sp = length(vel);
  if (sp > 1e-4) {
    vec3 d = vel / sp;
    float st = 1.0 + min(sp * 3.0, 0.22);
    float side = inversesqrt(st);
    p = side * p + (st - side) * dot(p, d) * d;
  }
  return p;
}

float pulsedRadius(float E) {
  return uRadius * (1.0 + 0.15 * uEnergy * E + 0.25 * uKick * E);
}
