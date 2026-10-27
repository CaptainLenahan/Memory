// Colour themes. The UI and brain are designed in blue; a theme re-tints every blue-family colour in OKLCH:
// hues are pulled toward the theme hue (k compresses the blue band so a theme stays one family), chroma and
// lightness are scaled, and lightness/contrast relationships survive the swap. Data colours (logical/creative
// regions, due/overdue status, dashboard series) are deliberately left alone so they keep their meaning.

export const THEMES = [
  { id: 'blue', name: 'Neural blue', h: 222, k: 1, c: 1, l: 1 },
  { id: 'teal', name: 'Teal', h: 190, k: 0.35, c: 1, l: 1 },
  { id: 'green', name: 'Synapse green', h: 152, k: 0.35, c: 1, l: 1 },
  { id: 'gold', name: 'Gold', h: 80, k: 0.3, c: 1.15, l: 1 },
  { id: 'orange', name: 'Ember orange', h: 55, k: 0.3, c: 1.25, l: 0.97 },
  { id: 'red', name: 'Coral red', h: 24, k: 0.3, c: 1.3, l: 0.9 },
  { id: 'purple', name: 'Violet', h: 302, k: 0.35, c: 1, l: 1 },
  { id: 'silver', name: 'Graphite', h: 222, k: 1, c: 0.1, l: 1 },
];
const BASE_HUE = 222; // OKLCH hue of the blue accent (#5fd8ff)

// The --t-* channels in css/app.css (each holds "r, g, b" of the blue design colour it is named after).
const CSS_CHANNELS = ['02060e', '040a17', '040c1c', '04223a', '051024', '071226', '071328', '09162e', '0a1a35', '0a2850',
  '0e2040', '102448', '142c56', '183464', '1d5ac8', '1e508c', '1f63d6', '285aa0', '2f8cff', '5a7396', '5fb0ff', '5fbeff',
  '5fd8ff', '7846ff', '8aa6c8', '8fe9ff', 'b47cff', 'c9def5', 'd8e8fb', 'e3f1ff'];

// ---------- OKLCH ----------
const lin = c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const gam = c => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function toOklch(hex) {
  const [r, g, b] = [1, 3, 5].map(i => lin(parseInt(hex.slice(i, i + 2), 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
  return [L, Math.hypot(A, B), ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360];
}

function fromOklch(L, C, H) {
  const A = C * Math.cos((H * Math.PI) / 180), B = C * Math.sin((H * Math.PI) / 180);
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3;
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3;
  const s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
}

const inGamut = rgb => rgb.every(v => v >= -1e-4 && v <= 1 + 1e-4);

const cache = new Map();
// The themed version of a blue design colour, as [r, g, b] bytes. Out-of-gamut results lose chroma, not hue.
function themedRgb(hex, t) {
  const key = `${t.id}${hex}`;
  if (cache.has(key)) return cache.get(key);
  let [L, C, H] = toOklch(hex);
  const d = ((H - BASE_HUE + 540) % 360) - 180;
  L = Math.min(1, L * t.l); C *= t.c; H = t.h + t.k * d;
  let rgb = fromOklch(L, C, H);
  if (!inGamut(rgb)) {
    let lo = 0, hi = C;
    for (let i = 0; i < 16; i++) { const mid = (lo + hi) / 2; if (inGamut(fromOklch(L, mid, H))) lo = mid; else hi = mid; }
    rgb = fromOklch(L, lo, H);
  }
  const out = rgb.map(v => Math.round(Math.max(0, Math.min(1, gam(Math.max(0, Math.min(1, v))))) * 255));
  cache.set(key, out);
  return out;
}

let current = THEMES[0];
const listeners = [];

export const currentTheme = () => current;
export const themeById = id => THEMES.find(t => t.id === id) || THEMES[0];
export function themed(hex, theme = current) {
  return `#${themedRgb(hex.toLowerCase(), theme).map(v => v.toString(16).padStart(2, '0')).join('')}`;
}
export const onThemeChange = fn => listeners.push(fn);

export function applyTheme(id) {
  const t = themeById(id);
  const vars = {};
  for (const hex of CSS_CHANNELS) vars[`--t-${hex}`] = themedRgb(`#${hex}`, t).join(', ');
  const root = document.documentElement;
  for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v);
  root.dataset.theme = t.id;
  try { localStorage.setItem('memoryTheme', JSON.stringify({ id: t.id, vars })); } catch { /* private mode */ }
  if (t.id === current.id && root.dataset.themeApplied) return;
  root.dataset.themeApplied = '1';
  current = t;
  for (const fn of listeners) fn(t);
}
