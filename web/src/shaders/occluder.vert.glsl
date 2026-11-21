// A background-colored body inside each point cloud, so nearer spheres cover
// farther ones and the back half of a sphere doesn't show through.
attribute vec3 iPos;
attribute vec3 iVel;
attribute vec4 iSquash;
attribute vec4 iState;

uniform float uRadius, uEnergy, uKick;

#include deform

void main() {
  vec3 world = iPos + deform(position * 0.93, iSquash, iVel) * pulsedRadius(iState.x);
  gl_Position = projectionMatrix * viewMatrix * vec4(world, 1.0);
}
