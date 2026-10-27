// Procedural see-through electronic brain with synapse slots, built with Three.js.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';
import { themed } from './themes.js';

export const REGION_COLORS = {
  logical: new THREE.Color('#38c8ff'),
  balanced: new THREE.Color('#c9d6e8'),
  creative: new THREE.Color('#ff6fb0'),
  executive: new THREE.Color(themed('#7fe3ff')),  // chrome, not data: follows the colour theme
};
// A synapse's colour comes from where it sits: left = logical, right = creative; the centre shows the task's own kind.
export function slotColor(side, region) {
  if (side < 0) return REGION_COLORS.logical;
  if (side > 0) return REGION_COLORS.creative;
  return REGION_COLORS[region] || REGION_COLORS.balanced;
}

const URGENT = new THREE.Color('#ef5a5a');
const SOON = new THREE.Color('#fab219');
const HEMI_CENTER_X = 0.34;

// ---------- noise (improved Perlin, seeded) ----------
const perm = new Uint8Array(512);
(() => {
  const p = Array.from({ length: 256 }, (_, i) => i);
  let s = 1337;
  for (let i = 255; i > 0; i--) {
    s = (s * 16807) % 2147483647;
    const j = s % (i + 1);
    [p[i], p[j]] = [p[j], p[i]];
  }
  for (let i = 0; i < 512; i++) perm[i] = p[i & 255];
})();
const fade = t => t * t * t * (t * (t * 6 - 15) + 10);
const lerp = (a, b, t) => a + (b - a) * t;
function grad(h, x, y, z) {
  const u = (h & 15) < 8 ? x : y;
  const v = (h & 15) < 4 ? y : ((h & 15) === 12 || (h & 15) === 14) ? x : z;
  return ((h & 1) ? -u : u) + ((h & 2) ? -v : v);
}
function noise3(x, y, z) {
  const X = Math.floor(x) & 255, Y = Math.floor(y) & 255, Z = Math.floor(z) & 255;
  x -= Math.floor(x); y -= Math.floor(y); z -= Math.floor(z);
  const u = fade(x), v = fade(y), w = fade(z);
  const A = perm[X] + Y, AA = perm[A] + Z, AB = perm[A + 1] + Z;
  const B = perm[X + 1] + Y, BA = perm[B] + Z, BB = perm[B + 1] + Z;
  return lerp(
    lerp(lerp(grad(perm[AA], x, y, z), grad(perm[BA], x - 1, y, z), u),
      lerp(grad(perm[AB], x, y - 1, z), grad(perm[BB], x - 1, y - 1, z), u), v),
    lerp(lerp(grad(perm[AA + 1], x, y, z - 1), grad(perm[BA + 1], x - 1, y, z - 1), u),
      lerp(grad(perm[AB + 1], x, y - 1, z - 1), grad(perm[BB + 1], x - 1, y - 1, z - 1), u), v), w);
}

// Gyri: winding plateaus separated by narrow sulci along the zero-set of domain-warped noise.
function folds(x, y, z) {
  const wx = noise3(x * 1.7 + 11, y * 1.7, z * 1.7) * 0.55;
  const wy = noise3(x * 1.7, y * 1.7 + 23, z * 1.7) * 0.55;
  const wz = noise3(x * 1.7, y * 1.7, z * 1.7 + 37) * 0.55;
  const n = noise3((x + wx) * 4.4, (y + wy) * 4.4, (z + wz) * 4.4);
  const n2 = noise3(x * 9.5 + 5, y * 9.5, z * 9.5);
  const a = Math.abs(n);
  const height = THREE.MathUtils.smoothstep(a, 0.0, 0.28) * 0.85 + 0.15 * THREE.MathUtils.smoothstep(Math.abs(n2), 0, 0.3);
  const sulcus = 1 - THREE.MathUtils.smoothstep(a, 0.0, 0.07);
  return { height, sulcus };
}

// Surface point of one hemisphere for a unit direction from its centre.
function hemisphereSurface(dir, side, withFolds = true) {
  const rx = 0.6, ry = 0.72, rz = 1.1;
  const z = dir.z;
  const p = new THREE.Vector3(dir.x * rx, dir.y * ry, dir.z * rz);
  p.y *= 1 - 0.16 * Math.max(0, z) ** 2 - 0.12 * Math.max(0, -z) ** 3;         // taper frontal & occipital poles
  p.x *= 1 - 0.14 * Math.max(0, z) ** 2 - 0.08 * Math.max(0, -z) ** 2;
  if (p.y < -0.2) p.y = -0.2 + (p.y + 0.2) * 0.5;                               // flatter base
  const lateral = Math.abs(dir.x);
  const temporal = Math.exp(-((z - 0.15) ** 2) / 0.07) * Math.max(0, -dir.y) * lateral;
  p.y -= temporal * 0.28;                                                      // temporal lobe
  p.x += side * temporal * 0.05;
  let sulcus = 0;
  if (withFolds) {
    // Sylvian (lateral) fissure: runs from the front-bottom back and up, separating the temporal lobe.
    const sylv = Math.abs(dir.y - (-0.08 - 0.42 * (dir.z - 0.05))) ;
    const sylvW = Math.exp(-((sylv / 0.05) ** 2)) * THREE.MathUtils.smoothstep(lateral, 0.35, 0.7) * THREE.MathUtils.smoothstep(dir.z, -0.55, -0.2) * (1 - THREE.MathUtils.smoothstep(dir.z, 0.55, 0.7));
    // Central sulcus: from the crown down toward the Sylvian fissure.
    const cent = Math.abs(dir.z - (-0.02 + 0.22 * dir.y));
    const centW = Math.exp(-((cent / 0.035) ** 2)) * THREE.MathUtils.smoothstep(dir.y, -0.05, 0.25);
    const f = folds(p.x + side * 3, p.y, p.z);
    p.multiplyScalar(1 + 0.075 * (f.height - 0.7) - 0.09 * sylvW - 0.05 * centW);
    sulcus = Math.min(1, f.sulcus * 0.85 + sylvW + centW * 0.9);
  }
  p.x += side * HEMI_CENTER_X;
  p.y += 0.08;
  if (side * p.x < 0.02) p.x = side * 0.02;                                     // medial wall (longitudinal fissure)
  return { p, sulcus };
}

// ---------- shaders ----------
const shellVertex = /* glsl */`
  attribute float aFold;
  varying vec3 vN; varying vec3 vView; varying float vFold; varying vec3 vPos;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vN = normalize(normalMatrix * normal);
    vView = normalize(-mv.xyz);
    vFold = aFold; vPos = position;
    gl_Position = projectionMatrix * mv;
  }`;
const shellFragment = /* glsl */`
  uniform float uTime; uniform vec3 uDeep; uniform vec3 uGlow; uniform float uOpacity;
  varying vec3 vN; varying vec3 vView; varying float vFold; varying vec3 vPos;
  void main() {
    float fres = pow(1.0 - abs(dot(vN, vView)), 2.0);
    float scan = 0.5 + 0.5 * sin(vPos.y * 60.0 - uTime * 1.6);
    float band = 1.0 - smoothstep(0.0, 0.07, abs(fract(vPos.z * 0.35 - uTime * 0.08) - 0.5));
    vec3 col = mix(uDeep, uGlow, clamp(fres + vFold * 0.7, 0.0, 1.0));
    float a = 0.035 + fres * 0.5 + vFold * 0.22 * (0.7 + 0.3 * scan) + band * 0.08;
    gl_FragColor = vec4(col * (0.8 + band * 0.6), a * uOpacity);
  }`;
const pointsVertex = /* glsl */`
  attribute float aSeed; uniform float uTime; uniform float uSize;
  varying float vTw;
  void main() {
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vTw = 0.55 + 0.45 * sin(uTime * (0.8 + aSeed * 2.0) + aSeed * 40.0);
    gl_PointSize = uSize * (0.6 + aSeed * 0.8) * (3.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }`;
const pointsFragment = /* glsl */`
  uniform vec3 uColor; uniform float uOpacity; varying float vTw;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    float a = smoothstep(0.5, 0.0, d);
    gl_FragColor = vec4(uColor, a * vTw * uOpacity);
  }`;

function shellMaterial(uniforms, opacity = 1) {
  return new THREE.ShaderMaterial({
    vertexShader: shellVertex, fragmentShader: shellFragment,
    uniforms: { ...uniforms, uOpacity: { value: opacity } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  });
}

function glowTexture(inner = 'rgba(255,255,255,1)', stops = [[0, 1], [0.2, 0.6], [0.5, 0.12], [1, 0]]) {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  for (const [o, a] of stops) grd.addColorStop(o, inner.replace(/[\d.]+\)$/, `${a})`));
  g.fillStyle = grd;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

function ringTexture(dashed) {
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  g.strokeStyle = 'white';
  g.lineWidth = 6;
  if (dashed) g.setLineDash([14, 10]);
  g.beginPath();
  g.arc(64, 64, 52, 0, Math.PI * 2);
  g.stroke();
  return new THREE.CanvasTexture(c);
}

// ---------- Brain ----------
export class Brain {
  // options: fps [busy, idle] caps, maxPixelRatio, pixelBudget (max rendered pixels; big screens render at a lower
  // internal resolution and are scaled up, which a soft glow hides well)
  constructor(container, labelLayer, handlers = {}, options = {}) {
    this.container = container;
    this.fps = options.fps || [60, 30];
    this.maxPixelRatio = options.maxPixelRatio ?? 1.5;
    this.pixelBudget = options.pixelBudget ?? 2.2e6;
    this.labelLayer = labelLayer;
    this.handlers = handlers;       // onSelect(taskId), onEmptySlot(index, event), onSynapseDragStart(taskId, event)
    this.synapses = [];             // per slot: {index, group, core, halo, ring, urgency, hit, label, task, normal}
    this.links = [];
    this.highlighted = null;
    this.hovered = null;
    this.lastInteraction = 0;
    this.swayPhase = 0;
    this.clock = new THREE.Clock();
    this.themedColors = [];         // [THREE.Color, blue design hex] pairs re-tinted by setTheme()
    REGION_COLORS.executive.set(themed('#7fe3ff'));
    this.pauses = new Set();        // reasons the brain is hidden (dashboard, pop-up); no frames while any are set
    this.lastFrame = 0;
    this.tmp = { wp: new THREE.Vector3(), n: new THREE.Vector3(), v: new THREE.Vector3() };

    const w = container.clientWidth, h = container.clientHeight;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(this.pixelRatioFor(w, h));
    this.renderer.setSize(w, h);
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, w / h, 0.1, 50);
    this.homePosition = new THREE.Vector3(-2.75, 3.15, 1.55);
    this.camera.position.copy(this.homePosition);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, -0.05, 0.05);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 2.2;
    this.controls.maxDistance = 7;
    this.controls.enablePan = false;
    this.controls.addEventListener('start', () => { this.lastInteraction = performance.now(); this.interacting = true; });
    this.controls.addEventListener('end', () => { this.lastInteraction = performance.now(); this.interacting = false; });

    this.uniforms = {
      uTime: { value: 0 },
      uDeep: { value: this.tc('#0a2a6b') },
      uGlow: { value: this.tc('#5fd8ff') },
    };
    this.glowTex = glowTexture();
    this.ringTex = ringTexture(false);
    this.dashTex = ringTexture(true);

    this.root = new THREE.Group();
    this.scene.add(this.root);
    this.buildBrain();
    this.buildPaths();

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.bindPointer();
    new ResizeObserver(() => this.resize()).observe(container);
    this.renderer.setAnimationLoop(now => this.tick(now));
  }

  // this.fps[0] (60) while the user is orbiting, hovering or dragging; this.fps[1] (30) for the idle sway; nothing while hidden.
  // (rAF runs at the display's refresh rate, which can be 120 Hz+, so both rates are capped.)
  tick(now) {
    if (this.pauses.size) return;
    const busy = this.interacting || this.hovered || this.highlighted != null || now - this.lastInteraction < 1200
      || this.synapses.some(s => s.flash && now - s.flash < 1500);
    if (now - this.lastFrame < 1000 / this.fps[busy ? 0 : 1] - 4) return; // slack for rAF jitter
    this.lastFrame = now;
    this.frame();
  }

  // Colour of a blue design hex in the current theme; remembered so setTheme() can re-tint it in place.
  tc(hex, color = new THREE.Color()) {
    color.set(themed(hex));
    this.themedColors.push([color, hex]);
    return color;
  }

  setTheme() {
    for (const [color, hex] of this.themedColors) color.set(themed(hex));
    REGION_COLORS.executive.set(themed('#7fe3ff'));
    if (this.lastTasks) this.setTasks(this.lastTasks, this.lastLinks, this.lastDeps); // empty executive slot + axons
    if (this.pauses.size) this.renderer.render(this.scene, this.camera);
  }

  // Freeze orbiting and synapse interaction (the wallpaper does this while a Memory window is open, because the
  // wallpaper host keeps forwarding mouse movement even when that window has focus).
  setLocked(locked) {
    if (!!this.locked === locked) return;
    this.locked = locked;
    this.controls.enabled = !locked;
    if (!locked) return;
    this.cancelOrbit();
    if (this.hovered) {
      this.hovered = null;
      for (const s of this.synapses) s.label.classList.remove('hover');
    }
  }

  // End an orbit drag whose pointerup never arrived (e.g. the wallpaper host stopped forwarding mid-drag), so plain
  // mouse movement doesn't keep rotating the brain. Mirrors OrbitControls' own pointer-up cleanup.
  cancelOrbit() {
    const c = this.controls;
    if (!c._pointers?.length) return;
    for (const id of c._pointers) { try { c.domElement.releasePointerCapture(id); } catch { /* already released */ } }
    c._pointers.length = 0;
    c.domElement.removeEventListener('pointermove', c._onPointerMove);
    c.domElement.removeEventListener('pointerup', c._onPointerUp);
    c.state = -1; // OrbitControls' STATE.NONE
    c.dispatchEvent({ type: 'end' });
  }

  setPaused(reason, paused) {
    const was = this.pauses.size > 0;
    if (paused) this.pauses.add(reason); else this.pauses.delete(reason);
    if (was && !this.pauses.size) this.clock.getDelta(); // don't jump the animations forward
  }

  // ----- construction -----
  buildBrain() {
    this.shells = [];
    this.surfaceSamples = [];
    for (const side of [-1, 1]) {
      const geo = new THREE.SphereGeometry(1, 260, 200);
      const pos = geo.attributes.position;
      const fold = new Float32Array(pos.count);
      const v = new THREE.Vector3();
      for (let i = 0; i < pos.count; i++) {
        v.fromBufferAttribute(pos, i).normalize();
        const { p, sulcus } = hemisphereSurface(v, side);
        pos.setXYZ(i, p.x, p.y, p.z);
        fold[i] = sulcus;
        if (i % 4 === 0 && sulcus < 0.15) this.surfaceSamples.push(p.clone());
      }
      geo.setAttribute('aFold', new THREE.BufferAttribute(fold, 1));
      geo.computeVertexNormals();
      const mesh = new THREE.Mesh(geo, shellMaterial(this.uniforms));
      this.root.add(mesh);
      this.shells.push(mesh);
    }

    // cerebellum with folia
    const cg = new THREE.SphereGeometry(1, 120, 80);
    const cp = cg.attributes.position;
    const cf = new Float32Array(cp.count);
    const v = new THREE.Vector3();
    for (let i = 0; i < cp.count; i++) {
      v.fromBufferAttribute(cp, i);
      const stripe = Math.sin(v.y * 34 + noise3(v.x * 3, v.y * 3, v.z * 3) * 2);
      const r = 1 + 0.035 * stripe;
      cp.setXYZ(i, v.x * 0.52 * r, v.y * 0.25 * r - 0.42, v.z * 0.33 * r - 0.74);
      cf[i] = Math.max(0, -stripe) * 0.7;
    }
    cg.setAttribute('aFold', new THREE.BufferAttribute(cf, 1));
    cg.computeVertexNormals();
    const cerebellum = new THREE.Mesh(cg, shellMaterial(this.uniforms, 0.85));
    this.root.add(cerebellum);
    this.shells.push(cerebellum);

    // brainstem
    const sg = new THREE.CylinderGeometry(0.1, 0.075, 0.7, 40, 20, true);
    sg.setAttribute('aFold', new THREE.BufferAttribute(new Float32Array(sg.attributes.position.count), 1));
    const stem = new THREE.Mesh(sg, shellMaterial(this.uniforms, 0.8));
    stem.position.set(0, -0.62, -0.36);
    stem.rotation.x = -0.32;
    this.root.add(stem);

    // neural point cloud: surface + sparse interior
    const pts = [], seeds = [];
    for (const s of this.surfaceSamples) { pts.push(s.x, s.y, s.z); seeds.push(Math.random()); }
    for (let i = 0; i < 700; i++) {
      const side = Math.random() < 0.5 ? -1 : 1;
      const d = new THREE.Vector3(Math.random() * 2 - 1, Math.random() * 2 - 1, Math.random() * 2 - 1).normalize();
      const { p } = hemisphereSurface(d, side, false);
      const k = Math.cbrt(Math.random()) * 0.92;
      const c = new THREE.Vector3(side * HEMI_CENTER_X, 0.08, 0);
      p.sub(c).multiplyScalar(k).add(c);
      pts.push(p.x, p.y, p.z);
      seeds.push(Math.random() * 0.6);
    }
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    pg.setAttribute('aSeed', new THREE.Float32BufferAttribute(seeds, 1));
    this.points = new THREE.Points(pg, new THREE.ShaderMaterial({
      vertexShader: pointsVertex, fragmentShader: pointsFragment,
      uniforms: { uTime: this.uniforms.uTime, uSize: { value: 5 }, uColor: { value: this.tc('#7fe3ff') }, uOpacity: { value: 0.5 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }));
    this.root.add(this.points);

    // soft core glow
    const core = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glowTex, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false }));
    this.tc('#1d6bff', core.material.color);
    core.scale.set(3.4, 3.0, 1);
    core.position.set(0, 0.05, 0);
    this.root.add(core);
  }

  buildPaths() {
    // background neural pathways with travelling impulses
    this.pathGroup = new THREE.Group();
    this.root.add(this.pathGroup);
    this.pulses = [];
    const mat = new THREE.LineBasicMaterial({ transparent: true, opacity: 0.13, blending: THREE.AdditiveBlending, depthWrite: false });
    this.tc('#3aa8ff', mat.color);
    const samples = this.surfaceSamples;
    for (let i = 0; i < 46; i++) {
      const a = samples[(Math.random() * samples.length) | 0];
      const b = samples[(Math.random() * samples.length) | 0];
      if (a.distanceTo(b) < 0.5) { i--; continue; }
      const mid = a.clone().add(b).multiplyScalar(0.5);
      mid.lerp(new THREE.Vector3(Math.sign(mid.x) * HEMI_CENTER_X, 0.05, 0), 0.55);
      const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
      this.pathGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(curve.getPoints(32)), mat));
      if (i % 2 === 0) this.tc('#8fe9ff', this.addPulse(curve, '#8fe9ff', 0.045, this.pathGroup).sprite.material.color);
    }
  }

  addPulse(curve, baseHex, size, parent) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glowTex, color: themed(baseHex), transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
    s.scale.setScalar(size);
    parent.add(s);
    const pulse = { sprite: s, curve, t: Math.random(), speed: 0.12 + Math.random() * 0.25 };
    this.pulses.push(pulse);
    return pulse;
  }

  // ----- slots -----
  slotPosition(slot) {
    const c = this.customPositions?.[slot.index];
    if (c) return { pos: new THREE.Vector3(c[0], c[1], c[2]), normal: new THREE.Vector3(c[3], c[4], c[5]).normalize() };
    if (slot.side === 0) {
      const { p } = hemisphereSurface(new THREE.Vector3(0.05, 0.62, 0.78).normalize(), 1);
      return { pos: new THREE.Vector3(0, p.y + 0.06, p.z), normal: new THREE.Vector3(0, 0.6, 0.8).normalize() };
    }
    const z = THREE.MathUtils.lerp(0.78, -0.72, slot.frontness);
    const row = Math.round(slot.frontness * 10);
    const up = 0.85 + (row % 2 ? 0.1 : -0.05);
    const dir = new THREE.Vector3(slot.side * 0.55, up, z).normalize();
    const { p } = hemisphereSurface(dir, slot.side);
    const normal = p.clone().sub(new THREE.Vector3(slot.side * HEMI_CENTER_X, 0.08, 0)).normalize();
    return { pos: p.add(normal.clone().multiplyScalar(0.035)), normal };
  }

  setSlots(slots, customPositions = {}) {
    this.customPositions = customPositions;
    for (const s of this.synapses) { this.root.remove(s.group); s.label.remove(); }
    this.synapses = [];
    for (const slot of slots) {
      const { pos, normal } = this.slotPosition(slot);
      const color = REGION_COLORS[slot.region] || REGION_COLORS.balanced;
      const group = new THREE.Group();
      group.position.copy(pos);
      const core = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending, depthWrite: false }));
      core.scale.setScalar(0.03);
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.glowTex, color, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false }));
      halo.scale.setScalar(0.22);
      const ring = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.dashTex, color, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
      ring.scale.setScalar(0.13);
      const urgency = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.ringTex, color: SOON, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
      urgency.scale.setScalar(0.2);
      const hit = new THREE.Mesh(new THREE.SphereGeometry(0.09, 8, 6), new THREE.MeshBasicMaterial({ visible: false }));
      const dendrites = new THREE.Group();
      group.add(core, halo, ring, urgency, hit, dendrites);
      this.root.add(group);
      const label = document.createElement('div');
      label.className = 'syn-label empty';
      label.innerHTML = `<span class="syn-idx">${slot.index + 1}</span><span class="syn-title">Empty synapse</span>`;
      this.labelLayer.appendChild(label);
      const syn = { index: slot.index, slot, group, core, halo, ring, urgency, hit, dendrites, label, normal, baseColor: color, task: null, growth: -1 };
      hit.userData.syn = syn;
      this.synapses.push(syn);
    }
  }

  setTasks(tasks, links = [], deps = []) {
    this.lastTasks = tasks;
    this.lastLinks = links;
    this.lastDeps = deps;
    const byId = new Map(tasks.map(t => [t.id, t]));
    const bySlot = new Map(tasks.filter(t => t.status === 'active' && t.slot_index != null).map(t => [t.slot_index, t]));
    const today = new Date().toISOString().slice(0, 10);
    const soon = new Date(Date.now() + 2 * 864e5).toISOString().slice(0, 10);
    for (const syn of this.synapses) {
      const t = bySlot.get(syn.index) || null;
      syn.task = t;
      const color = t ? slotColor(syn.slot.side, t.region) : syn.baseColor;
      syn.core.material.color.copy(color);
      syn.halo.material.color.copy(color);
      syn.ring.material.color.copy(color);
      syn.ring.material.map = t ? this.ringTex : this.dashTex;
      syn.urgentColor = null;
      if (t?.due_at) {
        if (t.due_at.slice(0, 10) < today) syn.urgentColor = URGENT;
        else if (t.due_at.slice(0, 10) <= soon) syn.urgentColor = SOON;
      }
      if (t?.at_risk && !syn.urgentColor) syn.urgentColor = SOON;
      if (syn.urgentColor) syn.urgency.material.color.copy(syn.urgentColor);
      const g = t ? t.growth : -1;
      if (g !== syn.growth) { syn.growth = g; this.grow(syn); }
      syn.label.classList.toggle('empty', !t);
      syn.label.classList.toggle('urgent', syn.urgentColor === URGENT);
      const title = t ? t.title : 'Empty synapse';
      const meta = t ? [t.due_at ? `due ${t.due_at.slice(5, 10)}` : null, t.checklist_total ? `${t.checklist_done}/${t.checklist_total}` : null].filter(Boolean).join(' · ') : 'drop a task';
      syn.label.innerHTML = `<span class="syn-idx">${syn.index + 1}</span><span class="syn-title">${escapeHtml(title)}</span><span class="syn-meta">${escapeHtml(meta)}</span>${t?.seq ? stepPill(t, byId) : ''}`;
    }
    this.setLinks(links, deps);
  }

  // Dendrites grow with the task: more notes, steps, files and links -> longer, more branches.
  grow(syn) {
    syn.dendrites.clear();
    if (!syn.task) return;
    const g = Math.max(0, syn.growth);
    const count = 3 + Math.round(g * 7);
    const mat = new THREE.LineBasicMaterial({ color: syn.core.material.color, transparent: true, opacity: 0.35 + g * 0.3, blending: THREE.AdditiveBlending, depthWrite: false });
    const n = syn.normal;
    const t1 = new THREE.Vector3().crossVectors(n, new THREE.Vector3(0, 1, 0.3)).normalize();
    const t2 = new THREE.Vector3().crossVectors(n, t1).normalize();
    let seed = syn.task.id * 9301;
    const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
    for (let i = 0; i < count; i++) {
      const ang = (i / count) * Math.PI * 2 + rnd() * 0.5;
      const len = 0.07 + g * 0.22 * (0.6 + rnd() * 0.6);
      const pts = [new THREE.Vector3()];
      let dir = t1.clone().multiplyScalar(Math.cos(ang)).add(t2.clone().multiplyScalar(Math.sin(ang)));
      const segs = 5;
      for (let s = 1; s <= segs; s++) {
        dir = dir.add(new THREE.Vector3(rnd() - 0.5, rnd() - 0.5, rnd() - 0.5).multiplyScalar(0.5)).normalize();
        pts.push(pts[s - 1].clone().add(dir.clone().multiplyScalar(len / segs)).add(n.clone().multiplyScalar(-0.006 * s)));
        if (s === 3 && g > 0.35) {   // fork
          const fork = [pts[s].clone(), pts[s].clone().add(dir.clone().applyAxisAngle(n, 0.8).multiplyScalar(len * 0.35))];
          syn.dendrites.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(fork), mat));
        }
      }
      syn.dendrites.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), mat));
    }
  }

  // Axons between tasks that both hold synapses: thin glowing ones for related tasks, and thicker ones for
  // dependencies, with impulses flowing from the step that comes first toward the one it unlocks.
  setLinks(links, deps = []) {
    for (const l of this.links) {
      this.root.remove(l.mesh, l.pulseGroup);
      l.mesh.geometry.dispose();
      l.mesh.material.dispose();
      l.pulseGroup.children.forEach(s => s.material.dispose());
    }
    this.pulses = this.pulses.filter(p => !p.axon);
    this.links = [];
    const byTask = new Map(this.synapses.filter(s => s.task).map(s => [s.task.id, s]));
    const key = (a, b) => (a < b ? `${a}-${b}` : `${b}-${a}`);
    const depKeys = new Set(deps.map(d => key(d.task_id, d.depends_on_id)));
    const axon = (from, to, o) => {
      const pa = from.group.position, pb = to.group.position;
      const mid = pa.clone().add(pb).multiplyScalar(0.5);
      mid.add(mid.clone().sub(new THREE.Vector3(0, 0.05, 0)).normalize().multiplyScalar(0.18 + pa.distanceTo(pb) * 0.15));
      const curve = new THREE.QuadraticBezierCurve3(pa.clone(), mid, pb.clone());
      const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, o.radius, 6, false),
        new THREE.MeshBasicMaterial({ color: o.color, transparent: true, opacity: o.opacity, blending: THREE.AdditiveBlending, depthWrite: false }));
      const pulseGroup = new THREE.Group();
      this.root.add(mesh, pulseGroup);
      for (let i = 0; i < o.pulses; i++) {
        const p = this.addPulse(curve, o.pulseHex, o.pulseSize, pulseGroup);
        Object.assign(p, { axon: true, speed: o.speed, t: i / o.pulses });
      }
      this.links.push({ mesh, pulseGroup });
    };
    for (const link of links) {
      const a = byTask.get(link.a_id), b = byTask.get(link.b_id);
      if (!a || !b || depKeys.has(key(link.a_id, link.b_id))) continue;
      axon(a, b, { radius: 0.0035, color: themed('#5fd8ff'), opacity: 0.28 + 0.4 * link.strength, pulses: 1, pulseHex: '#e8fbff', pulseSize: 0.06, speed: 0.3 });
    }
    for (const d of deps) {
      const first = byTask.get(d.depends_on_id), next = byTask.get(d.task_id);
      if (!first || !next) continue;
      axon(first, next, { radius: 0.008, color: themed('#e8fbff'), opacity: 0.6, pulses: 3, pulseHex: '#ffffff', pulseSize: 0.09, speed: 0.45 });
    }
  }

  // ----- interaction -----
  bindPointer() {
    const el = this.renderer.domElement;
    el.addEventListener('pointermove', e => {
      if (e.buttons === 0) this.cancelOrbit();
      if (this.locked) return;
      this.lastInteraction = performance.now();
      const syn = this.synapseAtEvent(e);
      if (syn !== this.hovered) {
        this.hovered = syn;
        el.style.cursor = syn ? 'pointer' : 'grab';
        for (const s of this.synapses) s.label.classList.toggle('hover', s === syn);
      }
    });
    el.addEventListener('pointerleave', () => {
      if (!this.hovered) return;
      this.hovered = null;
      for (const s of this.synapses) s.label.classList.remove('hover');
    });
    el.addEventListener('pointerdown', e => {
      if (this.locked) return;
      const syn = this.synapseAtEvent(e);
      if (!syn) return;
      if (this.arranging) { this.startArrangeDrag(syn, e); return; }
      this.controls.enabled = false;
      const start = { x: e.clientX, y: e.clientY };
      let dragging = false;
      const move = ev => {
        if (!dragging && syn.task && Math.hypot(ev.clientX - start.x, ev.clientY - start.y) > 8) {
          dragging = true;
          this.handlers.onSynapseDragStart?.(syn.task, ev);
        }
      };
      const up = ev => {
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        this.controls.enabled = !this.locked;
        if (dragging) return;
        if (syn.task) this.handlers.onSelect?.(syn.task.id, ev);
        else this.handlers.onEmptySlot?.(syn.index, ev);
      };
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    });
  }

  // ----- Arrange mode: drag synapses to new spots on their hemisphere's surface -----
  setArrange(on) {
    this.arranging = on;
    this.labelLayer.classList.toggle('arranging', on);
    if (on) { this.swayPhase = 0; this.root.rotation.y = 0; }
  }

  startArrangeDrag(syn, e) {
    this.controls.enabled = false;
    const el = this.renderer.domElement;
    try { el.setPointerCapture(e.pointerId); } catch { /* not a live pointer (synthetic event) */ }
    // a synapse stays on its own hemisphere (so its logical/creative side never flips); the centre slot can go anywhere
    const targets = syn.slot.side < 0 ? [this.shells[0]] : syn.slot.side > 0 ? [this.shells[1]] : [this.shells[0], this.shells[1]];
    let pending = null, moved = false;
    const apply = () => {
      const ev = pending;
      pending = null;
      this.raycaster.setFromCamera(this.ndc(ev.clientX, ev.clientY), this.camera);
      const hit = this.raycaster.intersectObjects(targets, false)[0];
      if (!hit) return;
      const p = this.root.worldToLocal(hit.point.clone());
      const n = hit.face.normal.clone().normalize();
      syn.normal.copy(n);
      syn.group.position.copy(p.add(n.clone().multiplyScalar(0.035)));
      moved = true;
      this.lastInteraction = performance.now();
    };
    const move = ev => { if (!pending) requestAnimationFrame(apply); pending = ev; };
    const up = () => {
      el.removeEventListener('pointermove', move);
      el.removeEventListener('pointerup', up);
      el.removeEventListener('pointercancel', up);
      this.controls.enabled = !this.locked;
      if (!moved) return;
      this.grow(syn);
      this.setLinks(this.lastLinks || [], this.lastDeps || []);
      const p = syn.group.position, n = syn.normal;
      this.handlers.onSynapseMoved?.(syn.index, [p.x, p.y, p.z, n.x, n.y, n.z].map(v => Math.round(v * 1e4) / 1e4));
    };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointercancel', up);
  }

  // Keep picking correct even when no frame has rendered yet (e.g. a background tab).
  syncMatrices() {
    this.scene.updateMatrixWorld();
    this.camera.updateMatrixWorld();
  }

  ndc(clientX, clientY) {
    this.syncMatrices();
    const r = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    return this.pointer;
  }

  synapseAtEvent(e) {
    this.raycaster.setFromCamera(this.ndc(e.clientX, e.clientY), this.camera);
    const hits = this.raycaster.intersectObjects(this.synapses.map(s => s.hit), false);
    return hits.length ? hits[0].object.userData.syn : null;
  }

  screenPos(syn) {
    this.syncMatrices();
    const r = this.renderer.domElement.getBoundingClientRect();
    const v = syn.group.getWorldPosition(new THREE.Vector3()).project(this.camera);
    return { x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
  }

  overBrain(clientX, clientY) {
    this.raycaster.setFromCamera(this.ndc(clientX, clientY), this.camera);
    return this.raycaster.intersectObjects(this.shells, false).length > 0;
  }

  // For drag-and-drop: nearest synapse under the cursor, or the nearest free one if dropped on the brain.
  slotAt(clientX, clientY, excludeTaskId = null) {
    let best = null, bestD = Infinity;
    for (const s of this.synapses) {
      const p = this.screenPos(s);
      const d = Math.hypot(p.x - clientX, p.y - clientY);
      if (d < bestD) { bestD = d; best = s; }
    }
    if (best && bestD < 46) return best.index;
    if (!this.overBrain(clientX, clientY)) return null;
    let free = null, freeD = Infinity;
    for (const s of this.synapses) {
      if (s.task && s.task.id !== excludeTaskId) continue;
      const p = this.screenPos(s);
      const d = Math.hypot(p.x - clientX, p.y - clientY);
      if (d < freeD) { freeD = d; free = s; }
    }
    return free ? free.index : best?.index ?? null;
  }

  highlight(index) {
    this.highlighted = index;
    for (const s of this.synapses) s.label.classList.toggle('drop', s.index === index);
  }

  occupant(index) {
    return this.synapses.find(s => s.index === index)?.task || null;
  }

  focusTask(taskId) {
    const syn = this.synapses.find(s => s.task?.id === taskId);
    if (!syn) return;
    syn.flash = performance.now();
  }

  resetView() {
    this.camera.position.copy(this.homePosition);
    this.controls.target.set(0, -0.05, 0.05);
    this.root.rotation.set(0, 0, 0);
    this.swayPhase = 0;
  }

  // GPU cost is mostly pixels filled: cap the ratio for HiDPI, then shrink further if the canvas is huge.
  pixelRatioFor(w, h) {
    const pr = Math.min(window.devicePixelRatio, this.maxPixelRatio);
    return w * h * pr * pr > this.pixelBudget ? Math.sqrt(this.pixelBudget / (w * h)) : pr;
  }

  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(this.pixelRatioFor(w, h));
    this.renderer.setSize(w, h);
    if (this.pauses.size) this.renderer.render(this.scene, this.camera); // resizing clears the canvas
  }

  // ----- render loop -----
  frame() {
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const t = this.clock.elapsedTime;
    this.uniforms.uTime.value = t;

    // idle sway: the brain gently turns side to side, frozen while the user interacts
    const idle = !this.interacting && !this.arranging && performance.now() - this.lastInteraction > 5000;
    if (idle) this.swayPhase += dt * 0.18;
    this.root.rotation.y += (Math.sin(this.swayPhase) * 0.3 - this.root.rotation.y) * Math.min(1, dt * 1.5);

    for (const p of this.pulses) {
      p.t = (p.t + dt * p.speed) % 1;
      p.sprite.position.copy(p.curve.getPoint(p.t));
      p.sprite.material.opacity = Math.sin(p.t * Math.PI);
    }

    const camPos = this.camera.position;
    const { wp, n, v } = this.tmp;
    const r = this.renderer.domElement.getBoundingClientRect();
    const layerRect = this.labelLayer.getBoundingClientRect();
    for (const s of this.synapses) {
      const filled = !!s.task;
      const hot = s === this.hovered || s.index === this.highlighted;
      const beat = 0.5 + 0.5 * Math.sin(t * (filled ? 3.2 : 1.4) + s.index);
      const size = filled ? 0.032 + 0.03 * Math.max(0, s.growth) : 0.022;
      const flash = s.flash ? Math.max(0, 1 - (performance.now() - s.flash) / 1500) : 0;
      s.core.scale.setScalar(size * (1 + 0.15 * beat + (hot ? 0.45 : 0) + flash));
      s.core.material.opacity = filled ? 0.85 : 0.25 + 0.15 * beat;
      s.halo.scale.setScalar((filled ? 0.26 + 0.18 * Math.max(0, s.growth) : 0.14) * (1 + 0.2 * beat + (hot ? 0.5 : 0) + flash * 2));
      s.halo.material.opacity = filled ? 0.55 + 0.25 * beat : 0.22;
      s.ring.material.opacity = filled ? 0.35 : (hot ? 0.95 : 0.45 + 0.25 * beat);
      s.ring.material.rotation = t * (filled ? 0.2 : -0.6);
      s.ring.scale.setScalar(filled ? 0.1 + 0.05 * Math.max(0, s.growth) : (hot ? 0.2 : 0.12));
      s.urgency.material.opacity = s.urgentColor ? 0.5 + 0.45 * Math.sin(t * 5) : 0;
      s.urgency.scale.setScalar(0.16 + 0.04 * Math.sin(t * 5));

      // label placement + fade when the synapse faces away
      s.group.getWorldPosition(wp);
      n.copy(s.normal).applyQuaternion(this.root.quaternion);
      const facing = n.dot(v.copy(camPos).sub(wp).normalize());
      v.copy(wp).project(this.camera);
      const x = r.left - layerRect.left + (v.x + 1) / 2 * r.width;
      const y = r.top - layerRect.top + (1 - v.y) / 2 * r.height;
      const flip = x > layerRect.width - 230;
      s.label.classList.toggle('left', flip);
      s.label.style.transform = flip ? `translate(calc(${x.toFixed(1)}px - 100%), ${y.toFixed(1)}px)` : `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
      s.label.style.opacity = hot ? 1 : Math.max(0.12, Math.min(1, 0.35 + facing * 1.2)).toFixed(2);
      s.label.style.zIndex = String(Math.round(100 + facing * 50 + (hot ? 100 : 0)));
    }

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

// "Step 2 of 3 → Launch site" on a synapse label: where this task sits in its dependency chain.
function stepPill(t, byId) {
  const { seq } = t;
  const goal = byId.get(seq.goal);
  const isGoal = t.id === seq.goal;
  const text = isGoal ? `Final step ${seq.step} of ${seq.of}` : `Step ${seq.step} of ${seq.of}${goal ? ` → ${goal.title}` : ''}`;
  const wait = seq.waiting ? ` · waits on ${seq.waiting}` : '';
  return `<span class="syn-step ${seq.waiting ? 'waiting' : ''}" title="${escapeHtml(text + wait)}">${escapeHtml(text)}${escapeHtml(wait)}</span>`;
}

export function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
