// A globe surface that is lit by the real sun: Blue Marble where it is day,
// Black Marble city lights where it is night, blended across the terminator.
//
// This is a SHADER, a small program that runs on the graphics card once per pixel.
// It is written in GLSL, a C-like language, and handed to three.js as strings.
// The idea is simple even if the syntax is not:
//
//     brightness = dot(surface normal, direction to the sun)
//
// The dot product of two unit vectors is the cosine of the angle between them:
// +1 where the sun is overhead, 0 on the terminator, negative on the night side.
// smoothstep turns that into a 0-to-1 blend with a soft twilight edge.

import * as THREE from "three";

const vertexShader = /* glsl */ `
  varying vec3 vNormal;
  varying vec2 vUv;
  void main() {
    // modelMatrix, not normalMatrix: we want the normal in WORLD space, the same
    // space the sun vector is given in. globe.gl moves the camera, never the globe,
    // so world space stays fixed to the earth.
    vNormal = normalize(mat3(modelMatrix) * normal);
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  uniform sampler2D dayTexture;
  uniform sampler2D nightTexture;
  uniform vec3 sunDirection;
  varying vec3 vNormal;
  varying vec2 vUv;
  void main() {
    float light = dot(normalize(vNormal), normalize(sunDirection));
    // Civil twilight is about 6 degrees below the horizon: sin(6°) ≈ 0.1.
    float blend = smoothstep(-0.1, 0.1, light);
    vec4 day = texture2D(dayTexture, vUv);
    vec4 night = texture2D(nightTexture, vUv);
    gl_FragColor = mix(night, day, blend);
  }
`;

export function makeDayNightMaterial(dayUrl: string, nightUrl: string) {
  const loader = new THREE.TextureLoader();
  const material = new THREE.ShaderMaterial({
    uniforms: {
      dayTexture: { value: loader.load(dayUrl) },
      nightTexture: { value: loader.load(nightUrl) },
      sunDirection: { value: new THREE.Vector3(1, 0, 0) },
    },
    vertexShader,
    fragmentShader,
  });
  // No colour-space conversion on the textures: a raw ShaderMaterial also skips the
  // conversion on the way OUT, so leaving both alone passes the image's pixels
  // through untouched and the lit side matches the plain basemaps exactly.
  return material;
}

export function setSun(material: THREE.ShaderMaterial, [x, y, z]: [number, number, number]) {
  material.uniforms.sunDirection.value.set(x, y, z);
}
