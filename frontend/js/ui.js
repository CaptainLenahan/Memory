// Small DOM helpers, icons, toasts, modals and formatting shared across the UI.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'style' && typeof v === 'object') for (const [p, x] of Object.entries(v)) { if (p.startsWith('--')) el.style.setProperty(p, x); else el.style[p] = x; }
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const PATHS = {
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9Z"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
  infinity: '<path d="M12 12c-2-2.7-4-4-6-4a4 4 0 0 0 0 8c2 0 4-1.3 6-4Zm0 0c2 2.7 4 4 6 4a4 4 0 0 0 0-8c-2 0-4 1.3-6 4Z"/>',
  basket: '<path d="M5 10h14l-1.5 9.5a2 2 0 0 1-2 1.5h-7a2 2 0 0 1-2-1.5Z"/><path d="m9 10 3-6 3 6M3 10h18"/>',
  brain: '<path d="M12 5a3 3 0 0 0-5.6-1.5A3 3 0 0 0 4 8a3 3 0 0 0-.5 5.4A3.5 3.5 0 0 0 7 19a3 3 0 0 0 5 1Z"/><path d="M12 5a3 3 0 0 1 5.6-1.5A3 3 0 0 1 20 8a3 3 0 0 1 .5 5.4A3.5 3.5 0 0 1 17 19a3 3 0 0 1-5 1Z"/>',
  queue: '<path d="M4 6h16M4 12h16M4 18h10"/>',
  done: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  planner: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 4v16M3 9h5M3 14h5"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
  repeat: '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
  flag: '<path d="M4 22V4M4 4h12l-2 4 2 4H4"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  week: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 14h8"/>',
  tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8Z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
  file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6"/>',
  clip: '<path d="m21 11-8.6 8.6a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.6 8.6a2 2 0 0 1-2.8-2.8L15.5 7"/>',
  link: '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-14"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  grip: '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
  pin: '<path d="M12 17v5M9 3h6l-1 6 4 3v2H6v-2l4-3Z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  template: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  move: '<path d="M12 2v20M2 12h20M12 2l-3 3M12 2l3 3M12 22l-3-3M12 22l3-3M2 12l3-3M2 12l3 3M22 12l-3-3M22 12l-3 3"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  bulb: '<path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2Z"/>',
};

export function icon(name, cls = '') {
  const span = document.createElement('span');
  span.innerHTML = `<svg viewBox="0 0 24 24" class="${cls}" aria-hidden="true">${PATHS[name] || ''}</svg>`;
  return span.firstChild;
}
export const iconHtml = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${PATHS[name] || ''}</svg>`;

// ---------- toasts ----------
export function toast(message, { type = 'info', action, onAction, timeout = 4500 } = {}) {
  const el = h('div', { class: `toast ${type}` }, h('span', { class: 'grow' }, message));
  if (action) el.append(h('button', { onclick: () => { onAction?.(); el.remove(); } }, action));
  el.append(h('button', { 'aria-label': 'Dismiss', onclick: () => el.remove() }, '×'));
  document.getElementById('toasts').append(el);
  if (timeout) setTimeout(() => el.remove(), timeout);
  return el;
}
export const toastError = err => toast(err?.message || String(err), { type: 'error', timeout: 7000 });

// ---------- modals ----------
export function modal({ title, body, actions = [], onClose, wide = false }) {
  const root = document.getElementById('modal-root');
  const backdrop = h('div', { class: 'modal-backdrop' });
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey); onClose?.(); };
  const onKey = e => { if (e.key === 'Escape') close(); };
  const foot = h('div', { class: 'modal-foot' }, actions.map(a => h('button', {
    class: `btn ${a.kind || ''}`, onclick: async () => { if ((await a.onClick?.()) !== false) close(); },
  }, a.label)));
  const box = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', style: wide ? { width: 'min(720px, calc(100vw - 32px))' } : null },
    h('div', { class: 'modal-head' }, h('h2', {}, title), h('button', { class: 'btn icon ghost', 'aria-label': 'Close', onclick: close }, icon('x'))),
    h('div', { class: 'modal-body' }, body),
    actions.length ? foot : null);
  backdrop.append(box);
  backdrop.addEventListener('mousedown', e => { if (e.target === backdrop) close(); });
  document.addEventListener('keydown', onKey);
  root.append(backdrop);
  return { close, el: box };
}

export function confirmDialog(title, message, okLabel = 'OK', kind = 'primary') {
  return new Promise(resolve => {
    let result = false;
    modal({
      title, body: h('p', { style: { margin: 0 } }, message),
      actions: [
        { label: 'Cancel', onClick: () => { result = false; } },
        { label: okLabel, kind, onClick: () => { result = true; } },
      ],
      onClose: () => resolve(result),
    });
  });
}

export function popover(anchorRect, content) {
  closePopover();
  const el = h('div', { class: 'popover' }, content);
  document.body.append(el);
  const w = 300, hgt = Math.min(360, el.scrollHeight + 4);
  el.style.left = `${Math.min(window.innerWidth - w - 10, Math.max(10, anchorRect.x - w / 2))}px`;
  el.style.top = `${Math.min(window.innerHeight - hgt - 10, anchorRect.y + 14)}px`;
  setTimeout(() => document.addEventListener('mousedown', outside), 0);
  function outside(e) { if (!el.contains(e.target)) closePopover(); }
  el._outside = outside;
  return el;
}
export function closePopover() {
  document.querySelectorAll('.popover').forEach(p => { document.removeEventListener('mousedown', p._outside); p.remove(); });
}

export function lightbox(src) {
  const el = h('div', { class: 'lightbox', onclick: () => el.remove() }, h('img', { src, alt: '' }));
  document.body.append(el);
}

// ---------- formatting ----------
export function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function addDays(iso, n) {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function fmtDate(iso, { weekday = false } = {}) {
  if (!iso) return '';
  const d = new Date(iso.slice(0, 10) + 'T00:00:00');
  const today = todayISO();
  const day = iso.slice(0, 10);
  if (day === today) return 'Today';
  if (day === addDays(today, 1)) return 'Tomorrow';
  if (day === addDays(today, -1)) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: weekday ? 'short' : undefined, month: 'short', day: 'numeric', year: d.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined });
}
export function fmtDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
export function fmtWeek(week, weeks) {
  const w = weeks?.find(x => x.week === week);
  const start = w?.start || isoWeekStart(week);
  return start ? `Week of ${new Date(start + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}` : week;
}
export function isoWeekStart(week) {
  const m = /^(\d{4})-W(\d{2})$/.exec(week || '');
  if (!m) return null;
  const jan4 = new Date(Date.UTC(+m[1], 0, 4));
  const monday = new Date(jan4);
  monday.setUTCDate(jan4.getUTCDate() - ((jan4.getUTCDay() + 6) % 7) + (+m[2] - 1) * 7);
  return monday.toISOString().slice(0, 10);
}
export function fmtSize(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
export function dueClass(t) {
  if (!t.due_at || t.status === 'done') return '';
  const day = t.due_at.slice(0, 10), today = todayISO();
  if (day < today) return 'late';
  if (day <= addDays(today, 2)) return 'soon';
  return '';
}
export const REGION_VAR = { logical: 'var(--logical)', balanced: 'var(--balanced)', creative: 'var(--creative)' };

// Minimal, safe markdown for Claude replies: escape first, then a few inline/block rules.
export function renderMarkdown(src) {
  const lines = esc(src || '').split('\n');
  const out = [];
  let list = null;
  const inline = s => s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = /^\s*[-*•]\s+(.*)$/.exec(line))) {
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul'; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = /^\s*\d+[.)]\s+(.*)$/.exec(line))) {
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol'; }
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = /^#{1,4}\s+(.*)$/.exec(line))) {
      closeList();
      out.push(`<p><strong>${inline(m[1])}</strong></p>`);
    } else if (line.trim() === '') {
      closeList();
    } else {
      closeList();
      out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList();
  return out.join('');
}

export function debounce(fn, ms) {
  let t;
  const d = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  d.flush = (...args) => { clearTimeout(t); fn(...args); };
  d.cancel = () => clearTimeout(t);
  return d;
}
