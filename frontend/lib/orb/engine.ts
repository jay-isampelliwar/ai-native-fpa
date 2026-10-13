/**
 * The maths behind the thinking orbs: nine dotted animations, each a pure function of time.
 *
 * Ported from thinking-orbs 0.3.2 (MIT © 2026 Jakub Antalik, https://libraries.dev/orbs) so the
 * app carries no extra package. The cursor "gravity" effect is left out.
 *
 * A frame function takes the canvas size and a time in seconds and returns every dot (and, for
 * `connecting`, every line) to draw. Dots are points on or around a unit sphere, turned and tilted
 * by `makeProj`, then sorted far to near so the near ones paint on top. `white` is the ink value:
 * 0 is the strongest ink, 1 fades into the background.
 */

export type OrbState =
  | 'working'
  | 'searching'
  | 'solving'
  | 'listening'
  | 'connecting'
  | 'weaving'
  | 'composing'
  | 'breathing'
  | 'shaping';

/** The two sizes the library hand-tunes. Any other pixel size borrows the nearest one's tuning. */
export type OrbPreset = 20 | 64;

export interface Dot {
  x: number;
  y: number;
  z: number;
  r: number;
  white: number;
  a?: number;
}

export interface Line {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  white: number;
  a?: number;
  w: number;
}

export interface OrbFrame {
  dots: Dot[];
  lines: Line[];
}

export interface Tint {
  r: number;
  g: number;
  b: number;
}

type Opts = Record<string, number | undefined>;
type FrameFn = (size: number, t: number, o: Opts) => OrbFrame;
type Point = [number, number, number];

const lerp = (a: number, b: number, f: number) => a + (b - a) * f;
const frac = (x: number) => x - Math.floor(x);

/** Deterministic hash in [0, 1). */
function hashD(a: number, b: number): number {
  const h = Math.sin(a * 12.9898 + b * 78.233) * 43758.5453;
  return h - Math.floor(h);
}

/** Smooth value noise on a 2D lattice. */
function vnoise(x: number, y: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  let fx = x - xi;
  let fy = y - yi;
  fx = fx * fx * (3 - 2 * fx);
  fy = fy * fy * (3 - 2 * fy);
  const a = hashD(xi, yi);
  const b = hashD(xi + 1, yi);
  const c = hashD(xi, yi + 1);
  const d = hashD(xi + 1, yi + 1);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}

/** Evenly spread directions on a unit sphere (Fibonacci lattice). */
function fibDir(i: number, n: number): Point {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const y = 1 - (2 * (i + 0.5)) / n;
  const rad = Math.sqrt(1 - y * y);
  const a = i * golden;
  return [rad * Math.cos(a), y, rad * Math.sin(a)];
}

/** Shortest signed angle between two angles. */
const angleDelta = (a: number, b: number) => Math.atan2(Math.sin(a - b), Math.cos(a - b));

/** Spin by `yaw`, tilt by `tilt`, then flatten onto the canvas around (cx, cy). */
function makeProj(yaw: number, tilt: number, cx: number, cy: number, scale: number) {
  const st = Math.sin(tilt);
  const ct = Math.cos(tilt);
  const sy = Math.sin(yaw);
  const cyw = Math.cos(yaw);

  return (x: number, y: number, z: number): Point => {
    const x1 = x * cyw + z * sy;
    const z1 = -x * sy + z * cyw;
    const y1 = y * ct - z1 * st;
    const z2 = y * st + z1 * ct;
    return [cx + x1 * scale, cy - y1 * scale, z2];
  };
}

/** Dot radii were tuned for a 300px frame; this shrinks them less than linearly so small orbs stay legible. */
const radiusScale = (size: number, pow: number) => (size / 300) ** pow;

/** Drop invisible marks, keep a minimum radius, and sort far to near. */
function finalizeFrame(dots: Dot[], lines: Line[], rMin = 0.3): OrbFrame {
  const visible: Dot[] = [];

  for (const d of dots) {
    if ((d.a ?? 1) < 0.02) continue;
    d.r = Math.max(rMin, d.r);
    visible.push(d);
  }

  visible.sort((a, b) => a.z - b.z);

  return { dots: visible, lines: lines.filter((l) => (l.a ?? 1) >= 0.02) };
}

/**
 * The fill for one ink value. On a dark page the ramp runs from the tint down to black, so near
 * dots read bright; on a light page it runs from the tint up to white, so near dots read strong.
 */
function inkColor(w: number, alpha: number, dark: boolean, tint?: Tint): string {
  if (!tint) {
    const g = Math.round((dark ? 1 - w : w) * 255);
    return `rgba(${g},${g},${g},${alpha})`;
  }

  const ramp = (c: number) => Math.round(dark ? c * (1 - w) : c + (255 - c) * w);

  return `rgba(${ramp(tint.r)},${ramp(tint.g)},${ramp(tint.b)},${alpha})`;
}

/** Draw a finished frame. Lines first, so the dots sit on top of them. */
export function paintFrame(ctx: CanvasRenderingContext2D, frame: OrbFrame, dark: boolean, tint?: Tint): void {
  for (const l of frame.lines) {
    ctx.strokeStyle = inkColor(Math.min(1, Math.max(0, l.white)), l.a ?? 1, dark, tint);
    ctx.lineWidth = l.w;
    ctx.beginPath();
    ctx.moveTo(l.x1, l.y1);
    ctx.lineTo(l.x2, l.y2);
    ctx.stroke();
  }

  for (const d of frame.dots) {
    ctx.fillStyle = inkColor(Math.min(1, Math.max(0, d.white)), d.a ?? 1, dark, tint);
    ctx.beginPath();
    ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** working — particles running on tilted orbits, over faint orbit tracks. */
const frameOrbits: FrameFn = (size, t, o) => {
  const c = size / 2;
  const R = (size / 2) * 0.82;
  const pt = makeProj(t * 0.12, 0.3, c, c, 1);
  const rs = radiusScale(size, o.rsPow ?? 0.6);
  const dots: Dot[] = [];
  const orbitN = o.orbitN ?? 12;
  const ghostN = o.ghostN ?? 40;
  const particles = o.particles ?? 3;

  for (let orb = 0; orb < orbitN; orb++) {
    const h1 = hashD(orb, 1.7);
    const h2 = hashD(orb, 5.2);
    const h3 = hashD(orb, 8.9);
    const ro = R * (0.45 + 0.52 * h1);
    const th = h1 * 2 * Math.PI;
    const phi = Math.acos(2 * h2 - 1);
    const nx = Math.sin(phi) * Math.cos(th);
    const ny = Math.cos(phi);
    const nz = Math.sin(phi) * Math.sin(th);
    const ul = Math.max(1e-6, Math.sqrt(ny * ny + nx * nx));
    const ux = -ny / ul;
    const uy = nx / ul;
    const uz = 0;
    const vx = ny * uz - nz * uy;
    const vy = nz * ux - nx * uz;
    const vz = nx * uy - ny * ux;
    const speed = (0.25 + 0.55 * h3) * (h3 > 0.5 ? 1 : -1);

    const at = (a: number) =>
      pt(
        (ux * Math.cos(a) + vx * Math.sin(a)) * ro,
        (uy * Math.cos(a) + vy * Math.sin(a)) * ro,
        (uz * Math.cos(a) + vz * Math.sin(a)) * ro,
      );

    for (let k = 0; k < ghostN; k++) {
      const [x, y, z] = at((k / ghostN) * 2 * Math.PI);
      const depth = (z / ro + 1) / 2;
      dots.push({ x, y, z, r: (o.ghostR ?? 0.9) * rs, white: 0.72, a: (o.ghostA ?? 0.5) * (0.4 + 0.6 * depth) });
    }

    for (let m = 0; m < particles; m++) {
      const [x, y, z] = at(t * speed + (m / particles) * 2 * Math.PI + h2 * 6);
      const depth = (z / ro + 1) / 2;
      dots.push({ x, y, z, r: ((o.partR ?? 1.2) + (o.partRDepth ?? 1.6) * depth) * rs, white: 0.3 - 0.22 * depth });
    }
  }

  return finalizeFrame(dots, [], o.rMin);
};

/** searching — a dotted globe with a bright scan line sweeping round it. */
const frameGlobe: FrameFn = (size, t, o) => {
  const spin = 0.5;
  const c = size / 2;
  const pt = makeProj(t * spin, 0.4 + 0.06 * Math.sin(t * 0.35), c, c, (size / 2) * 0.82);
  const scan = t * (spin + (1.7 - spin) * (o.scanMul ?? 1));
  const rs = radiusScale(size, o.rsPow ?? 0.6);
  const dimBase = o.dimBase ?? 1;
  const dots: Dot[] = [];
  const latRings = o.latRings ?? 17;
  const lonDensity = o.lonDensity ?? 44;

  for (let li = 0; li <= latRings; li++) {
    const lat = -Math.PI / 2 + (li / latRings) * Math.PI;
    const cosLat = Math.cos(lat);
    const sinLat = Math.sin(lat);
    const lonCount = Math.max(1, Math.round(Math.abs(cosLat) * lonDensity));

    for (let lj = 0; lj < lonCount; lj++) {
      const lon = (lj / lonCount) * 2 * Math.PI;
      const [x, y, z] = pt(cosLat * Math.cos(lon), sinLat, cosLat * Math.sin(lon));
      const depth = (z + 1) / 2;
      const d = angleDelta(lon + t * spin, scan);
      const boost = Math.exp(-(d * d) / 0.18) * Math.max(0, z);

      dots.push({
        x,
        y,
        z,
        r: ((o.rBase ?? 0.6) + (o.rDepth ?? 1.7) * depth + (o.rBoost ?? 1) * boost) * rs,
        white: (o.inkFar ?? 0.62) - (o.inkSpan ?? 0.54) * depth,
        a: dimBase + (1 - dimBase) * Math.min(1, boost),
      });
    }
  }

  return finalizeFrame(dots, [], o.rMin);
};

interface Move {
  axis: number;
  lo: number;
  hi: number;
  ang: number;
}

/** Where each twist is in a scramble-then-solve cycle: 0 untouched, 1 fully turned. */
function solveCycle(time: number, count: number, slotDur: number, rest: number) {
  const tc = time % (2 * count * slotDur + rest);
  const amount = new Array<number>(count).fill(0);
  let active = -1;

  if (tc < 2 * count * slotDur) {
    const slot = Math.floor(tc / slotDur);
    const p = (tc - slot * slotDur) / slotDur;
    const ep = 1 - (1 - Math.min(1, p / 0.7)) ** 3;

    if (slot < count) {
      for (let i = 0; i < slot; i++) amount[i] = 1;
      amount[slot] = ep;
      active = slot;
    } else {
      const u = 2 * count - 1 - slot;
      for (let i = 0; i < u; i++) amount[i] = 1;
      amount[u] = 1 - ep;
      active = u;
    }
  }

  return { amount, active };
}

function makeMoves(count: number): Move[] {
  const moves: Move[] = [];

  for (let i = 0; i < count; i++) {
    const axis = Math.min(2, Math.floor(hashD(i, 2.3) * 3));
    const lo = -1 + 0.5 * Math.min(3, Math.floor(hashD(i, 5.9) * 4));
    const dir = hashD(i, 7.7) < 0.5 ? 1 : -1;
    moves.push({ axis, lo, hi: lo + 0.5, ang: (dir * Math.PI) / 2 });
  }

  return moves;
}

/** Turn one point through every twist that has started, and say if it is in the twist now moving. */
function applyMoves(point: Point, moves: Move[], sc: { amount: number[]; active: number }): [...Point, boolean] {
  let [x, y, z] = point;
  let inActive = false;

  for (let i = 0; i < moves.length; i++) {
    if (sc.amount[i] <= 0) continue;

    const mv = moves[i];
    const coord = mv.axis === 0 ? x : mv.axis === 1 ? y : z;

    if (coord < mv.lo || coord >= mv.hi) continue;
    if (i === sc.active) inActive = true;

    const ca = Math.cos(mv.ang * sc.amount[i]);
    const sa = Math.sin(mv.ang * sc.amount[i]);

    if (mv.axis === 0) {
      [y, z] = [y * ca - z * sa, y * sa + z * ca];
    } else if (mv.axis === 1) {
      [x, z] = [x * ca + z * sa, -x * sa + z * ca];
    } else {
      [x, y] = [x * ca - y * sa, x * sa + y * ca];
    }
  }

  return [x, y, z, inActive];
}

/** solving — bands of the sphere twist out of place, then click back solved. */
const frameRubik: FrameFn = (size, t, o) => {
  const c = size / 2;
  const pt = makeProj(t * 0.55, 0.35 + 0.1 * Math.sin(t * 0.9), c, c, (size / 2) * 0.82);
  const rs = radiusScale(size, o.rsPow ?? 0.6);
  const moveCount = o.moveCount ?? 14;
  const moves = makeMoves(moveCount);
  const sc = solveCycle(t, moveCount, 0.42, 1.2);
  const dots: Dot[] = [];
  const latRings = o.latRings ?? 15;
  const lonDensity = o.lonDensity ?? 40;

  for (let li = 0; li <= latRings; li++) {
    const lat = -Math.PI / 2 + (li / latRings) * Math.PI;
    const cosLat = Math.cos(lat);
    const sinLat = Math.sin(lat);
    const lonCount = Math.max(1, Math.round(Math.abs(cosLat) * lonDensity));

    for (let lj = 0; lj < lonCount; lj++) {
      const lon = (lj / lonCount) * 2 * Math.PI;
      const [mx, my, mz, inActive] = applyMoves([cosLat * Math.cos(lon), sinLat, cosLat * Math.sin(lon)], moves, sc);
      const [x, y, z] = pt(mx, my, mz);
      const depth = (z + 1) / 2;

      dots.push({
        x,
        y,
        z,
        r: ((o.rBase ?? 0.6) + (o.rDepth ?? 1.7) * depth + (inActive ? (o.rActive ?? 0.3) : 0)) * rs,
        white: (o.inkFar ?? 0.62) - (o.inkSpan ?? 0.54) * depth - (inActive ? 0.14 : 0),
      });
    }
  }

  return finalizeFrame(dots, [], o.rMin);
};

/** listening — a wave rolls through the sphere's rings, swelling them in turn. */
const frameWave: FrameFn = (size, t, o) => {
  const c = size / 2;
  const R = (size / 2) * 0.874;
  const pt = makeProj(t * 0.18, 0.38, c, c, 1);
  const rs = radiusScale(size, o.rsPow ?? 0.6);
  const dots: Dot[] = [];
  const rings = o.rings ?? 15;
  const lonDensity = o.lonDensity ?? 40;

  for (let ri = 0; ri <= rings; ri++) {
    const lat = -Math.PI / 2 + (ri / rings) * Math.PI;
    const cosLat = Math.cos(lat);
    const sinLat = Math.sin(lat);
    const w = 0.62 * Math.sin(t * 2.1 - ri * 0.52) + 0.38 * Math.sin(t * 1.27 + ri * 0.83);
    const rr = R * (0.88 + 0.105 * w);
    const crest = Math.max(0, w);
    const lonCount = Math.max(1, Math.round(Math.abs(cosLat) * lonDensity));

    for (let lj = 0; lj < lonCount; lj++) {
      const lon = (lj / lonCount) * 2 * Math.PI;
      const [x, y, z] = pt(cosLat * Math.cos(lon) * rr, sinLat * rr, cosLat * Math.sin(lon) * rr);
      const depth = (z / R + 1) / 2;

      dots.push({
        x,
        y,
        z,
        r: ((o.rBase ?? 0.6) + (o.rDepth ?? 1.7) * depth) * (1 + 0.4 * crest) * rs,
        white: 0.66 - 0.56 * depth - 0.1 * crest,
      });
    }
  }

  return finalizeFrame(dots, [], o.rMin);
};

/** connecting — drifting nodes wire themselves to near neighbours, with signals running between them. */
const frameWeb: FrameFn = (size, t, o) => {
  const c = size / 2;
  const pt = makeProj(t * 0.12, 0.32, c, c, (size / 2) * 0.8 * (o.spread ?? 1));
  const rs = radiusScale(size, o.rsPow ?? 0.6);
  const nodeN = o.nodeN ?? 30;
  const thr = o.thr ?? 0.72;
  const nodeR = o.nodeR ?? 1.4;
  const nodeRDepth = o.nodeRDepth ?? 1.8;
  const nodes: Point[] = [];

  for (let i = 0; i < nodeN; i++) {
    const d = fibDir(i, nodeN);
    const x = d[0] + 0.3 * (vnoise(i * 0.31 + 9, t * 0.24) - 0.5) * 2;
    const y = d[1] + 0.3 * (vnoise(i * 0.53 + 27, t * 0.21) - 0.5) * 2;
    const z = d[2] + 0.3 * (vnoise(i * 0.77 + 55, t * 0.27) - 0.5) * 2;
    const l = Math.sqrt(x * x + y * y + z * z);
    nodes.push([x / l, y / l, z / l]);
  }

  const lines: Line[] = [];
  const dots: Dot[] = [];

  for (let i = 0; i < nodeN; i++) {
    for (let j = i + 1; j < nodeN; j++) {
      const dist = Math.hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1], nodes[i][2] - nodes[j][2]);

      if (dist >= thr) continue;

      const [x1, y1, z1] = pt(...nodes[i]);
      const [x2, y2, z2] = pt(...nodes[j]);
      const depth = ((z1 + z2) / 2 + 1) / 2;

      lines.push({
        x1,
        y1,
        x2,
        y2,
        white: 0.42,
        a: (1 - dist / thr) * (0.3 + 0.55 * depth),
        w: Math.max(0.6, (o.lineW ?? 0.8) * rs),
      });
    }
  }

  for (let i = 0; i < nodeN; i++) {
    const [x, y, z] = pt(...nodes[i]);
    const depth = (z + 1) / 2;
    const pulse = 1 + 0.25 * Math.sin(t * 1.4 + i * 2.7);
    dots.push({ x, y, z, r: (nodeR + nodeRDepth * depth) * pulse * rs, white: 0.55 - 0.45 * depth });
  }

  const signals = o.signals ?? 5;

  for (let s = 0; s < signals; s++) {
    const seg = Math.floor(t * 0.55 + s * 7.31);
    const a = Math.floor(hashD(seg, s * 3.1 + 1.7) * nodeN);
    const b = Math.floor(hashD(seg, s * 5.7 + 4.2) * nodeN);

    if (a === b) continue;

    const f = frac(t * 0.55 + s * 7.31);
    const x = lerp(nodes[a][0], nodes[b][0], f);
    const y = lerp(nodes[a][1], nodes[b][1], f);
    const z = lerp(nodes[a][2], nodes[b][2], f);
    const l = Math.max(1e-6, Math.sqrt(x * x + y * y + z * z));
    const [px, py, pz] = pt(x / l, y / l, z / l);
    const depth = (pz + 1) / 2;

    dots.push({ x: px, y: py, z: pz, r: (nodeR * 1.5 + nodeRDepth * depth) * rs, white: 0.05, a: 0.5 + 0.5 * depth });
  }

  return finalizeFrame(dots, lines, o.rMin);
};

/** The faint sphere of dots behind the weaving and composing strands. */
function ghostSphere(pt: ReturnType<typeof makeProj>, R: number, ghostN: number, rs: number): Dot[] {
  const dots: Dot[] = [];

  for (let i = 0; i < ghostN; i++) {
    const d = fibDir(i, ghostN);
    const [x, y, z] = pt(d[0] * R, d[1] * R, d[2] * R);
    const depth = (z / R + 1) / 2;
    dots.push({ x, y, z, r: 0.8 * rs, white: 0.78, a: 0.1 + 0.22 * depth });
  }

  return dots;
}

/** weaving — three strands plait around the sphere from pole to pole. */
const frameBraid: FrameFn = (size, t, o) => {
  const c = size / 2;
  const R = (size / 2) * 0.76;
  const pt = makeProj(t * 0.4, 0.3, c, c, 1);
  const rs = radiusScale(size, o.rsPow ?? 0.6);
  const dots = ghostSphere(pt, R, o.ghostN ?? 150, rs);
  const strandN = o.strandN ?? 52;
  const turns = o.turns ?? 3;

  for (let s = 0; s < 3; s++) {
    const phase = (s / 3) * 2 * Math.PI;

    for (let i = 0; i < strandN; i++) {
      const u = (frac(i / strandN + t * 0.045) * 2 - 1) * 0.96;
      const surf = Math.sqrt(Math.max(0, 1 - u * u));
      const endFade = Math.min(1, (1 - Math.abs(u)) / 0.1);
      const a = u * Math.PI * turns + phase;
      const weave = 1 + 0.075 * Math.sin(u * Math.PI * turns * 2 + phase * 2 + t * 0.8);
      const rr = surf * R * weave;
      const [x, y, z] = pt(Math.cos(a) * rr, u * R * weave, Math.sin(a) * rr);
      const depth = (z / R + 1) / 2;

      dots.push({
        x,
        y,
        z,
        r: ((o.rBase ?? 1.2) + (o.rDepth ?? 1.8) * depth) * rs,
        white: 0.55 - 0.45 * depth,
        a: endFade * (0.45 + 0.55 * depth),
      });
    }
  }

  return finalizeFrame(dots, [], o.rMin);
};

/**
 * composing — an undulating band of dots wraps the sphere.
 * breathing — the same band seen face-on, its waves moved onto the radius, with no sphere behind.
 */
const frameRibbon: FrameFn = (size, t, o) => {
  const c = size / 2;
  const R = (size / 2) * 0.78;
  const spin = o.spin ?? 1;
  const camTilt = 0.3;
  const pt = makeProj(t * 0.1 * spin, camTilt, c, c, 1);
  const rs = radiusScale(size, o.rsPow ?? 0.6);
  const dots = ghostSphere(pt, R, o.ghostN ?? 150, rs);
  const ya = t * 0.24 * spin;
  const ta = o.faceOn ? -camTilt : 0.55 + 0.3 * Math.sin(t * 0.18) * spin;
  const ux = Math.cos(ya);
  const uy = 0;
  const uz = Math.sin(ya);
  const vx = -uz * Math.sin(ta);
  const vy = Math.cos(ta);
  const vz = ux * Math.sin(ta);
  const nx = uy * vz - uz * vy;
  const ny = uz * vx - ux * vz;
  const nz = ux * vy - uy * vx;
  const wobMul = o.wobMul ?? 1;
  const baseR = o.faceOn ? R / (1 + 0.85 * 0.23 * wobMul) : R;
  const lanes = Math.max(1, Math.round((o.lanes ?? 5) * (o.bandMul ?? 1)));
  const segs = o.segs ?? 88;

  for (let w = 0; w < lanes; w++) {
    const laneOff = (w - (lanes - 1) / 2) * 0.075;
    const edge = Math.abs(w - (lanes - 1) / 2) / Math.max(1, (lanes - 1) / 2);

    for (let k = 0; k < segs; k++) {
      const a = (k / segs) * 2 * Math.PI;
      const wob = (0.16 * Math.sin(a * 3 - t * 1.7 + w * 0.22) + 0.07 * Math.sin(a * 5 + t * 1.1)) * wobMul;
      const radial = o.faceOn ? 1 + wob : 1;
      const off = o.faceOn ? laneOff : laneOff + wob;
      const x = ux * Math.cos(a) + vx * Math.sin(a) + nx * off;
      const y = uy * Math.cos(a) + vy * Math.sin(a) + ny * off;
      const z = uz * Math.cos(a) + vz * Math.sin(a) + nz * off;
      const l = Math.sqrt(x * x + y * y + z * z);
      const rr = baseR * radial;
      const [px, py, pz] = pt((x / l) * rr, (y / l) * rr, (z / l) * rr);
      const depth = (pz / R + 1) / 2;

      dots.push({
        x: px,
        y: py,
        z: pz,
        r: ((o.rBase ?? 1.1) + (o.rDepth ?? 1.7) * depth) * (1 - 0.25 * edge) * rs,
        white: 0.52 - 0.44 * depth + 0.18 * edge,
        a: 0.4 + 0.6 * depth,
      });
    }
  }

  return finalizeFrame(dots, [], o.rMin);
};

type Path = (f: number) => [number, number];

/** A closed outline through these corners, walked by the fraction of its length. */
function polyPath(verts: [number, number][]): Path {
  const lengths = verts.map((a, i) => {
    const b = verts[(i + 1) % verts.length];
    return Math.hypot(b[0] - a[0], b[1] - a[1]);
  });
  const total = lengths.reduce((sum, l) => sum + l, 0);

  return (f) => {
    let target = f * total;
    let i = 0;

    while (target > lengths[i] && i < verts.length - 1) {
      target -= lengths[i];
      i++;
    }

    const a = verts[i];
    const b = verts[(i + 1) % verts.length];
    const ff = lengths[i] ? Math.min(1, target / lengths[i]) : 0;

    return [a[0] + (b[0] - a[0]) * ff, a[1] + (b[1] - a[1]) * ff];
  };
}

const CIRCLE: Path = (f) => {
  const a = -Math.PI / 2 + f * 2 * Math.PI;
  return [Math.cos(a) * 0.24, Math.sin(a) * 0.24];
};

const SHAPES: Path[] = [
  CIRCLE,
  polyPath([
    [0, -0.26],
    [0.24, 0.16],
    [-0.24, 0.16],
  ]),
  polyPath([
    [0, -0.2],
    [0.2, -0.2],
    [0.2, 0.2],
    [-0.2, 0.2],
    [-0.2, -0.2],
  ]),
];

const HOLD = 1.4;
const MORPH = 0.9;

/** shaping — a dotted outline holds, then morphs: circle, triangle, square, and round again. */
const frameMorph: FrameFn = (size, t, o) => {
  const seg = HOLD + MORPH;
  const tc = t % (seg * SHAPES.length);
  const k = Math.floor(tc / seg);
  const local = tc - k * seg;
  const raw = local > HOLD ? (local - HOLD) / MORPH : 0;
  const m = raw * raw * (3 - 2 * raw);
  const spread = o.spread ?? 1;
  const from = SHAPES[k];
  const to = SHAPES[(k + 1) % SHAPES.length];
  const M = 160;
  const pts: [number, number][] = [];

  for (let i = 0; i < M; i++) {
    const a = from(i / M);
    const b = to(i / M);
    pts.push([(a[0] + (b[0] - a[0]) * m) * spread, (a[1] + (b[1] - a[1]) * m) * spread]);
  }

  const lengths = pts.map((a, i) => {
    const b = pts[(i + 1) % M];
    return Math.hypot(b[0] - a[0], b[1] - a[1]);
  });
  const total = lengths.reduce((sum, l) => sum + l, 0);
  const n = Math.max(6, Math.round(34 * (o.iconD ?? 1)));
  const re = (o.rDot ?? 0.021) * 1.35 * spread;
  const pulse = 1 + 0.02 * Math.sin(local * 3.1);
  const c = size / 2;
  const dots: Dot[] = [];
  let at = 0;
  let acc = 0;

  for (let j = 0; j < n; j++) {
    const target = (j / n) * total;

    while (acc + lengths[at] < target && at < M - 1) {
      acc += lengths[at];
      at++;
    }

    const a = pts[at];
    const b = pts[(at + 1) % M];
    const f = lengths[at] ? Math.min(1, (target - acc) / lengths[at]) : 0;

    dots.push({
      x: c + (a[0] + (b[0] - a[0]) * f) * pulse * size,
      y: c + (a[1] + (b[1] - a[1]) * f) * pulse * size,
      z: 0,
      r: Math.max(0.35, re * size),
      white: 0.1,
    });
  }

  return finalizeFrame(dots, [], o.rMin);
};

const FRAMES: Record<OrbState, FrameFn> = {
  working: frameOrbits,
  searching: frameGlobe,
  solving: frameRubik,
  listening: frameWave,
  connecting: frameWeb,
  weaving: frameBraid,
  composing: frameRibbon,
  breathing: frameRibbon,
  shaping: frameMorph,
};

/** The starting knobs for each state, before a size's tuning is applied. */
const BASE: Record<OrbState, Opts> = {
  working: { orbitN: 12, ghostN: 40, ghostR: 0.9, ghostA: 0.5, particles: 3, partR: 1.2, partRDepth: 1.6, rsPow: 0.6, rMin: 0.3 },
  searching: { latRings: 17, lonDensity: 44, rBase: 0.6, rDepth: 1.7, rBoost: 1, inkFar: 0.62, inkSpan: 0.54, rsPow: 0.6, rMin: 0.3 },
  solving: { latRings: 15, lonDensity: 40, moveCount: 14, rBase: 0.6, rDepth: 1.7, rActive: 0.3, inkFar: 0.62, inkSpan: 0.54, rsPow: 0.6, rMin: 0.3 },
  listening: { rings: 15, lonDensity: 40, rBase: 0.6, rDepth: 1.7, rsPow: 0.6, rMin: 0.3 },
  connecting: { nodeN: 30, thr: 0.72, signals: 5, nodeR: 1.4, nodeRDepth: 1.8, lineW: 0.8, rsPow: 0.6, rMin: 0.3 },
  weaving: { strandN: 52, turns: 3, ghostN: 150, rBase: 1.2, rDepth: 1.8, rsPow: 0.6, rMin: 0.3 },
  composing: { lanes: 5, segs: 88, ghostN: 150, rBase: 1.1, rDepth: 1.7, rsPow: 0.6, rMin: 0.3 },
  breathing: { lanes: 5, segs: 88, ghostN: 0, faceOn: 1, rBase: 1.1, rDepth: 1.7, rsPow: 0.6, rMin: 0.3 },
  shaping: { rDot: 0.021, iconD: 1, rMin: 0.25 },
};

interface Tuning {
  speed: number;
  count: number;
  size: number;
  extra?: Opts;
}

/** The library's hand tuning per state and size: animation speed, dot count and dot size multipliers. */
const TUNING: Record<OrbState, Record<OrbPreset, Tuning>> = {
  working: { 64: { speed: 1.885, count: 1, size: 1 }, 20: { speed: 3.9, count: 0.238, size: 2.4 } },
  searching: {
    64: { speed: 2.015, count: 0.42, size: 1.15, extra: { scanMul: 4.08, dimBase: 0.45 } },
    20: { speed: 2.665, count: 0.105, size: 1.75, extra: { scanMul: 4.335, dimBase: 0.45 } },
  },
  solving: { 64: { speed: 1.82, count: 0.35, size: 1.05 }, 20: { speed: 1.95, count: 0.088, size: 1.9 } },
  listening: { 64: { speed: 4.388, count: 0.341, size: 1 }, 20: { speed: 3.998, count: 0.105, size: 1.6 } },
  connecting: { 64: { speed: 3.315, count: 1.35, size: 0.95 }, 20: { speed: 6.63, count: 0.25, size: 1.52 } },
  weaving: { 64: { speed: 1.625, count: 0.5, size: 1 }, 20: { speed: 2.75, count: 0.1125, size: 1.36 } },
  composing: {
    64: { speed: 2.34, count: 0.25, size: 0.85, extra: { spin: 0, bandMul: 3.9, wobMul: 1 } },
    20: { speed: 3.12, count: 0.051, size: 1.073, extra: { spin: 0, bandMul: 4.94, wobMul: 1 } },
  },
  breathing: {
    64: { speed: 3.24, count: 0.25, size: 0.956, extra: { spin: 0, bandMul: 3.627, wobMul: 0.368 } },
    20: { speed: 3.78, count: 0.028, size: 1.622, extra: { spin: 0, bandMul: 3.968, wobMul: 0.565 } },
  },
  shaping: {
    64: { speed: 2.405, count: 0.702, size: 0.395, extra: { spread: 1.45 } },
    20: { speed: 2.08, count: 0.53, size: 1.011, extra: { spread: 1.45 } },
  },
};

const COUNT_PAIRS = [
  ['latRings', 'lonDensity'],
  ['rings', 'lonDensity'],
  ['lanes', 'segs'],
] as const;
const COUNT_KEYS = ['orbitN', 'ghostN', 'nodeN', 'strandN', 'signals'] as const;
const RADIUS_KEYS = ['rBase', 'rDepth', 'rActive', 'rDot', 'ghostR', 'partR', 'partRDepth', 'nodeR', 'nodeRDepth'] as const;

/** Multiply the dot counts. Grid pairs share the factor as a square root, so the total scales by it. */
function scaleCounts(opts: Opts, scale: number): Opts {
  const out = { ...opts };
  const done = new Set<string>();
  const rt = Math.sqrt(scale);

  for (const [a, b] of COUNT_PAIRS) {
    const va = out[a];
    const vb = out[b];

    if (va == null || vb == null || done.has(a) || done.has(b)) continue;

    out[a] = Math.max(2, Math.round(va * rt));
    out[b] = Math.max(2, Math.round(vb * rt));
    done.add(a);
    done.add(b);
  }

  for (const k of COUNT_KEYS) {
    const v = out[k];
    if (v != null && v !== 0 && !done.has(k)) out[k] = Math.max(1, Math.round(v * scale));
  }

  if (out.iconD != null) out.iconD = Math.max(0.02, out.iconD * scale);

  return out;
}

function scaleRadii(opts: Opts, scale: number): Opts {
  const out = { ...opts };

  for (const k of RADIUS_KEYS) {
    const v = out[k];
    if (v != null) out[k] = v * scale;
  }

  return out;
}

const resolved = new Map<string, { speed: number; opts: Opts }>();

/** The speed and knobs for one state at one tuned size, worked out once and kept. */
function resolve(state: OrbState, preset: OrbPreset) {
  const key = `${state}-${preset}`;
  const hit = resolved.get(key);

  if (hit) return hit;

  const tuning = TUNING[state][preset];
  let opts = { ...BASE[state] };

  if (tuning.count !== 1) opts = scaleCounts(opts, tuning.count);
  if (tuning.size !== 1) opts = scaleRadii(opts, tuning.size);
  if (tuning.extra) opts = { ...opts, ...tuning.extra };

  const result = { speed: tuning.speed, opts };
  resolved.set(key, result);

  return result;
}

/** The tuned size closest to a pixel size: small inline orbs use the 20px tuning, the rest the 64px one. */
export const presetFor = (size: number): OrbPreset => (size < 40 ? 20 : 64);

/** A function that gives the frame for any time in seconds, plus how fast that state's clock runs. */
export function orbAnimation(state: OrbState, size: number) {
  const { speed, opts } = resolve(state, presetFor(size));
  const frameFn = FRAMES[state];

  return { speed, frame: (t: number) => frameFn(size, t, opts) };
}
