// Analytics dashboard: KPI tiles, week-by-week layout, due-date calendar, capacity, balance and trend.
import { api } from './api.js';
import { store } from './store.js';
import { themed } from './themes.js';
import { esc, fmtDate, h, toastError, todayISO } from './ui.js';

// Chart colors (validated for the dark chart surface). Regions are a polarity: logical <-> creative with a
// neutral midpoint, so they use a diverging pair; the trend uses categorical slots 1-2.
const VIZ = {
  logical: '#3987e5', balanced: '#b9c0c9', creative: '#d55181',
  series1: '#3987e5', series2: '#d95926',
  seq: ['#12284a', '#184f95', '#256abf', '#3987e5', '#6da7ec'],
  warning: '#fab219', critical: '#d03b3b',
};
// Chart chrome (labels, surface rings) follows the colour theme; the data colours above don't.
const INK = () => themed('#c9def5');
const SURFACE = () => themed('#08142a');
const REGION_LABEL = { logical: 'Logical', balanced: 'Balanced', creative: 'Creative' };

let handlers = {};
let tip;
export function initDashboard(h_) {
  handlers = h_;
  tip = h('div', { class: 'chart-tooltip', role: 'tooltip' });
  document.body.append(tip);
}

function showTip(e, html) {
  tip.innerHTML = html;
  tip.style.display = 'block';
  const x = Math.min(window.innerWidth - tip.offsetWidth - 10, e.clientX + 14);
  const y = Math.min(window.innerHeight - tip.offsetHeight - 10, e.clientY + 14);
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
const hideTip = () => { tip.style.display = 'none'; };
const withTip = (el, html) => {
  el.addEventListener('mousemove', e => showTip(e, html));
  el.addEventListener('mouseleave', hideTip);
  return el;
};

const svgNS = 'http://www.w3.org/2000/svg';
function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  for (const c of children.flat()) if (c != null) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}
// bar with 4px rounded data-end, square at the baseline
function barPath(x, y, w, hgt, r = 4) {
  if (hgt <= 0) return '';
  r = Math.min(r, w / 2, hgt);
  return `M${x},${y + hgt}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt}Z`;
}
function niceMax(v) {
  if (v <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p * 2) / 2 * p;
}

export async function renderDashboard() {
  const root = document.getElementById('view-dashboard');
  let d;
  try { d = await api('/api/dashboard'); } catch (e) { toastError(e); return; }
  const k = d.kpis;
  root.replaceChildren(
    h('div', { class: 'dash-head' }, h('h1', {}, 'Memory dashboard'),
      h('span', { class: 'sub' }, `${new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })} · capacity ${store.state.settings.weekly_capacity_hours}h / week`)),
    h('div', { class: 'kpis' },
      kpi('RAM in use', `${k.active}`, `/ ${k.ram_slots}`),
      kpi('Backlog queue', k.backlog),
      kpi('Basket', k.basket),
      kpi('Due this week', k.due_this_week),
      kpi('Overdue', k.overdue, null, k.overdue ? 'bad' : ''),
      kpi('At risk', k.at_risk, null, k.at_risk ? 'warn' : ''),
      kpi('Done this week', k.done_this_week)),
    h('div', { class: 'dash-grid' },
      panel('Task layout by week', 'Each open task is auto-assigned an estimated completion week from priority, due date, effort and weekly capacity. Click a task to open it.', timeline(d), 'wide'),
      panel('Planned hours vs capacity', 'Effort hours scheduled into each week; the dashed line is your weekly capacity.', capacityChart(d), ''),
      panel('Thinking balance', 'Open tasks by hemisphere.', regionSplit(d.regions), ''),
      panel('Due-date calendar', 'Open tasks due per day over the next six weeks.', calendar(d), ''),
      panel('Completed vs added', 'Tasks per week over the last eight weeks.', trendChart(d.trend), ''),
      panel('Insights', 'What your memory is telling you.', insightList(d.insights), 'wide')),
  );
}

function kpi(label, value, small, cls = '') {
  return h('div', { class: `kpi ${cls}` }, h('div', { class: 'k' }, label), h('div', { class: 'v' }, String(value), small ? h('small', {}, ` ${small}`) : null));
}
function panel(title, sub, body, cls) {
  return h('section', { class: `panel ${cls}` }, h('h3', {}, title), h('div', { class: 'sub' }, sub), body);
}

// ---------- week timeline ----------
function timeline(d) {
  const current = store.state.current_week;
  const today = todayISO();
  const cols = d.weeks.map(w => {
    const over = w.hours > w.capacity;
    const head = h('div', { class: `tl-head ${w.week === current ? 'current' : ''}` },
      h('strong', {}, w.week === current ? 'This week' : new Date(w.start + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })),
      h('span', {}, `${w.hours}h`));
    const cap = h('div', { class: 'tl-cap', title: `${w.hours}h planned of ${w.capacity}h` },
      h('i', { class: over ? 'over' : '', style: { width: `${Math.min(100, (w.hours / w.capacity) * 100)}%` } }));
    const items = w.tasks.slice(0, 8).map(t => {
      const late = t.due_at && t.due_at.slice(0, 10) < today;
      const el = h('div', {
        class: `tl-task ${t.at_risk ? 'risk' : ''} ${late ? 'late' : ''}`, style: `--c:${VIZ[t.region]}`,
        onclick: () => handlers.openTask(t.id),
      }, h('span', { class: 't' }, t.title), h('span', { class: 'd' }, t.due_at ? fmtDate(t.due_at) : t.effort));
      return withTip(el, `<strong>${esc(t.title)}</strong><br>${REGION_LABEL[t.region]} · effort ${t.effort} · ${t.priority}${t.due_at ? `<br>Due ${esc(fmtDate(t.due_at))}` : ''}${t.at_risk ? '<br>⚠ At risk for its due date' : ''}`);
    });
    return h('div', { class: 'tl-col' }, head, cap, items, w.tasks.length > 8 ? h('div', { class: 'tl-more' }, `+${w.tasks.length - 8} more`) : null,
      !w.tasks.length ? h('div', { class: 'tl-more' }, 'Free') : null);
  });
  const legend = h('div', { class: 'split-legend', style: { justifyContent: 'flex-start', gap: '16px' } },
    ['logical', 'balanced', 'creative'].map(r => h('span', {}, h('i', { style: `--c:${VIZ[r]}` }), REGION_LABEL[r])),
    d.later ? h('span', {}, `${d.later} more scheduled beyond 8 weeks`) : null);
  return h('div', {}, h('div', { class: 'timeline' }, cols), legend);
}

// ---------- capacity bar chart (single axis: hours) ----------
function capacityChart(d) {
  const W = 520, H = 230, m = { l: 34, r: 12, t: 12, b: 26 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const cap = d.weeks[0]?.capacity || 20;
  const max = niceMax(Math.max(cap * 1.15, ...d.weeks.map(w => w.hours)));
  const y = v => m.t + ih - (v / max) * ih;
  const band = iw / d.weeks.length, bw = Math.min(46, band * 0.56);
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Planned hours per week versus capacity' });
  const grid = s('g', { class: 'grid' });
  for (let i = 0; i <= 4; i++) {
    const v = (max / 4) * i;
    grid.append(s('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }), s('text', { x: m.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, `${Math.round(v)}h`));
  }
  svg.append(grid);
  d.weeks.forEach((w, i) => {
    const x = m.l + band * i + (band - bw) / 2;
    const within = Math.min(w.hours, cap), over = Math.max(0, w.hours - cap);
    const g = s('g', { cursor: 'default' });
    g.append(s('rect', { x: m.l + band * i, y: m.t, width: band, height: ih, fill: 'transparent' }));  // hit target
    if (over > 0) {
      g.append(s('path', { d: barPath(x, y(w.hours), bw, y(cap) - y(w.hours) - 2), fill: VIZ.warning }));
      g.append(s('path', { d: `M${x},${y(0)}V${y(within)}H${x + bw}V${y(0)}Z`, fill: VIZ.series1 }));
    } else if (w.hours > 0) {
      g.append(s('path', { d: barPath(x, y(w.hours), bw, y(0) - y(w.hours)), fill: VIZ.series1 }));
    }
    const label = i === 0 ? 'This wk' : new Date(w.start + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    g.append(s('text', { x: x + bw / 2, y: H - 8, 'text-anchor': 'middle' }, label));
    if (w.hours > 0) g.append(s('text', { x: x + bw / 2, y: y(w.hours) - 5, 'text-anchor': 'middle', fill: INK() }, `${w.hours}`));
    withTip(g, `<strong>${label}</strong><br>${w.hours}h planned · ${w.capacity}h capacity<br>${w.tasks.length} task(s)${over ? `<br>⚠ ${over}h over capacity` : ''}`);
    svg.append(g);
  });
  svg.append(s('line', { x1: m.l, x2: W - m.r, y1: y(cap), y2: y(cap), stroke: INK(), 'stroke-width': 1.5, 'stroke-dasharray': '5 4' }));
  svg.append(s('text', { x: W - m.r, y: y(cap) - 6, 'text-anchor': 'end', fill: INK() }, `capacity ${cap}h`));
  const legend = h('div', { class: 'split-legend', style: { justifyContent: 'flex-start', gap: '16px' } },
    h('span', {}, h('i', { style: `--c:${VIZ.series1}` }), 'Planned within capacity'),
    h('span', {}, h('i', { style: `--c:${VIZ.warning}` }), '⚠ Over capacity'));
  return h('div', { class: 'chart' }, svg, legend);
}

// ---------- region split ----------
function regionSplit(regions) {
  const total = Object.values(regions).reduce((a, b) => a + b, 0);
  if (!total) return h('div', { class: 'status-line' }, 'No open tasks yet.');
  const bar = h('div', { class: 'split-bar' }, ['logical', 'balanced', 'creative'].filter(r => regions[r]).map(r => {
    const pct = (regions[r] / total) * 100;
    return withTip(h('div', { style: { width: `${pct}%`, background: VIZ[r], color: r === 'balanced' ? '#0a1a35' : '#fff' } }, pct >= 12 ? String(regions[r]) : ''),
      `<strong>${REGION_LABEL[r]}</strong><br>${regions[r]} task(s) · ${Math.round(pct)}%`);
  }));
  const legend = h('div', { class: 'split-legend' }, ['logical', 'balanced', 'creative'].map(r =>
    h('span', {}, h('i', { style: `--c:${VIZ[r]}` }), `${REGION_LABEL[r]} ${Math.round((regions[r] / total) * 100)}%`)));
  const active = store.active;
  const ac = { logical: 0, balanced: 0, creative: 0 };
  for (const t of active) ac[t.region]++;
  return h('div', {}, bar, legend,
    h('div', { class: 'sub', style: { margin: '16px 0 6px' } }, 'Holding synapses right now'),
    h('div', { class: 'status-stack', style: { gridTemplateColumns: 'repeat(3, 1fr)' } },
      ['logical', 'balanced', 'creative'].map(r => h('div', {}, h('div', { class: 'k' }, REGION_LABEL[r]), h('div', { class: 'v' }, String(ac[r]))))));
}

// ---------- calendar heatmap (sequential blue) ----------
function calendar(d) {
  const today = todayISO();
  const max = Math.max(1, ...d.calendar.map(c => c.count));
  const step = c => (c === 0 ? null : VIZ.seq[Math.min(VIZ.seq.length - 1, Math.ceil((c / max) * (VIZ.seq.length - 1)))]);
  const grid = h('div', { class: 'cal' }, h('span'), ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(x => h('div', { class: 'dow' }, x)));
  d.calendar.forEach((c, i) => {
    if (i % 7 === 0) grid.append(h('div', { class: 'wk' }, new Date(c.date + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })));
    const fill = step(c.count);
    const cell = h('div', {
      class: `day ${c.date === today ? 'today' : ''} ${c.date < today ? 'past' : ''}`,
      style: fill ? { background: fill } : null,
    }, h('span', { class: 'n' }, new Date(c.date + 'T00:00:00').getDate()), c.count ? h('span', { class: 'c', style: { color: '#fff' } }, c.count) : null);
    withTip(cell, `<strong>${esc(fmtDate(c.date, { weekday: true }))}</strong><br>${c.count ? c.titles.map(esc).join('<br>') + (c.count > c.titles.length ? `<br>+${c.count - c.titles.length} more` : '') : 'Nothing due'}`);
    grid.append(cell);
  });
  return h('div', {}, grid, d.overdue ? h('div', { class: 'status-line bad', style: { marginTop: '8px' } }, `⚠ ${d.overdue} overdue task(s) not shown on the calendar`) : null);
}

// ---------- trend lines ----------
function trendChart(trend) {
  const W = 520, H = 220, m = { l: 30, r: 70, t: 14, b: 26 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const max = niceMax(Math.max(...trend.map(t => Math.max(t.completed, t.created))));
  const x = i => m.l + (iw / (trend.length - 1)) * i;
  const y = v => m.t + ih - (v / max) * ih;
  const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Completed versus added tasks per week' });
  const grid = s('g', { class: 'grid' });
  for (let i = 0; i <= 4; i++) {
    const v = (max / 4) * i;
    grid.append(s('line', { x1: m.l, x2: m.l + iw, y1: y(v), y2: y(v) }), s('text', { x: m.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, Math.round(v)));
  }
  svg.append(grid);
  trend.forEach((t, i) => {
    if (i % 2 === 1 && i !== trend.length - 1) return;
    svg.append(s('text', { x: x(i), y: H - 8, 'text-anchor': 'middle' }, i === trend.length - 1 ? 'This wk' : new Date(t.start + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })));
  });
  const series = [['completed', 'Completed', VIZ.series1], ['created', 'Added', VIZ.series2]];
  for (const [key, label, color] of series) {
    svg.append(s('path', { d: trend.map((t, i) => `${i ? 'L' : 'M'}${x(i)},${y(t[key])}`).join(''), fill: 'none', stroke: color, 'stroke-width': 2, 'stroke-linejoin': 'round' }));
    const last = trend.length - 1;
    svg.append(s('circle', { cx: x(last), cy: y(trend[last][key]), r: 4, fill: color, stroke: SURFACE(), 'stroke-width': 2 }));
    svg.append(s('text', { x: x(last) + 8, y: y(trend[last][key]) + 4 + (key === 'created' && trend[last].created === trend[last].completed ? 12 : 0), fill: INK() }, label));
  }
  // crosshair hover
  const cross = s('line', { y1: m.t, y2: m.t + ih, stroke: INK(), 'stroke-width': 1, opacity: 0 });
  const dots = series.map(([, , color]) => s('circle', { r: 4, fill: color, stroke: SURFACE(), 'stroke-width': 2, opacity: 0 }));
  svg.append(cross, ...dots);
  const hit = s('rect', { x: m.l, y: m.t, width: iw, height: ih, fill: 'transparent' });
  hit.addEventListener('mousemove', e => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(trend.length - 1, Math.round((px - m.l) / (iw / (trend.length - 1)))));
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('opacity', 0.5);
    series.forEach(([key], j) => { dots[j].setAttribute('cx', x(i)); dots[j].setAttribute('cy', y(trend[i][key])); dots[j].setAttribute('opacity', 1); });
    showTip(e, `<strong>Week of ${esc(new Date(trend[i].start + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' }))}</strong><br>Completed: ${trend[i].completed}<br>Added: ${trend[i].created}`);
  });
  hit.addEventListener('mouseleave', () => { hideTip(); cross.setAttribute('opacity', 0); dots.forEach(dt => dt.setAttribute('opacity', 0)); });
  svg.append(hit);
  const legend = h('div', { class: 'split-legend', style: { justifyContent: 'flex-start', gap: '16px' } },
    series.map(([, label, color]) => h('span', {}, h('i', { style: `--c:${color}` }), label)));
  return h('div', { class: 'chart' }, svg, legend);
}

function insightList(items) {
  if (!items.length) return h('div', { class: 'status-line' }, 'All calm. Add tasks and they will start generating insights.');
  return h('div', { class: 'ins-list' }, items.map(i => h('div', { class: `ins ${i.severity}` }, h('span', {}, i.text))));
}
